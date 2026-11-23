---
name: erpforall-orm-scale
description: Use ERPForAll's scale and search primitives in a native addon - business keys (UNIQUE NULLS NOT DISTINCT), batch Upsert with update and accumulate/accumulate_floor, optimistic concurrency with row_version and expect_versions, and bounded #[search_method] domain providers for nonstored computed fields. Use when maintaining balances, counters, idempotent batch imports, conflict-checked edits, or searchable computed fields.
---

# Scale primitives and nonstored search

Native addons have three built-in ORM scale primitives (no Odoo equivalent) plus bounded search providers for nonstored computed fields.

## 1. Business keys and batch `upsert`

Declare a unique key (NULLs are equal under `UNIQUE NULLS NOT DISTINCT`) and opt into `row_version = true` if needed:

```rust
use erp_sdk::prelude::*;

#[model(
    name = "stock.quant",
    description = "Quant",
    row_version = true,
    keys = [key(
        name = "_quant_key",
        fields = ["product_ref", "location_id", "lot_ref"],
        message = "A quant already exists for this product, location and lot."
    )]
)]
pub struct Quant {
    #[field(char, required)]
    pub product_ref: Option<Arc<str>>,
    #[field(many2one, comodel = "stock.location", required)]
    pub location_id: Option<RecId>,
    #[field(char)]
    pub lot_ref: Option<Arc<str>>,
    #[field(float, digits = 0)]
    pub quantity: Decimal,
}
```

- `Quant::QUANT_KEY` (generated constant, leading `_` stripped and upper-cased) identifies the key for `Upsert::on(Quant::QUANT_KEY)`. Extend a model's keys with `#[extend(Target, keys = [...])]`. Keep leading key columns `required` so index joins stay effective.
- Batch upsert runs in **one statement per batch** (1,000 keys/batch):
  ```rust
  let quants = tx.env().model::<Quant>()?;
  let out = quants.upsert(
      &mut tx,
      Upsert::on(Quant::QUANT_KEY)
          .rows([row])
          .update([Quant::LOT_REF])              // overwrite if different
          .accumulate(Quant::QUANTITY),           // existing + delta (or .accumulate_floor(..., Decimal::ZERO))
  ).await?;
  ```
- Each input row must set all key fields, `update` fields, `accumulate` fields, and any non-static-default required fields (including computed defaults/sequences; `default_get` does not run). Do not pass server-set fields (`id`, `create_uid`, `row_version`, etc.).
- Duplicate keys within one `upsert` call merge (`update` keeps last, `accumulate` sums; `accumulate_floor` rejects duplicates in one batch).
- **`create` and `write` overrides do NOT run on `upsert`.** If logic must observe every upsert, override `upsert` itself with `#[method(override)]` taking `call: UpsertCall, sup: Super`. Every matched row must be readable and writable under the caller's rules.

## 2. Optimistic concurrency (`row_version`)

Adding `row_version = true` on `#[model]` (opt-in; ~10% trigger cost on writes) maintains an `int8 NOT NULL` `row_version` incremented on every `UPDATE`. Read `Base::ROW_VERSION` and guard a subsequent flush without extra queries:

```rust
let version: i64 = note.get(&mut tx, Base::ROW_VERSION).await?;
note.expect_versions(&mut tx, [(note.rec_ids()[0], version)]).await?;
note.set(&mut tx, StockNote::BODY, "edited").await?;
tx.flush().await?; // ErrorKind::Conflict (HTTP 409) if modified concurrently
```

`ErrorKind::Conflict` is never auto-retried by `Orm::run`; reload the record and reapply.

## 3. Search providers for nonstored computed fields (`#[search_method]`)

A nonstored field can support domain search by translating operators into a domain over stored or searchable fields:

```rust
#[field(boolean, compute = "_compute_has_vat", search_method = "_search_has_vat")]
pub has_vat: bool,

#[methods(ResPartner)]
impl ResPartner {
    #[search_method]
    fn _search_has_vat(
        req: &FieldSearchRequest<'_>,
        ctx: &mut FieldSearchContext<'_>,
    ) -> Result<Domain> {
        ctx.charge_work(1)?;
        // inspect req.operator() and req.operand(); return Domain over stored fields
        todo!()
    }
}
```

- Signature is synchronous (`fn(&FieldSearchRequest<'_>, &mut FieldSearchContext<'_>) -> Result<Domain>`), with no SQL or I/O. Override in another addon with `#[search_method(override)]` taking `FieldSearchSuper<'_>`.
- Call `ctx.charge_work(1)?` per loop iteration; hard ceilings (32 expansions, 4,096 AST nodes, 8,192 work units) and disallowance of internal traversal operators (`any!`, `not any!`) apply. Use `Value::Domain(sub)` on `id child_of` / `parent_of` for hierarchy seeds.

## Not covered here

Two-phase post-commit key index build for tables > 100,000 rows (`SchemaSyncOptions::large_table_rows`), `WriteHook` registration (`keys-upsert-versions.md`), full `#[search_method]` operator admission table (`search-methods.md`).

## Sources

- docs/addon-guide/keys-upsert-versions.md
- docs/addon-guide/search-methods.md
- addons/base/src/res_partner.rs
- crates/erp-test-models/tests/search_method.rs
