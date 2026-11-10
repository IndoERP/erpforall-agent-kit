---
name: erpforall-views
description: Write ERPForAll views - list, form and search XML in ir.ui.view records under the <erp> root, header buttons, groups and notebooks, field widgets, and extending another addon's view with xpath/position inheritance. Use when adding or changing a screen, a column, a filter or a form layout.
---

# Views

Views are `<record model="ir.ui.view">` entries in a data file (listed in the manifest `data`). The file root is **`<erp>`** (legacy `<odoo>`, `<openerp>`, `<data>` are still read; write `<erp>`).

## List, form, search

```xml
<?xml version="1.0" encoding="utf-8"?>
<erp>
    <record id="book_list" model="ir.ui.view">
        <field name="name">sample_library.book.list</field>
        <field name="model">sample_library.book</field>
        <field name="arch" type="xml">
            <list string="Books">
                <field name="title"/>
                <field name="author_id"/>
                <field name="rating" widget="priority"/>
            </list>
        </field>
    </record>
    <record id="book_form" model="ir.ui.view">
        <field name="name">sample_library.book.form</field>
        <field name="model">sample_library.book</field>
        <field name="arch" type="xml">
            <form string="Book">
                <sheet>
                    <div class="oe_title"><h1><field name="title"/></h1></div>
                    <group>
                        <group string="Book"><field name="author_id"/><field name="isbn"/></group>
                        <group string="Catalogue"><field name="genre_ids" widget="many2many_tags"/></group>
                    </group>
                    <notebook>
                        <page name="summary" string="Summary"><field name="summary"/></page>
                        <page name="loans" string="Loans" groups="base.group_user"><field name="loan_ids"/></page>
                    </notebook>
                </sheet>
                <aside>
                    <group string="Record information">
                        <field name="create_uid" readonly="1"/><field name="create_date" readonly="1"/>
                        <field name="write_uid" readonly="1"/><field name="write_date" readonly="1"/>
                    </group>
                </aside>
            </form>
        </field>
    </record>
    <record id="book_search" model="ir.ui.view">
        <field name="name">sample_library.book.search</field>
        <field name="model">sample_library.book</field>
        <field name="arch" type="xml">
            <search>
                <field name="title"/>
                <filter name="available" string="Available" domain="[('available', '=', True)]"/>
                <separator/>
                <filter name="excellent" string="Excellent" domain="[('rating', '=', '3')]"/>
            </search>
        </field>
    </record>
</erp>
```

- A form header with a status bar, as in the loan form of `sample_library`: `<header><field name="state" widget="statusbar"/></header>` before `<sheet>`.
- Use `<list>` (the guide's addons do not use `<tree>`). Every `<field name>` must be a field of the view's model; a view that names a missing field fails the install.
- Form layout: `sheet` directly under `form`; `group` takes optional `name`/`string`; a `notebook` holds only `page` elements (a page needs `name` or `string`); at most one `aside` and one `<chatter/>`, directly in the form (see `erpforall-chatter`). Odd track counts, arbitrary HTML and dynamic layout modifiers are refused.
- Modifier attributes seen in the guide: `invisible`, `readonly`, `required` (expressions such as `phase != 'draft'`), and `groups` on pages and fields.
- Widgets used by the real addons (all via `widget="..."`): `email`, `phone`, `url`, `many2many_tags`, `priority`, `badge`, `percentage`, `color`, `color_picker`, `radio`, `statusbar`, `boolean_toggle`, `boolean_favorite`, `CopyClipboardChar`, `CopyClipboardURL`, `CopyClipboardText`, `statinfo`. An unknown widget or an incompatible field kind fails explicitly.
- Header buttons: `<button name="submit" type="object" string="Submit" class="btn-primary" confirm="Submit this record?" invisible="phase != 'draft'"/>`. `name` must be an exposed model method; `invisible`/`groups` only hide the button and do **not** authorize the call, so keep the check in the method.
- Stat buttons live in `<div name="button_box" class="oe_button_box">` as `type="object"` buttons with a `<field widget="statinfo">`.

## Extend another addon's view (never edit it)

```xml
<record id="partner_form_extra" model="ir.ui.view">
    <field name="name">res.partner.form.extra</field>
    <field name="model">res.partner</field>
    <field name="inherit_id" ref="base.partner_form"/>
    <field name="arch" type="xml">
        <xpath expr="//field[@name='phone']" position="after">
            <field name="nickname"/>  <!-- a field your addon added with extend = "res.partner" -->
        </xpath>
    </field>
</record>
```

- Positions: `inside` (default), `after`, `before`, `replace` (empty body removes the node; `mode="inner"` keeps the tag), `attributes`, `move`.
- Shorthand locator: `<field name="phone" position="after">...</field>`.
- Change attributes: `<field name="name" position="attributes"><attribute name="required">1</attribute></field>`; list attributes take `add=`/`remove=`/`separator=`; expression attributes combine with `separator="or"` or `"and"`.
- xpath subset: `//field[@name='x']`, `/form/sheet`, `[n]`, `[text() = '..']`, `hasclass('c')`, `not(...)`, `and`/`or`. Prefer short anchored expressions.
- **Never select on translated attributes** (`string`, `help`, `placeholder`, `confirm`, `title`): rejected. Select by `@name`.
- Moving the root, or moving a node into itself, is refused. Extensions apply in `(priority, id)` order.
- Reference another addon's view by external id: `ref="base.partner_form"`; that addon must be in `depends`.

## Not covered here

Kanban, calendar, pivot, graph, activity and other view types; `get_views` wire format; custom view types. The guide's `views.md` describes the registry; this skill only covers list, form and search.

## Sources

- docs/addon-guide/views.md
- docs/addon-guide/human-form-layout.md
- docs/addon-guide/data-files.md
- docs/addon-guide/two-addon-tutorial.md
- addons/sample_library/views/sample_library_views.xml
- addons/acceptance_notes/views/acceptance_notes_views.xml
- addons/contacts/views/contacts_views.xml
- addons/base/data/partner_views.xml
