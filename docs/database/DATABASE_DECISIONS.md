# Database Decisions

## Purpose

This document records database-level decisions from architecture discussions.

## Source of truth

PostgreSQL is the application state source of truth.

## Primary key and identifier types

- **`id` columns**: UUID, generated server-side with `gen_random_uuid()`. Applies to all tables (users, github_accounts, profiles, auth_sessions, and all future tables).
- **`github_user_id`**: BIGINT. GitHub numeric user IDs are currently within int32 range, but BIGINT provides a safe margin.
- **Cascade on user deletion**: `github_accounts`, `profiles`, and `auth_sessions` carry `ON DELETE CASCADE` foreign keys referencing `users.id`. Dependent rows are deleted automatically when a user row is deleted. Account deletion as a product feature (user-initiated flow, data handling) remains an open question per ADR-012.

## Core entities

```text
users
auth_sessions
profiles
experiences
educations
skills

projects
project_showcases
technologies
project_technologies
project_screenshots
project_demo

github_accounts
github_repositories
project_repository

github_sync_jobs
github_sync_category_status
github_contributors
github_commits

analytics_events

files
```

Storage shapes confirmed by ADR-011-partial-sync-success.md:
- **README**: TEXT column on `github_repositories`, replaced wholesale on each successful fetch.
- **Languages**: JSONB column on `github_repositories`, replaced wholesale on each successful fetch.
- **File tree**: JSONB column on `github_repositories`, replaced wholesale on each successful fetch. Configurable entry limit; truncation is a final outcome, not a retry trigger (see ADR-011).
- **Contributors**: separate table `github_contributors` (snapshot, upsert + delete missing per successful fetch).

The exact `github_repositories` field list is not fixed by this document.

GitHub sync status storage is resolved: `github_sync_jobs` is the single source of truth, one row per logical sync job, retries reuse the same row (`attempt_count`) — see ADR-009-github-sync-worker-execution-model.md. `github_repositories` does not duplicate sync status. `outbox_events` remains removed; it existed only to support the Kafka-based transport rejected in ADR-008-no-kafka-outbox-v1.md.

## Important constraints

- `users.github_user_id` is unique (stable GitHub numeric id; primary user identifier — see ADR-012-github-oauth-only-authentication.md).
- `users.email` is nullable and not unique (GitHub users may keep their email private — see ADR-012).
- One user has one GitHub Account (1:1 — see ADR-012). The earlier `USER 1:N GITHUB_ACCOUNT` relationship is replaced.
- `auth_sessions.token_hash` is unique; `auth_sessions` columns: `id`, `user_id`, `token_hash`, `created_at`, `expires_at` — see ADR-012.
- One user has one profile.
- `profiles.slug` is unique; format: lowercase letters, digits, hyphens; length 3–39 characters; reserved words excluded; generated from `github_login` on account creation, conflict resolved with a random 6-character hex suffix — see ADR-012-github-oauth-only-authentication.md. The slug cannot be changed in V1 — see ADR-013-profile-editing-and-origin-check.md.
- `profiles.status` is one of PRIVATE, PUBLISHED — see ADR-005-project-lifecycle-and-visibility.md.
- `profiles.display_name` (≤ 100), `headline` (≤ 160), `bio` (≤ 2000, plain text) and `location` (≤ 100) are nullable TEXT columns; CHECK constraints enforce the length and reject blank values. A `PUBLISHED` profile must have `display_name` and `headline` (`ck_profiles_published_complete`); the same rule is enforced in the domain layer — see ADR-013.
- `github_accounts.avatar_url` is nullable GitHub data, refreshed on every login; a login response without a usable avatar keeps the stored value — see ADR-013.
- One project has at most one showcase record.
- One project has at most one Demo.
- One project has at most one linked GitHub repository in V1.
- GitHub external IDs are unique.
- Featured projects are limited to three per profile.
- `projects.status` is one of DRAFT, PUBLISHED, ARCHIVED (see ADR-005-project-lifecycle-and-visibility.md).
- `projects.visibility` is one of PUBLIC, PRIVATE, independent of `projects.status`.
- GitHub sync must be idempotent.
- `github_sync_jobs` allows at most one row with `status IN ('QUEUED','SYNCING')` per `github_repository_id` (partial unique index) — see ADR-009-github-sync-worker-execution-model.md.
- `github_sync_jobs` columns: `id`, `github_repository_id`, `status`, `attempt_count`, `scheduled_at`, `last_error`, `created_at`, `updated_at`.
- `github_sync_category_status` is unique on `(github_repository_id, category)` — one row per pair, updated after each category attempt — see ADR-011-partial-sync-success.md.
- `github_contributors` is unique on `(github_repository_id, github_user_id)`; `github_user_id` is the GitHub numeric user id; `login` is a regular field; snapshot data, upsert + delete missing per successful contributors fetch — see ADR-011-partial-sync-success.md.
- `github_commits` is unique on `(github_repository_id, sha)`; inserted idempotently (`ON CONFLICT ... DO NOTHING`); never automatically deleted; the 100-most-recent limit applies per sync run's fetch, not to the total rows stored for a repository — see ADR-010-github-evidence-data-model-v1.md.
- Snapshot GitHub data (repository metadata, README, languages, file tree, contributors) and history data (commits) have different deletion rules: snapshot rows absent from a complete, successful fetch are deleted; history rows are never automatically deleted — see ADR-010-github-evidence-data-model-v1.md.
- Contributors and commits are optional sync categories: fetch failures do not block `SYNCED`. Commits are history data (append-only, `ON CONFLICT DO NOTHING`); existing rows are preserved on both success and failure — there is nothing to delete on a failed fetch, and no rows are ever automatically deleted — see ADR-010-github-evidence-data-model-v1.md. Mandatory categories (metadata, README, languages, file tree) cause retry/FAILED on failure — see ADR-011-partial-sync-success.md.

## Deliberately excluded

- separate project contributor entity (role/contribution are plain fields on `projects` — see ADR-004-project-contribution.md);
- `outbox_events` table (existed only to support Kafka-based sync, removed — see ADR-008-no-kafka-outbox-v1.md);
- GitHub Dependencies as a synced entity (deferred pending a separate GitHub API review, not rejected outright — see ADR-010-github-evidence-data-model-v1.md);
- GitHub Pull Requests, Releases and CI/CD as separate synced entities, and storing GitHub file content in PostgreSQL, in V1 (see ADR-010-github-evidence-data-model-v1.md);
- recruiter entities;
- vacancies;
- applications;
- matching;
- AI scores.

## Implementation note

The SQLAlchemy models and Alembic migrations are implementation artifacts.

The architecture documentation is the source for the intended domain decisions. If implementation exposes a contradiction, stop and discuss the contradiction before changing the architecture.
