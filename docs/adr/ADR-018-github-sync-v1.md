# ADR-018: GitHub Synchronization in V1

## Status

Accepted.

Narrows ADR-010-github-evidence-data-model-v1.md and ADR-011-partial-sync-success.md for V1 (which categories are synchronized and stored) and refines ADR-009-github-sync-worker-execution-model.md (triggers, rate limits, a missing repository, the status contract). Those ADRs keep their text; each carries a note pointing here.

## Context

ADR-009 fixed how the worker claims and retries jobs. ADR-010 and ADR-011 fixed the evidence scope: metadata, README, languages and file tree as mandatory categories, contributors and commits as optional ones. They left open when jobs are created, how the client sees the outcome, and how GitHub's rate limits are handled.

In V1 the GitHub data shown is the block on project cards (ADR-019): repository metadata and languages. README display needs a separate decision on safe rendering, the file tree is needed only by the code viewer, and contributors and commits are not shown and contain other people's data (ADR-017). GitHub data is read with app credentials, with one budget of 5,000 requests per hour for the whole platform (ADR-016).

## Decision

### Categories in V1

- V1 synchronizes and stores two categories: **metadata** and **languages**. Both are mandatory in the sense of ADR-011: a failure is retried, and when attempts are exhausted the job is `FAILED`.
- README, file tree, contributors and commits are **deferred, not rejected**. They are not fetched or stored in V1, and their tables and columns (`github_contributors`, `github_commits`, the README and tree columns) are not created. They return with the public project page (Phase 4) and a separate decision on how README is shown safely; the classification, reconciliation and storage rules of ADR-010 and ADR-011 apply to them unchanged when they return.
- The contributor list is still read during a sync to recompute the relation (ADR-017), without being stored. A failure to read it does not fail the job; the previous relation stays.
- Reconciliation follows ADR-010: everything is fetched before a short transaction that only writes; each category has its own transaction (ADR-011); `github_sync_category_status` gets one row per repository and category.

### When jobs are created

A job is a row in `github_sync_jobs` (ADR-009). The partial unique index on active jobs makes every enqueue idempotent: `INSERT ... ON CONFLICT DO NOTHING`, so an existing `QUEUED` or `SYNCING` job is reused.

- **On link and import** (ADR-017): a job is queued in the same transaction as the link.
- **Manually**: `POST /integrations/github/repositories/{id}/sync`, by a user who links the repository to one of their projects. If no job of this repository was created in the last **10 minutes** (configurable, `GITHUB_MANUAL_SYNC_COOLDOWN`), a job is queued; if a job is active, it is returned; otherwise 429 `GITHUB_SYNC_TOO_SOON` with `Retry-After` and `details.retry_after_seconds`. The pause is per repository, since the data is shared by every project that links it. Ten minutes is short enough for a developer who has just pushed, and limits one repository to six manual syncs an hour.
- **Periodically**: in its polling loop, at most once a minute, the worker queues a job for every repository that is linked to at least one `PUBLISHED` project and has no job created in the last **24 hours** (configurable). Unavailable repositories are included, so one that becomes public again recovers on its own. No cron or scheduler is added.

### Rate limits

- A 403 or 429 answer with `x-ratelimit-remaining: 0` is not a job failure. The job returns to `QUEUED` with `scheduled_at` set to `x-ratelimit-reset`, and `attempt_count` is not increased.
- A secondary-limit answer (403 or 429 with `retry-after`, or one whose message names a secondary limit) is handled the same way, waiting `retry-after` seconds, or 60 seconds when there is none (GitHub's guidance).
- Until that time the worker process claims no new jobs. Each worker process keeps this pause in memory; with several processes each one finds the limit on its own request.
- Requests are made one at a time, never in parallel (GitHub's guidance against secondary limits).
- In HTTP requests (link, import, repository list) an exhausted limit gives 503 `GITHUB_RATE_LIMITED` with `Retry-After`.

### Request budget

The platform's 5,000 requests per hour (ADR-016) are shared by the backend and the worker, and by every user; GitHub's `x-ratelimit-remaining` and `x-ratelimit-reset` describe this one shared budget. Without a split, one user who repeats links or manual syncs can exhaust it for everyone. Decided before step 5.2, 2026-10-30.

Cost of one operation, in GitHub requests:

- repository list: 1 per page;
- link or import: 1, plus up to 5 contributor pages when the developer is not the owner (ADR-017);
- sync job: up to 7 (metadata, languages, up to 5 contributor pages).

Rules:

- **Per user.** Each user may spend at most **60** GitHub requests in the last 60 minutes (configurable, `GITHUB_USER_REQUESTS_PER_HOUR`). Before calling GitHub the backend checks that the user's remaining budget covers the operation's maximum (6 for link and import, 1 for a list page); otherwise it answers 429 `GITHUB_USER_LIMIT_REACHED` with `Retry-After` and `details.retry_after_seconds`, without calling GitHub. The requests actually made are counted, so linking one's own repository costs 1. A manual sync that queues a new job counts 7 for the user who asked for it, because the worker makes those requests later; returning an active job counts nothing. Jobs queued by link, import and the periodic schedule are not counted against a user. Sixty requests cover a developer importing a dozen repositories in one sitting; the platform budget then holds about eighty users at their limit in the same hour.
- **Reserve for users.** The worker claims no job while the latest `x-ratelimit-remaining` it has seen is at or below **500** (configurable, `GITHUB_WORKER_RESERVE`), until that response's `x-ratelimit-reset`. Syncs may wait (data is already up to 24 hours old), a developer who is linking a repository is waiting now, so the reserve protects HTTP requests and not the worker.
- **Platform pause in the backend.** After an exhausted-limit answer the backend answers 503 `GITHUB_RATE_LIMITED` without calling GitHub until the reset time it was given, as the worker does.
- The order in a request: input validation, then the repository list cache (ADR-017; a cached page costs nothing), then the user's budget (429), then the platform pause (503), then GitHub.
- Counters and the pause are kept in the backend process's memory. V1 runs one backend process (the image starts uvicorn without `--workers`); a restart resets the counters, which allows at most one extra hour's budget per user. If the backend runs several processes, each keeps its own counters and the per-user limit multiplies by their number; that is the point to move the counters into PostgreSQL. Redis is not introduced for this.

### GitHub unavailable

Timeouts, 5xx answers and malformed responses are retryable failures with ADR-009's backoff and attempt limit.

### Repository not found

- A 404 for the repository's metadata is recorded in `github_sync_category_status` (`last_error = 'NOT_FOUND'`), and the job is retried once after the base retry delay, charging an attempt.
- If the previous metadata attempt also ended with `NOT_FOUND` (no success in between), `github_repositories.unavailable_since` is set and the job ends `FAILED` without further attempts. This applies whether the two 404s come from one job or two.
- A later successful metadata fetch clears `unavailable_since`.
- `unavailable_since` is a fact about the repository (ADR-017), not a job status. ADR-009's rule that `github_repositories` does not duplicate sync status, timestamps or errors still holds for job data.

### Credentials

The worker checks the app credentials at startup and exits on a 401 or an unauthenticated limit (ADR-016). It never falls back to unauthenticated requests.

### Status for the client

There is no separate status endpoint. The cabinet project response (`GET /projects/{id}` and every response that returns `ProjectResponse`) carries `github.sync`:

- `status`: `NOT_SYNCED` (no job yet), or the latest job's `QUEUED`, `SYNCING`, `SYNCED`, `FAILED`;
- `last_success_at`: the older of the two categories' `last_success_at`, or `null`;
- `next_manual_sync_at`: when a manual sync is allowed again, or `null` if it is allowed now.

`POST .../sync` answers 202 with the same `sync` object. The frontend polls `GET /projects/{id}` while the status is `QUEUED` or `SYNCING`. Job errors are not returned to the client; the cabinet shows the state and, for an unavailable repository or a lost relation, the texts of ADR-017.

### Worker deployment

The worker is a separate process from the backend image (ADR-009), run as its own service in Docker Compose, with the same environment as the backend, including the GitHub credentials. It runs with `restart: unless-stopped` and starts after the `migrate` service has completed.

## Consequences

### Positive

- The stored GitHub data is exactly what V1 shows: no README text, file names or other people's data sit in the database unused.
- Rate limits never exhaust a job's attempts; a busy hour delays syncs and does not fail them.
- A repository that became private disappears from public pages within one retry delay of the second 404.
- The client learns the outcome through the response it already reads.

### Negative

- Data is up to 24 hours old unless a developer syncs manually.
- A worker with a rate-limit pause in memory forgets it on restart and makes one more limited request.
- The per-user budget is approximate: in-memory counters reset on restart and would multiply with several backend processes; a manual sync is counted at its maximum, not at what the worker spends.
- A developer at the per-user limit waits up to an hour, even when the platform budget has room.
- The deferred categories need a migration and new code when they return; their rules are already fixed, so it is additive.

## Alternatives considered

- **Keep the full category set of ADR-011 in V1**: rejected — README and file tree would be stored before there is a safe way and a place to show them, and contributors and commits are other people's data with no V1 use.
- **Counting rate-limit answers as failed attempts**: rejected — an exhausted platform budget would turn every queued job into `FAILED`.
- **Only the platform limit, no per-user budget**: rejected — one user's repeated links or manual syncs (50 projects × 6 manual syncs an hour × 7 requests) could take the whole budget.
- **A reserve for the worker instead of for users**: rejected — a delayed sync is invisible to most users, a refused link is not.
- **Per-user counters in PostgreSQL or Redis**: rejected for V1 — one backend process is enough for in-memory counters; PostgreSQL is the path when there are several processes, and Redis is not part of V1.
- **A separate sync status endpoint**: rejected for V1 — the cabinet already reads the project.
- **A cron container for periodic syncs**: rejected — the worker already polls the database and the partial unique index makes its enqueue idempotent.

## Not verified

Checked by hand in step 5.2 (DEVELOPMENT_PLAN), without a user token:

- whether README and the recursive file tree are readable with app credentials (needed only when those categories return);
- whether conditional requests with Basic app credentials save the rate limit (ADR-016); V1 does not store ETags until this is known.

## Open questions

- File content for the code viewer (ADR-011's open question) and the return of README and the file tree.
- Whether periodic syncs should skip repositories linked only to hidden (`PUBLISHED` + `PRIVATE`) projects.
- Worker health checks and alerting beyond the restart policy (Phase 9).
