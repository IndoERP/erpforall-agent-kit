---
name: erpforall-dynamic-reports
description: Build an on-screen dynamic report in an ERPForAll addon with the report engine (addon reporting) - a report as data (reporting.report, line, column and expression records with aggregate, formula and native engines), a native ReportProvider in Rust (lines, expand with paging, drill, init_options), typed cells, caret items and drill actions, and the client action that opens it. Use when the user wants a ledger, balance, aging or analysis screen with dates, comparison, unfolding, totals and drill-down. Printed PDF documents are the erpforall-reports skill.
---

# Dynamic reports (the report engine)

The addon `reporting` shows a report as a tree of lines with a filter bar (dates, comparison, companies, search), unfolding, load-more, totals, drill-down and PDF/XLSX export. Add `"reporting"` to `depends` in `manifest.toml`. Two ways to supply the lines:

- **A report as data**: records only; the built-in provider `reporting.definition` computes them. Works in a data-only addon.
- **A native provider**: Rust code that answers the lines of the reports naming it. Needed for ledgers (running balances, one line per record) or anything the definition engines cannot express.

Every read runs as the caller, in the call's read transaction. Nothing is kept between calls.

## 1. A report as data

```xml
<erp noupdate="1">
    <record id="report_partner_country" model="reporting.report">
        <field name="name">Contacts by Country</field>
        <field name="comparison" eval="False"/>
        <field name="date_default">this_year</field>
    </record>
    <record id="report_partner_country_count" model="reporting.report.column">
        <field name="report_id" ref="report_partner_country"/>
        <field name="name">Contacts</field>
        <field name="label">count</field>
        <field name="kind">integer</field>
        <field name="scale">0</field>
        <field name="sortable" eval="True"/>
    </record>
    <record id="report_partner_country_line" model="reporting.report.line">
        <field name="report_id" ref="report_partner_country"/>
        <field name="name">Contacts</field>
        <field name="code">PARTNERS</field>
        <field name="groupby">country_id</field>
    </record>
    <record id="report_partner_country_line_count" model="reporting.report.expression">
        <field name="line_id" ref="report_partner_country_line"/>
        <field name="label">count</field>
        <field name="model">res.partner</field>
    </record>
</erp>
```

A column shows, on every line, the expression whose `label` equals the column's `label`.

| Model | Fields you set |
|---|---|
| `reporting.report` | `name`; `provider` (default `reporting.definition`); `date_mode` `range` \| `single`; `date_default` `today` \| `this_month` \| `last_month` \| `this_quarter` \| `last_quarter` \| `this_year` \| `last_year`; booleans `comparison`, `multi_company`, `unfold_all`, `search_bar`, `totals_below`, `current_only`; `hide_zero` `never` \| `optional` \| `by_default`; `load_more_limit` (default 500) |
| `reporting.report.column` | `report_id`, `sequence`, `name` (header), `label`, `kind` `monetary` \| `decimal` \| `integer` \| `percent` \| `date` \| `text`, `scale`, `sortable`, `blank_if_zero`, `rollup` `sum` \| `none` with `rollup_field`, `groups` |
| `reporting.report.line` | `report_id`, `sequence`, `name`, `code`, `parent_id`, `groupby` (fields the line unfolds by, comma-separated, outermost first), `foldable` `foldable` \| `always_unfolded` \| `never_unfolded`, `hide_if_zero`, `optional` (left out, and named, for a caller who may not read its records) |
| `reporting.report.expression` | `line_id`, `label`, `engine` `aggregate` (default) \| `formula` \| `native`, then the engine's fields below |

- A line `code` is `[A-Z][A-Z0-9_]*`, a `label` is lowercase letters, digits and `_`; both at most 64 bytes. Codes are unique per report, labels per report (columns) and per line (expressions).
- A parent line must come before its children (lower `sequence`).
- **`aggregate`**: `model`, `domain` (a **JSON** domain as text: `[["state","=","sale"]]`), `field` (an integer, float or monetary field to sum; empty counts records), `date_field` (a date or datetime field the period applies to; empty: no period), `date_scope` `strict_range` (default) \| `from_beginning` \| `before_period`.
- **`formula`**: `formula` with `+ - * /`, parentheses, decimal numbers, `label` (same line), `CODE.label` (another line) and `sum_children`; `zero_division` `error` (default) \| `empty`. At most 4096 bytes.
- **`native`**: `function` names a registered Rust function (section 3) and uses the aggregate fields as its input.
- Every save of one of these records checks the whole report, so a wrong field, model, code or formula stops the install with a message naming the report and the part.

A subtotal over child lines, from the accounting reports:

```xml
<record id="profit_loss_gross_profit_amount" model="reporting.report.expression">
    <field name="line_id" ref="profit_loss_gross_profit"/>
    <field name="label">amount</field>
    <field name="engine">formula</field>
    <field name="formula">OP_INCOME.amount - COGS.amount</field>
</record>
```

With `totals_below`, the engine itself adds a line `Total <name>` after the children of every unfolded line; do not create those.

Report definitions are usually `noupdate` data: changing a shipped one later needs a migration (skill `erpforall-migrations`).

## 2. Open it: client action and menu

The screen is the client action tag `reporting.report`; its `params` take only `report`, the record id:

```xml
<record id="action_partner_ledger" model="ir.actions.client">
    <field name="name">Partner Ledger</field>
    <field name="tag">reporting.report</field>
    <field name="params" eval="{'report': ref('report_partner_ledger')}"/>
</record>
<menuitem id="menu_partner_ledger" name="Partner Ledger" parent="menu_account_reporting"
          action="action_partner_ledger" groups="account.group_account_readonly" sequence="40"/>
```

`base.group_user` may read the four definition models and `base.group_system` may change them; what a reader sees in the lines depends on their own rights on the source models.

## 3. A native provider

Add the crate `erp-addon-reporting` to the addon's `Cargo.toml` (as `addons/sale/Cargo.toml` does) and implement `ReportProvider`. The report record names it in `provider`, and still declares the columns:

```xml
<record id="report_sales_ledger" model="reporting.report">
    <field name="name">Sales Report</field>
    <field name="provider">sale.sales_report</field>
    <field name="comparison" eval="False"/>
    <field name="multi_company" eval="False"/>
    <field name="totals_below" eval="True"/>
</record>
```

```rust
use erp_addon_reporting::{
    definition::ReportDef,
    line::{Cell as ReportCell, CellKind, DrillTarget, ExpandPage, Expansion, Line, LineId, LineKind, Segment, SegmentKind},
    options::Options,
    provider::{ProviderSpec, ReportCx, ReportProvider},
};
use erp_sdk::prelude::*;
use erp_sdk::serde_json::{Value as Json, json};
use erp_sdk::BoxFuture;

pub(crate) struct SalesReport;
const SPEC: ProviderSpec = ProviderSpec::new("sale.sales_report", 2);

impl ReportProvider for SalesReport {
    fn spec(&self) -> &ProviderSpec { &SPEC }
    fn init_options<'a>(&'a self, _cx: &'a mut ReportCx<'_>, _report: &'a ReportDef,
                        options: &'a mut Options, _strict: bool) -> BoxFuture<'a, Result<()>> {
        Box::pin(async move {
            match options.provider.keys().next() {
                Some(key) => Err(Error::validation(format!("The Sales Report has no option {key}."))),
                None => Ok(()),
            }
        })
    }
    fn lines<'a>(&'a self, cx: &'a mut ReportCx<'_>, report: &'a ReportDef,
                 options: &'a Options) -> BoxFuture<'a, Result<Expansion>> { /* top-level lines */ }
    fn expand<'a>(&'a self, cx: &'a mut ReportCx<'_>, report: &'a ReportDef, options: &'a Options,
                  line: &'a LineId, page: ExpandPage) -> BoxFuture<'a, Result<Expansion>> { /* one page of children */ }
    fn drill<'a>(&'a self, cx: &'a mut ReportCx<'_>, report: &'a ReportDef, options: &'a Options,
                 line: &'a LineId, target: &'a DrillTarget) -> BoxFuture<'a, Result<Json>> { /* an action result */ }
}

erp_addon_reporting::provider_declarations!(SalesReport);
```

The provider name is `<addon>.<name>`; bump the version in `ProviderSpec::new(name, version)` when its options or line ids change meaning. `provider_declarations!` defines one static, so call it once per module (`account_reporting` has one call in each provider's module). Two installed addons registering one name fail every lookup. `Snapshot::WholeTree` is refused; keep the default.

Rules the shipped providers follow; follow them too:

1. **Read as the caller, through the ORM.** `cx.env()`, `cx.tx()` (or `cx.parts()`) are the caller's; there is no elevated environment. Use `env.records(model)?` with `search`, `search_count`, `read_rows` and `_read_group(cx.tx(), ReadGroup::new(domain).groupby([..]).aggregates(["amount_total:sum"]))`, so record rules and field groups apply. Do not check access on the model and then run your own SQL over its table: that skips record rules and field groups.
2. **Refuse unknown option keys.** `options.provider` holds the provider's own keys; `init_options` refuses any it does not know and fills defaults for the ones it does (the Partner Ledger accepts only a boolean `unreconciled`).
3. **Check what the options allow.** The sales provider refuses more than one company (`options.companies`), more than one period (`options.column_groups.len() != 1`) and a period without a start (`options.period.from` is `None` in single-date mode).
4. **Map columns by label.** Build one cell per entry of `report.columns`, matching `col.label` (and `col.kind`), and refuse a column the provider does not know; apply `cell.blank_if_zero()` when `col.blank_if_zero`. An administrator can then reorder or remove columns.
5. **Check every line id before any query.** A `LineId` comes from the browser; `LineId::parse` checks syntax only. Write a `locate(report, id)` that returns a typed position or a `Validation` error: `id.report() == report.id`, then each of `id.segments()` by `kind()` (`SegmentKind::Group(field)`, `SegmentKind::Line(code)`), `model()` and a parsed positive `value()`. Use it first in `expand` and `drill`.
6. **Bound and page.** The top level reads at most `cx.bounds().max_screen_lines` groups (ask for one more and refuse when exceeded, naming `reporting.max_screen_lines`). `expand` reads `page.offset` / `page.limit` children (`SearchOptions::new().offset(page.offset).limit(page.limit)`), refuses `offset + limit` beyond `max_screen_lines`, and when more exist ends with a load-more line:

```rust
let mut more = Line::new(id.child(Segment::more()), "", LineKind::More, empty_cells);
more.remaining = Some(count - end);
more.next_offset = Some(end);
lines.push(more);
```

### Lines and cells

- Ids: `LineId::root(report.id)`, then `.child(Segment::group("partner_id", "res.partner", &id.to_string()))` (an empty value is the group of records without one), `Segment::line("INITIAL")`, `Segment::total()`, `Segment::more()`.
- `Line::new(id, name, kind, cells)` with `LineKind::Group` (unfolds further), `Detail`, `Section`, `Total`, `More`; then set `line.unfoldable`, `line.unfolded` (`options.unfold_all || options.unfolded.contains(&id)`) and `line.caret`.
- Cells: `ReportCell::monetary(value, scale, Some(currency_id))`, `ReportCell::number(CellKind::Decimal | Integer | Percent, value, scale)`, `ReportCell::date(date)`, `ReportCell::text(..)`, `ReportCell::empty()`. Numbers are `Option<Decimal>`, never floats; never add amounts of two currencies.
- `.with_drillable(true)` says a numeric cell can be opened (the screen then calls `drill` with `DrillTarget::Cell(index)`); `.with_danger(true)` gives the cell the `danger` tone (an overdue date).
- A grand total is a root line of the provider's own: `Line::new(root.child(Segment::total()), "Total", LineKind::Total, cells)`. Totals below unfolded lines come from the engine when the report has `totals_below`.

### Caret items and drill results

`line.caret` lists item names; the screen shows `open` as "Open", `journal_items` as "Journal items", `partner` as "Open partner", `entry` as "View journal entry", and any other name as written. `drill` gets `DrillTarget::Item(name)` or `DrillTarget::Cell(index)` and returns a window action result (shapes: skill `erpforall-wizards-actions`); refuse a target the line does not offer:

```rust
fn list_action(name: &str, domain: &Domain) -> Result<Json> {
    Ok(json!({ "type": "ir.actions.act_window", "name": name, "res_model": "sale.order",
               "target": "current", "views": [[false, "list"], [false, "form"]],
               "domain": domain.to_json()?, "context": {} }))
}
fn form_action(name: &str, model: &str, id: i64) -> Json {
    json!({ "type": "ir.actions.act_window", "name": name, "res_model": model, "res_id": id,
            "target": "current", "views": [[false, "form"]] })
}
```

Before opening one record, confirm it is inside the report's scope with a `search_count` as the caller.

### A native expression function

For one value a definition report cannot aggregate, register a function and name it in an expression's `function` (`engine` = `native`): `erp_addon_reporting::expression_function_declarations!(VALUE, "my_addon.value", value, source_domain);`. The function gets `(&mut ReportCx, &Options, NativeRequest { model, field, domain, group })` and returns one `(Option<i64>, Decimal)` per group key; the second function returns the extra domain used when the cell is opened. Read `addons/stock/src/report_net.rs` before writing one.

## 4. Bounds and settings

The engine's limits are Settings entries (block "Dynamic reports"): `reporting.max_load_more_limit`, `reporting.max_unfold_depth`, `reporting.max_screen_lines`, `reporting.max_comparison_periods`, `reporting.max_filter_source_rows`, `reporting.export_max_rows`, `reporting.export_max_request_bytes`. An answer over `max_screen_lines` is refused, never cut. Read them in a provider from `cx.bounds()`.

## 5. Tests

Unit-test cell building in the addon (`addons/sale/src/report.rs`, `mod tests`). Full-stack tests call the engine as a user in a suite crate: `erp_addon_reporting::runtime::report_lines(&tx.env(), &mut tx, &options)` with options such as `{"report": id, "companies": [company], "date": {"preset": "custom", "from": "2024-02-01", "to": "2024-02-29"}}`, then assert on `["lines"]`; see `crates/erp-suite-sale/tests/report_providers.rs` (skill `erpforall-addon-tests`).

## Not covered here

Comparison periods and several companies in a native provider (the shipped ledgers refuse them; the definition provider handles both), `ProviderSpec::server_search`, delegating to `DefinitionProvider` from a native provider (`ReportDef::restricted_to`, `check_page_parent`), the export endpoints, the report screen's TypeScript, and the `rollup` / `groups` column options beyond their field descriptions. The addon guide has no page for the report engine yet; this skill was written from the code.

## Sources

- addons/reporting/src/lib.rs
- addons/reporting/src/models.rs
- addons/reporting/src/provider.rs
- addons/reporting/src/line.rs
- addons/reporting/src/options.rs
- addons/reporting/src/definition.rs
- addons/reporting/src/formula.rs
- addons/reporting/src/functions.rs
- addons/reporting/src/runtime.rs
- addons/reporting/src/settings.rs
- addons/reporting/src/client_action.rs
- addons/reporting/static/src/report-screen.ts
- addons/reporting/data/reporting_data.xml
- addons/reporting/security/ir.access.csv
- addons/reporting/manifest.toml
- addons/account_reporting/data/profit_loss.xml
- addons/account_reporting/data/partner_ledger.xml
- addons/account_reporting/src/lib.rs
- addons/account_reporting/src/partner_ledger.rs
- addons/account_reporting/src/aged_partner.rs
- addons/sale/src/report.rs
- addons/sale/data/sale_report_data.xml
- addons/sale/Cargo.toml
- addons/stock/src/report_net.rs
- crates/erp-suite-sale/tests/report_providers.rs
