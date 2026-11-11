# Instructions for agents working on this repository

This repository is a kit of skills and tools for people who build ERPForAll addons. You are editing the kit itself.

- `skills/<name>/SKILL.md` is the single source of truth. Edit the skill; never edit generated files by hand
  (`.claude-plugin/*.json`, `templates/AGENTS.md.snippet`): run `python3 scripts/build-packaging.py`.
- **Zero fabrication.** Every API name, macro, file layout, CLI command, XML element and attribute in a skill must come
  from a page of the ERPForAll addon guide (`docs/addon-guide/`) or a real addon in a checkout of the framework.
  Read it, then write it. If the guide does not cover something, the skill says "not covered here". Never describe a
  feature as existing because it sounds plausible; the guide's pages mark work in progress, so mention that.
- Each skill ends with a `## Sources` section: repo-relative paths of the guide pages and addon files it was written
  from. Keep it accurate when you change the body.
- Keep skills short and procedural, with real minimal examples. Name skills `erpforall-<topic>`; the directory name
  equals the `name` in the frontmatter.
- No secrets, internal host names, team-process details, personal names or e-mail addresses. Mention other ERP products
  only in `erpforall-for-odoo-developers`.
- Tools use Python 3.10+ and the standard library only, and each has unit tests in `tests/`.
- Before finishing, run:
  ```bash
  python3 -I -m unittest discover -s tests
  python3 -I scripts/check.py --source <checkout of the ERPForAll repository>
  python3 -I scripts/build-packaging.py --check
  ```
- Do not run the framework's build or test suite for this kit; these checks are plain Python.
- Commit messages are plain and descriptive, with a `Signed-off-by` line (`git commit -s`, see `CONTRIBUTING.md`).
