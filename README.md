# ERPForAll agent kit

Skills and four small tools that help an AI coding agent build correct ERPForAll
addons: manifest and layout, models and fields, views, menus and actions, access control, data files, tests, client
extensions, the chatter, reports, settings, attachments, WebAssembly packages, migrations, background jobs, wizards
and client actions, scale primitives, and pre-review checks. It works with Claude Code, OpenAI Codex CLI and Google
Antigravity / Gemini CLI from one set of skill files.

Every skill was written from the framework's addon guide (`docs/addon-guide/`) and its real addons, and ends with a
**Sources** list. Where the guide does not cover something, the skill says "not covered here" instead of guessing.
The guide state the skills were written against is in `SOURCE_REVISION`.

Licence: `MIT OR Apache-2.0`.

## Install

Clone this repository, then run `install.sh` for your agent. It symlinks the skill folders (add `--copy` to copy),
is safe to repeat, never overwrites anything it did not create, and accepts `--dry-run`, `--scope project`,
`--project-dir DIR` and `--uninstall`. It also links four commands into `~/.local/bin` (`--no-tools` skips that).

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
| `erpforall-models-fields` | declare models and fields in TOML or with the Rust macros, including binary, image, translated and company-dependent fields |
| `erpforall-views` | write list, form, search, kanban, pivot, graph and calendar views, binary widgets, prompt buttons, read mode, search defaults, list dashboards and dashboard cards, and extend views with xpath |
| `erpforall-menus-actions` | add window actions, initial `search_default_*` / `default_*` context, and menus (`lucide:` or addon SVG/PNG icons) |
| `erpforall-security` | access rows, groups, record rules, field access, `company_access`, scoped elevation, device API keys |
| `erpforall-data-files` | XML and CSV data, `noupdate`, default and demo data |
| `erpforall-extend-addon` | add fields and screens to another addon without editing it |
| `erpforall-addon-tests` | lint, install, native Rust tests, component tests |
| `erpforall-client-extensions` | custom widgets, record events, list headers, database appearance themes, brand assets and Elang extensions |
| `erpforall-chatter` | messages, followers, activities and record history on a model; bridge addons |
| `erpforall-reports` | declare a report and its action, QWeb templates, the print profile, printed business documents |
| `erpforall-settings` | settings and system parameters with a default, a floor and a bound |
| `erpforall-attachments` | store, list, serve and move files that belong to a record (native addons) |
| `erpforall-wasm-addons` | build, package and install a light addon as a WebAssembly package |
| `erpforall-migrations` | write schema and data migrations (`pre`, `post`, `end`, `0.0.0`, SQL scripts) and test upgrades |
| `erpforall-jobs` | declare durable background job kinds, chunked step methods, deduplication and cancellations |
| `erpforall-wizards-actions` | build transient wizard modal dialogs and full-screen `ir.actions.client` workspaces |
| `erpforall-orm-scale` | use business keys, batch `upsert`, `row_version` optimistic concurrency and `#[search_method]` providers |
| `erpforall-review` | run the pre-review checklist and static/security/migration/client quality checks before submitting |
| `erpforall-for-odoo-developers` | map Odoo concepts to ERPForAll |
| `erpforall-knowledge-graph` | look up what your own addons define before writing against it |

## Optional companion: ECC reviewers

This kit has zero external dependencies and works standalone across Claude Code, Codex CLI, Antigravity and Gemini CLI.
If you use Claude Code or Codex CLI and want deep automated code review on Rust, PostgreSQL SQL, TypeScript or security
beyond the kit's built-in `erpforall-review` checklist, you can optionally install the MIT-licensed
[ECC plugin](https://github.com/affaan-m/ECC) alongside this kit and pair `erpforall-review` with ECC's specialist
reviewers (`rust-reviewer`, `database-reviewer`, `security-reviewer`, `typescript-reviewer`, `silent-failure-hunter`,
`type-design-analyzer`).

## Tools

Python 3.10+, standard library only.

- `tools/new-addon.py <name> [--dest addons]` (command `erpforall-new-addon`): scaffolds a data-only addon in the
  layout of the framework's `sample_library` example (manifest, one model, access rows, list and form views, action,
  menu). For a native addon use the framework's `erp scaffold`.
- `tools/addon-lint.py <addon-dir> [--addons-path DIR]...` (command `erpforall-addon-lint`): static checks for
  manifest/data file mismatches, access CSV shape, XML structure and root, references used before they are defined,
  model and field names, and model-file keys. It is not a substitute for installing the addon.
- `tools/addon-graph.py [--addons-path DIR]... [--framework-root DIR] summary|model|field|impact|context|export` (command `erpforall-addon-graph`):
  a graph of your own addons (models, fields, RPC methods, views, menus, actions, access rows, inheritance, addon
  dependencies), each fact with `path:line`. From the ERPForAll root it also indexes core models, fields and methods.
  Pass `--framework-root DIR` to include the core from a standalone addon project. `model` and `field` exit 1 on a miss;
  `impact <file>...` shows what a change reaches; `context "<task>"` lists the places to read first; `export`
  prints the whole graph as JSON. A worked example with two addons and sample output is in
  [examples/README.md](examples/README.md).

## Test levels

For work inside a checkout of the ERPForAll repository, `tools/test-levels.py <level>` (command `erpforall-test`)
runs one of three levels of the framework's own checks and writes a receipt for the revision it ran on:

| Level | When | What it costs |
|---|---|---|
| `basic` | while you build: check that it compiles and lints, then try it in your local instance | minutes, no database |
| `normal` | before you push: the tests of what your change affects | tens of minutes, a PostgreSQL 18 server |
| `advanced` | before a release or a merge to a tested branch: the whole workspace and the whole client suite | an hour or more |

`erpforall-test <level> --dry-run` prints the commands first. `erpforall-test status --require normal` tells a
maintainer whether the current revision has a passing run of that level. Details and the two ways a run can be
meaningless (a tree edited during the tests, a database server short of lock memory) are in the
`erpforall-addon-tests` skill.

## Develop the kit

```bash
python3 -I -m unittest discover -s tests          # tests of the tools, installer and packaging
python3 -I scripts/check.py --source /path/to/erpforall   # validates every SKILL.md and its Sources
python3 -I scripts/build-packaging.py --check     # generated files are current
```

See [CONTRIBUTING.md](CONTRIBUTING.md) to add or change a skill.
