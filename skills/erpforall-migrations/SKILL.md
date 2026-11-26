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

## Changing shipped `noupdate` records

Data in a `noupdate` block (report definitions, default records) is not rewritten by an upgrade, so a new layout reaches an existing database only through a migration. `account_reporting` follows these rules, and so should you:

- **Change a record only while it still holds the value you shipped.** Find it by its external id in `ir_model_data` and put the old value in the `WHERE`, so an administrator's change stays:

```rust
#[erp_sdk::migration(addon = "account_reporting", version = "1.8", stage = post)]
async fn guard_builtin_partner_ledger(tx: &mut Transaction, _from: &SemverVersion) -> Result<()> {
    tx.execute(
        "UPDATE reporting_report r SET provider = 'account_reporting.partner_ledger' \
         FROM ir_model_data d WHERE d.module = 'account_reporting' AND d.name = 'report_partner_ledger' \
           AND d.model = 'reporting.report' AND d.res_id = r.id AND r.provider = 'reporting.definition'",
        &[],
    )
    .await?;
    Ok(())
}
```

  When several columns must match, compare each with `IS NOT DISTINCT FROM` (so a `NULL` shipped value matches). A translated `name` is JSON: compare `r.name->>'en_US'` and write it with `jsonb_set`.
- **Skip what is gone.** No external id: the record was not shipped yet at the installed version (the data files create it later in this upgrade). An external id without its record: an administrator deleted it. Leave both alone.
- **Delete by external id, unchanged records only,** then remove the external ids left without a record (`DELETE FROM ir_model_data d WHERE d.module = '<addon>' AND d.model = $1 AND NOT EXISTS (SELECT 1 FROM <table> r WHERE r.id = d.res_id)`): the end-of-upgrade cleanup never removes `noupdate` ids.
- **Fail with a name when a kept change no longer fits.** After the steps, load what you changed the way the application loads it; on an error, stop the upgrade with a `Validation` naming the record and telling the administrator to reset it to its shipped value (`check_definitions` in `addons/account_reporting/src/migrations.rs`).

## Testing upgrades

Test against a disposable database restored to the previous version's schema and rows: assert the old state, run `erp module upgrade -d mydb my_addon --addons-path ./addons`, verify preserved identities and backfilled values, test in a non-UTC session if SQL timestamps exist, and run a second upgrade to verify idempotency.

For data upgrades, the framework keeps **predecessor fixtures**: the addon's earlier `manifest.toml` and data files, unchanged, under `crates/erp-cli/tests/fixtures/<addon>_previous/<version>/<addon>/`, with a `README.md` and a provenance file recording the revision each was captured from. The test in `crates/erp-cli/tests/account_off_balance_guard.rs`:

1. copies the current addons into a temporary directory, with the fixture version in place of the addon, and builds a `ModuleSystem` over it (listing in `.code([...])` only the native descriptors that version had);
2. installs the old version (`button_immediate_install`), then makes an administrator's edits through the ORM;
3. builds the current system and runs `button_immediate_upgrade`, asserting `post_commit.is_clean()`;
4. reads the result as an ordinary user, checking that the edits were kept, that an upgrade equals a fresh install where nothing was edited, and that a kept change that cannot fit stops the upgrade with its named error.

## Not covered here

Details of moving a Settings entry to a system parameter (`settings.md`), multi-node rolling restart rules for SQL object changes and stock 1.6/1.7 fill scripts (`migrations.md`), operator backup/restore (`cli.md`).

## Sources

- docs/addon-guide/migrations.md
- docs/addon-guide/company-dependent-fields.md
- docs/addon-guide/settings.md
- addons/stock/src/migrations.rs
- addons/base/src/migrations.rs
- addons/account_reporting/src/migrations.rs
- crates/erp-cli/tests/account_off_balance_guard.rs
- crates/erp-cli/tests/fixtures/account_reporting_previous/README.md
- crates/erp-cli/tests/fixtures/account_reporting_previous/1.13.0/account_reporting/manifest.toml
