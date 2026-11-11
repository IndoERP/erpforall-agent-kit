#!/usr/bin/env python3
"""Generate the per-agent packaging files from the one source, skills/*/SKILL.md.

Writes:
  .claude-plugin/plugin.json        Claude Code plugin manifest (skills/ at the repo root is the default location)
  .claude-plugin/marketplace.json   Claude Code marketplace catalog listing this one plugin
  templates/AGENTS.md.snippet       skill index for agents without a skills mechanism ({{KIT}} = checkout path)

Codex CLI and Antigravity / Gemini CLI read the same skills/<name>/SKILL.md folders directly, so they need
no generated files: install.sh links or copies the folders into their discovery directories.

Usage: scripts/build-packaging.py [--check]   (--check exits 1 if a generated file is out of date)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check import split_frontmatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = "erpforall-agent-kit"
DESCRIPTION = "Skills and small tools that help AI coding agents build ERPForAll addons correctly."


def skills() -> list[tuple[str, str]]:
    out = []
    for d in sorted((ROOT / "skills").iterdir()):
        if (d / "SKILL.md").is_file():
            fm, _ = split_frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
            if fm is None:
                raise SystemExit(f"{d.name}: bad frontmatter (run scripts/check.py)")
            out.append((fm["name"], fm["description"]))
    return out


def generate() -> dict[str, str]:
    version = (ROOT / "VERSION").read_text().strip()
    plugin = {
        "name": PLUGIN,
        "version": version,
        "description": DESCRIPTION,
        "author": {"name": "ERPForAll contributors"},
        "license": "MIT OR Apache-2.0",
        "keywords": ["erpforall", "addons", "erp", "skills"],
    }
    market = {
        "name": PLUGIN,
        "description": DESCRIPTION,
        "owner": {"name": "ERPForAll contributors"},
        "plugins": [{"name": PLUGIN, "source": "./", "description": DESCRIPTION}],
    }
    lines = [
        "## ERPForAll addon development",
        "",
        "Before writing or changing an ERPForAll addon, read the matching skill file (each starts with a",
        "short procedure and ends with its sources). The skills live in `{{KIT}}/skills/`.",
        "",
    ]
    for name, desc in skills():
        lines.append(f"- `{{{{KIT}}}}/skills/{name}/SKILL.md`: {desc}")
    lines += [
        "",
        "Tools (Python 3.11+): `python3 {{KIT}}/tools/new-addon.py <name> --dest addons` scaffolds a data-only",
        "addon; `python3 {{KIT}}/tools/addon-lint.py addons/<name> --addons-path addons` checks one;",
        "`python3 {{KIT}}/tools/addon-graph.py context \"<task>\"` lists what your addons define before you write against it.",
        "If a skill does not cover something, say so; do not invent APIs, XML attributes or CLI flags.",
        "",
    ]
    return {
        ".claude-plugin/plugin.json": json.dumps(plugin, indent=2) + "\n",
        ".claude-plugin/marketplace.json": json.dumps(market, indent=2) + "\n",
        "templates/AGENTS.md.snippet": "\n".join(lines),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    stale = []
    for rel, text in generate().items():
        p = ROOT / rel
        if a.check:
            if not p.is_file() or p.read_text(encoding="utf-8") != text:
                stale.append(rel)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            print(f"wrote {rel}")
    if stale:
        print("out of date (run scripts/build-packaging.py): " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
