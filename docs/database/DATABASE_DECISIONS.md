# Database Decisions

## Purpose

This document records database-level decisions from architecture discussions.

## Source of truth

PostgreSQL is the application state source of truth.

## Primary key and identifier types

- **`id` columns**: UUID, generated server-side with `gen_random_uuid()`. Applies to all tables (users, github_accounts, profiles, auth_sessions, and all future tables).
- **`github_user_id`**: BIGINT. GitHub numeric user IDs are currently within int32 range, but BIGINT provides a safe margin.
- **Cascade on user deletion**: `github_accounts`, `profiles`, `auth_sessions` and `projects` (ADR-015) carry `ON DELETE CASCADE` foreign keys referencing `users.id`. Dependent rows are deleted automatically when a user row is deleted. Account deletion as a product feature (user-initiated flow, data handling) remains an open question per ADR-012.
- **Cascade on project deletion**: projects are hard-deleted; `project_showcases` and `project_technologies` carry `ON DELETE CASCADE` foreign keys referencing `projects.id`, and `project_showcases` also cascades from `profiles.id`. `project_technologies.technology_id` is `ON DELETE RESTRICT`: shared technologies are not deleted in V1, and a technology in use cannot be. Tables added later with a `project_id` cascade too unless their own decision says otherwise — see ADR-015-project-model.md.

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
project_repositories

github_sync_jobs
github_sync_category_status
github_contributors (deferred, not in V1)
github_commits (deferred, not in V1)

analytics_events

files
```

V1 GitHub storage (ADR-016, ADR-017, ADR-018):
- **No user token**: V1 reads public data with the app's credentials; `github_accounts` has no token columns (ADR-016).
- **Repositories are shared**: `github_repositories` has one row per GitHub repository, unique on `github_repo_id`, not owned by a user or a GitHub account; `project_repositories` links a project to one repository, and many projects of different users may link the same one (ADR-017). This replaces the earlier `GITHUB_ACCOUNT 1:N GITHUB_REPOSITORY`, which contradicted unique external ids as soon as two developers linked one repository.
- **Field list** of `github_repositories` for V1: fixed by ADR-017 (see `DATABASE_SCHEMA.md`).
- **Stored categories**: metadata (columns) and languages (JSONB column, replaced wholesale on each successful fetch). Nothing else in V1 (ADR-018).

Storage shapes confirmed by ADR-011-partial-sync-success.md for the deferred categories, applied when they return:
- **README**: TEXT column on `github_repositories`, replaced wholesale on each successful fetch.
- **File tree**: JSONB column on `github_repositories`, replaced wholesale on each successful fetch. Configurable entry limit; truncation is a final outcome, not a retry trigger (see ADR-011).
- **Contributors**: separate table `github_contributors` (snapshot, upsert + delete missing per successful fetch).
- **Commits**: separate table `github_commits` (history, append-only).

GitHub sync status storage is resolved: `github_sync_jobs` is the single source of truth, one row per logical sync job, retries reuse the same row (`attempt_count`) — see ADR-009-github-sync-worker-execution-model.md. `github_repositories` does not duplicate sync status; its `unavailable_since` (two 404s in a row) is a fact about the repository, not sync status (ADR-017, ADR-018). `outbox_events` remains removed; it existed only to support the Kafka-based transport rejected in ADR-008-no-kafka-outbox-v1.md.

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
- One project has at most one showcase record (`project_showcases.project_id` unique); a showcase row means the project is featured.
- One project has at most one Demo.
- One project has at most one linked GitHub repository in V1 (`project_repositories.project_id` unique). A user links a given repository to at most one of their projects (domain rule under the owner's profile lock) — see ADR-017-repository-linking-and-import.md.
- `project_repositories.relation` is one of OWNER, CONTRIBUTOR, NONE; set when linking, recomputed by every sync; the contributor list behind it is not stored — see ADR-017.
- `project_repositories.project_id` cascades on project deletion; `github_repository_id` is `ON DELETE RESTRICT`, so a linked repository row cannot be removed.
- GitHub external IDs are unique (`github_repositories.github_repo_id`).
- Featured projects are limited to three per profile, held by the database: `project_showcases.position` CHECK 1..3 and UNIQUE (`profile_id`, `position`). The unique constraint is `DEFERRABLE INITIALLY IMMEDIATE`, so it is checked at the end of each statement and a reorder or gap renumbering is a single `UPDATE`. Positions have no gaps. Only `PUBLISHED` + `PUBLIC` projects are featured; that rule crosses tables and is enforced in the domain — see ADR-015-project-model.md.
- `projects.owner_id` references `users.id`; at most 50 projects per user, checked in the domain under a lock on the owner's profile row.
- `projects.status` is one of DRAFT, PUBLISHED, ARCHIVED (see ADR-005-project-lifecycle-and-visibility.md).
- `projects.visibility` is one of PUBLIC, PRIVATE.
- `(projects.status, projects.visibility)` is one of (DRAFT, PRIVATE), (PUBLISHED, PUBLIC), (PUBLISHED, PRIVATE), (ARCHIVED, PRIVATE) (`ck_projects_state`) — see ADR-015.
- `projects.title` (≤ 100), `summary` (≤ 300), `description` (≤ 5000), `problem` (≤ 2000), `results` (≤ 2000), `role` (≤ 100) and `contribution` (≤ 2000) are nullable TEXT columns; CHECK constraints enforce the length and reject blank values. A `PUBLISHED` project must have `title`, `summary`, `role` and `contribution` (`ck_projects_published_complete`); "at least one technology" is enforced in the domain only — see ADR-015.
- `technologies` is shared by all users; `name` ≤ 50, unique ignoring case (unique index on `lower(name)`); the spelling of the first creator is kept.
- `project_technologies`: unique (`project_id`, `technology_id`) and (`project_id`, `position`), `position` 1..20 — at most 20 technologies per project, in the developer's order.
- GitHub sync must be idempotent.
- `github_sync_jobs` allows at most one row with `status IN ('QUEUED','SYNCING')` per `github_repository_id` (partial unique index) — see ADR-009-github-sync-worker-execution-model.md.
- `github_sync_jobs` columns: `id`, `github_repository_id`, `status`, `attempt_count`, `scheduled_at`, `last_error`, `created_at`, `updated_at`.
- `github_sync_category_status` is unique on `(github_repository_id, category)` — one row per pair, updated after each category attempt — see ADR-011-partial-sync-success.md. V1 categories: `metadata` and `languages`, both mandatory (ADR-018).
- Jobs are queued idempotently (`INSERT ... ON CONFLICT DO NOTHING` on the partial unique index) on link and import, by a manual sync at most every 10 minutes per repository, and every 24 hours by the worker for repositories linked to a `PUBLISHED` project. A rate-limit answer moves the job to `x-ratelimit-reset` without increasing `attempt_count` — see ADR-018-github-sync-v1.md.
- The rules below for contributors, commits, README and file tree apply when those categories return; they are not fetched or stored in V1 (ADR-018).
- `github_contributors` is unique on `(github_repository_id, github_user_id)`; `github_user_id` is the GitHub numeric user id; `login` is a regular field; snapshot data, upsert + delete missing per successful contributors fetch — see ADR-011-partial-sync-success.md.
- `github_commits` is unique on `(github_repository_id, sha)`; inserted idempotently (`ON CONFLICT ... DO NOTHING`); never automatically deleted; the 100-most-recent limit applies per sync run's fetch, not to the total rows stored for a repository — see ADR-010-github-evidence-data-model-v1.md.
- Snapshot GitHub data (repository metadata, README, languages, file tree, contributors) and history data (commits) have different deletion rules: snapshot rows absent from a complete, successful fetch are deleted; history rows are never automatically deleted — see ADR-010-github-evidence-data-model-v1.md.
- Contributors and commits are optional sync categories: fetch failures do not block `SYNCED`. Commits are history data (append-only, `ON CONFLICT DO NOTHING`); existing rows are preserved on both success and failure — there is nothing to delete on a failed fetch, and no rows are ever automatically deleted — see ADR-010-github-evidence-data-model-v1.md. Mandatory categories (metadata, README, languages, file tree) cause retry/FAILED on failure — see ADR-011-partial-sync-success.md.

## Deliberately excluded

- separate project contributor entity (role/contribution are plain fields on `projects` — see ADR-004-project-contribution.md);
- `outbox_events` table (existed only to support Kafka-based sync, removed — see ADR-008-no-kafka-outbox-v1.md);
- GitHub Dependencies as a synced entity (deferred pending a separate GitHub API review, not rejected outright — see ADR-010-github-evidence-data-model-v1.md);
- GitHub Pull Requests, Releases and CI/CD as separate synced entities, and storing GitHub file content in PostgreSQL, in V1 (see ADR-010-github-evidence-data-model-v1.md);
- GitHub user tokens in V1 (see ADR-016-github-access-v1.md);
- README, file tree, contributors and commits in V1 — deferred, not rejected (see ADR-018-github-sync-v1.md);
- recruiter entities;
- vacancies;
- applications;
- matching;
- AI scores.

## Implementation note

The SQLAlchemy models and Alembic migrations are implementation artifacts.

The architecture documentation is the source for the intended domain decisions. If implementation exposes a contradiction, stop and discuss the contradiction before changing the architecture.
