---
name: erpforall-models-fields
description: Declare ERPForAll models and fields - TOML model files for data-only addons and the #[model] / #[field] / #[extend] macros for native Rust addons, field types and keys, relations, defaults, constraints and computed fields. Use when adding or changing a model, a field or a relation in an addon.
---

# Models and fields

## Data-only: `models/*.toml`

Files are read in file-name order (prefix `10_`, `20_` so a model that points at another comes later). One file may hold several `[[model]]` tables.

```toml
[[model]]
name = "sample_library.book"
description = "Library Book"
order = "title, id"
rec_name = "title"

[[model.field]]
name = "title"
type = "char"
required = true
index = true

[[model.field]]
name = "author_id"
type = "many2one"
comodel = "sample_library.author"
ondelete = "restrict"

[[model.field]]
name = "loan_ids"
type = "one2many"
comodel = "sample_library.loan"
inverse = "book_id"

[[model.field]]
name = "state"
type = "selection"
selection = [["draft", "Draft"], ["out", "On Loan"]]
default = "draft"
```

- Model keys: `name` (new model) **or** `extend` (add fields to a model another addon owns, e.g. `extend = "res.partner"`) - exactly one; plus `inherit`, `description`, `order`, `rec_name`, `table`, `transient`, `abstract`.
- Field `type`: `boolean`, `integer`, `float`, `monetary`, `char`, `text`, `html`, `selection`, `date`, `datetime`, `json`, `many2one`, `one2many`, `many2many`.
- Field keys: `string`, `help`, `required`, `readonly`, `store`, `copy`, `groups`, `index` (`true`, `false`, `"btree"`, `"btree_not_null"`, `"trigram"`), `default` (a static value of the field's type; none for relational/json), `related` (a path; the only computed field allowed here), `size` (char), `digits` (float, `[precision, scale]`), `currency_field` (monetary), `selection` / `selection_add` (`[[value, label], ...]`), `comodel`, `inverse` (one2many, required), `relation` + `column1` + `column2` (many2many, all three or none), `ondelete` (many2one/many2many: `"set null"`, `"restrict"`, `"cascade"`), `domain`, `context`, `check_company`.
- `compute` and `depends` are **refused** in model files (use `related`, or make the addon native). `reference` and `many2one_reference` fields need a native addon.
- Unknown keys, wrong types, and keys that do not fit the field type are errors that name the file and line. Field names need no `x_` prefix here.
- Tables and columns are created at install and altered at upgrade; a mistake stops the install and changes nothing.
- Models that need a chatter: `inherit = ["mail.thread"]` (see the `erpforall-chatter` skill).

## Native: macros

```rust
erp_sdk::addon!(name = "library");
use erp_sdk::prelude::*;

#[model(name = "library.book", description = "Book")]
pub struct Book {
    #[field(char, required)]
    pub name: Option<Arc<str>>,
    #[field(integer, default = 1)]
    pub copies: i32,
    #[field(selection, selection = [("draft", "Draft"), ("done", "Done")], default = "draft")]
    pub state: Option<Arc<str>>,
}
```

- `Book` is a declaration type; records are `RecordSet<Book>`; fields are constants (`Book::NAME`). Every data call takes `tx: &mut Transaction`.
- Kinds and Rust types: `boolean` `bool`; `integer` `i32`; `float` `f64`; `monetary` / `float, digits=...` `Decimal`; `char`, `text`, `html`, `selection` `Option<Arc<str>>`; `date` / `datetime` `Option<Date>` / `Option<DateTime>`; `json` `Option<serde_json::Value>`; `many2one` `Option<RecId>` or `Many2one<C>`; `one2many`/`many2many` `Vec<RecId>` or `X2many<C>`. A kind/type mismatch is a compile error.
- In the macro the one2many key is `inverse_name = "..."` (in TOML it is `inverse`).
- Methods: `#[methods(Book)] impl Book { #[method] async fn label(this: &RecordSet<Book>, tx: &mut Transaction) -> Result<String> { ... } }`. Another addon overrides with `#[method(override)]` and a `sup: Super` parameter, calling `sup.call(tx, this.as_records(), ()).await?`.
- Computed field: `#[field(float, compute = "_compute_weight", store)]` plus `#[compute(depends = ["pages"])] fn _compute_weight(batch: &mut Batch<'_, Book>) -> Result<()>` using `batch.indices()`, `batch.get(i, Book::PAGES)?`, `batch.set(i, Book::WEIGHT, v)?`. Related: `#[field(char, related = "shelf_id.name")]`.
- Constraint: `#[constrains("pages")] async fn _check_pages(this: &RecordSet<Book>, tx: &mut Transaction) -> Result<()>` returning `Err(Error::validation("..."))`.
- Onchange: `#[onchange("partner_id")] async fn ...(this, tx) -> Result<OnchangeResult>` (`OnchangeResult::warning(title, msg)`, `OnchangeResult::none()`).
- Extend a model you do not own: `#[extend(Book)] pub struct BookIsbn { #[field(char, size = 13)] pub isbn: Option<Arc<str>>, }` in an addon that depends on the owner (manifest `depends` and `addon!(depends = [...])`).
- Other model parameters exist (`inherit`, `kind`, `table`, `constraints`, `indexes`, `rec_name`, `order`, `parent_store`, ...); read `models.md` before using them.

## Not covered here

Delegation (`inherits`), partitioned models, translated fields, money/currency handling, exclusion constraints, sequences, tracking, onchange on x2many lines: see the matching pages of the guide (`models.md`, `money-currency.md`, `translated-fields.md`, `exclusions.md`, `sequences.md`, `tracking.md`).

## Sources

- docs/addon-guide/cross-addon-extension.md
- docs/addon-guide/data-only-addon.md
- docs/addon-guide/models.md
- addons/sample_library/models/20_book.toml
- addons/sample_library/models/30_loan.toml
- addons/acceptance_notes/src/models.rs
