#!/usr/bin/env python3
"""Three test levels for a checkout of the ERPForAll repository: basic, normal, advanced.

Run it inside the checkout. Each level is a fixed list of the framework's own commands; this tool only chooses
them, runs them in order, keeps their output, and writes a receipt that says what ran on which revision.

  test-levels.py basic     minutes, no database: layer check, formatting and clippy of the packages your diff
                           affects, the web type check when client files changed, then a rebuild and restart of
                           your local instance (`scripts/install.sh --rebuild`) so you can try the change
  test-levels.py normal    needs a database: the same checks plus the tests of the affected packages
                           (`scripts/check.sh --affected --tests`) and the client test files your diff changed
  test-levels.py advanced  the full cycle, an hour or more: checks and tests of the whole workspace
                           (`scripts/check.sh --tests`), the web install, type check and the whole client suite
  test-levels.py status    the receipts of the current revision; `--require LEVEL` exits 1 unless a clean run of
                           that level or a higher one passed on it

Options: --root DIR (default: found from the current directory), --base REF (default origin/main),
--dry-run (print the plan, run nothing), --no-deploy (basic without the rebuild), --deploy (normal or advanced
with it), --fast (pass --fast to install.sh; use it when the instance was installed with it),
--threads N (tests run N at a time), --out DIR (default ~/.erpforall/test-runs/<checkout name>).

A run is not a result, and its receipt says `invalid`, when the working tree changed while it ran: the tests
install addons from the tree and refuse one that changes under them. Exit: 0 passed, 1 failed, 2 could not start,
3 invalid. Python 3.10+, standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

LEVELS = ("basic", "normal", "advanced")
# A database URL can appear in test output: its password never reaches the terminal, a log or a receipt.
SECRET = re.compile(r"(postgres(?:ql)?://[^:/@\s]+:)[^@\s]+@")
# Failures that say nothing about the code under test.
ENVIRONMENT = (
    ("out of shared memory", "the database server ran out of lock memory: rerun with --threads 2, or raise "
                             "max_locks_per_transaction on the test server"),
    ("artifact changed during lifecycle operation", "an addon's files changed while a test was installing it: "
                                                    "stop editing the tree and rerun"),
)
WEB = 'eval "$(scripts/web-toolchain.sh env)" && '


@dataclass
class Step:
    name: str
    command: str  # run by bash in the checkout
    database: bool = False  # needs DATABASE_URL and a tree that stays unchanged
    env: dict[str, str] = field(default_factory=dict)


def redact(text: str) -> str:
    return SECRET.sub(r"\1***@", text)


def find_root(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / "scripts" / "check.sh").is_file() and (folder / "Cargo.toml").is_file():
            return folder
    return None


def changed_client_tests(changed: list[str]) -> list[str]:
    """The client test files of a diff, as paths vitest takes from `web/`."""
    return sorted("../" + path if not path.startswith("web/") else path[4:] for path in changed if path.endswith(".test.ts"))


def changed_data_addons(changed: list[str]) -> list[str]:
    """Addons whose manifest, data, views or access files changed: they reach a database only through an upgrade."""
    names = set()
    for path in changed:
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "addons" and (parts[2] == "manifest.toml" or parts[2] in ("data", "views", "security", "demo", "report")):
            names.add(parts[1])
    return sorted(names)


def plan(level: str, *, base: str, web: bool, client_tests: list[str], deploy: bool, fast: bool, threads: int | None) -> list[Step]:
    """The steps of a level. `web`: the diff touches the web client; `client_tests`: its changed client test files."""
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}; the levels are {', '.join(LEVELS)}")
    env = {"NEXTEST_TEST_THREADS": str(threads)} if threads else {}
    steps: list[Step] = []
    if level == "basic":
        steps.append(Step("check", f"scripts/check.sh --affected {base}"))
        if web:
            steps.append(Step("web-typecheck", WEB + "pnpm --dir web install --frozen-lockfile && cd web && pnpm run typecheck"))
    elif level == "normal":
        steps.append(Step("check-and-tests", f"scripts/check.sh --affected {base} --tests", database=True, env=env))
        if web:
            steps.append(Step("web-typecheck", WEB + "pnpm --dir web install --frozen-lockfile && cd web && pnpm run typecheck"))
        if client_tests:
            steps.append(Step("web-tests", WEB + "cd web && pnpm exec vitest run " + " ".join(client_tests)))
    else:
        steps.append(Step("check-and-tests", "scripts/check.sh --tests", database=True, env=env))
        steps.append(Step("web-typecheck", WEB + "pnpm --dir web install --frozen-lockfile && cd web && pnpm run typecheck"))
        steps.append(Step("web-tests", WEB + "cd web && pnpm run test"))
    if deploy:
        steps.append(Step("deploy", "scripts/install.sh --rebuild" + (" --fast" if fast else "")))
    return steps


def classify(log_text: str) -> str | None:
    """Why a failed step is not a verdict on the code, or None."""
    for needle, advice in ENVIRONMENT:
        if needle in log_text:
            return advice
    return None


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False).stdout


def tree_state(root: Path) -> tuple[str, str]:
    """The revision and a fingerprint of every uncommitted change (tracked diff plus untracked names)."""
    head = git(root, "rev-parse", "HEAD").strip()
    dirt = git(root, "status", "--porcelain") + git(root, "diff", "HEAD")
    return head, hashlib.sha256(dirt.encode()).hexdigest() if dirt else ""


def tool_versions() -> dict[str, str]:
    found = {}
    for name, argv in (("cargo", ["cargo", "--version"]), ("rustc", ["rustc", "--version"]), ("nextest", ["cargo", "nextest", "--version"]),
                       ("node", ["node", "--version"]), ("pnpm", ["pnpm", "--version"])):
        try:
            out = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=30)
            found[name] = out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout.strip() else "not available"
        except (OSError, subprocess.TimeoutExpired):
            found[name] = "not available"
    return found


def preflight(steps: list[Step], environ: dict[str, str], versions: dict[str, str]) -> list[str]:
    """What stops a run before its first step."""
    problems = []
    if any(step.database for step in steps):
        if not environ.get("DATABASE_URL") and not environ.get("ERP_TEST_DATABASE_URLS"):
            problems.append("DATABASE_URL is not set: the tests create their databases on the PostgreSQL 18 server it names "
                            "(a role that may create databases)")
        if versions.get("nextest") == "not available":
            problems.append("cargo-nextest is not installed: `cargo install cargo-nextest --locked`")
    return problems


def lock_memory(environ: dict[str, str]) -> int | None:
    """max_locks_per_transaction of the test server, when psql can ask it."""
    url = (environ.get("DATABASE_URL") or environ.get("ERP_TEST_DATABASE_URLS", "").split(" ")[0]).strip()
    if not url or not shutil.which("psql"):
        return None
    try:
        out = subprocess.run(["psql", url, "-Atc", "show max_locks_per_transaction"], capture_output=True, text=True, check=False, timeout=20)
        return int(out.stdout.strip()) if out.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def run_step(step: Step, root: Path, log: Path, environ: dict[str, str]) -> int:
    """Run one step; its output goes to the terminal and the log, both without secrets."""
    with log.open("w", encoding="utf-8") as sink:
        proc = subprocess.Popen(["bash", "-c", step.command], cwd=root, env={**environ, **step.env}, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        assert proc.stdout is not None
        for line in proc.stdout:
            clean = redact(line)
            sink.write(clean)
            sys.stdout.write(clean)
        return proc.wait()


def execute(level: str, steps: list[Step], root: Path, out: Path, environ: dict[str, str], base: str, runner=run_step) -> dict:
    """Run the steps in order, stop at the first failure, and return the receipt."""
    head, dirt = tree_state(root)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = out / f"{level}-{head[:12]}-{stamp}"
    folder.mkdir(parents=True, exist_ok=True)
    receipt = {"level": level, "root": str(root), "revision": head, "clean_tree": dirt == "", "base": base, "started_utc": stamp,
               "host": platform.node(), "platform": platform.platform(), "python": platform.python_version(), "tools": tool_versions(), "steps": []}
    verdict = "passed"
    for number, step in enumerate(steps, 1):
        log = folder / f"{number}-{step.name}.log"
        print(f"== {level} {number}/{len(steps)} {step.name}: {step.command}", flush=True)
        began = time.monotonic()
        code = runner(step, root, log, environ)
        entry = {"name": step.name, "command": step.command, "env": step.env, "exit": code, "seconds": round(time.monotonic() - began), "log": str(log)}
        if code != 0:
            why = classify(log.read_text(encoding="utf-8", errors="replace")) if log.is_file() else None
            if why:
                entry["environment"] = why
            verdict = "failed"
        receipt["steps"].append(entry)
        if step.database and tree_state(root) != (head, dirt):
            # tests install addons from the tree: a change while they ran makes their outcome meaningless
            verdict = "invalid"
            receipt["invalid"] = f"the working tree changed during step {step.name}: this run is not a result for {head[:12]}"
        if verdict != "passed":
            break
    receipt["verdict"] = verdict
    receipt["finished_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def receipts(out: Path, revision: str) -> list[dict]:
    found = []
    for path in sorted(out.glob(f"*-{revision[:12]}-*/receipt.json")):
        try:
            found.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return [r for r in found if r.get("revision") == revision]


def satisfied(found: list[dict], level: str) -> bool:
    """A clean-tree run of `level` or a higher level passed."""
    wanted = LEVELS.index(level)
    return any(r.get("verdict") == "passed" and r.get("clean_tree") and r.get("level") in LEVELS[wanted:] for r in found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Basic, normal and advanced test levels for an ERPForAll checkout.")
    parser.add_argument("level", choices=(*LEVELS, "status"))
    parser.add_argument("--root", type=Path)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--no-deploy", action="store_true")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--threads", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require", choices=LEVELS)
    args = parser.parse_args(argv)

    root = args.root.resolve() if args.root else find_root(Path.cwd())
    if root is None or not (root / "scripts" / "check.sh").is_file():
        print("test-levels: run this inside a checkout of the ERPForAll repository (scripts/check.sh was not found). "
              "An addons-only project is checked with erpforall-addon-lint and `erp module install --dry-run`.", file=sys.stderr)
        return 2
    if args.threads is not None and not 1 <= args.threads <= 256:
        print("test-levels: --threads must be from 1 to 256", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[A-Za-z0-9._/~^-]{1,200}", args.base) or args.base.startswith("-"):
        print(f"test-levels: --base {args.base!r} is not a git revision name", file=sys.stderr)
        return 2
    out = (args.out or Path.home() / ".erpforall" / "test-runs" / root.name).resolve()

    if args.level == "status":
        head, dirt = tree_state(root)
        found = receipts(out, head)
        print(f"revision {head[:12]}{' with uncommitted changes' if dirt else ''}: {len(found)} run(s) in {out}")
        for r in found:
            print(f"  {r['level']:9} {r['verdict']:8} {'clean' if r.get('clean_tree') else 'dirty'} tree  {r.get('started_utc')}")
        if args.require:
            ok = not dirt and satisfied(found, args.require)
            print(f"{args.require}: {'satisfied' if ok else 'not satisfied (no passing run of this level or higher on a clean tree at this revision)'}")
            return 0 if ok else 1
        return 0

    changed = [line for line in git(root, "diff", "--name-only", args.base).splitlines() if line]
    changed += [line[3:] for line in git(root, "status", "--porcelain").splitlines() if line.startswith("??")]
    # web/dist/ is build output the rebuild writes, not a change to the client
    web = any((path.startswith("web/") and not path.startswith("web/dist/")) or "/static/" in path for path in changed)
    deploy = (args.level == "basic" and not args.no_deploy) or (args.level != "basic" and args.deploy)
    threads = args.threads
    environ = dict(os.environ)
    if args.level != "basic" and threads is None and not args.dry_run:
        locks = lock_memory(environ)
        if locks is not None and locks < 256:
            threads = 2
            print(f"test-levels: the test server has max_locks_per_transaction = {locks}; tests run 2 at a time "
                  "(pass --threads N to choose, or raise the setting on the server)")
    steps = plan(args.level, base=args.base, web=web, client_tests=changed_client_tests(changed), deploy=deploy, fast=args.fast, threads=threads)

    if args.dry_run:
        print(f"{args.level} in {root} against {args.base}: {len(changed)} changed file(s), web {'affected' if web else 'not affected'}")
        for number, step in enumerate(steps, 1):
            extra = "".join(f" {key}={value}" for key, value in step.env.items())
            print(f"  {number}. {step.name}{' [database]' if step.database else ''}:{extra} {step.command}")
        return 0

    problems = preflight(steps, environ, tool_versions())
    if problems:
        for problem in problems:
            print(f"test-levels: {problem}", file=sys.stderr)
        return 2
    receipt = execute(args.level, steps, root, out, environ, args.base)
    print(f"== {args.level}: {receipt['verdict']} at {receipt['revision'][:12]}{'' if receipt['clean_tree'] else ' (uncommitted changes)'}; receipt in {out}")
    for entry in receipt["steps"]:
        if entry.get("environment"):
            print(f"   {entry['name']}: not a verdict on the code: {entry['environment']}")
    if receipt.get("invalid"):
        print(f"   {receipt['invalid']}")
    upgrades = changed_data_addons(changed)
    if deploy and upgrades and receipt["verdict"] == "passed":
        print("   changed manifests, data or views reach the database only through `erp module upgrade`: " + ", ".join(upgrades))
    return {"passed": 0, "failed": 1, "invalid": 3}[receipt["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
