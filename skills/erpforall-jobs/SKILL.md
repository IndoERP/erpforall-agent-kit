---
name: erpforall-jobs
description: Declare and enqueue durable background jobs in an ERPForAll addon - JobKindDecl and register_job_kind!, chunked StepArgs / StepOutcome model methods, EnqueueRequest with deduplication and singleton keys, job_cancel_by_key, JobHandler chunk_items isolation, and extending another addon's job step. Use when work should run asynchronously in short transactions or on a schedule.
---

# Background jobs

A background job is a row in the durable queue written in the same database transaction as the business change that schedules it. Workers claim due jobs under the **caller's principal** (resolved again on every chunk) and commit progress chunk-by-chunk.

## 1. Declare a job kind and step method

```rust
use erp_sdk::jobs::{HandlerRef, JobKindDecl, StepArgs, StepOutcome};
use erp_sdk::prelude::*;

erp_sdk::addon!(name = "guide_jobs");

#[model(name = "guide_jobs.recount", description = "Recount", addon = "guide_jobs")]
pub struct Recount {
    #[field(char)]
    pub name: Option<Arc<str>>,
}

#[methods(Recount, addon = "guide_jobs")]
impl Recount {
    #[method]
    async fn run_step(
        _this: &RecordSet<Recount>,
        _tx: &mut Transaction,
        args: StepArgs,
    ) -> Result<StepOutcome> {
        let done = args.progress.as_ref().and_then(|p| p["done"].as_u64()).unwrap_or(0);
        let total = args.payload["total"].as_u64().unwrap_or(1);
        let next = done + 1;
        let progress = erp_sdk::serde_json::json!({ "done": next });
        Ok(if next >= total {
            StepOutcome::done(progress, 1)
        } else {
            StepOutcome::more(progress, 1, Some(total - next))
        })
    }
}

erp_sdk::jobs::register_job_kind!(
    RECOUNT_KIND,
    JobKindDecl::new(
        "guide_jobs",
        "guide_jobs.recount",
        HandlerRef::Step { model: "guide_jobs.recount", method: "run_step" },
    )
    .max_attempts(5)
);
```

- Kind names are `<addon>.<name>` and unique across all addons. `principal(PrincipalPolicy::System)` is refused for ordinary addons (reserved for core and `base`).
- Payloads and progress are bounded JSON data; never put secrets or credentials in them (store a reference).

## 2. Enqueue and cancel inside your transaction

```rust
use erp_sdk::jobs::{EnqueueRequest, JobKey, OnDuplicate, When};
use erp_sdk::prelude::*;
use std::time::Duration;

async fn schedule(tx: &mut Transaction, record_id: i64) -> Result<()> {
    let env = tx.env();
    let request = EnqueueRequest::new("guide_jobs.recount")
        .payload(&erp_sdk::serde_json::json!({ "total": 3 }))?
        .at(When::After(Duration::from_secs(60)))
        .dedup(JobKey::new(&format!("recount:{record_id}"))?, OnDuplicate::Earliest);
    tx.enqueue(&env, request).await?;
    Ok(())
}
```

- `enqueue` uses the caller's user and active companies; if the user is archived or loses the company, the job becomes a dead letter without falling back to another user.
- `dedup` prevents duplicate live jobs (`Keep` keeps the existing schedule; `Earliest` pulls it forward). Include the user id in the key if work differs per user. Use `.singleton(JobKey::new(...)?)` when at most one job with that key may run concurrently across nodes. Use `enqueue_many` for up to 1,024 jobs in one statement.
- Cancel obsolete jobs with `tx.job_cancel_by_key(&env, "guide_jobs.recount", &key).await?` (or `job_cancel_by_keys` for up to 10,000 keys). It returns a count (including `0` when already done, dead-lettered, gone, or currently claimed by another transaction).

## 3. Failures, native handlers and overrides

| Returned error | Queue behaviour |
|---|---|
| Database/lock failure (`?`) | Retried with exponential backoff + jitter; dead letter after `max_attempts` (progress commits reset attempts) |
| Validation, access or programming error | Dead letter immediately |
| `JobError::Yield { after }` | Rescheduled after `after` without consuming an attempt (e.g. rate limits) |
| `JobError::item(..)` inside `chunk_items` | Batch retries with per-item savepoints; failing items recorded in `erp_job_item_failure` |

- Native addons needing custom chunk loops implement `JobHandler` (`ctx.chunk(|tx| Box::pin(async move { ... }))`, `chunk_items`, or lease-renewed `external` work polling `CancelToken` and checkpointing).
- **Extend another addon's step:** override the target model's step method with `#[method(override)]` and call `sup` so both run in one chunk.
- **Data-only addons** cannot declare job kinds; they can schedule existing server actions via `ir.cron` XML records (`erpforall-data-files`).

## 4. Recurring jobs (native)

Give one of your step job kinds a `Schedule`:

```rust
use erp_sdk::jobs::{HandlerRef, JobKindDecl, Schedule};

erp_sdk::jobs::register_job_kind!(
    DAILY_REFRESH,
    JobKindDecl::new(
        "my_addon",
        "my_addon.daily_refresh",
        HandlerRef::Step { model: "my_addon.record", method: "refresh_step" },
    )
    .schedule(Schedule::daily_at(1, 0, "Asia/Jakarta", "my_addon.user_scheduler"))
);
```

- `Schedule::daily_at(hour, minute, time_zone, run_as)` (wall-clock time in an IANA zone), or `Schedule::every(interval, run_as)` / `Schedule::every_from(interval, offset, run_as)` (60 s to 31 days, aligned to the Unix epoch plus the offset).
- `run_as` is the external id of an active internal `res.users` record your addon ships in its data; a scheduled kind never runs as the system.
- Install or upgrade creates the kind's one job row; uninstall removes it (refused while it runs). Code cannot enqueue that row.
- The step receives `{"scheduled_for": "<RFC 3339>", "previous": "<RFC 3339>" | null}`. Missed runs collapse into one run for the latest missed instant, so process "the period since `previous`" and stay idempotent.
- On `finished` the row is rescheduled; a dead-lettered run waits for an operator to requeue it.

## Not covered here

Shared node/database job settings (`Orm::job_settings_snapshot`), isolated maintenance runner composition (`JobRunnerBuilder::maintenance_kinds`), operator queue settings (`jobs.md`).

## Sources

- docs/addon-guide/jobs.md
- addons/base/src/ir_job.rs
- addons/base/src/ir_cron/mod.rs
- docs/development.md
- crates/erp-orm/src/jobs/schedule.rs
- crates/erp-test-models/tests/jobs_schedule.rs
