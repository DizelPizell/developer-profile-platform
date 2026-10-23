# ADR-009: GitHub Sync Worker Execution Model

## Status

Accepted

## Context

ADR-008 established that GitHub synchronization in V1 is asynchronous but does not use Kafka or an Outbox pattern. The exact worker/queue mechanism was left as an open implementation decision. This ADR resolves that decision.

## Decision

The GitHub Sync Worker runs as a separate process, independent from the FastAPI request/response cycle.

The worker claims pending work using PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`, polling `github_sync_jobs` at a configurable interval. This allows multiple worker processes to run concurrently without double-processing the same job, and without any external broker.

One row in `github_sync_jobs` represents one logical sync request (a "job"), not one physical attempt. Automatic retries reuse the same row and increment `attempt_count`; a new row is only created for a new, separately initiated sync request after a prior one has reached a terminal state.

`github_sync_jobs` is the single source of truth for sync status. `github_repositories` does not duplicate sync status, timestamps, or error information.

At most one active job per repository is allowed. This is enforced with a partial unique index on `github_repository_id` for rows with `status IN ('QUEUED', 'SYNCING')`.

### States and retry semantics

- `QUEUED` — the job is waiting to be picked up for its first attempt, or waiting for a scheduled retry.
- `SYNCING` — a worker has claimed the job and is actively processing it.
- `SYNCED` — the job completed successfully.
- `FAILED` — the job has permanently failed after exhausting the allowed number of attempts.

`FAILED` is only ever a terminal state. When a transient failure occurs and attempts remain, the job transitions directly back to `QUEUED` with a future `scheduled_at` (for backoff), in the same operation as the failure handling — it is never left resting in `FAILED` while a retry is still pending. This is what keeps the partial unique index above correct: a row that still has retries ahead of it is always observable as `QUEUED` or `SYNCING`, never as a lingering `FAILED`.

### Configuration (V1 starting values — configurable, not hardcoded)

- Maximum attempts: 5
- Polling interval: 5 seconds
- Base retry delay: 30 seconds
- Maximum retry delay: 30 minutes
- Abandoned-`SYNCING` threshold: 10 minutes

Retry delay uses exponential backoff between the base and maximum values above. These values must be configurable, not hardcoded into business logic. GitHub HTTP request timeouts are configured separately from the retry/backoff values above.

A watchdog mechanism recovers jobs stuck in `SYNCING` past the abandoned threshold (for example after a worker crash or restart), subject to the same attempt limit and the same concurrency protection (`SKIP LOCKED`) as normal processing — watchdog recovery is not a separate, unprotected code path.

## Consequences

### Positive

- No new infrastructure beyond PostgreSQL, consistent with ADR-008 and CLAUDE.md's "no distributed system in V1" principle.
- `SKIP LOCKED` allows safe horizontal scaling to multiple worker processes with zero coordination code.
- A single source of truth for status removes an entire class of dual-write consistency bugs.

### Negative

- Polling adds a small, constant load on PostgreSQL per worker per tick; acceptable at V1 scale, revisit only if a concrete problem appears.
- A watchdog/timeout mechanism is required to guarantee liveness — logic that would not exist in a broker-based design, where delivery guarantees come from the broker itself.

## Rejected

- Kafka/Outbox for job delivery — already rejected in ADR-008; this ADR is the concrete mechanism that replaces it.
- FastAPI `BackgroundTasks` as the execution mechanism — does not survive process restart/crash, violating the recoverability already required by ADR-008.

## Not decided by this ADR

- Whether the API exposes a dedicated sync-status endpoint, and its exact contract.
