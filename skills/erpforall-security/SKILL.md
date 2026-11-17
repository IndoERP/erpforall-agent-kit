---
name: erpforall-security
description: Set access control for an ERPForAll addon - security/ir.access.csv rows (permissions and restrictions), res.groups records, field-level groups, record domains with user.id and company_ids, company_access declarations, scoped elevation instead of sudo, user-writable preferences. Use when a model needs access rights, per-user or per-company record rules, a custom group, or code that must read past the user's rights.
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

A search by a user also applies the rules of the related models it goes through (`any` conditions, dotted paths, x2many conditions), and a related model's rule may use `child_of` / `parent_of`.

## Company restriction: `company_access`

A company-scoped model declares once how the user's active companies restrict its records, and the restriction row is generated from it; the registry refuses a concrete company-scoped model without a declaration. Native, on the model:

```rust
#[model(name = "acceptance_notes.note", description = "Note",
        company_access = direct(field = "company_id", branch = "exact", empty = "deny"))]
```

`branch` (`"exact"` or `"ancestor"`) and `empty` (`"deny"` or `"allow"`) have no default. Other forms: `parent(edge = "order_id")` for lines that take their owner's company, `unrestricted(reason = "...")`. In a model file the table is `[model.company_access]` with `direct = { field = "company_id", branch = "exact", empty = "deny" }`, `parent = "..."` or `unrestricted = "..."`. Details and the `escape` modifier: `company-consistency.md`, section 7.

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
- Check access from code with `check_access`, `has_access`, `filtered_access`. Keep business authorization in methods, not in view attributes.
- **Instead of `sudo`**, open a scoped, audited elevation block that names exactly what the code may read or write: `tx.elevated(env, ElevationReason::new("my_addon.reason")?, scope, async |tx, env| { ... })` with an `ElevationScope` of `ScopeItem`s (model and operations). Restrictions, including the company restriction, still apply; the block's environment is valid only inside the body; library code that calls `sudo(true)` fails inside a block. Read `access.md`, "Scoped elevation blocks", before using it.
- `with_user(other)` is admitted only for the `System` principal, for your own user, or with the capability `principal.impersonate`; to ask whether a user is in a group use `tx.user_has_group(&env, user, "module.group")`.

## A preference on My Preferences

A field you add to `res.users` is administrator-only unless marked `user_writeable`. To let users set their own value, add the field with `user_writeable` and inherit the dialog `base.users_preferences_form`, placing the field in its named group `other_preferences` (or `calendar_preferences`), as `mail` does for the notification choice:

```xml
<record id="users_preferences_form_inherit_mail" model="ir.ui.view">
    <field name="name">res.users.preferences.form.inherit.mail</field>
    <field name="model">res.users</field>
    <field name="inherit_id" ref="base.users_preferences_form"/>
    <field name="arch" type="xml">
        <xpath expr="//group[@name='other_preferences']" position="inside">
            <field name="notification_type" widget="radio" string="Notifications" options="{'horizontal': True}"/>
        </xpath>
    </field>
</record>
```

Mark only what is the user's own business. Do not make such a field `required` at the column unless every writer sets it (`mail` uses a default plus a `#[constrains]` check).

## Not covered here

Capabilities, authentication and sessions, the `erp access` report command, multi-company link checks (`check_company`, `company_match`), approval policies (`ir.approval.policy`) and multi-user acceptance testing: see `capabilities.md`, `auth.md`, `company-consistency.md`, `field-access.md`, `security.md`, `access-rules.md`.

## Sources

- docs/addon-guide/security.md
- docs/addon-guide/access.md
- docs/addon-guide/access-rules.md
- docs/addon-guide/field-access.md
- docs/addon-guide/odoo-compatibility.md
- docs/addon-guide/company-consistency.md
- addons/acceptance_notes/security/ir.access.csv
- addons/acceptance_notes/src/models.rs
- addons/mail/views/res_users_views.xml
- addons/mail/src/res_users.rs
- crates/erp-modules/src/model_files.rs
- addons/sample_library/security/ir.access.csv
- addons/uom/security/ir.access.csv
- addons/product/security/product_security.xml
- addons/base/data/bootstrap_groups.xml
