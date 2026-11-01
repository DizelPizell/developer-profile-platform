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
- **Manually**: `POST /integrations/github/repositories/{id}/sync`, by a user who links the repository to one of their projects. If no job of this repository was created in the last **10 minutes** (configurable, `GITHUB_MANUAL_SYNC_COOLDOWN_SECONDS`), a job is queued; if a job is active, it is returned; otherwise 429 `GITHUB_SYNC_TOO_SOON` with `Retry-After` and `details.retry_after_seconds`. The pause is per repository, since the data is shared by every project that links it. Ten minutes is short enough for a developer who has just pushed, and limits one repository to six manual syncs an hour.
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
- link: 1, plus 1 when the name is an old one that GitHub redirects, plus up to 5 contributor pages when the developer is not the owner (ADR-017);
- import: 1, plus up to 5 contributor pages;
- sync job: up to 7 (metadata, languages, up to 5 contributor pages).

Rules:

- **Per user.** Each user may spend at most **60** GitHub requests in the last 60 minutes (configurable, `GITHUB_USER_REQUESTS_PER_HOUR`). Before calling GitHub the backend checks that the user's remaining budget covers the operation's maximum (7 for a link, 6 for an import, 1 for a list page); otherwise it answers 429 `GITHUB_USER_LIMIT_REACHED` with `Retry-After` and `details.retry_after_seconds`, without calling GitHub. The requests actually made are counted, so linking one's own repository costs 1. A manual sync that queues a new job counts 7 for the user who asked for it, because the worker makes those requests later; returning an active job counts nothing. Jobs queued by link, import and the periodic schedule are not counted against a user. Sixty requests cover a developer importing a dozen repositories in one sitting; the platform budget then holds about eighty users at their limit in the same hour.
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

### Sync tables

Decided in step 6.1, 2026-10-31; columns and indexes in `docs/database/DATABASE_SCHEMA.md` ("GitHub sync fields").

- `last_error` in `github_sync_jobs` and `github_sync_category_status` is a fixed label such as `NOT_FOUND`; a CHECK allows only `^[A-Z_]{1,64}$`, so GitHub's text cannot be stored (ADR-016 keeps it out of logs for the same reason).
- The watchdog finds a stale `SYNCING` job by `updated_at`, which every status change sets; there is no separate claim time.
- Both tables cascade from `github_repositories`. A linked repository cannot be deleted (ADR-017); when an unlinked one is, its sync records go with it.
- Jobs carry no trigger or requesting user: the pause, the schedule and the per-user budget do not need them.
- Links made before step 6.1 get no job: their status is `NOT_SYNCED`. A repository linked to a `PUBLISHED` project is queued by the periodic sync (step 6.5); one linked only to drafts waits for a manual sync or a new link. The migration queues nothing, since there is no worker before step 6.3.
- A successful link or import reads the repository's metadata, so it is recorded as a metadata success in `github_sync_category_status` (`last_success_at` set, `last_error` cleared), as it already clears `unavailable_since` (ADR-017). Without it, a 404 before the link and one after it would count as two in a row. Implemented in step 6.2.

### Queueing and manual syncs

Decided in step 6.2, 2026-10-31.

- Link and import queue the job in `store_link`, the write they share, after the link row is written; the same place records the metadata read ("Sync tables" above). A refused or failed link writes neither.
- An enqueue inserts with `ON CONFLICT (github_repository_id) WHERE status IN ('QUEUED', 'SYNCING') DO NOTHING` and otherwise reads the active job. The job's times come from the application's clock, as the pause compares them with it.
- A manual sync checks, in order: the repository is linked by one of the user's projects (404 otherwise); an active job is returned and costs nothing; a job created less than the pause ago is 429 `GITHUB_SYNC_TOO_SOON`, `retry_after_seconds` rounded up; otherwise a job is queued and 7 requests are charged. Over the budget it is 429 `GITHUB_USER_LIMIT_REACHED` and the rollback removes the job. The repository is never refused for being unavailable or for a `NONE` relation: a sync is how either recovers.
- The charge comes after the insert, so a reused job costs nothing. If the commit fails after it, the user loses those 7 until they leave the window; the budget has no refund.
- The manual sync locks the repository row (`SELECT ... FOR UPDATE`) before it reads the latest job. A link holds the same lock through its upsert. The partial unique index alone keeps one active job, but a job that finishes before the first request commits would leave the index empty, and a second request could queue another job inside the pause; the lock makes it read the new job first. An advisory lock was rejected (a key derived from a UUID, invisible in the schema), and so was SERIALIZABLE (retries).

### Worker core

Decided in step 6.3, 2026-11-01; the code is `backend/app/github/worker.py`.

- **One worker process in V1.** ADR-009's `SKIP LOCKED` would let several run, but requests go one at a time ("Rate limits" above), and each process would keep its own pause. A second process started by mistake is still safe: it skips the rows the first has locked.
- **Claim.** A short transaction takes the due `QUEUED` job scheduled earliest (`FOR UPDATE SKIP LOCKED`), sets `SYNCING`, `attempt_count + 1` and `updated_at`, and commits before the job runs. The processor runs outside any transaction of the worker and commits its own writes (one transaction per category, step 6.4); what it leaves uncommitted is rolled back.
- **Outcome and fence.** The outcome is written in another short transaction, only while the job is still `SYNCING` at the claimed `attempt_count`. If the watchdog took the job back in between, the outcome is dropped and logged, so a lost worker cannot overwrite the next attempt. Rejected: one transaction around the whole job (GitHub requests inside an open transaction, and its failure would undo the category writes) and a heartbeat (a job is at most 7 requests of at most 10 seconds, far below the stale threshold).
- **Attempts** are counted at the claim, so a worker that dies during a job has used the attempt. A rate limit gives it back (`attempt_count - 1`), sets `scheduled_at` to the reset and starts the pause; `last_error` keeps the previous label.
- **Labels** of `last_error` in jobs: `NOT_FOUND` (404), `GITHUB_UNAVAILABLE` (timeout, network error, 5xx, malformed answer), `UNEXPECTED_STATUS` (a redirect the processor did not follow, another 4xx), `WORKER_LOST` (the watchdog), `INTERNAL_ERROR` (an exception from the code, the only case logged with a traceback). Labels carry no status code; a rate limit has no label.
- **Retries.** A failure with attempts left returns the job to `QUEUED` at `now + min(base · 2^(attempt − 1), max)`: 30 seconds, then 1, 2 and 4 minutes, and `FAILED` after the fifth attempt. No jitter, as there is one worker. The processor can end a job `FAILED` at once (the second 404 in a row, step 6.5).
- **401 during a job**: the job returns to `QUEUED` with its attempt given back, and the worker stops with an error. It is a configuration problem; failing every job would only hide it.
- **Watchdog.** Before each claim, also while claims are held: `SYNCING` jobs whose `updated_at` is older than the stale threshold, with `SKIP LOCKED`, return to `QUEUED` due now with `WORKER_LOST`, or become `FAILED` when their attempts are used up.
- **Holding claims.** No claim during the rate-limit pause, nor while the latest `x-ratelimit-remaining` seen is at or below the reserve, until that answer's reset. Without a known remaining or reset the worker claims: only its own requests would tell it more. The worker charges no user; a manual sync already counted its 7.
- **Startup.** `GET /rate_limit` (it does not spend the limit) with the app credentials: a 401 or a core limit of 60 or less stops the worker with an error, and so does an unavailable GitHub; the restart policy (step 6.6) starts it again. The answer seeds the rate-limit state, so a worker started in a busy hour keeps to the reserve from its first claim.
- **Loop.** Due jobs run back to back; when none is due the worker waits the poll interval. SIGTERM and SIGINT end the loop after the current job, so the Compose service (step 6.6) needs a stop grace period longer than one job (about 70 seconds). Any other failed iteration, such as the database being down, is logged and retried after a poll.
- **Settings**: `GITHUB_WORKER_POLL_SECONDS` (5), `GITHUB_WORKER_MAX_ATTEMPTS` (5), `GITHUB_WORKER_RETRY_BASE_SECONDS` (30), `GITHUB_WORKER_RETRY_MAX_SECONDS` (1800, not below the base), `GITHUB_WORKER_STALE_SECONDS` (600), `GITHUB_WORKER_RESERVE` (500).
- **Processor and entry point** came in step 6.4 ("Processor" below), not in step 6.3: a worker deployed with a placeholder would have marked jobs `SYNCED` without data. Jobs queued since step 6.2 run in a first burst, within the reserve.
- **Logs**: job and repository ids, attempt, status, label and times; never a response body, a header or the credentials (the client logs only the operation, the status and the remaining budget).

### Processor

Decided in step 6.4, 2026-11-01; the code is `backend/app/github/sync.py`.

- **Requests.** Metadata by GitHub's repository id (`GET /repositories/{id}`), so a renamed or transferred repository is found under its new name; then languages under the name just read; then, only when a linked developer is not the owner, up to 5 contributor pages, read once for all links and stopped when every such developer is found. 2 requests usually, 7 at most: the 7 a manual sync charges.
- **Writes.** Metadata and languages each get their own short transaction after their request, with their success in `github_sync_category_status`. Metadata sets the columns a link sets (`owner_github_id`, `owner_login`, `name`, `full_name`, `html_url`, `description`, `is_fork`, `parent_full_name`, `is_archived`, `pushed_at`), clears `unavailable_since`, and so also refreshes a renamed repository's names. Languages replace the stored object whole. No transaction is open while GitHub answers.
- **A failed category** keeps its data and its last success; its label and time go to `github_sync_category_status` in their own transaction, and the error goes to the worker, which retries the job. A rate limit and a 401 record no label. When metadata fails, languages and the relation are not requested. Languages failing after metadata succeeded is a partial success: metadata is stored, the job is retried, and `synced_at` (the older category) stays as it was.
- **Relation.** After both categories, every link to the repository, whoever made it, gets `OWNER` (owner id equals the developer's GitHub id), `CONTRIBUTOR` (in the pages read) or `NONE`, with `relation_checked_at`. A transfer changes the owner and so the relations. If the pages cannot be read for any reason but a 401, the links of developers who are not the owner keep their relation and check time, a warning is logged, and the job still succeeds. A link replaced during the sync is a new row and is left alone. A repository with no links is still synced, without contributor pages.
- **Language names** with a control character are a malformed answer (a JSONB key cannot hold NUL).
- **Entry point**: `python -m app.github.worker` sets up logging at INFO, the worker's own client, rate-limit state and pause, and one database session per iteration; it exits with 0 after SIGTERM or SIGINT and with 1 when GitHub rejects the credentials or cannot be reached at startup. Run as `__main__`, the file delegates to the imported module, so the processor and the worker share one copy of each class.
- **Running it** before the Compose service of step 6.6: `docker compose run --rm --no-deps backend python -m app.github.worker` (backend README).
- **404** is retried with `NOT_FOUND` like any failure until step 6.5 adds the two-404 rule.
- **Conditional requests** (ETags) are not used in V1: two requests a day per repository linked to a published project do not need them. The open question below stays for later.

### Status for the client

There is no separate status endpoint. The cabinet project response (`GET /projects/{id}` and every response that returns `ProjectResponse`) carries `github.sync`:

- `status`: `NOT_SYNCED` (no job yet), or the latest job's `QUEUED`, `SYNCING`, `SYNCED`, `FAILED`;
- `last_success_at`: the older of the two categories' `last_success_at`, or `null`;
- `next_manual_sync_at`: when a manual sync is allowed again, or `null` if it is allowed now. It is shown while a job is active too, although `POST .../sync` then returns that job; the cabinet does not offer a sync while the status is `QUEUED` or `SYNCING`.

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

## Checked by hand

Checked in step 5.2 on 2026-10-30, with app credentials and no user token (`backend/scripts/github_smoke.py`, one run):

- README and the recursive file tree of a public repository are readable (`octocat/Hello-World`; the tree was not truncated). Access does not block the deferred categories when they return.
- A `304` to a conditional request did not spend the limit (ADR-016). V1 still does not store ETags; see "Open questions".

## Open questions

- Conditional requests in syncs: storing an ETag per repository and category would let an unchanged repository cost no budget, since a 304 did not spend the limit in step 5.2. Not used in V1 (decided in step 6.4, "Processor"); open for after V1.
- File content for the code viewer (ADR-011's open question) and the return of README and the file tree.
- Whether periodic syncs should skip repositories linked only to hidden (`PUBLISHED` + `PRIVATE`) projects.
- Worker health checks and alerting beyond the restart policy (Phase 9).
- Retention of finished jobs: kept in V1 (about one row a day per repository linked to a published project); deleting old `SYNCED` and `FAILED` rows can come later without a schema change.
