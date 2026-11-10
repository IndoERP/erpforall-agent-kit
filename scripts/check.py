#!/usr/bin/env python3
"""Validate every skills/*/SKILL.md. Python 3.11+, standard library only.

Checks per skill: frontmatter between '---' lines with `name` and `description`; name equals the
directory name and is lowercase-hyphen (at most 64 characters); description is 1..1024 characters;
a final `## Sources` section whose list items are repo-relative paths; with --source <checkout>
every listed path must exist there, and every `something.md` page named in backticks must exist in
the checkout's docs/addon-guide/. Without --source the existence checks are skipped (and reported).
A hygiene scan fails on internal host names, team-process words and e-mail addresses.

Usage: scripts/check.py [--source PATH] [--skills DIR]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FORBIDDEN = [
    r"crewbus", r"ubuntu-build", r"mac-kantor", r"radit-mini", r"arkana", r"co-authored-by",
    r"generated with", r"[\w.+-]+@[\w-]+\.[\w.-]+",
]
FORBIDDEN_RE = re.compile("|".join(FORBIDDEN), re.I)
PAGE_RE = re.compile(r"`([a-z0-9][a-z0-9_-]*\.md)`")


def split_frontmatter(text: str) -> tuple[dict[str, str] | None, str]:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm: dict[str, str] = {}
            for ln in lines[1:i]:
                if not ln.strip():
                    continue
                m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", ln)
                if not m:
                    return None, text
                fm[m.group(1)] = m.group(2).strip().strip('"')
            return fm, "\n".join(lines[i + 1:])
    return None, text


def sources_of(body: str) -> list[str] | None:
    idx = [m.start() for m in re.finditer(r"^## Sources\s*$", body, re.M)]
    if len(idx) != 1:
        return None
    tail = body[idx[0]:].split("\n")[1:]
    if any(re.match(r"^#{1,6} ", ln) for ln in tail):
        return None  # Sources must be the last section
    return [m.group(1).strip().strip("`") for ln in tail if (m := re.match(r"^- (.+)$", ln))]


def check_skill(skill_dir: Path, source: Path | None) -> list[str]:
    errs: list[str] = []
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return [f"{skill_dir.name}: SKILL.md missing"]
    text = md.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    tag = skill_dir.name
    if fm is None:
        return [f"{tag}: frontmatter missing or malformed (must start on line 1 with ---)"]
    name, desc = fm.get("name", ""), fm.get("description", "")
    if name != skill_dir.name:
        errs.append(f"{tag}: name {name!r} does not match the directory")
    if not NAME_RE.match(name) or len(name) > 64:
        errs.append(f"{tag}: name {name!r} must be lowercase letters, digits and hyphens, at most 64 characters")
    if not desc:
        errs.append(f"{tag}: description missing")
    elif len(desc) > 1024:
        errs.append(f"{tag}: description is {len(desc)} characters (max 1024)")
    elif len(desc) < 40:
        errs.append(f"{tag}: description is too short to say when to use the skill")
    if not body.strip().startswith("# "):
        errs.append(f"{tag}: body should start with a '# Title' heading")
    srcs = sources_of(body)
    if srcs is None:
        errs.append(f"{tag}: needs exactly one '## Sources' section, and it must be the last section")
    elif not srcs:
        errs.append(f"{tag}: Sources list is empty")
    for m in FORBIDDEN_RE.finditer(text):
        errs.append(f"{tag}: forbidden text {m.group(0)!r}")
    if source is not None:
        for s in srcs or []:
            if s.startswith("/") or ".." in Path(s).parts:
                errs.append(f"{tag}: source {s!r} must be a repo-relative path")
            elif not (source / s).is_file():
                errs.append(f"{tag}: source {s!r} does not exist in {source}")
        guide = source / "docs" / "addon-guide"
        for page in sorted(set(PAGE_RE.findall(body))):
            if not (guide / page).is_file():
                errs.append(f"{tag}: names guide page {page!r}, which does not exist in {guide}")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--source", type=Path, help="checkout of the ERPForAll source repository")
    ap.add_argument("--skills", type=Path, default=ROOT / "skills")
    a = ap.parse_args(argv)
    if a.source is not None and not a.source.is_dir():
        print(f"error: --source {a.source} is not a directory", file=sys.stderr)
        return 2
    dirs = sorted(p for p in a.skills.iterdir() if p.is_dir()) if a.skills.is_dir() else []
    if not dirs:
        print(f"error: no skills found in {a.skills}", file=sys.stderr)
        return 2
    errs: list[str] = []
    for d in dirs:
        errs += check_skill(d, a.source)
    for e in errs:
        print(f"ERROR {e}")
    note = "" if a.source else " (source paths NOT verified: pass --source)"
    print(f"{len(dirs)} skill(s) checked, {len(errs)} error(s){note}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
