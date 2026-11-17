# Changelog

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
