---
name: erpforall-knowledge-graph
description: Look up what your own ERPForAll addons define before you write against it - models, fields, RPC methods, views, menus, actions, access rows, inheritance and addon dependencies, each with a file and line - and what a change to a file can affect. Use before naming a model or field in a view, an access row or a client call, before extending another addon, and before finishing a change.
---

# Knowledge graph of your addons

`tools/addon-graph.py` in this kit reads the addons under an addons path and answers from what the files say. It needs
Python 3.11+ and nothing else; it does not build, install or start anything. Run it from the project root (default
addons path is `./addons`; repeat `--addons-path DIR` for several). Installed with `install.sh`, the command is
`erpforall-addon-graph`.

## Procedure

1. **Before you start:** `python3 <kit>/tools/addon-graph.py context "<what you are about to do>"`. It lists the
   models, fields, views, menus, actions, exposed methods and addons that match, each with `path:line`. Read those
   files first.
2. **Before you write a model or field name** into a view, an access CSV row, an action or a client call:
   `addon-graph.py model <name>` and `addon-graph.py field <model> <field>`. Exit status 1 means "not declared in these
   addons": do not write it. Use a name it suggests, or read the addon that should define it.
3. **Before you extend another addon:** `addon-graph.py model <name>` shows who defines and extends the model, its
   fields, exposed methods, views, actions, menus and access rows, so your extension does not repeat or contradict them.
4. **Before you finish:** `addon-graph.py impact <changed file>...` lists the addon that owns the files, the addons
   that depend on it, the models in the files and the views, actions, access rows and fields that point at them. Then
   run the kit's lint (`tools/addon-lint.py`) on the addons it names, and install the addon: the framework's loader
   is the authority.
5. `addon-graph.py summary` prints the counts and everything the tool could not understand (a native model written in
   a form it does not read, an XML file that does not parse). An absence is only meaningful when that list does not
   cover the file you care about.

Add `--json` to any command for tool use.

## What it reads

- `manifest.toml` (dependencies), `models/*.toml` (data-only models, `extend`, fields and their `comodel`),
- native Rust addons in `src/`: `#[model(...)]`, `#[extend(...)]`, `#[field(...)]` and `#[methods(...)]` blocks with
  `#[rpc(...)]` functions,
- XML data files: `ir.ui.view` records (model, `inherit_id`, the fields the arch shows), menus, window actions, other
  records; and access CSV files (`model_id/id` or `model_id:id` columns).

## Not covered here

- Models and fields of the framework itself (for example `res.partner`) and of addons outside `--addons-path`: the tool
  reports them as not found in your addons; check the framework's guide pages (`models.md`, `data-only-addon.md`).
- Fields and methods that a macro generates, and Rust written in a form the reader does not know: they show under
  "not understood" in `summary`, or not at all.
- Whether the addon installs or its tests pass: run the framework's own commands for that.

## Sources

- docs/addon-guide/data-only-addon.md
- docs/addon-guide/models.md
- docs/addon-guide/views.md
- docs/addon-guide/data-files.md
- docs/addon-guide/cross-addon-extension.md
- docs/addon-guide/rpc.md
- addons/sample_library/manifest.toml
- addons/sample_library/models/20_book.toml
- addons/sample_library/security/ir.access.csv
- addons/mail/src/res_partner.rs
