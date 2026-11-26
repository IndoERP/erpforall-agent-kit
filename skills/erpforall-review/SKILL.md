---
name: erpforall-review
description: Review an ERPForAll addon before committing or opening a pull request - pre-review checklist for manifest and data files, fail-loudly error handling, access rows and company_access, migrations, views and client code, tests, and optional specialist review lenses (Rust, SQL, security, UI). Use when finishing an addon task or auditing an addon diff.
---

# Pre-review checklist for ERPForAll addons

Run these checks before setting a change ready for review or opening a pull request. Every item below corresponds to a loud-failure rule in the framework.

## 1. Static analysis and addon graph

1. Inspect affected models, views and cross-addon dependencies with `erpforall-addon-graph impact <changed-file>...`.
2. Run `erpforall-addon-lint --strict addons/<my_addon> --addons-path addons` and resolve every error and warning (including `Cargo.toml` layer checks for native addons).
3. Verify test isolation and affected checks: keep full-stack domain tests in `crates/erp-suite-<domain>` (never adding leaf addons to `crates/erp-test-models` or domain tests to `crates/erp-cli`) and run `scripts/check.sh --affected --tests` (or `-p erp-addon-<name> -p erp-suite-<name> --tests`).

## 2. Manifest and data files

- **Manifest keys:** only documented keys or `[extra]` are present; `icon` (when set) uses `lucide:<name>`; `depends` in `manifest.toml` matches `erp_sdk::addon!(depends = [...])` in native crates.
- **No unlisted files:** every XML/CSV file in `security/`, `views/`, `data/` is listed under `data`, and every demo XML under `demo`; no file is listed twice.
- **Strict XML & load order:** root tag is `<erp>`; `<list>` is used instead of `<tree>`; every `ref` targets an id defined earlier in load order or in a declared dependency.
- **Default & demo data:** every concrete model ships appropriate reference/default data (listed in `data`) and realistic `demo` data when applicable (`data-files.md`).

## 3. Security and multi-company

- **Access rows:** every concrete model (including transient wizards) has rows in `security/ir.access.csv` using valid `crud` ordering (`u`, never `w`), listed early in `data`.
- **Company rules:** every concrete company-scoped model declares `company_access` (`direct`, `parent`, or `unrestricted(reason = "...")`) (`company-consistency.md`).
- **Server-side authorization:** business permissions are checked inside model and `#[rpc]` methods, never relying on view `invisible`/`groups` attributes or client-side UI hiding (`security.md`, `access.md`).
- **Scoped elevation & narrow RPC effects:** avoid `sudo(true)` in addon code where `tx.elevated(env, reason, scope, ...)` works; give every `#[rpc(effect = ...)]` the narrowest honest effect (`read` / `write`); restrict secrets/credentials via `.secret()` or restricted `groups`.
- **Multi-user tests:** test allow and deny cases across separate non-superuser users and companies using valid payloads (`access-rules.md`).

## 4. Models, settings, migrations, and fail-loudly hygiene

- **Fail loudly:** return typed `Error::validation`, `Error::user`, `Error::programming`, etc. on invalid inputs or unsupported states; never swallow errors or fall back to silent defaults.
- **Configurable policy:** use `SettingDecl` or `ParameterDecl` (`settings.md`) instead of hardcoded limits/timeouts, with non-zero floors (>= 1 unless `*_floor_below_one` with explicit reason) and hard bounds.
- **Numbers & sequences:** use `monetary` or `Decimal` (`digits = ...`) rather than binary floats for currency and stock quantities; use `implementation = 'no_gap'` for sequences generated at runtime (`models.md`).
- **Upgrades:** verify schema/data migrations handle existing rows cleanly inside the upgrade transaction, avoid forbidden transaction statements in SQL scripts, and preserve existing customizations (`migrations.md`).

## 5. Views and client extensions

- **XPath selectors:** never match `<xpath>` or locator nodes by translated attributes (`string`, `help`, `placeholder`, `confirm`, `title`); match by `@name`, tag structure, or `hasclass(...)` (`views.md`).
- **Widget & component discipline:** field widgets emit edits via `props.change(value)` (never bypassing form state with direct writes), unregister listeners/timers/overlays inside `dispose()`, and attach cleanly in `static/dist/manifest.json` (`human-client-extensions.md`).
- **Commit hygiene:** signed off (`git commit -s`), no unrelated edits, no generated files edited by hand, tests run for the changed behaviour. `scripts/check-dco.py BASE HEAD` fails on any non-merge commit without `Signed-off-by:`; `git rebase --signoff BASE` adds it to commits already made.
- **Suite crates:** `python3 -I scripts/check-layers.py` passes (rule 8: nothing depends on an `erp-suite-*` crate, a suite does not depend on `erp-cli`, every suite is a workspace member).
- **Reports and secrets:** a report provider reads as the caller through the ORM (skill `erpforall-security`); a stored secret is an `encrypted = true` field (skill `erpforall-models-fields`).

## 6. Optional specialist review lenses

If your coding agent also has external specialist review subagents installed (such as the optional **ECC** companion plugin), run the matching lens on your diff alongside this checklist:
- Native Rust changes -> `rust-reviewer` + `silent-failure-hunter`
- SQL migrations, raw `tx.query` / `tx.execute`, locks -> `database-reviewer`
- Access rules, auth routes, RPC inputs, SVG/static endpoints -> `security-reviewer`
- Web client TypeScript widgets, services, overlays -> `typescript-reviewer`
- New public SDK types or traits -> `type-design-analyzer`

## Not covered here

Host build/CI workflows of the framework repository itself or visual design review rubrics.

## Sources

- docs/addon-guide/security.md
- docs/addon-guide/access.md
- docs/addon-guide/access-rules.md
- docs/addon-guide/company-consistency.md
- docs/addon-guide/models.md
- docs/addon-guide/views.md
- docs/addon-guide/data-files.md
- docs/addon-guide/settings.md
- docs/addon-guide/migrations.md
- docs/addon-guide/human-client-extensions.md
- scripts/check-dco.py
- scripts/check-layers.py
