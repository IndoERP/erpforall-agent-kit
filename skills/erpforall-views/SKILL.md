---
name: erpforall-views
description: Write ERPForAll views - list, form and search XML in ir.ui.view records under the <erp> root, header buttons, groups and notebooks, field widgets, one2many line views, list dashboards and column widths, kanban, pivot, graph and calendar views, dashboard cards, and extending another addon's view with xpath/position inheritance. Use when adding or changing a screen, a column, a filter, a form layout or a board.
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
- Widgets used by the real addons (all via `widget="..."`): `email`, `phone`, `url`, `binary`, `image`, `many2many_tags`, `priority`, `badge`, `percentage`, `color`, `color_picker`, `radio`, `statusbar`, `boolean_toggle`, `boolean_favorite`, `CopyClipboardChar`, `CopyClipboardURL`, `CopyClipboardText`, `statinfo`. An unknown widget or an incompatible field kind fails explicitly.
- **Binary fields (`widget="binary"`):** A `binary` field defaults to `widget="binary"` in a form or list (showing the file name, size and Download, plus Upload/Replace and Clear when editable). `filename="document_name"` (or `options="{'filename': 'document_name'}"`, not both) names a `char` field on the same model holding the file's name so Upload updates both; `options="{'accepted_file_extensions': '.pdf,image/*'}"` hints the file chooser (the server stays the authority). Use `widget="image"` for pictures.
- **Read-first forms:** `<form edit_mode="read">` opens a saved record read-first with an Edit button (or the `E` key outside a field); a successful Save or a Discard returns to read mode, a failed save stays editable with its errors, and a new record opens editable. It cannot be combined with `edit="0"` or `record_mode="service"`.
- Header buttons: `<button name="submit" type="object" string="Submit" class="btn-primary" confirm="Submit this record?" invisible="phase != 'draft'"/>`. `name` must be an exposed model method; `invisible`/`groups` only hide the button and do **not** authorize the call, so keep the check in the method.
- **Object button prompts:** Instead of a one-field wizard, an `object` button can ask for one short answer before calling the method:
  ```xml
  <button name="action_refuse" type="object" string="Refuse"
          prompt="text" prompt-label="Reason" prompt-required="1" prompt-max="500"/>
  <button name="action_run" type="object" string="Run" prompt="date" prompt-label="Run for date"/>
  <button name="action_close" type="object" string="Close"
          prompt="selection" prompt-label="Outcome" prompt-options="won:Won,lost:Lost"/>
  ```
  `prompt-label` is required; `prompt-max` (1 to 4096) applies to `text`; `prompt-options` (`value:Label` entries) is required for `selection`; `prompt-required="1"` makes the answer required. A prompt cannot combine with `confirm`. The answer reaches the method as the keyword argument `prompt_value` (`String` when required, `Option<String>` when optional); validate it on the server too.
- Stat buttons live in `<div name="button_box" class="oe_button_box">` as `type="object"` buttons with a `<field widget="statinfo">`.
- `create="0"`, `edit="0"`, `delete="0"` on a `<list>` or `<form>` root hide New, make the form read-only, or remove Delete.
- `options="{'enable_formatting': False}"` on an integer or float field (a year, a sequence number) drops the thousands separator. An `html` field uses `widget="html"` (or no widget).
- **A one2many's lines.** A one2many shows its lines with the comodel's default list (lowest `priority`) and edits a line in the comodel's default form; an inline `<list>` or `<form>` inside the `<field>` is refused ("Field nodes cannot contain children."). When two fields of one form need different line views, name them in a constant `context` with qualified view ids of the comodel (from `account`'s invoice form):
  ```xml
  <field name="invoice_line_ids"
         context="{'list_view_ref': 'account.view_invoice_line_list', 'form_view_ref': 'account.view_invoice_line_form'}"/>
  ```
  A name that does not resolve is refused by the server.
- **Search views (`<search>`), filters and `search_default_*`:**
  - Consecutive `<filter name="..." string="..." domain="[...]"/>` nodes share an OR group; `<separator/>`, `<field>`, or `<group>` starts the next group (groups are AND-ed).
  - `<filter name="..." string="..." context="{'group_by': 'field'}"/>` (boolean, char, integer, selection or many2one, stored and readable; temporal fields also support `field:month`, `day`, `week`, `quarter`, `year`) populates the Group By menu.
  - `<field name="..." filter_domain="[('name', 'ilike', self)]"/>` declares a quick-search field.
  - An action's `context` can preselect search items with `search_default_<name>` (`true`/`1` for a `<filter>` or `group_by` item; a string or integer for a search `<field>`).

## List extras

```xml
<list string="Books">
    <dashboard>
        <count name="available" string="Available books" filter="available" color="success"/>
        <count name="unavailable" string="Unavailable books" domain="[('available', '=', False)]"/>
        <kpi name="pages_added" string="Pages added" field="pages" aggregate="sum" date_field="create_date"/>
    </dashboard>
    <field name="title" width="[200px]"/>
    <field name="pages"/>
</list>
```

- `<dashboard>` (one, directly under the list root, addon depends on `web`): a `count` has exactly one `domain` or `filter` (a filter of the action's search view) and an optional `color` (`info`, `success`, `warning`, `danger`); a `kpi` names a stored integer or float `field`, an `aggregate` (`sum`, `avg`, `min`, `max`) and a stored date or datetime `date_field`. Item names are unique letters, digits and underscores. Unknown attributes are refused; reads use the caller's access rights.
- `width` on a list `<field>`: `"60px"` exact, `"[200px]"` at least, `"[100px,400px]"` between; 1 to 2000 px. Anything else, or `width` outside a list, refuses the view.

## Kanban, pivot, graph, calendar

Each is a view type owned by `web`: the addon's manifest lists `web` in `depends`, and the action lists the type in `view_mode` (`sample_library`'s books use `list,kanban,form,pivot,graph`). No code is needed.

```xml
<kanban string="Books">
    <progressbar field="book_format" colors='{"hardcover": "success", "paperback": "info", "ebook": "warning"}'/>
    <templates>
        <t t-name="card">
            <main><field name="title"/><field name="author_id"/></main>
            <aside><field name="title"/></aside>
            <footer><field name="genre_ids" widget="many2many_tags"/><field name="rating" widget="priority"/></footer>
        </t>
    </templates>
</kanban>
<pivot string="Books" display_quantity="1" default_order="pages desc">
    <field name="author_id" type="row"/>
    <field name="published_on" type="row" interval="year"/>
    <field name="book_format" type="col"/>
    <field name="pages" type="measure"/>
</pivot>
```

- **Kanban:** one card template `<t t-name="card">` holding only `<field>` nodes and at most one each of `<main>` (first field is the title), `<aside>` and `<footer>`. Markup (`<div>`, `<span>`, `<img>`), `t-if`, `t-esc`, `class`, dynamic `invisible` and one2many fields on a card are refused. Root attributes include `limit`, `default_group_by`, `quick_create`, `can_open`, `create`, `edit`, `delete`. Not available yet: grouped columns, drag and drop, quick creation, drawing the progress bar.
- **Pivot:** `type="row"` / `type="col"` groupings (up to six per axis; boolean, char, integer, selection, many2one, date or datetime; `interval` `day`, `week`, `month`, `quarter` or `year` on dates) and `type="measure"` (integer, float or monetary). `widget`, `invisible` and `options` on a pivot field are refused. Every pivot gets a Download (xlsx) button.
- **Graph:** `<graph string="Books" type="bar">` (bar, line or pie) with one or two grouping fields and `type="measure"` fields; see `graph-view.md`.
- **Calendar:** `<calendar date_start="loan_date" date_stop="due_date" color="borrower_id" mode="month">` with the fields to show; `date_start` is required; see `calendar-view.md`.

## Dashboard cards (application overview boards)

A kanban card can be one computed `text` field drawn with `widget="dashboard_card"`: the model computes (not stored) a JSON text with buttons that open window actions by external id, figures with a count, an optional amount and a domain, and a small bar or line chart. The JSON contract (`"v": 1`, every key required, amounts as decimal text) is in `dashboard-cards.md`; a value that departs from it is named on the card instead of drawn. The widget is refused on any other field type and draws only on kanban cards.


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

The full attribute and refusal tables of kanban, pivot, graph and calendar views (`kanban-view.md`, `pivot-view.md`, `graph-view.md`, `calendar-view.md`); activity, gantt and other view types; the form's visual layout rules (`views.md`, "Form header band and field presentation"); `get_views` wire format; custom view types.

## Sources

- docs/addon-guide/views.md
- docs/addon-guide/human-form-layout.md
- docs/addon-guide/data-files.md
- docs/addon-guide/two-addon-tutorial.md
- docs/addon-guide/kanban-view.md
- docs/addon-guide/pivot-view.md
- docs/addon-guide/graph-view.md
- docs/addon-guide/calendar-view.md
- docs/addon-guide/dashboard-headers.md
- docs/addon-guide/dashboard-cards.md
- addons/sample_library/manifest.toml
- addons/sample_library/views/sample_library_views.xml
- addons/account/views/account_invoice_views.xml
- addons/acceptance_notes/views/acceptance_notes_views.xml
- addons/contacts/views/contacts_views.xml
- addons/base/data/partner_views.xml
- addons/web/src/h18_lower.rs
- addons/web/static/src/client/binary-field.ts
- addons/web/static/src/client/button-prompt.ts
- addons/web/static/src/client/record-form.ts
- addons/web/static/src/client/search/search-arch.ts
