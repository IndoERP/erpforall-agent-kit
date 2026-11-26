---
name: erpforall-models-fields
description: Declare ERPForAll models and fields - TOML model files for data-only addons and the #[model] / #[field] / #[extend] macros for native Rust addons, field types and keys, relations, defaults, constraints and computed fields, binary and image fields, company-dependent fields. Use when adding or changing a model, a field or a relation in an addon.
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
- Field `type`: `boolean`, `integer`, `bigint`, `float`, `monetary`, `char`, `text`, `html`, `selection`, `date`, `datetime`, `json`, `many2one`, `one2many`, `many2many`.
- Field keys: `string`, `help`, `required`, `readonly`, `store`, `copy`, `groups`, `index` (`true`, `false`, `"btree"`, `"btree_not_null"`, `"trigram"`), `default` (a static value of the field's type; none for relational/json), `related` (a path; the only computed field allowed here), `size` (char), `digits` (float, `[precision, scale]`), `currency_field` (monetary), `selection` / `selection_add` (`[[value, label], ...]`), `comodel`, `inverse` (one2many, required), `relation` + `column1` + `column2` (many2many, all three or none), `ondelete` (many2one/many2many: `"set null"`, `"restrict"`, `"cascade"`), `domain`, `context`, `check_company`, `collation` (`"C"` or `"default"`, char and text only). Model key `audit_reads = true` selects the model's successful RPC reads for auditing.
- `compute` and `depends` are **refused** in model files (use `related`, or make the addon native). `reference` and `many2one_reference` fields need a native addon, and so do `binary` and `image` fields, `company_dependent`, `tracking` and SQL objects (`sql_function`, `sql_trigger`, ... are refused as native-only).
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
- `bigint` is `BigInt` (`BigInt::from_i64(v)`, `.get()`), exact signed 64-bit; over JSON-2 it travels as a decimal string. Changing a stored `integer` to `bigint` widens the column on upgrade; the reverse is refused.
- `#[field(boolean, required, default = true, db_default)]` keeps a fail-closed flag's default as the column's database default, for rows written by plain SQL; only for a stored, required boolean.
- `#[field(char, collation = "C")]` selects byte ordering for a stored char or text field.
- Other model parameters exist (`inherit`, `kind`, `table`, `constraints`, `indexes`, `rec_name`, `order`, `parent_store`, ...); read `models.md` before using them.

## Files and pictures (native)

```rust
#[field(binary, string = "Scan")]
pub scan: Option<Blob>,
#[field(image, max_width = 1024, max_height = 1024, string = "Cover")]
pub cover: Option<Blob>,
#[field(image, max_width = 256, max_height = 256, related = "cover", store = true)]
pub cover_256: Option<Blob>,   // a stored smaller size of `cover`
```

- `Blob` (in the prelude) is shared immutable bytes; over RPC the value is base64 text, and `false` clears it. A read with `bin_size` in the context returns the size text instead of the content; the web client's views read that way.
- An `image` field accepts PNG, JPEG, GIF or WebP only (read from the bytes; SVG is refused), scales a larger PNG or JPEG down to its bounds (16 to 4096 pixels per edge, or none) and is limited by the system parameters `base.image_max_bytes` and `base.image_max_pixels`.
- Binary and image fields cannot be indexed, translated, company-dependent, ordered by or grouped by.
- `erp_addon_base::ImageMixin` (`inherit = [ImageMixin]`) adds `image_1920` and the stored sizes `image_1024`, `image_512`, `image_256`, `image_128`; write `image_1920` only. Show a picture with `widget="image"`, in lists and cards with `options="{'preview_image': 'image_128'}"`.
- Storage is a `bytea` column of the model's table; attachment-backed storage is not built yet. In a form or list, a `binary` field automatically uses `widget="binary"` with optional `filename="<char_field>"` (skill `erpforall-views`). Files attached to a record (not a field) are `ir.attachment` records (skill `erpforall-attachments`).

## Translated fields (native)

`#[field(char, translate = true)]` (or `.translate(true)` on `Char`, `Text`, `Html`) stores a JSONB language map and projects `context["lang"]` with `en_US` fallback on scalar reads, searches and ordering. Non-default languages must be active; a required translated field requires a non-empty `en_US` base on save; writing `false` clears the whole field. It cannot combine with `company_dependent`, `compute`, or `related`. In Rust, use `Records::get_field_translations(tx, field)` (`FieldTranslations`) and `Records::update_field_translations(tx, field, entries)` to read or update the map without fallback. Static selection field labels are reflected into `ir.model.fields.selection` (`<module>.selection__<model_ident>__<field>__<value_ident>`) and translated through PO files (`translated-fields.md`).

## Company-dependent fields (native)

`company_dependent = true` keeps one value per company: a read returns the value of the environment's current company, a write stores it for that company only, and a company without its own value reads its `ir.default` fallback (per company, then global). The Rust type stays the scalar type:

```rust
#[field(many2one, comodel = "stock.location", company_dependent = true, check_company = true, string = "Customer location")]
pub property_stock_customer: Option<RecId>,
```

Supported kinds: char, text, html, boolean, integer, float, monetary, selection, date, datetime, many2one (bigint is admitted but the guide lists it as untested). Refused: other kinds, computed, related, inverse, generated or tracked company-dependent fields, a translated one, upsert on the model, keyset pagination ordered by the field. Reading or writing it needs a current company. Do not switch an existing field to company-dependent without the migration described in `company-dependent-fields.md`, "Existing data".

## Encrypted fields (native)

`#[field(char, encrypted = true)]` (or `text`) stores the value encrypted in a `bytea` column; the application reads and writes the clear value. The field must be stored (or related to an encrypted field). It is refused together with translate, company-dependent, an index, a collation, a key, an exclusion constraint or tracking. Conditions, sorting, grouping and aggregates on it are refused, and your SQL must not read the column. Declaring it plain again later is refused. Every node then needs `field_key_file` in its configuration, or the commands that build the ORM stop with an error naming the field (`docs/deployment.md`, "Encrypted fields"). No shipped addon uses it yet; the declaration rules are tested in `crates/erp-test-models/tests/field_encryption.rs`. Model files (`models/*.toml`) have no `encrypted` key.

## Naming the fields of a refusal

`Error::validation("End date is before start date.").with_fields(["date_start", "date_end"])` attaches the field names (JSON-2 error body, `context.fields`) so the client can show the message on those fields; a refusal about the whole record names none.

## Values an administrator may change

A value an administrator or operator may change (a limit, an interval, a default choice) is not a constant in code: declare a setting or a system parameter with a default, a floor and a bound (skill `erpforall-settings`), or use a company-dependent field when it is a value per company.

## Not covered here

Delegation (`inherits`), partitioned models, money/currency handling, exclusion constraints and range types, sequences (`sequences.md`; one rule to know: numbering an addon creates while the server runs must be gapless, `implementation = 'no_gap'`, because a deployed server may not create database sequences then; numbering created by an install or upgrade may stay standard), onchange on x2many lines, columns only the owner may add (`owner_only_stored_fields`), notifying the ORM after your own SQL (`modified_external`): see `models.md`, `money-currency.md`, `exclusions.md`, `sequences.md`. Business keys, `upsert`, `row_version` and `#[search_method]` are in the `erpforall-orm-scale` skill (`keys-upsert-versions.md`, `search-methods.md`). Tracking is in the `erpforall-chatter` skill (`tracking.md`).

## Sources

- docs/addon-guide/cross-addon-extension.md
- docs/addon-guide/data-only-addon.md
- docs/addon-guide/models.md
- docs/addon-guide/binary-image-fields.md
- docs/addon-guide/company-dependent-fields.md
- docs/addon-guide/translated-fields.md
- docs/addon-guide/sequences.md
- docs/addon-guide/rpc.md
- crates/erp-modules/src/model_files.rs
- addons/sample_library/models/20_book.toml
- addons/sample_library/models/30_loan.toml
- addons/acceptance_notes/src/models.rs
- crates/erp-macros/src/model.rs
- crates/erp-test-models/tests/field_encryption.rs
- crates/erp-fields/src/error.rs
- docs/deployment.md
