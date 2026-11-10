---
name: erpforall-security
description: Set access control for an ERPForAll addon - security/ir.access.csv rows (permissions and restrictions), res.groups records, field-level groups, record domains with user.id and company_ids. Use when a model needs access rights, per-user or per-company record rules, or a custom group.
---

# Security: access rows, groups, field access

Without an access row nobody but the superuser can read or write a model. Rows live in `security/ir.access.csv` (listed first in the manifest `data`).

```csv
id,name,model_id/id,group_id/id,operation,domain
note_user,Own notes,acceptance_notes.model_acceptance_notes_note,base.group_user,crud,"[('owner_id', '=', user.id)]"
note_admin,Manage notes,acceptance_notes.model_acceptance_notes_note,base.group_system,crud,
note_company,Allowed companies,acceptance_notes.model_acceptance_notes_note,,crud,"[('company_id', 'in', company_ids)]"
```

| Column | Meaning |
|---|---|
| `id` | External id of the row inside the addon. |
| `name` | Label. |
| `model_id/id` | `<addon>.model_<model name with dots as underscores>`: model `sample_library.book` is `sample_library.model_sample_library_book`. (`model_id:id` is also used; in the same addon the module prefix may be left out, as `uom` does.) |
| `group_id/id` | A `res.groups` external id (`base.group_user` internal users, `base.group_system` administrators). **Empty = applies to everyone** (a restriction). |
| `operation` | A non-empty subset of `crud` **in that order**: `c` create, `r` read, `u` update, `d` delete. `w` and out-of-order strings (`rc`) fail loudly. Examples in use: `r`, `ru`, `u`, `crud`. |
| `domain` | Optional record filter as a list of tuples, `[('field', 'op', value)]`; empty = all records. |

How rows combine:
- A row **with a group** is a *permission*: members may do the listed operations on the records its domain matches. Permissions of all the user's groups are OR-ed.
- A row **without a group** is a *restriction*: it narrows everyone's access and restrictions are AND-ed. A restriction never grants anything alone.
- Access domain = `OR(permissions) AND AND(restrictions)`.

## What a `domain` may contain

Compiled once and bound per statement, so only these forms work: literals; `user.id`; `user.partner_id.id` (paths of stored many2one fields ending in `id` or `ids`); `company_ids`, `company_id`; `company_ids + [False]`; today/now (`context_today()`, `datetime.datetime.now()`); sub-queries `('f', 'in', user.env['m'].search([...]).ids)` with a literal domain; `('f', 'access', 'read')`. Prefix operators `'&'`, `'|'`, `'!'` and dotted paths work. Anything else is refused with a message saying what to write instead.

## Groups

Define a group as a record (data file, usually `<erp noupdate="1">`):

```xml
<erp noupdate="1">
  <record id="group_product_manager" model="res.groups">
    <field name="name">Product Administrator</field>
    <field name="implied_ids" eval="[Command.link(ref('base.group_user'))]"/>
    <field name="implied_by_ids" eval="[Command.link(ref('base.group_system'))]"/>
  </record>
</erp>
```

`implied_ids`: membership implies those groups. Reference it from CSV as `<your_addon>.group_product_manager`. List the groups file in `data` before the CSV that uses it (as `uom` and `product` do).

## Field-level access

- Native: `#[field(text, groups = "base.group_system")]`.
- Data-only: `groups = "base.group_system"` in a `[[model.field]]`.
- In a view, `groups="base.group_system"` on a `page` or field hides it for others; it is presentation, not authorization.

## Rules

- Group ids you do not define must come from an addon in `depends`.
- A native model can change its predicate in code with an `#[access_domain]` function (`fn(ctx: &AccessCtx, op: Operation, sup: AccessSuper) -> Result<Domain>`, synchronous, no I/O, no user values: use `PrincipalParam`s such as `PrincipalParam::Uid`). Read `access.md` first.
- Check access from code with `check_access`, `has_access`, `filtered_access`; `sudo(true)` passes every check. Keep business authorization in methods, not in view attributes.

## Not covered here

Capabilities, authentication and sessions, the `erp access` report command, multi-company consistency flags (`company_access`, `check_company`): see `capabilities.md`, `auth.md`, `company-consistency.md`, `field-access.md`.

## Sources

- docs/addon-guide/security.md
- docs/addon-guide/access.md
- docs/addon-guide/access-rules.md
- docs/addon-guide/field-access.md
- docs/addon-guide/odoo-compatibility.md
- addons/acceptance_notes/security/ir.access.csv
- addons/sample_library/security/ir.access.csv
- addons/uom/security/ir.access.csv
- addons/product/security/product_security.xml
- addons/base/data/bootstrap_groups.xml
