---
name: erpforall-wasm-addons
description: Build a light ERPForAll addon as a WebAssembly package - the same Rust source as a native addon compiled to a sandboxed component, export_component!, model_ref! to extend a data-only addon's model, what a component body may do, what is refused, the [wasm] manifest section, erp addon build/package/install, and the data files a package may ship. Use when the user wants an addon that installs into a running server as an .erpaddon file instead of a compiled-in native addon.
---

# WebAssembly addons (`.erpaddon` packages)

A WebAssembly addon is written with the same macros as a native addon (`addon!`, `#[model]`, `#[extend]`,
`#[methods]`, `#[method]`, `#[method(override)]`, `#[compute]`, `#[constrains]`; see `erpforall-models-fields`),
compiled to a `wasm32-wasip2` component, packed as one `.erpaddon` archive and installed into a running server's
database. Its methods join the same override chains as native layers, and `super` crosses in both directions. No
`cfg` is needed in business code: `erp_sdk` picks its backend by target. The real example is
`examples/wasm/sample_library_wasm`, which extends the data-only `sample_library`.

## 1. Source

```rust
use erp_sdk::prelude::*;

erp_sdk::addon!(name = "sample_library_wasm", depends = ["sample_library"]);

#[cfg(feature = "component")]          // only when another package builds on this crate (below)
erp_sdk::export_component!();          // the leaf crate exports the component; natively it expands to nothing

erp_sdk::model_ref!(pub Loan = "sample_library.loan" {   // a model declared in TOML has no Rust type
    state: Option<Arc<str>>,
    due_date: Option<Date>,
});

#[extend(Loan)]
pub struct LoanRenewals {
    #[field(integer, string = "Renewals")]
    pub renewals: i32,
}

#[methods(Loan)]
impl LoanRenewals {
    #[method(wire, rpc)]               // `rpc`: callable from the web client and JSON-2
    async fn renew(this: &RecordSet<Loan>, tx: &mut Transaction, note: Option<String>) -> Result<i32> {
        let loan = this.ensure_one()?;
        let n = loan.get(tx, LoanRenewals::RENEWALS).await? + 1;
        loan.set(tx, LoanRenewals::RENEWALS, n).await?;
        Ok(n)
    }
}
```

- `model_ref!` field handles are checked against the registry when the package is installed or upgraded: an unknown
  model or field, or a Rust type that cannot hold the field's kind, refuses the install. Handles add no field; declare
  your own fields with `#[extend]`. An extension must add at least one field or method.
- `rpc` exposes a method; nothing is exposed by default. Not allowed on an `override` or a name starting with `_`.
  Calls run as the signed-in user with a writing transaction. A button passes no arguments, so make those `Option<T>`.
- When an addon is both the leaf of its own package and a dependency of another package, put `export_component!()`
  behind a default feature `component` and let the dependent turn default features off (a component exports once).

## 2. What a component body may do

`ensure_one`, `get`/`set` on scalar, date, many2one and x2many fields, `sup.call`, typed calls of other methods,
`tx.search_json(domain_json, limit, order)` (guest only), `this.env().model::<M>()`, `vals().set(..)`, `create`,
`write`, `related`, `this.context_today(tx)`. Each host call runs as the calling user and company through the access
rules. One call has a CPU time budget; overrunning it fails the method and poisons the transaction. The only WASI
import answered is the wall clock. `HashMap`/`HashSet` trap (no randomness): use `BTreeMap`/`BTreeSet` or a `Vec`.

Overrides of `create`, `write` and `unlink` work with the native signatures and need no `wire`. A `create`
override must return exactly the records its `super` created. An override that skips `super` skips the core too.

## 3. Refused or not available yet (fails loudly, never skipped)

- Compile error: `#[rpc(...)]`, `#[data_callable]`, `#[field_access]`, `#[access_domain]`.
- Refused at install: `#[onchange]`, `async` computes, `#[compute(override)]`, a `depends`/`reads` path through a
  relation, `inverse`, `related`, `precompute`, `compute_sudo = true`, `tracking` (`tracking.md`); `selection_add`, `selection_method`,
  `default_fn`, a named `digits`; raw SQL `constraints`/`indexes`/`unique_indexes`; keys or `parent_store` on an
  `extend`; relational fields other than `many2one`; redeclaring a field another addon introduced.
- Not in the guest API: `Vals::commands`, new (in-memory) records, typed `Domain` search; range, JSON and binary
  fields in `get`/`set`.
- Overriding a sealed method (`#[method(sealed)]`, every constraint and onchange, record methods of `res.users`,
  `res.groups`, `ir.access`, `res.users.apikeys`, `ir.config_parameter`) or a method whose types have no wire form
  is refused when the registry is built.
- `#[migration]` and SQL migration scripts: not available; the schema follows the declared fields.
- Manifest capabilities (`network:outbound:`, `filesystem:temp:`, `migrations-sql`) are refused: this host cannot
  enforce them yet.
- A package may not take the name of a native addon; at most 4096 methods, 256 models and 4096 fields.

## 4. Manifest, data files, build, install

```toml
name = "Sample Library WASM"
version = "1.3.6"
depends = ["sample_library"]
data = ["security/ir.access.csv", "views/sample_library_wasm_views.xml"]

[wasm]
sdk_version = "1.0"
```

The leaf crate's `Cargo.toml` replaces `[lints] workspace = true` with `[lints.rust] unsafe_code = "deny"` plus the
clippy denies (the export glue is unsafe ABI code). Data files may hold `ir.ui.view` records for models the package
declares or extends (only extension views on a model it only extends), `ir.actions.act_window`, menus, and an
`ir.access.csv` with the columns `id,name,model_id/id,group_id/id,operation,active` (no `domain`) for its own models.
Refused: `demo`, `.sql`, `<function>`, `<delete>`, `<template>`, `<asset>`, other models' records, `context`/`uid`.

```sh
rustup target add wasm32-wasip2                                  # once
erp addon build my_addon --target wasm --addons-path ./addons   # fat LTO, checks describe(), writes wasm/<name>.wasm
erp addon package my_addon --addons-path ./addons -o my_addon-1.0.0.erpaddon
erp addon install my_addon-1.0.0.erpaddon -d mydb --config <server config> --approve none
erp addon upgrade my_addon-1.1.0.erpaddon -d mydb --config <server config> --approve none
erp addon uninstall my_addon -d mydb --config <server config>
```

`--approve` lists exactly the capabilities requested, or `none`. Client code in `static/dist/` also needs
`--ack-client-digest <sha256>` (printed by `package`). Dependencies must already be installed. Read `rpc_methods` in
the output: consent does not cover it. Keep the package's source out of the server's addons path. Exit codes: 1
refused, 3 busy, 4 rolled back, 5 committed but post-commit unfinished, 2 system error. After an install, upgrade or
uninstall a membership-bound server must be drained and restarted.

## Not covered here

Onchanges in a component (planned), `company_access` declarations on package models (the sample's wizard carries one;
see `wasm-addons.md`), the embedding API (`WasmLifecycle`, `HostLoader`), the `describe()` JSON format
in detail, the archive's path rules and size bounds (`erpaddon-package.md`), the operator rollout procedure. `cli.md`
does not list the `erp addon` commands; they are documented in `wasm-addons.md`.

## Sources

- docs/addon-guide/wasm-addons.md
- docs/addon-guide/erpaddon-package.md
- docs/addon-guide/tracking.md
- examples/wasm/sample_library_wasm/manifest.toml
- examples/wasm/sample_library_wasm/Cargo.toml
- examples/wasm/sample_library_wasm/src/lib.rs
- examples/wasm/sample_library_wasm/security/ir.access.csv
- examples/wasm/sample_library_wasm/views/sample_library_wasm_views.xml
- examples/wasm/sample_library_wasm_policy/Cargo.toml
