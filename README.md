# ERPForAll agent kit

Skills and three small tools that help an AI coding agent build correct ERPForAll
addons: manifest and layout, models and fields, views, menus and actions, access control, data files, tests, client
extensions and the chatter. It works with Claude Code, OpenAI Codex CLI and Google Antigravity / Gemini CLI from one
set of skill files.

Every skill was written from the framework's addon guide (`docs/addon-guide/`) and its real addons, and ends with a
**Sources** list. Where the guide does not cover something, the skill says "not covered here" instead of guessing.
The guide state the skills were written against is in `SOURCE_REVISION`.

Licence: `MIT OR Apache-2.0`.

## Install

Clone this repository, then run `install.sh` for your agent. It symlinks the skill folders (add `--copy` to copy),
is safe to repeat, never overwrites anything it did not create, and accepts `--dry-run`, `--scope project`,
`--project-dir DIR` and `--uninstall`. It also links three commands into `~/.local/bin` (`--no-tools` skips that).

| Agent | Command | Skills end up in |
|---|---|---|
| Claude Code | `./install.sh --agent claude` | `~/.claude/skills` |
| Codex CLI | `./install.sh --agent codex` | `~/.agents/skills` |
| Antigravity | `./install.sh --agent antigravity` | `~/.gemini/config/skills` |
| Gemini CLI | `./install.sh --agent gemini` | `~/.gemini/skills` |

Claude Code can also load the repository as a plugin:
`claude plugin marketplace add /path/to/erpforall-agent-kit` then
`claude plugin install erpforall-agent-kit@erpforall-agent-kit`.

An agent without skill support (or an older version) can still use the kit: `./install.sh --agent codex --scope project
--agents-md` adds a marked block to the project's `AGENTS.md` that points at the skill files. What was confirmed from
each vendor's documentation, and what is unconfirmed, is in [docs/agent-support.md](docs/agent-support.md).

## Skills

| Skill | Use it to |
|---|---|
| `erpforall-create-addon` | start an addon: manifest, layout, data-only versus native, install into a database |
| `erpforall-models-fields` | declare models and fields in TOML or with the Rust macros |
| `erpforall-views` | write list, form and search views and extend views with xpath |
| `erpforall-menus-actions` | add window actions and menus |
| `erpforall-security` | access rows, groups, record rules, field access |
| `erpforall-data-files` | XML and CSV data, `noupdate`, default and demo data |
| `erpforall-extend-addon` | add fields and screens to another addon without editing it |
| `erpforall-addon-tests` | lint, install, native Rust tests, component tests |
| `erpforall-client-extensions` | custom widgets and client code (native addons) |
| `erpforall-chatter` | messages, followers and activities on a model |
| `erpforall-for-odoo-developers` | map Odoo concepts to ERPForAll |

## Tools

Python 3.10+, standard library only.

- `tools/new-addon.py <name> [--dest addons]` (command `erpforall-new-addon`): scaffolds a data-only addon in the
  layout of the framework's `sample_library` example (manifest, one model, access rows, list and form views, action,
  menu). For a native addon use the framework's `erp scaffold`.
- `tools/addon-lint.py <addon-dir> [--addons-path DIR]...` (command `erpforall-addon-lint`): static checks for
  manifest/data file mismatches, access CSV shape, XML structure and root, references used before they are defined,
  model and field names, and model-file keys. It is not a substitute for installing the addon.
- `tools/addon-graph.py [--addons-path DIR]... summary|model|field|impact|context` (command `erpforall-addon-graph`):
  a graph of your own addons (models, fields, RPC methods, views, menus, actions, access rows, inheritance, addon
  dependencies), each fact with `path:line`. `model` and `field` exit 1 when a name is not declared in your addons;
  `impact <file>...` shows what a change reaches; `context "<task>"` lists the places to read first; `export`
  prints the whole graph as JSON. A worked example with two addons and sample output is in
  [examples/README.md](examples/README.md).

## Develop the kit

```bash
python3 -I -m unittest discover -s tests          # tests of the tools, installer and packaging
python3 -I scripts/check.py --source /path/to/erpforall   # validates every SKILL.md and its Sources
python3 -I scripts/build-packaging.py --check     # generated files are current
```

See [CONTRIBUTING.md](CONTRIBUTING.md) to add or change a skill.
