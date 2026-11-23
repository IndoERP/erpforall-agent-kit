---
name: erpforall-migrations
description: Write ERPForAll schema and data migrations for an addon upgrade - pre, post and end stages, #[erp_sdk::migration] Rust functions, migrations/<version>/<stage>-*.sql scripts, 0.0.0 every-upgrade hooks, adopting company-dependent fields, and upgrade tests. Use when bumping an addon's manifest version or migrating existing tables and records.
---

# Migrations: upgrading data and schema

When an installed addon is upgraded to a newer manifest `version`, its migrations run inside the upgrade's single PostgreSQL transaction: any failure rolls back schema changes, data files and migrations together. Fresh installs and reinits (`init` mode) run no migrations.

## Which migrations run, and in what order

Upgrading from installed version `I` to manifest version `T` runs every migration of version `V` with `I < V <= T`, plus version `0.0.0` whenever `I < T`. Versions compare as semver (`1.1` and `20.0.1.1` are both `1.1.0`).

| Stage | When it runs | Version order |
|---|---|---|
| `pre` | Before the addon's schema update and data files (new columns do not exist yet; use SQL) | `0.0.0` first, then ascending |
| `post` | After the addon's schema update and data files, on the updated registry | Ascending, then `0.0.0` last |
| `end` | After every addon of the operation finished loading | Ascending, then `0.0.0` last |

Within one `(version, stage)`, Rust and SQL migrations run together sorted by name (defaults to the function name for Rust, or filename without `.sql`). When a multi-addon upgrade selects a `pre` migration on an addon that creates or alters a table, schema updates for that table wait until the last such addon's `pre` stage finishes.

## Native Rust migrations (`#[erp_sdk::migration]`)

```rust
use erp_sdk::migrations::SemverVersion;
use erp_sdk::{Result, Transaction};

/// After schema update (`post`): backfill new `isbn` column from legacy `code`.
#[erp_sdk::migration(addon = "library", version = "1.1", stage = post)]
async fn fill_isbn(tx: &mut Transaction, _from: &SemverVersion) -> Result<()> {
    tx.execute("UPDATE library_book SET isbn = code WHERE isbn IS NULL", &[])
        .await?;
    Ok(())
}

/// Every upgrade (`0.0.0`), at `end`: run conditional logic using previously installed `from`.
#[erp_sdk::migration(addon = "library", version = "0.0.0", stage = end, name = "recount")]
async fn recount(tx: &mut Transaction, from: &SemverVersion) -> Result<()> {
    if *from < SemverVersion::new(1, 1, 0) {
        tx.batch("REFRESH MATERIALIZED VIEW library_book_counts").await?;
    }
    Ok(())
}
```

- When converting an existing scalar field to `company_dependent = true`, run `tx.migrate_company_dependent("model.name", "field_name", &CompanyMigrationPolicy::row_company("company_id")?).await` (or `CompanyMigrationPolicy::companies([1, 2])`) in a **`pre`** migration (`company-dependent-fields.md`, `migrations.md`).
- Packaged/embedded addons must use Rust migrations (SQL scripts are read only from an addon's development folder).

## SQL migrations

Place files named `<stage>-<name>.sql` under `migrations/<version>/`:

```text
my_addon/
  manifest.toml
  migrations/
    1.1/
      pre-rename.sql
      post-fill.sql
    0.0.0/
      end-reindex.sql
```

- Scripts execute inside the upgrade transaction. Starting a statement with `BEGIN`, `START`, `COMMIT`, `END`, `ROLLBACK`, `ABORT`, `SAVEPOINT`, `RELEASE`, `PREPARE TRANSACTION` or `BEGIN ATOMIC` is refused (`Error::MigrationSqlRefused`). Write function bodies with dollar quoting, not `BEGIN ATOMIC`.
- Never commit, roll back, or open a transaction inside a Rust migration either.
- If old writable records become `noupdate`, protect their external IDs in a **`pre`** migration before upgrade data files overwrite them.

## Testing upgrades

Test against a disposable database restored to the previous version's schema and rows: assert the old state, run `erp module upgrade -d mydb my_addon --addons-path ./addons`, verify preserved identities and backfilled values, test in a non-UTC session if SQL timestamps exist, and run a second upgrade to verify idempotency.

## Not covered here

Details of moving a Settings entry to a system parameter (`settings.md`), multi-node rolling restart rules for SQL object changes and stock 1.6/1.7 fill scripts (`migrations.md`), operator backup/restore (`cli.md`).

## Sources

- docs/addon-guide/migrations.md
- docs/addon-guide/company-dependent-fields.md
- docs/addon-guide/settings.md
- addons/stock/src/migrations.rs
- addons/base/src/migrations.rs
