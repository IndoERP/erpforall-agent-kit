# Skill drift, November 2026

Compares the kit's skills, pinned to public framework revision `2b32cce91dac` (2026-11-23), with public `main` at
`7e42b120663d` (2026-11-26): 340+ commits, mostly new `account`, `stock`, `sale`, `purchase`, `hr`, `reporting`,
`account_reporting` and `web` code. Everything below was read at `7e42b120` with `git show` / `git grep`. The
private addon guide (`docs/addon-guide/`) had no commits since the kit's `SOURCE_REVISION`, so it does not describe any
of this; the new material is in the code and in the public `docs/development.md` and `docs/deployment.md`.

The inventory was written during this update, alongside the first skill edits, not strictly before them.

Legend: **missing** = an addon author can do it and the skill does not say; **wrong** = the skill says something the
code no longer does; **none** = no drift found.

## New skill needed

| Topic | Evidence | Action |
|---|---|---|
| On-screen dynamic reports (report engine) | `addons/reporting/src/{models,provider,line,options,definition,formula,functions,runtime,settings,client_action}.rs`; data reports in `addons/account_reporting/data/*.xml`, `addons/sale/data/sale_report_data.xml`, `addons/reporting/data/reporting_data.xml`; native providers in `addons/account_reporting/src/*.rs`, `addons/sale/src/report.rs`, `addons/purchase/src/report.rs`, `addons/stock/src/position_report.rs`; native functions in `addons/stock/src/report_net.rs`, `addons/stock_account/src/report_value.rs` | new `erpforall-dynamic-reports` |

## Per skill

### erpforall-menus-actions
- missing: a method's window result has its own, narrower contract (in-page list, one record, dialog); pointer to `erpforall-wizards-actions`.
- missing: opening a dynamic report through an `ir.actions.client` with tag `reporting.report`.

### erpforall-wizards-actions
- missing: `target: "current"` results (`addons/web/src/action_result.rs`, `current_window`): a list is `views` list then optionally form with a required literal `domain`; one record is `res_id` with exactly one form view and no domain; context admits `default_*`, `search_default_*`, `active_test`, `create`. Used by HR and purchase stat buttons (`addons/hr/src/employee.rs`, `action_open_versions`) and report drills.
- missing: a dialog (`target: "new"`) takes no `domain`; a window result without `target` is refused.

### erpforall-migrations
- missing: changing shipped `noupdate` records on upgrade only while they still hold the shipped value, skipping records an administrator deleted, deleting by external id and cleaning dangling `ir_model_data`, failing by name when a kept change no longer fits (`addons/account_reporting/src/migrations.rs`).
- missing: upgrade tests from predecessor fixtures (`crates/erp-cli/tests/fixtures/account_reporting_previous/`, `crates/erp-cli/tests/account_off_balance_guard.rs`).

### erpforall-security
- missing: a model-level `check_access` on an empty recordset followed by raw SQL skips record rules and field groups; read as the caller through the ORM (commits `dd5ec582`, `fcc28508`; `addons/sale/src/report.rs`, `addons/account_reporting/src/aged_partner.rs`).

### erpforall-settings
- missing: `PanelItemDecl::module_toggle` and `PanelItemDecl::group_toggle` rows, light groups (`_get_light_group_xmlids`), `erp_toggle_group` (`addons/purchase/src/settings.rs`, `addons/stock/src/settings_panel.rs`, `addons/stock/src/res_groups.rs`, `docs/development.md`).
- missing: reacting to a saved value by overriding `_apply_value_changes` (`addons/stock/src/settings.rs`).
- not added: `erp_addon_base::warning_text` (`base.warning_message_max_chars`), a helper for one base feature.
- wrong: none.

### erpforall-models-fields
- missing: `#[field(char|text, encrypted = true)]` and its limits (`crates/erp-macros/src/model.rs`, `crates/erp-registry/src/compose.rs`, `docs/deployment.md`). No shipped addon uses it yet.
- missing: `Error::with_fields([...])` to place a refusal on fields (`crates/erp-fields/src/error.rs`).
- not added: `ir.field.access` administrator overrides of field groups (administrator feature; `addons/base/src/ir_field_access.rs`).

### erpforall-data-files
- missing (examples only; the loader did not change): `Command.set` in `eval`, `ref()` inside a `search` domain, a `<function name="write">` with `<value>` arguments to close a circular reference (`addons/hr/demo/hr_demo.xml`, `addons/purchase/demo/purchase_demo.xml`).

### erpforall-create-addon, erpforall-extend-addon, erpforall-orm-scale
- none found in what they state. New `erp_sdk` surface (`env.request().client_address()`, `tx.idempotency_key()`, `erp_sdk::net::IpNetwork`) is not added: no shipped addon uses it, so how an author is meant to use it is not established.

### erpforall-views, erpforall-client-extensions
- wrong (views): "Not covered here" listed activity views as unavailable; `<activity>` exists (`addons/web/src/h18_activity.rs`, `addons/hr/views/hr_employee_views.xml`).
- missing (views): `<hierarchy>` view and its root attributes (`addons/web/src/h18_hierarchy.rs`, `addons/hr/views/hr_department_views.xml`); `<searchpanel>` sidebar now drawn in list, kanban, pivot, graph, hierarchy and activity (`addons/web/static/src/client/search-panel.ts`); badge `tone_*` options (`crates/erp-views/src/wire.rs`); `invisible` on `<page>` and `web_ribbon` (`addons/web/src/h18_lower.rs`); widgets `progressbar` and `many2one_avatar` (`addons/web/src/lib.rs`); New/Edit/Delete narrowed to the caller's rights (`addons/web/src/view_rights.rs`); stat buttons returning in-page results.
- missing (views): the list root and list `<field>` allow-lists (no `optional`, `decoration-*`, `sum`, `column_invisible`).
- not added (views): kanban card accent through an invisible `color` field (marked as a shortcut in `kanban.ts`); the longer widget table in `fields.ts` (most entries existed at the pin and no shipped view of the sweep used them).
- missing (client): `render(env)` widgets without templates (`addons/hr/static/src/client.ts`); `ShellNavigation` (`navigate`, `openAction`); `t()` / `registerTranslations` / `extract-client-strings.mjs`; `registerRefusedActionPage` (`docs/development.md`).
- not added (client): saved favourites and list export/import (no author hook found); `brand.json` / `login.css` brand files (accepted by `addons/web/src/assets/assembly.rs`, no addon ships them).
- Note: `binary-field.ts`, `button-prompt.ts`, `edit_mode`, button `prompt` and `onRecordEvent` already in the skills are absent at the public pin `2b32cce9` but present at `7e42b120`; the 0.3.0 skills were written from the private tree, which was ahead. They match the code now.

### erpforall-addon-tests, erpforall-jobs, erpforall-chatter, erpforall-attachments, erpforall-reports, erpforall-review
- missing (addon-tests): domain suite crate layout and `TemplateDb::clone_or_init` (`crates/erp-suite-hr/Cargo.toml`, `crates/erp-suite-hr/tests/hr_actions.rs`); a policy ORM to act as a user (`crates/erp-suite-sale/tests/support/report_access.rs`); the 16 MiB stack runner; `scripts/check.sh` `--affected [BASE]` default, `--committed-only`, `--affected` with `-p` refused.
- not added (addon-tests): the upgrade identity procedure (`identity-enroll`, `--identity-previous`); `docs/deployment.md` names the commands but not the steps.
- missing (jobs): recurring jobs through `JobKindDecl::schedule` with `Schedule::daily_at`, `every`, `every_from` (`docs/development.md`, `crates/erp-orm/src/jobs/schedule.rs`, `crates/erp-test-models/tests/jobs_schedule.rs`).
- missing (review): DCO check `scripts/check-dco.py BASE HEAD` and `git rebase --signoff`; layer rule 8 for suite crates (`scripts/check-layers.py`); report providers read as the caller; secrets as encrypted fields.
- not added (attachments): `Uploader::create` is used only by the CLI report print path, not by an addon.
- not added (reports): the reports' own testing helpers; dynamic reports are the new skill.
- none (chatter, reports): no change an addon author needs; the HR chatter use matches the skill.

### erpforall-for-odoo-developers, erpforall-knowledge-graph, erpforall-wasm-addons
- not reviewed in this update; only their cited paths were checked (`scripts/check.py --public-source`).
