---
name: erpforall-menus-actions
description: Add menus and window actions to an ERPForAll addon - ir.actions.act_window records, view_mode, linking specific views, <menuitem> trees, groups, icons, root menus and settings entries. Use when the user wants an app menu, a menu entry, or an action that opens a model's list or form.
---

# Menus and actions

## Window action + menu

```xml
<record id="book_action" model="ir.actions.act_window">
    <field name="name">Books</field>
    <field name="res_model">sample_library.book</field>
    <field name="view_mode">list,form</field>
</record>
<menuitem id="library_menu" name="Library" groups="base.group_user" sequence="70" web_icon="lucide:library">
    <menuitem id="book_menu" name="Books" action="book_action" sequence="10"/>
</menuitem>
```

- The real addons define an action before the menu that names it; do the same.
- `res_model` must be a model of the registry. `view_mode` is a comma list with **no spaces** and no repeated type (`list,form`); `list, form` and `list,,form` are refused. Without a `name`, the action takes the model's description.
- Optional `path` field: the URL segment, `[a-z][a-z0-9_-]*`, at most 128 bytes, unique across all action types, not starting with `m-` or `action-`, not `new`.
- To pin particular views, add `ir.actions.act_window.view` records (fields `act_window_id`, `view_id`, `view_mode`, `sequence`) and, optionally, `view_id` / `search_view_id` on the action. Example from the Contacts addon:

```xml
<record id="action_contacts" model="ir.actions.act_window">
    <field name="name">Contacts</field>
    <field name="res_model">res.partner</field>
    <field name="view_mode">list,form</field>
    <field name="view_id" ref="base.partner_list"/>
    <field name="search_view_id" ref="base.partner_search"/>
</record>
<record id="action_contacts_list" model="ir.actions.act_window.view">
    <field name="act_window_id" ref="action_contacts"/>
    <field name="view_id" ref="base.partner_list"/>
    <field name="view_mode">list</field>
    <field name="sequence" eval="10"/>
</record>
```

- **Defaults and initial search filters** go in the action's `context`, a literal dictionary of at most 16 `default_<field>` keys (each a text, boolean or integer) and up to 16 `search_default_<name>` keys (`{'default_move_type': 'out_invoice', 'search_default_available': True}`). `search_default_<name>` turns on a named search `<filter>` or `group_by` item (`true`/`1`), or pre-fills a search `<field>` with a string or integer. Refused: expressions (`uid`, `context.get(...)`), lists, negative `default_*` integers or non-existent fields, computed/related/x2many fields for `default_*`, and session keys (`allowed_company_ids`). Dates are `YYYY-MM-DD` text.

## `<menuitem>` rules

- A nested `<menuitem>` takes the enclosing menu as its parent (do not write `parent`); a standalone submenu may use `parent="other_menu_id"` (seen in `acceptance_notes`: `parent="notes_menu"`).
- `web_icon` is for **root** menus only and must match one of:
  - `lucide:<name>`: a bundled Lucide glyph (unknown names fall back to the default glyph with a console diagnostic, and shipped addons fail tests on unknown names);
  - `<addon>,static/<path>.svg` or `.png`: an image published from the addon's `static/` directory under `static_files` in `static/dist/manifest.json` (served with sandboxed SVG CSP and drawn as `<img>`);
  - a `data:image/svg+xml` or `data:image/png` URL of at most 2048 bytes.
  Any other form fails the `ir.ui.menu` write, so a mistyped icon stops install.
- A submenu has either an `action` or child menus, not neither.
- `groups="base.group_user"` limits who sees the menu; `groups="a,-b"` links `a` and unlinks `b`. Limit a Configuration branch with `groups="base.group_system"`.
- `sequence` orders siblings (default 10). The menu name may be left out when it has an action (the action's name is used).
- Menu tree: `ir.ui.menu` records; a menu with children cannot be deleted; loops are refused.

## Other action types

A **method** that returns an action (a stat button, a drill) is checked against a narrower contract than these records: an in-page list is `target` `"current"` with `views` list then form and a literal `domain`, one record is `res_id` with one form view, a dialog is `target` `"new"` with no domain. Shapes and examples: skill `erpforall-wizards-actions`. An on-screen dynamic report opens through an `ir.actions.client` record with tag `reporting.report` (skill `erpforall-dynamic-reports`).

`ir.actions.act_url`, `ir.actions.client`, `ir.actions.server` and `ir.actions.report` exist and share one id space with window actions. Full-screen client actions (`ir.actions.client`) and modal wizard actions (`target="new"`) are covered in the `erpforall-wizards-actions` skill. Server actions (including `code` actions, sandboxed Luau scripts) run with the caller's rights unless an administrator sets `run_as_superuser`; `object_copy` and `webhook` are not available yet. Report actions: skill `erpforall-reports`. To show an addon's own settings page, `acceptance_notes` declares a form on `ir.config.setting` with `<widget name="web.settings" scope_kinds="global,company" app="acceptance_notes"/>` and a window action over it; copy that file's last records rather than inventing the pattern; declaring the settings themselves is in the `erpforall-settings` skill.

## Not covered here

Contextual (binding) actions (`binding_model_id`, `binding_type`), server-action code, the web client's menu loading: see `actions-menus.md`.

## Sources

- docs/addon-guide/actions-menus.md
- docs/addon-guide/data-files.md
- docs/addon-guide/data-only-addon.md
- addons/contacts/views/contacts_views.xml
- addons/sample_library/views/sample_library_views.xml
- addons/acceptance_notes/views/acceptance_notes_views.xml
- addons/account/views/account_invoice_views.xml
- addons/base/src/ir_ui_menu.rs
- addons/web/static/src/client/icons.ts
- addons/web/src/action_result.rs
- addons/reporting/src/client_action.rs
