# ADR-011: Partial Sync Success — Mandatory and Optional Categories

## Status

Accepted

## Context

ADR-010 defined the scope and reconciliation rules for GitHub Evidence and established that if a category fetch fails or is incomplete, existing stored data is not modified and the job is retried or marked `FAILED` per ADR-009.

ADR-010 left open whether all categories have equal weight regarding job outcome and left the storage shapes for README, languages and contributors undecided. This ADR resolves those questions.

## Decision

### Category classification

**Mandatory** (failure triggers retry; after attempts exhausted → `FAILED`):

- Repository metadata
- README
- Programming languages
- File tree metadata

  **Special case — truncated tree.** If GitHub returns a truncated tree response, or the entry count exceeds the configured limit, this is treated as a **final outcome for the category**, not a fetch error. The category is marked processed with a `tree_truncated` flag; the job may still reach `SYNCED`. The UI must indicate that the tree is unavailable when this flag is set.

  > ✓ **Confirmed by project owner (2026-10-23).** Treating truncation as a non-error final outcome changes user-visible behaviour for large repositories. If large repositories should instead fail and retry until the limit is raised, the standard mandatory failure path (retry → FAILED) would apply instead.

**Optional** (failure does not block `SYNCED`):

- Contributors

  A failed contributors fetch does not transition the job to retry or `FAILED`. The job may complete with `SYNCED` status even if contributors data could not be fetched. Existing contributors rows are preserved on failure, consistent with ADR-010's rule: if a fetch fails or is incomplete, do not delete or otherwise modify existing stored data for that category.

- Commits

  A failed commits fetch does not transition the job to retry or `FAILED`. The job may complete with `SYNCED` status even if commits could not be fetched. Commits are **history data, not snapshot data** (defined in ADR-010): append-only, `ON CONFLICT DO NOTHING`, never automatically deleted. This means existing rows are always preserved — on failure there is simply nothing new to append, and no rows are ever deleted. Commits freshness is tracked in `github_sync_category_status` on the same terms as contributors: one row per `(github_repository_id, category)`, updated after each category attempt regardless of job outcome.

### Per-category transactions

Each successfully fetched category is committed in its own short PostgreSQL transaction. There is no single transaction covering the entire sync job. This allows partial success: a job may reach `SYNCED` with different data freshness across categories.

The transaction-boundary rule from ADR-010 still applies per category: fetch entirely before opening the transaction; no GitHub network calls inside the transaction. For snapshot categories this means upsert current and delete missing in one short transaction. For history categories (commits) this means insert new rows with `ON CONFLICT DO NOTHING`.

### Job status remains single, no sub-statuses

The `github_sync_jobs` status (`QUEUED`, `SYNCING`, `SYNCED`, `FAILED`) represents the overall job outcome. There are no sub-statuses or per-category status fields on `github_sync_jobs`. The lifecycle from ADR-009 is unchanged:

```text
NOT_SYNCED -> QUEUED -> SYNCING -> SYNCED
                            \-> FAILED (attempts exhausted)
```

A job reaches `SYNCED` when all mandatory categories have been successfully fetched and committed. It reaches `FAILED` (after retries exhausted) only when a mandatory category could not be fetched successfully.

### Category freshness tracking

A separate table `github_sync_category_status` tracks per-category freshness independently of job outcome:

- Natural key: `(github_repository_id, category)` — one row per pair.
- Fields: `category`, `last_success_at`, `last_error`, `last_error_at`.
- Updated after each category attempt, regardless of whether the overall job succeeds or fails.
- Enables the application and UI to show which categories were last synced when.

### Storage shape (resolves open questions from ADR-010)

- **README**: TEXT column on `github_repositories`, replaced wholesale on each successful README fetch.
- **Languages**: JSONB column on `github_repositories`, replaced wholesale on each successful languages fetch.
- **File tree**: JSONB column on `github_repositories`, replaced wholesale on each successful file tree fetch. Each entry stores `path`, `type`, `size` and `sha`. A configurable entry-count limit applies; truncation and limit-exceeded cases are treated as final outcomes rather than fetch errors — see the truncated-tree special case under Category classification above.
- **Contributors**: separate table `github_contributors`, one row per contributor per repository, unique on `(github_repository_id, github_user_id)`. `github_user_id` is the GitHub numeric user id and the stable identifier; `login` is stored as a regular (non-unique) field. Snapshot data: reconciled on each successful contributors fetch (upsert current, delete missing in one transaction), consistent with ADR-010's reconciliation algorithm.
- **Commits**: separate table `github_commits`, one row per commit per repository, unique on `(github_repository_id, sha)`. History data: append-only, `ON CONFLICT ... DO NOTHING`, never automatically deleted. On a successful fetch, new rows are inserted; existing rows are not overwritten. On a failed fetch, no rows are changed. Up to 100 most recent commits per sync run's fetch — see ADR-010 for the documented gap limitation.

## Consequences

### Positive

- A failed contributors or commits fetch no longer blocks sync completion for mandatory data.
- Per-category freshness is observable — the UI can indicate when each category was last successfully synced.
- README (TEXT column), languages (JSONB column) and file tree (JSONB column) storage shapes are decided, removing the open questions from ADR-010 and `docs/adr/README.md`.
- Contributors storage shape is decided (separate table, unique on `(github_repository_id, github_user_id)`), removing the remaining storage open question from ADR-010.
- Commits are classified as optional: a failed commits fetch does not block `SYNCED`. Because commits are history data (append-only), there is no data loss on a failed fetch — no rows are deleted.

### Negative

- Data across categories for the same repository may have different freshness at any point in time.
- An additional table (`github_sync_category_status`) adds schema surface.
- The mandatory/optional distinction must be maintained consistently across implementation and tests.

## Not decided by this ADR

- **File content retrieval for code viewer**: whether file content is fetched on demand from GitHub with a short-lived cache, or stored locally in PostgreSQL. Provisional direction: on-demand requests to GitHub. Not confirmed; a separate decision is required before implementation.
- **Sync status API endpoint contract**: provisional direction is a `GET` endpoint returning the latest `github_sync_jobs` row together with `github_sync_category_status` rows for that repository. This direction is not confirmed — a separate decision is required before implementation.

## Refines

ADR-010-github-evidence-data-model-v1.md — this ADR does not replace or invalidate ADR-010. It adds a mandatory/optional category distinction, per-category transaction semantics and storage shape decisions that ADR-010 explicitly left open.
