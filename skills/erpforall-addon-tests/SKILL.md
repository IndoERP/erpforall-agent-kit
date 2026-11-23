---
name: erpforall-addon-tests
description: Test an ERPForAll addon - static lint, install into a database, native Rust tests with erp_testkit::Harness and registry builds, manifest consistency tests, and Elang component tests for client code. Use when asked to verify an addon works, add tests, or debug a failing install.
---

# Testing an addon

Work from the cheapest check to the most expensive one.

## 1. Lint (no database, no compiler)

```bash
erpforall-addon-lint addons/my_addon --addons-path addons
```

(fallback `python3 <kit>/tools/addon-lint.py ...`). Fix every error. Add `--addons-path` pointing at the folder holding the addon's dependencies (including `base`) so model names can be verified. This is a static check; the framework's loader stays the authority.

## 2. Dry-run and real install

```bash
erp module install -d mytestdb my_addon --addons-path ./addons --dry-run   # load order, no database
export DATABASE_URL="postgres://erp@localhost/postgres"
erp module install -d mytestdb my_addon --addons-path ./addons
```

The target database must already be initialized (an empty one fails with `Database <name> not initialized`): `erp db init --config server.toml --admin-login admin --admin-password-file <mode-600 file> --with-demo` makes a demo database, and every addon installed later loads its demo files. A view that names a field its model does not have, a data file with a bad `ref`, or a schema mistake fails the install; the whole operation rolls back and the error names the module, the step and the cause. Run it on a throwaway database, then `erp module upgrade` to prove the upgrade path. To try an upgrade on a copy of a real database, `erp db dump` / `erp db restore` it under another name and run `erp db neutralize` on the copy first (scheduled actions off, jobs held, sessions, API keys and passwords replaced); see `cli.md`, "Database copies".

## 3. Native addons: Rust tests

Dev-dependencies the real addons use: `erp-testkit`, `tokio` (features `rt`, `macros`), `toml`, and `erp-addon-base` when the test needs the base registry.

- Registry builds, no database:
  ```rust
  let registry = erp_sdk::RegistryBuilder::new([&erp_addon_base::ADDON, &my_addon::ADDON])
      .build().expect("real linked registry");
  let note = registry.model("acceptance_notes.note").expect("model is linked");
  assert!(note.field("name").expect("declared field").required);
  ```
- Examples in the guide are checked with `erp_testkit::Harness::builder([&ADDON]).check()?` (and `.registry_only()`); `Harness::begin()` gives a transaction in tests that need a database.
- Manifest consistency (pattern from the `product` addon): read `manifest.toml` with the `toml` crate, assert that every listed data file exists, that no file under `data/`, `security/`, `views/` is left unlisted (an unlisted file silently never loads), and that `manifest depends` equals the `addon!` descriptor's `depends`.
- A default-data test: assert the records the data files declare exist after install (the `uom` addon checks ids in `data/uom_data.xml`).

### Placement and targeted execution

- Keep single-addon unit, manifest and registry tests inside `addons/<my_addon>/tests/` using only `erp-sdk`, other addons and `erp-testkit` (dev-dependency).
- Put multi-addon or full-stack integration tests that need core crates (`erp-orm`, `erp-modules`, `erp-security`) in an isolated L13 domain suite crate under `crates/erp-suite-<domain>` instead of adding leaf addons to `crates/erp-test-models` or domain tests to `crates/erp-cli`.
- Run targeted checks instead of `--workspace` while iterating: `erpforall-addon-graph impact <changed-file>...` lists the affected addons and suggested Cargo packages; in a repository checkout run `scripts/check.sh --affected --tests` or `scripts/check.sh -p erp-addon-<name> -p erp-suite-<name> --tests`.

## 4. Access with more than one user

An access CSV is an input, not the expected answer: write the expected outcome per user independently of the rows, use ordinary users with verified groups in separate companies (not a setup or System environment), send valid payloads (a validation error proves nothing about authorization), and check a success by reading it back and a refusal by the absence of the change. `access-rules.md`, "Multi-user acceptance", lists what else to cover.

## 5. Client code (widgets, panels)

Use `@erpforall/elang-test` from a workspace test: keep each test inside `withTestScope(async scope => { ... })` (it unmounts roots and restores registry and patch changes even when the callback rejects), mount with `scope.mount(ComponentClass, options)`, replace a service with `scope.mockService(CanonicalServiceClass, mockInstance)`, patch with `scope.patch` / `scope.patchStatic`. The package is test infrastructure: never import it from the entry point an addon ships. One scope per test realm at a time: no concurrent tests that share patch or registry state.

## Not covered here

Parity or performance test setups, CI configuration of the framework, the typed mock RPC helpers of `component-testing.md`.

## Sources

- docs/addon-guide/cli.md
- docs/addon-guide/data-only-addon.md
- docs/addon-guide/component-testing.md
- docs/addon-guide/models.md
- docs/addon-guide/auth.md
- docs/addon-guide/access-rules.md
- docs/addon-guide/demo-data.md
- addons/acceptance_notes/tests/test_acceptance_notes.rs
- addons/acceptance_notes/Cargo.toml
- addons/product/tests/install.rs
- addons/product/Cargo.toml
- addons/uom/tests/install.rs
- addons/uom/tests/support/guard_fixture.rs
- addons/mail/Cargo.toml
