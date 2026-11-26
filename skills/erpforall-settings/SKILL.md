---
name: erpforall-settings
description: Make a value of an ERPForAll addon configurable instead of hardcoding it - declare a Settings page entry (SettingDecl, global or company scope) or a technical system parameter (ParameterDecl) with a default, a floor and a hard bound, give the addon its own settings page, contribute settings to another app, read the values from Rust code. Use when an addon needs a limit, interval, switch, default choice or credential that an administrator may change.
---

# Settings and system parameters

A value an administrator may want to change (a limit, a size, an interval, a switch, a default choice) is not a
constant in code. Declare it, with a default and, for numbers, a floor and a hard bound; every write outside them
is refused with a sentence that names the key (for example `account.journal_code_max_length takes a whole number
from 1 to 32.`). Declarations live in a **native** addon (`erp_sdk::settings`); the WASM mapping is not supported
yet, and the guide does not describe declarations for data-only addons (not covered here).

## 1. Choose where the value lives

| Value | Declare as | Shown in |
|---|---|---|
| A business choice an administrator makes | `SettingDecl`, scope `ScopeKind::Global` (database) or `ScopeKind::Company` (one value per company, no fallback to the global value) | the Settings page |
| A technical value (limit, bound, timeout, size, batch, retry, interval) or a credential | `ParameterDecl` | Technical, System Parameters (`ir.config_parameter`) |
| A value per record that differs per company | a company-dependent field (`company_dependent = true`, see `company-dependent-fields.md`) | the record's form |

One key is either a setting or a parameter, never both. Keys start with your addon's name (`my_addon.enabled`;
nested segments such as `my_addon.import.batch` are allowed) and are unique across all addons.

## 2. Declare a setting

```rust
// addons/acceptance_notes/src/lib.rs
fn settings() -> erp_sdk::Result<Vec<erp_sdk::settings::SettingDecl>> {
    use erp_sdk::settings::{ScopeKind, SettingDecl};
    Ok(vec![
        SettingDecl::boolean("acceptance_notes.enabled", "Enable shared notes", ScopeKind::Global, true)?
            .access(&["base.group_system"], &["base.group_system"])?,
    ])
}
erp_sdk::setting_declarations!(settings);
```

- Typed constructors, no coercion: `boolean(key, label, scope, default)`, `string(key, label, scope, default,
  max_bytes)` (1 to 65,536), `integer(key, label, scope, default, (floor, bound))`, `float(...)` (finite, inclusive
  bounds), `selection(key, label, scope, default, &[("value", "Label"), ...])`.
- `.access(read_groups, write_groups)`: the groups must resolve and come from your dependency closure.
- `.help(text)` adds plain-text help and a **Use default** control; say the default and the allowed range in it,
  as `addons/base/src/attachments/settings.rs` does.
- `.block("Taxes")` puts it in a titled section (default `"General"`); `.sequence(n)` orders blocks and rows.
- Values that must agree with each other: `erp_sdk::setting_groups!(factory)` returning
  `SettingGroupDecl::new(identity, &[member keys], validator)`; the validator is a pure, synchronous
  `fn(&BTreeMap<String, Value>) -> Result<()>` that returns an error naming the setting.
- Read-only rows (a count, a link to a list) are `PanelItemDecl::info`, `action_link` or `menu_link`, registered
  with `erp_sdk::settings_panel_items!(items, resolve)`; they are not settings (read `settings.md` first).

### Toggle rows: install an addon, turn on a feature group

The same `settings_panel_items!` list takes two toggle rows, as `purchase` declares them:

```rust
PanelItemDecl::group_toggle("purchase.group_warning_purchase", "Warnings", crate::WARNING_GROUP)?
    .block("Orders")?.sequence(100).access(&["base.group_system"])
PanelItemDecl::module_toggle("purchase.module_stock_dropshipping", "Direct supplier delivery", "stock_dropshipping")?
    .block("Logistics")?.sequence(200).access(&["base.group_system"])
```

- **Module toggle**: installs or uninstalls the named addon. Not the declaring addon or one it depends on; a name the
  addon directory does not know is refused when the page is published.
- **Group toggle**: on, `base.group_user` implies the group; off removes that implication. The page calls
  `ir.config.setting` `erp_toggle_group(key, enabled)` (Settings administrators only). The group must belong to an
  addon in your dependencies, must not be `base.group_user`, `base.group_portal` or `base.group_public`, and must be
  a **light group**: extend `res.groups` and append its external id in `_get_light_group_xmlids`
  (`addons/stock/src/res_groups.rs`), then reclassify from data with a `data_callable` method called by
  `<function model="res.groups" name="_purchase_reclassify_light_groups"/>`
  (`addons/purchase/security/purchase_group_classification.xml`).
- Both toggles are readable only by `base.group_system`: `.access(&["base.group_system"])`.

### Act when a setting is saved

To change records when a value changes, extend `ir.config.setting` and override `_apply_value_changes(this, tx,
company: Option<i64>, changes: ValueMap, sup: Super)`; act on your keys in `changes`, then call
`sup.call(tx, this.as_records(), (company, changes))`. `addons/stock/src/settings.rs` turns the replenish-on-order
route on or off this way, refusing a call without a company scope.

## 3. Your addon's own settings page

Settings group by key prefix. To give the addon a Configuration > Settings entry, ship a service form that opens the
shared page on your app (exactly as `acceptance_notes` does):

```xml
<record id="settings_form" model="ir.ui.view">
    <field name="name">acceptance_notes.settings</field>
    <field name="model">ir.config.setting</field>
    <field name="arch" type="xml">
        <form record_mode="service">
            <widget name="web.settings" scope_kinds="global,company" app="acceptance_notes"/>
        </form>
    </field>
</record>
<record id="settings_action" model="ir.actions.act_window">
    <field name="name">Settings</field>
    <field name="res_model">ir.config.setting</field>
    <field name="view_mode">form</field>
    <field name="view_id" ref="settings_form"/>
</record>
<menuitem id="notes_config_menu" name="Configuration" parent="notes_menu" groups="base.group_system" sequence="90"/>
<menuitem id="notes_settings_menu" name="Settings" parent="notes_config_menu" action="settings_action" groups="base.group_system" sequence="10"/>
```

`app` must be an addon technical name, or the view is refused at load. To put a setting on **another** app's page
instead (an integration addon), keep your own prefix and add `.app("stock")?`; that app must be in your transitive
dependencies and installed.

## 4. Declare a system parameter

```rust
use erp_sdk::settings::ParameterDecl;
fn parameters() -> erp_sdk::Result<Vec<ParameterDecl>> {
    Ok(vec![
        ParameterDecl::integer("my_addon.import_batch", "Import batch", 500, (1, 10_000))?,
        ParameterDecl::string("my_addon.partner_token", "Partner API token", "", 256)?.secret(),
    ])
}
erp_sdk::system_parameters!(parameters); // or system_parameters!(parameters, groups)
```

- Constructors: `boolean`, `string` (bound 1 to 65,536 bytes), `integer`, `float`, `selection`; extras
  `.validator(fn)`, `.secret()`, `.without_default_row()`.
- Every number needs a floor of at least 1: zero never means "unlimited". When 0 or a fraction has a real meaning,
  use `integer_floor_below_one` / `float_floor_below_one`, whose last argument states the reason.
- The framework creates a row holding the default at install (never overwrites one); do not also ship a data record
  for the key. Stored rows are checked at install, upgrade and start; every write is checked and audited; a declared
  row cannot be deleted or renamed; a secret is hidden outside superuser mode and replaced with
  `ir.config_parameter.erp_replace_secret(key, value)`.

## 5. Read values from code

- Parameter: `erp_sdk::params::get_int(tx, &crate::ADDON, "my_addon.import_batch").await?` (also `get_float`,
  `get_bool`, `get_str`). Pass `&crate::ADDON` itself. It returns the default for a missing or empty row and fails
  with `Stored parameter <key> is invalid.` for a bad one; it never falls back silently.
- Setting: `erp_addon_base::ir_config_setting::read_values(env, tx, scope, keys)` inside your transaction
  (`addons/account/src/tax/settings.rs` reads with `SettingsScope::Global {}` and a `sudo(true)` environment).
  Over RPC: `ir.config.setting.erp_describe(scope)`, `erp_read_values(scope, keys)`,
  `erp_write_values(scope, expected_revision, changes)`; a stale revision is refused, so reload and retry.
- There is no node-local cache to invalidate. Never write the value tables with SQL.
- **Built-in helpers:** Addons that route approvals call `erp_addon_base::approval_settings::max_approvers(tx).await?` to
  read `base.approval_max_approvers` without requiring generic Settings access on the caller. An addon that contributes
  a database appearance declares a global selection setting `<addon>.appearance` on `ir.config.setting` with
  `"default"` and its theme choice (`web-client.md`, `addons/theme_office_blue/src/lib.rs`).

## Not covered here

Moving an existing setting to a parameter (a `post` migration; see "Moving a Settings value to a parameter" in
`settings.md` and `addons/stock/src/migrations.rs`), the browser navigation of link rows, the System Parameters
screen showing a key's label, bounds, reset or secret replacement (the guide says it does not yet), declarations
from data-only or WASM addons.

## Sources

- docs/addon-guide/settings.md
- docs/addon-guide/company-dependent-fields.md
- docs/addon-guide/web-client.md
- addons/acceptance_notes/src/lib.rs
- addons/acceptance_notes/views/acceptance_notes_views.xml
- addons/account/src/tax/settings.rs
- addons/base/src/approval_settings.rs
- addons/base/src/attachments/settings.rs
- addons/base/src/system_parameters.rs
- addons/sales_team/src/team.rs
- addons/theme_office_blue/src/lib.rs
- crates/erp-registry/src/settings.rs
- addons/stock/src/migrations.rs
- addons/stock/src/settings.rs
- addons/stock/src/res_groups.rs
- addons/purchase/src/settings.rs
- addons/purchase/security/purchase_group_classification.xml
- docs/development.md
