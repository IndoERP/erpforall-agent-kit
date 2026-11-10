---
name: erpforall-for-odoo-developers
description: Map Odoo concepts to ERPForAll - manifest, models, inheritance, api decorators, access rows and rules, views, data files, server actions, RPC - and the places where ERPForAll deliberately differs or fails loudly. Use when the user knows Odoo and asks how to do something the ERPForAll way.
---

# ERPForAll for Odoo developers

ERPForAll is an ERP framework in Rust that keeps the Odoo mental model (addons that declare and extend models, views, menus, actions, security) but replaces runtime patching with compile-time declarations and strict, loud errors. Data files, views and CSV rows read much like Odoo's.

## Concept map

| Odoo | ERPForAll |
|---|---|
| `__manifest__.py` | `manifest.toml` (plus `Cargo.toml` for native addons). Strict: unknown keys are refused unless under `[extra]`. |
| `models.Model`, `_name` | `#[model(name = "...")]` struct (native) or `[[model]]` in `models/*.toml` (data-only). |
| `_inherit` (extend) | `#[extend(Target)]` struct, or `[[model]] extend = "..."` in TOML. |
| `_inherits` | `#[model(inherits = [("model", "field")])]`. |
| Mixins such as `mail.thread` | `inherit = [MailThread]` (native) / `inherit = ["mail.thread"]` (TOML). |
| `fields.Char`, `Many2one`, ... | `#[field(char)]`, `#[field(many2one, comodel = "...")]`; TOML `type = "char"`. |
| `@api.depends` | `#[field(..., compute = "_m")]` + `#[compute(depends = [...])]`. Data-only models only get `related`. |
| `@api.onchange` | `#[onchange("field")]` returning `OnchangeResult`. |
| `@api.constrains` | `#[constrains("field")]` returning `Result<()>`. |
| `super().method()` | `#[method(override)]` with a `sup: Super` argument; overrides run in a deterministic `(depth, name)` order. |
| `ir.model.access.csv` + `ir.rule` | One `security/ir.access.csv` of `ir.access` rows: rows with a group are permissions (OR-ed), rows without a group are restrictions (AND-ed). Operation letters are `crud` in that order (`u`, not `w`). |
| Field `groups="..."` | `groups = "..."` on the field; enforced on every ORM path. |
| XML views, xpath inheritance | Same idea, root element `<erp>`, `<list>` for lists, a strict xpath subset, no selection by translated attributes. |
| XML/CSV data files, `noupdate` | Same, with stricter reading: only documented elements and attributes, file and line in errors. |
| Server actions with `state='code'` | Sandboxed Luau scripts; all server actions run with the caller's rights unless an administrator sets `run_as_superuser`. |
| `call_kw` JSON-RPC | JSON-2: `POST /json/2/<model>/<method>` with explicit `#[rpc(effect = ...)]` methods; private by default. |
| `wkhtmltopdf` reports | Native report engine (details outside this skill). |

## Differences that fail loudly

- Manifest: unknown key, wrong type or bad version stops startup with an error.
- Data files: a typo in an element or attribute aborts loading; booleans accept only `1/0`, `true/false`, `yes/no`, `on/off`; comments inside text values are rejected; `ref` to a missing id fails the load.
- Views: locating a node by a translated attribute is rejected; a view naming a missing field fails the install.
- RPC: methods are private unless exposed with `#[rpc]`; an `effect = read` method that writes fails.
- Install, upgrade and uninstall are one PostgreSQL transaction, not one per module.
- Access: company membership is validated under every elevation; companies and `user` values in rule domains are compiled into SQL parameters, so a rule can only use the documented forms (`user.id`, `company_ids`, user paths, literal sub-searches).
- Company checks are on by default for company-scoped many2one/many2many fields (opt out with `check_company = false`).
- Result rows: reading a missing key is an error, not `None`.
- `view_mode` must not contain spaces or repeats.

## How to work

1. For each Odoo habit, find the row above, then read the linked skill (`erpforall-create-addon`, `erpforall-models-fields`, `erpforall-views`, `erpforall-security`, ...).
2. Do not port Python code line by line: re-express the behaviour with the declarations above.
3. Run `erpforall-addon-lint` early; it catches the loud-failure cases statically.

## Not covered here

A list of every Odoo model or view the framework implements; the platform's roadmap and slice status (the compatibility page tracks it and changes). Read `docs/addon-guide/odoo-compatibility.md` in the framework repository for the current table.

## Sources

- docs/addon-guide/odoo-compatibility.md
- docs/addon-guide/security.md
- docs/addon-guide/actions-menus.md
- docs/addon-guide/data-files.md
- docs/addon-guide/views.md
- docs/addon-guide/models.md
