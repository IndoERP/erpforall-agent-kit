---
name: erpforall-data-files
description: Write ERPForAll data files - XML records, external ids, ref/eval/search values, noupdate, CSV files, default data every model must ship, and demo data. Use when adding seed or default records, demo records, or when a data file fails to load.
---

# Data files, default data, demo data

Data files are `.xml` or `.csv`, listed in the manifest `data` (always loaded) or `demo` (only in databases created with demo data). Every rule below is enforced when the file is read, before anything reaches the database, and errors name the file and line.

## XML

Root is `<erp>` (legacy `<odoo>`, `<openerp>`, `<data>` still read). Inside: `record`, `template`, `asset`, `menuitem`, `delete`, `function`. Containers nest and take `noupdate`, `auto_sequence`, `uid`, `context`.

```xml
<erp noupdate="1">
    <record id="tag_vip" model="res.partner.category">
        <field name="name">VIP</field>
        <field name="parent_id" ref="base.res_partner_category_0"/>
        <field name="color" type="int">3</field>
        <field name="category_id" eval="[(6, 0, [ref('tag_demo_customer')])]"/>
    </record>
</erp>
```

- A typo (`<feild>`, `modle=`) stops the file: only the documented elements and attributes are allowed. `<record>` takes `id`, `model`, `forcecreate`, `uid`, `context`.
- One value source per field: `ref="x"`, `eval="..."`, `search="[domain]"` (with `model=` / `use=`), or text with an optional `type` (`int`, `float`, `xml`, `html`, `list`, `tuple`, `bytes` with `file=`, `file`). Put view architectures in `type="xml"` and HTML in `type="html"`; markup in an untyped field is refused.
- External ids: `name` or `module.name`, at most one dot. `ref="x"` must already be defined (an earlier record or file, or a dependency's id); an unresolved ref fails the load.
- Booleans (`noupdate`, `active` on menus): `1/0`, `true/false`, `yes/no`, `on/off`; anything else fails. On `<template>`/`<asset>`, `active` must be exactly `True` or `False`.
- One2many children: `<field name="line_ids"><record ...>` creates the parent first, then each child with the inverse set.
- Comments inside plain text values, DOCTYPE and custom entities are refused.
- `<function model="..." name="..."/>` calls a method; see `data-functions.md`.

## noupdate and upgrades

Install writes every record. An upgrade leaves `noupdate` records alone (a record the user deleted is created again unless `forcecreate="0"`). At the end of an upgrade, records of the module whose external ids the data no longer names are deleted. Mark default data `<erp noupdate="1">` (or `# noupdate: 1` as the first CSV line) so tenants' edits survive upgrades.

## CSV

The file name gives the model (`ir.access.csv`, `res.partner-extra.csv` is `res.partner`). The first line holds field paths for `load()` (`id`, `name`, `group_id/id`, `model_id/id`). A different cell count per row, an empty/repeated header or an invalid id stops the file. On upgrade a file without an `id` column is skipped.

## Default data for every model

The framework's own base addons ship default records for every model they define (in `data/*.xml` or `*.csv`, `noupdate`), with an install test that checks they exist. Follow the same practice in your addon: default records in `data/`, marked `noupdate`, and a test that they exist after install.

## Demo data

- Declare `demo = ["demo/book_demo.xml"]` next to `data`; files load after all `data` files, in order, as if wrapped in `<erp noupdate="1">`.
- Demo loads only when every dependency has demo data; all demo files of one module load in one savepoint, and a failure installs the module without demo data and reports `DemoFailed`.
- Invent the content: fictional names, `example.com` addresses, fictional phone numbers. Give every record an external id (`partner_demo_...`). A company partner is a root partner with `vat`; people are children via `parent_id`.

## Not covered here

`<delete>`, `<function>` and `#[data_callable]` details, translations in data files, `keys`/upsert, migrations (`migrations/` needs a native addon): see `data-functions.md`, `keys-upsert-versions.md`, `migrations.md`.

## Sources

- docs/addon-guide/data-files.md
- docs/addon-guide/demo-data.md
- docs/addon-guide/data-only-addon.md
- addons/contacts/demo/contacts_demo.xml
- addons/sample_library/demo/sample_library_demo.xml
- addons/uom/data/uom_data.xml
