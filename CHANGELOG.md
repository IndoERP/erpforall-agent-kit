# Changelog

## 0.6.0

- **New `erpforall-dynamic-reports` skill**: on-screen reports of the `reporting` addon. Data reports (lines, columns, aggregate and formula expressions), native providers (`ReportProvider`, `ProviderSpec`, options, lines and cells, paging, drills), the `reporting.report` client action, native functions, bounds settings and tests.
- **Updated skills**, from the public framework code: `erpforall-security` (read as the caller), `erpforall-wizards-actions` and `erpforall-menus-actions` (in-page window results, dialog rules, report client action), `erpforall-migrations` (shipped `noupdate` records, predecessor fixtures), `erpforall-settings` (module and group toggles, `_apply_value_changes`), `erpforall-models-fields` (encrypted fields, `Error::with_fields`), `erpforall-data-files` (demo data forms), `erpforall-views` (hierarchy, activity, search panel, tones, list allow-list), `erpforall-client-extensions` (template-free widgets, navigation, translations, refused page), `erpforall-addon-tests` (suite crates, template databases, policy ORM), `erpforall-jobs` (recurring jobs), `erpforall-review` (DCO, layer rule 8).
- **Pin**: `PUBLIC_SOURCE_REVISION` moves to `7e42b120663d`.
- **`docs/skill-drift-2026-11.md`**: what each skill lacked, what changed, and what was left out and why.

## 0.5.0

- **Test levels (`tools/test-levels.py`, command `erpforall-test`)**: `basic`, `normal` and `advanced` runs for a checkout of the framework. `basic` checks the affected packages without a database and rebuilds the local instance; `normal` adds the tests of the affected packages and the changed client tests; `advanced` runs the whole workspace and the whole client suite. Every run writes a receipt (revision, commands, exit codes, durations, logs, tool versions); `status --require LEVEL` answers whether the current revision has a passing run. A run is marked `invalid` when the working tree changed under the tests, and environment failures (database lock memory, an addon edited during install) are named as such. Database passwords are removed from output, logs and receipts.
- The commands of each level come from the framework's own scripts and guides (`scripts/check.sh`, `scripts/install.sh`, `CONTRIBUTING.md`). The tool's logic has unit tests; a complete run of each level on a real checkout has not been recorded yet.
- **`erpforall-addon-tests` skill**: new section on the three levels, when each is enough, and what each proves.
- **Installer**: links `erpforall-test`; the help text names all four commands.

## 0.4.0

- **Static layer lint in `tools/addon-lint.py`**: validates native addon `Cargo.toml` dependencies so forbidden core crates (`erp-orm`, `erp-modules`, `erp-security`, `erp-cli`, `erp-suite-*`, non-dev `erp-testkit`) are flagged before `scripts/check-layers.py` runs, and guides full-stack tests to L13 `crates/erp-suite-<name>` crates.
- **Affected test suggestions in `tools/addon-graph.py`**: `impact` now reports `affected_addons`, `suggested_packages` (`erp-addon-*` and `erp-suite-*`), and a ready-to-run `scripts/check.sh -p ... --tests` command.
- **Updated testing, creation, and review skills**: `erpforall-addon-tests`, `erpforall-create-addon`, and `erpforall-review` now cover L13 domain test suites (`crates/erp-suite-*`) and affected-only checks (`scripts/check.sh --affected --tests`).
- **Public repository drift detection**: added `--public-source` to `scripts/check.py`, pinned `PUBLIC_SOURCE_REVISION` (`IndoERP/ERPForAll@main`), and added weekly `.github/workflows/drift-check.yml`.

## 0.3.0

Updated `SOURCE_REVISION` to `aea11474cc94713d7e1f639b6999a6be9f060de1`, expanded skill coverage, and updated `addon-lint.py`.

New skills:

- `erpforall-migrations`: schema and data migrations across `pre`, `post` and `end` stages (`#[erp_sdk::migration]` and `migrations/<version>/<stage>-*.sql`), `0.0.0` every-upgrade hooks, adopting company-dependent scalars, and upgrade testing.
- `erpforall-jobs`: durable background jobs (`register_job_kind!`, `StepArgs`/`StepOutcome`, `EnqueueRequest`, deduplication/singleton keys, `job_cancel_by_key`, `JobHandler` and `chunk_items`).
- `erpforall-wizards-actions`: transient wizard modal dialogs (`<footer>`, bounded `act_window` and `display_notification` results, cleanup policies) and full-screen `ir.actions.client` actions (`ClientActionDecl` and `registerClientAction`).
- `erpforall-orm-scale`: business keys (`UNIQUE NULLS NOT DISTINCT`), batch `upsert`, `row_version` optimistic concurrency (`expect_versions`), and bounded `#[search_method]` providers for nonstored computed fields.
- `erpforall-review`: agent-neutral pre-review checklist (manifest/data completeness, fail-loudly hygiene, security and `company_access`, migrations, client extension discipline) plus optional pairing with external ECC specialist reviewers.

Updated skills:

- `erpforall-views`: `widget="binary"` with `filename` and `accepted_file_extensions`, object button `prompt="text|date|selection"`, `<form edit_mode="read">`, search `<filter>` / `<field>` / `search_default_*` defaults.
- `erpforall-client-extensions`: `WidgetEnvironment.mode` and `onRecordEvent`, `registerListHeaderExtension`, `<addon>.appearance` database themes, and `static/brand/` server logo/favicon assets.
- `erpforall-menus-actions`: `search_default_<name>` in action context and custom SVG/PNG `web_icon` references (`<addon>,static/...` and bounded `data:image/*` URLs).
- `erpforall-models-fields`: translated fields (`#[field(..., translate = true)]`, `get_field_translations` / `update_field_translations`, static selection label translations) and `widget="binary"` defaults.
- `erpforall-settings`: `erp_addon_base::approval_settings::max_approvers` helper and `<addon>.appearance` global selection settings.
- `erpforall-security`: `POST /erp/session/api-key` device API key exchange and `_get_session_token_fields`.

Tools and documentation:

- `tools/addon-lint.py`: accepted `icon` in `manifest.toml`, `audit_reads`, `transient_max_age_seconds` and `transient_max_count` in `[[model]]`, `bigint` field type, `collation` field key, and `kanban`/`pivot`/`graph`/`calendar` view roots.
- `README.md`: documented optional **ECC** companion reviewers alongside the full 21-skill table.

## 0.2.0

The skills now follow the current addon guide of the framework.

New skills:

- `erpforall-reports`: declare a report and its action, write QWeb templates inside the print profile, and print
  business documents on the shared document parts of the `web` addon.
- `erpforall-settings`: make a value configurable instead of hardcoding it, as a Settings entry or a system parameter
  with a default, a floor and a bound; give an addon its own settings page and read the values from code.
- `erpforall-attachments`: store, list, serve and move files that belong to a record from a native addon.
- `erpforall-wasm-addons`: write, build, package and install a light addon as a WebAssembly package, with the limits
  the guide states.

Updated skills:

- `erpforall-chatter`: the history lines the chatter now writes by itself (creation line, tracked field changes), the
  hooks that change them, reporting a change made by SQL, bridge addons that add the chatter to another addon's model,
  and that nothing is declared for the messaging schema.
- `erpforall-views`: kanban, pivot, graph and calendar views, list dashboards, column widths, dashboard cards, the
  list and form views of a one2many's lines, Group By filters, `create`/`edit`/`delete` on a view.
- `erpforall-models-fields`: `bigint`, binary and image fields, the image mixin, company-dependent fields, column
  collation, and which keys model files refuse.
- `erpforall-security`: `company_access` declarations, scoped elevation blocks instead of `sudo`, who may switch
  users, adding a preference to My Preferences.
- `erpforall-create-addon`, `erpforall-addon-tests`, `erpforall-data-files`: initializing a database with or without
  demo data, the manifest `icon`, the `web` dependency of the extra view types, native addons the server binary must
  link, content receipts on upgrade, testing on a neutralized copy, checking access with several users.
- `erpforall-menus-actions`, `erpforall-extend-addon`, `erpforall-for-odoo-developers`,
  `erpforall-client-extensions`: action context defaults, report actions, selection values added by a native
  extension, owner-only columns, shell extension registries, and new rows in the concept map.

The tools are unchanged.

## 0.1.0

First release: twelve skills, `new-addon`, `addon-lint` and `addon-graph`.
