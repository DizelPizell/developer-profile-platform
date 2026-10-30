# ADR-010: GitHub Evidence Data Model V1

## Status

Accepted

Note (2026-10-30): narrowed for V1 by ADR-018-github-sync-v1.md. V1 synchronizes and stores only repository metadata and languages. README, file tree, contributors and commits are deferred, not rejected; the scope and reconciliation rules below apply to them unchanged when they return. The `github_repositories` field list for V1 is fixed by ADR-017-repository-linking-and-import.md.

## Context

ADR-007 established that GitHub is the source of technical repository evidence. This ADR defines the concrete scope and reconciliation rules for GitHub Evidence in V1 — what is synchronized, how it is classified (snapshot vs history), and how synchronization stays idempotent and safe under partial failure.

## Decision

### Scope

Required V1 GitHub Evidence data:

- Repository metadata.
- README.
- Programming languages.
- File tree metadata: `path`, `type`, `sha`, `size`. File content is not stored in PostgreSQL in V1; how content is retrieved for the code viewer is a separate decision, scoped to Project Workspace.
- Contributors, using GitHub's own reported data as-is. No derived contribution percentages, rankings, or scores are computed from this data (ADR-007, ADR-011).
- Commits: up to the 100 most recent commits per repository, per sync run.

Explicitly out of the required V1 scope: Dependencies, Pull Requests, Releases, CI/CD as a separate entity. Dependencies are deferred pending a separate review of GitHub API behavior and availability — deferred, not rejected outright.

### Snapshot data — reconciliation

Repository metadata, README, languages, file tree metadata and contributors are **snapshot** data: they represent current GitHub state, not accumulated history.

Reconciliation algorithm, identical across all snapshot categories:

1. Fetch a complete, correct snapshot from GitHub, including all pagination for that category.
2. If the fetch fails or is incomplete (including a truncated response), do not delete or otherwise modify existing stored data for that category. The job is retried or marked `FAILED` per ADR-009.
3. Upsert every item present in the current snapshot, and delete every previously stored item not present in the current snapshot — in one short PostgreSQL transaction.
4. No GitHub network requests are made inside that transaction. Fetching happens entirely before the transaction opens; the transaction only writes.

### History data — commits

Commits are **history**: append-only, never automatically deleted.

- Natural/unique key: `(github_repository_id, sha)`.
- On conflict (a commit already stored), the existing row is **not** overwritten — `ON CONFLICT ... DO NOTHING`. A commit's own content is immutable by git's nature; once stored, nothing about a given SHA should legitimately need to change.
- New commits are added idempotently — re-running the same sync produces no duplicates.
- Existing commits are never deleted automatically.
- The limit of 100 applies **per sync run's fetch**, not to the total number of rows ever stored for a repository. A repository's commit table can and will grow beyond 100 rows over multiple sync runs, since nothing already stored is removed.

**Documented limitation**: because each run only fetches the 100 most recent commits as of that run, a repository that accumulates more than 100 new commits between two sync runs will have a gap — commits in between will never be fetched by either run and will be permanently missing from stored history. This is an accepted V1 limitation, not a bug to silently work around.

## Consequences

### Positive

- One reconciliation algorithm covers every snapshot category — no bespoke logic per entity.
- Snapshot and history have deliberately different deletion rules, matching their different real-world semantics (current state vs immutable past).
- The transaction-boundary rule (fetch outside, write inside, short transaction) makes it safe to physically delete snapshot rows without risking data loss on partial failure.

### Negative

- The commit-history gap described above is a real, accepted limitation for very active repositories synced infrequently.
- Excluding Dependencies/Pull Requests/Releases/CI means the "technical evidence" shown is narrower than the original PRD wording implied — product documentation is updated to match this scope alongside this ADR.

## Rejected (for V1)

- Storing full file content in PostgreSQL during sync.
- Dependency graph / SBOM ingestion (deferred, not rejected outright — see Scope).
- Pull Requests, Releases, CI/CD as separate synced entities.
- Deriving contribution percentages, skill scores, or rankings from contributors or commit data (already established by ADR-007/ADR-011, restated here because it directly touches the Contributors data covered by this ADR).

## Not decided by this ADR — require separate confirmation

- Whether README is stored as a separate table or as a field on `github_repositories`.
- Whether Languages is stored as a normalized table or as a `JSONB` column.
- Whether Contributors is stored as a separate table (recommended in prior analysis, not yet confirmed).
- The exact field list for `github_repositories`.
- The Sync Status API endpoint and its response contract.

This ADR fixes scope, classification and reconciliation rules — not the final physical storage shape for every entity.
