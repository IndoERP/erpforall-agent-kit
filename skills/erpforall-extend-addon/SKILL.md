---
name: erpforall-extend-addon
description: Extend an existing ERPForAll addon from a new addon - add fields to someone else's model, add a column or field to their form, add access rows, without editing the original. Use for requests like "add a field to the contact form" or "customize the product addon".
---

# Extend an existing addon (without editing it)

Never edit another addon's files. Make a new addon that depends on it and contributes three things.

## 1. Fields on the existing model

Data-only (`models/10_extra.toml`):

```toml
[[model]]
extend = "res.partner"

[[model.field]]
name = "nickname"
type = "char"
string = "Nickname"
```

Native: `#[extend(Book)] pub struct BookIsbn { #[field(char, size = 13)] pub isbn: Option<Arc<str>>, }` in a crate that depends on the owner's crate; override methods with `#[method(override)]` and `sup: Super`. With `extend`, the model keeps the kind (abstract, transient) of the model it extends. Redefining a field merges attributes.

Fields added to a model get columns at install and upgrade. A required field needs a default when the table already has rows, or the schema update stops and changes nothing.

## 2. A view that inherits

```xml
<record id="partner_form_nickname" model="ir.ui.view">
    <field name="name">res.partner.form.nickname</field>
    <field name="model">res.partner</field>
    <field name="inherit_id" ref="base.partner_form"/>
    <field name="arch" type="xml">
        <xpath expr="//field[@name='phone']" position="after">
            <field name="nickname"/>
        </xpath>
    </field>
</record>
```

Find the parent view's external id in the owner addon's data files (for contacts, `base.partner_list`, `base.partner_form`, `base.partner_search` live in `addons/base/data/partner_views.xml`). Select by `@name`, never by a translated attribute (`string`, `help`, `placeholder`, `confirm`, `title`). A view that names a field the model lacks fails the install.

## 3. Manifest and access

```toml
name = "Partner Nickname"
version = "1.0.0"
license = "MIT OR Apache-2.0"
depends = ["base"]
data = ["views/partner_nickname_views.xml"]
```

Extending a model you do not own needs no new access rows for the new fields unless you restrict them (`groups = "..."` on the field). A new model of your own needs rows in `security/ir.access.csv` (see `erpforall-security`). `depends` must name every addon whose models, views or ids you use, and an addon that overrides another must depend on it.

Overrides run newest first in load order (dependency depth, then name); several addons can extend the same model and method independently.

## Check

`erpforall-addon-lint addons/partner_nickname --addons-path addons` then install on a throwaway database.

## Not covered here

Adding values to an existing selection with `selection_add` and `ondelete` policies beyond the TOML keys, extending a table that already holds many rows (`models.md`, "Extending a table that already holds many rows"), custom `x_` fields created at runtime for one database (`cross-addon-extension.md`).

## Sources

- docs/addon-guide/cross-addon-extension.md
- docs/addon-guide/data-only-addon.md
- docs/addon-guide/views.md
- docs/addon-guide/models.md
- docs/addon-guide/two-addon-tutorial.md
- addons/base/data/partner_views.xml
- addons/contacts/views/contacts_views.xml
