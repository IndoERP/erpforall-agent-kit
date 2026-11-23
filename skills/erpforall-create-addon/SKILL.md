---
name: erpforall-create-addon
description: Create a new ERPForAll addon from scratch - manifest.toml, directory layout, data-only versus native (Rust) addon, scaffolding, listing data files, installing it into a database. Use when the user asks to start, scaffold or register a new ERPForAll addon or module.
---

# Create an ERPForAll addon

An addon is a folder whose name is the module name (`^[a-zA-Z0-9_]{1,256}$`). It comes in two kinds.

| Kind | Has | Use it when |
|---|---|---|
| **Data-only** | `manifest.toml`, `models/*.toml`, XML/CSV data files. No `Cargo.toml`, no `src/`, nothing to compile. | You need models, fields, views, menus, actions, access rows, default and demo data. |
| **Native** | The same folders plus a Rust crate (`Cargo.toml`, `src/lib.rs`). | You need Rust methods, overrides with `super`, `#[rpc]` endpoints, constraints or computed fields in code, binary or company-dependent fields, or client widgets. |

A third form, a light addon packaged as WebAssembly, is described in the `erpforall-wasm-addons` skill.

Starting with data-only and adding a `Cargo.toml` plus `src/` later is mechanical: the `models/`, `views/` and `security/` folders stay.

## Steps

1. Decide data-only or native (table above). When in doubt, start data-only.
2. Scaffold.
   - Data-only, with this kit: `erpforall-new-addon my_addon --dest addons` (fallback: `python3 <kit>/tools/new-addon.py my_addon --dest addons`). It writes the layout of the `sample_library` example.
   - Either kind, with the framework CLI: `erp scaffold my_addon --summary "..." --author "..."` (native; creates `./addons/my_addon`) or `erp scaffold my_addon --data-only`.
3. Edit `manifest.toml` (below) and add models, views, access rows.
4. Run `erpforall-addon-lint addons/my_addon` and fix what it reports.
5. Install into a database that is already initialized (`erp module` never initializes one; `erp db init --config server.toml --admin-login admin --admin-password-file <mode-600 file> [--with-demo]` installs `base` and `web` and creates the administrator; the demo choice is fixed at that moment):
   ```bash
   export DATABASE_URL="postgres://erp@localhost/postgres"
   erp module install -d mydb my_addon --addons-path ./addons
   ```
   `--dry-run` prints the load order and needs no database. `--with-demo` on a database without demo data first loads the demo data of every installed addon (it cannot be undone). Upgrade after editing: `erp module upgrade -d mydb my_addon --addons-path ./addons`. Uninstall: `erp module uninstall -d mydb my_addon`. Upgrade and uninstall check a per-addon content receipt that install writes; an `identity unknown` refusal is answered by an operator with `erp module identity-enroll` (`cli.md`).

## Layout

```text
my_addon/
  manifest.toml
  models/10_thing.toml        # data-only models, read in file-name order
  security/ir.access.csv
  views/my_addon_views.xml    # <erp> root
  data/my_addon_data.xml      # default data
  demo/my_addon_demo.xml      # only with demo data
  # native addons add: Cargo.toml, src/lib.rs, src/models.rs, tests/
```

## manifest.toml

```toml
name = "Sample Library"
summary = "Books, authors and loans"
version = "1.0.0"
license = "MIT OR Apache-2.0"
author = "ERPForAll"
category = "Sample"
application = true
depends = ["base", "web"]
data = ["security/ir.access.csv", "views/sample_library_views.xml", "views/sample_library_reports.xml"]
demo = ["demo/sample_library_demo.xml"]
```

- Keys the guide documents: `name`, `summary`, `description`, `version`, `license`, `author`, `category`, `application`, `depends`, `data`, `demo`, `auto_install`, `countries`, `excludes`, `installable`, `icon`, `pre_init_hook`, `post_init_hook`, `uninstall_hook`, `exact_only`, and a free-form `[extra]` table. **Unknown keys are refused.**
- `icon = "lucide:<name>"` (same form as a menu's `web_icon`) is the addon's icon on the Apps page and in the Settings sidebar; any other form refuses the manifest. Declare one for an addon that shows in a menu.
- `depends`: these install first and your addon loads after them. An addon that overrides or extends another must depend on it. List `base`; list `web` when the addon ships kanban, pivot, graph or calendar views or list dashboards, which `web` owns (`sample_library` depends on both).
- `data` files load in the listed order on install and upgrade (put access rows and groups first, then views, actions, menus). **A file that is not listed never loads.** A file listed twice loads twice. `demo` files load only when the database was created with demo data.
- A data-only addon's `data` and `demo` entries must be `.xml` or `.csv`.

## Native addon

`src/lib.rs` registers the crate once:

```rust
erp_sdk::addon!(name = "my_addon", depends = ["base"]);
pub mod models;
```

`Cargo.toml` depends on `erp-sdk` (the framework's scaffold writes `erp-sdk = "0.1"`, `edition = "2024"`, `license = "MIT OR Apache-2.0"`). Until `erp-sdk` is published, point it at a checkout of the framework, and copy the `[patch.crates-io]` entries (`hyper`, `tokio-postgres`) of the framework's top-level `Cargo.toml`: Cargo applies `[patch]` only from the top-level workspace. Keep `depends` in `addon!` and in `manifest.toml` the same set. Native addons never depend on core internals (`erp-orm`, `erp-modules`, `erp-security`, `erp-cli`); if the addon needs full-stack multi-addon database tests, place them in a dedicated L13 `crates/erp-suite-<name>` crate and verify with `scripts/check.sh --affected --tests`.

A served node (`erp server`) and `erp module install` offer only data-only addons from the addons directory and the native addons compiled into the `erp` binary. A folder with a Rust crate that the binary does not link is refused by name (`this binary does not link the addon's native code: ...`); how the framework's own binary lists the linked addons is in `modules.md`, "Making a native addon installable on a served node".

## Rules of thumb

- Installing, upgrading and uninstalling are each one PostgreSQL transaction: on any failure nothing of the operation is kept.
- Exit codes of `erp module`: 1 refused (unknown module, bad dependencies, uninitialized database), 3 database busy, 4 a step failed and was rolled back.
- A data-only addon is offered by the server only if it holds nothing but `manifest.toml`, `models/*.toml`, `.xml`/`.csv` files under `views/`, `data/`, `demo/`, `security/`, and `README*`. Its model files cannot declare SQL objects (functions, triggers, grants).
- Building an addon by talking to the assistant (prompt-authored customization) is planned, not available.

## Not covered here

Publishing to a registry; operating a server (`erp db dump`, `restore`, `neutralize` and the rest of `cli.md`). WebAssembly packages: skill `erpforall-wasm-addons` (`wasm-addons.md`, `erpaddon-package.md`).

## Sources

- docs/addon-guide/data-only-addon.md
- docs/addon-guide/cli.md
- docs/addon-guide/modules.md
- docs/addon-guide/two-addon-tutorial.md
- docs/addon-guide/data-files.md
- addons/sample_library/manifest.toml
- addons/contacts/manifest.toml
- addons/acceptance_notes/manifest.toml
- addons/acceptance_notes/src/lib.rs
- addons/acceptance_notes/Cargo.toml
