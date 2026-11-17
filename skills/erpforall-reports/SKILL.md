---
name: erpforall-reports
description: Add a printed report to an ERPForAll addon - QWeb report templates, the ir.actions.report record that puts it under the Print menu, the print profile (the closed set of tags, classes, styles and directives a report may use), images, and business documents (invoice, order, slip) built from the shared document parts of the web addon. Use when the user asks for a PDF, a printout, a Print menu entry or a printed document of a model.
---

# Reports

A report is two things in the addon's data files: QWeb `<template>` records that draw it and an `ir.actions.report`
record that names the main template and binds it to its model's Print menu. A data-only addon can ship reports; keep the
file under `views/` (the sample library uses `views/sample_library_reports.xml`) and list it in the manifest `data`
after the views. The layouts and document parts come from the `web` addon: put `web` in `depends` (the sample library
lists `depends = ["base", "web"]`; `purchase` gets it through `account`).

## 1. Templates and action

```xml
<erp>
    <template id="report_book_sheet_document">
        <div class="page">
            <h2 t-field="doc.title"/>
            <div class="text-muted" t-if="doc.author_id">by <span t-field="doc.author_id.name"/></div>
        </div>
    </template>

    <template id="report_book_sheet">
        <t t-call="web.html_container">
            <t t-call="web.external_layout">
                <t t-foreach="docs" t-as="doc">
                    <div t-att-class="None if doc_first else 'page-break-before'">
                        <t t-call="sample_library.report_book_sheet_document"/>
                    </div>
                </t>
            </t>
        </t>
    </template>

    <record id="action_report_book_sheet" model="ir.actions.report">
        <field name="name">Book Sheet</field>
        <field name="model">sample_library.book</field>
        <field name="report_type">qweb-pdf</field>
        <field name="report_name">sample_library.report_book_sheet</field>
        <field name="print_report_name">'Book sheet - ' + object.title</field>
        <field name="binding_model_id" ref="sample_library.model_sample_library_book"/>
        <field name="binding_type">report</field>
    </record>
</erp>
```

- `<template id="x">` becomes a QWeb view keyed `<addon>.x`; `report_name` is that key.
- The templates see `docs` (the printed records), `company` (the records' own `company_id` when set, else the user's
  current company) and the `t-foreach` loop names (`doc_first`, `doc_last`, `doc_index`, ...).
- Call `web.html_container` and `web.external_layout` **once around the loop**, not per record: a document has one page
  header (letterhead) and one footer (contact line, page counter). `page-break-before` starts each later record on a
  new page. Records of several companies print company by company, each with its own letterhead.
- `report_type`: `qweb-pdf`, `qweb-html` or `qweb-text` (selection in the base addon). `print_report_name` names the
  file when one record prints (`object` is the record). `paperformat_id` picks the page (a `report.paperformat`
  record); without it the company's paper format applies.
- `binding_model_id` plus `binding_type` `report` lists the report under the Print button of the model's list and
  the form's record menu. Without a binding, a button or method prints by returning the report's action with
  `context.active_ids`.
- The report is checked against the print profile when it is saved and again when it prints.

## 2. A business document on the shared parts

For an invoice, order or slip, build the `page` from the `web` addon's parts (`addons/web/data/report_documents.xml`)
so documents look like one family. Shape taken from `addons/purchase/views/purchase_reports.xml`:

```xml
<template id="report_order_document">
    <div class="page">
        <t t-set="status" t-value="False"/>
        <t t-if="o.state == 'draft'" t-set="status">Draft</t>
        <t t-call="web.document_title" title.translate="Purchase Order" number="o.name" status="status"/>
        <t t-call="web.document_addresses">
            <t t-call="web.document_address" address="o.partner_id" label.translate="Vendor"/>
        </t>
        <t t-call="web.document_info">
            <t t-if="o.user_id" t-call="web.document_info_item" label.translate="Buyer"><span t-field="o.user_id.name"/></t>
        </t>
        <t t-call="web.document_lines">
            <thead><tr><th>Description</th><th class="text-end">Amount</th></tr></thead>
            <tbody>
                <tr t-foreach="o.order_line" t-as="line">
                    <td t-field="line.name"/>
                    <td class="text-end" t-field="line.price_subtotal"/>
                </tr>
            </tbody>
        </t>
        <t t-call="web.document_totals">
            <t t-call="web.document_total_grand" label.translate="Total"><span t-field="o.amount_total"/></t>
        </t>
    </div>
</template>
```

- Parts: `web.document_title`, `document_addresses` / `document_address`, `document_info` / `document_info_item`,
  `document_lines`, `document_line_section` / `document_line_note` (`columns`, `text`), `document_totals` /
  `document_total_row` / `document_total_grand`, `document_note`, `document_signatures` / `document_signature`.
- Arguments go on the `t-call`. `label.translate="..."` is a translated label; every other argument is an expression
  (a text literal needs quotes: `text="'Hardware'"`, not translated). Pass `False` for an empty argument; every argument
  a part names must be given. Guard optional info items with `t-if`.
- Put `text-end` on the `th` and every `td` of a number column. A monetary `t-field` takes its record's currency; a
  computed amount uses `t-options="{'widget': 'monetary', 'display_currency': o.currency_id}"`. Print a quantity with
  its unit. Write taxes one per line (`<br/>` between them).
- There is no amount-in-words part and no company setting for document colours yet (inherit `web.document_title` and
  `web.document_total_grand` to change the accent colour).

## 3. The print profile (what a template may use)

Only a closed vocabulary is accepted; anything else is an error naming the token, not a silent drop.
- Directives: `t-foreach`/`t-as`, `t-if`/`t-elif`/`t-else`, `t-set`/`t-value` (on `<t>`), `t-esc`/`t-out`,
  `t-field`/`t-options`, `t-call` (on `<t>`, static target), `t-lang`, `t-translation="off"`, `t-att`, `t-att-*`,
  `t-attf-*`. A dynamic `t-call` target and `t-tag` are refused.
- Elements: `div`, `span`, `p`, `a`, tables, headings, lists, `img`, `address`, `section`, `main` and inline styling
  tags; classes and inline styles only from the declared lists (the full tables are in `reports.md`, "Profile 1
  vocabulary"). `rowspan` above one is refused; `colspan` 1 to 1,000 works.
- `t-field` widgets: `char`, `text`, `integer`, `float` (`precision`), `monetary`, `date`/`datetime` (`date_only`,
  `time_only`, `hide_seconds`), `selection`, relational display names, `image`. Refused for now: `html`, `image_url`,
  `barcode`, `contact`, `duration`, `relative`. A method call on records must be a registered report helper.
- Images: `t-att-src="image_data_uri(company.logo)"`, `t-field` on a binary field with
  `t-options="{'widget': 'image', 'max_width': 100, 'max_height': 100}"`, or an embedded `data:image/...;base64,...`
  `src`. A `src` path or an external URL is refused: printing fetches nothing.
- A report that stores its PDF as an attachment (an `attachment` expression) refuses a template that prints a
  group-restricted field unless `allow_attachment_group_fields` is set on the action.
- Page breaks: `thead` rows repeat on every page. A row, a note, the totals and the signatures stay on one page,
  except one estimated taller than half the page body (a very long description), which may break so nothing runs
  past the margin.
- A document prints in the printing user's language formats (date, time, decimal point, grouping) and timezone; a
  background print uses those of the user who asked for it. Translated template terms are not loaded yet: labels and
  text print as written. A translation is text and is never evaluated (`{{ }}` in a term prints as written).
- Records are read with the user's rights. One exception, as on a form: a many2one printed only by its display name
  (`t-field="o.user_id"`) prints that name even when the user may not open the target; any other field of the
  target (`o.user_id.email`) needs read access to it.

## 4. Printing and its settings

Print from the Print menu. Up to `base.report_sync_max_records` records download at once from
`/erp/report/pdf/<report>/<ids>` (`html` instead of `pdf` gives the preview, `?download=1` an attachment); more run as
a background print job whose file is attached to a `report.job` row. System parameters (default, floor, bound):
`base.report_sync_max_records` 50, 1, 500; `base.report_job_chunk_records` 20, 1, 500; `base.report_job_max_records`
10,000, 1, 100,000; `base.report_job_poll_ms` 1,000, 250, 60,000. A server without its font directory answers each
print with an error naming `report.font_directory`.

## Not covered here

`qweb-text` report content (no print profile applies to it, the guide says nothing more), report helpers declared in
Rust, the layout engine and worker API (`reports-engine.md`), PDF merge, overlay and e-invoice embedding
(`pdf-post-processing.md`, used by report composition code, not by addon data files), user-facing report pages (the
guide notes they do not exist yet), and custom paper formats (`report.paperformat` fields are not documented in the
guide).

## Sources

- docs/addon-guide/reports.md
- docs/addon-guide/report-documents.md
- docs/addon-guide/reports-engine.md
- docs/addon-guide/pdf-post-processing.md
- addons/sample_library/manifest.toml
- addons/sample_library/views/sample_library_reports.xml
- addons/purchase/views/purchase_reports.xml
- addons/purchase/manifest.toml
- addons/web/data/report_documents.xml
- addons/web/manifest.toml
- addons/base/src/ir_actions/report.rs
- addons/base/src/report_paperformat.rs
