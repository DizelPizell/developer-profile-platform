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
- The deferred categories need a migration and new code when they return; their rules are already fixed, so it is additive.

## Alternatives considered

- **Keep the full category set of ADR-011 in V1**: rejected — README and file tree would be stored before there is a safe way and a place to show them, and contributors and commits are other people's data with no V1 use.
- **Counting rate-limit answers as failed attempts**: rejected — an exhausted platform budget would turn every queued job into `FAILED`.
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
