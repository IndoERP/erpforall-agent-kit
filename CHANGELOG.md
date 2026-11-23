# Changelog

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
