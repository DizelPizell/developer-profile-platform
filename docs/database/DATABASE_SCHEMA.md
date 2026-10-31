# Database Schema V1

This document is reconciled with `docs/database/DATABASE_DECISIONS.md` and the ADRs in `docs/adr/`. Where the two database documents could drift, `DATABASE_DECISIONS.md` records the decision and this file records the resulting shape.

## Entities

```text
USER
AUTH_SESSION
PROFILE
EXPERIENCE
EDUCATION
SKILL
PROJECT
PROJECT_SHOWCASE
TECHNOLOGY
PROJECT_TECHNOLOGY
PROJECT_SCREENSHOT
PROJECT_REPOSITORY
PROJECT_DEMO
GITHUB_ACCOUNT
GITHUB_REPOSITORY
GITHUB_SYNC_JOB
GITHUB_SYNC_CATEGORY_STATUS
GITHUB_CONTRIBUTOR (deferred, not in V1)
GITHUB_COMMIT (deferred, not in V1)
ANALYTICS_EVENT
```

There is no separate `PROJECT_CONTRIBUTION` entity in V1. `role` and `contribution` are plain fields on `PROJECT` — see ADR-004-project-contribution.md.

V1 stores only repository metadata and languages (ADR-018-github-sync-v1.md). Programming languages are a JSONB column on `github_repositories`, replaced wholesale on each successful fetch. README, file tree, contributors and commits are deferred, not rejected; when they return, README is a TEXT column, the file tree a JSONB column (configurable entry limit; truncation is a final outcome, not a retry trigger) and contributors and commits separate tables, as ADR-011-partial-sync-success.md fixes.

## Relationships

```text
USER 1:1 PROFILE
USER 1:N AUTH_SESSION
USER 1:N EXPERIENCE
USER 1:N EDUCATION
USER 1:N SKILL (not in Phase 3; see ADR-015)
USER 1:1 GITHUB_ACCOUNT
USER 1:N PROJECT (owner)

PROFILE 1:N PROJECT_SHOWCASE (0..3)
PROJECT 1:0/1 PROJECT_SHOWCASE

PROJECT 1:N PROJECT_TECHNOLOGY
TECHNOLOGY 1:N PROJECT_TECHNOLOGY
PROJECT 1:N PROJECT_SCREENSHOT
PROJECT 0/1 PROJECT_DEMO
PROJECT 0/1 PROJECT_REPOSITORY

GITHUB_REPOSITORY 1:N PROJECT_REPOSITORY (shared by all users; ADR-017)
GITHUB_REPOSITORY 1:N GITHUB_SYNC_JOB
GITHUB_REPOSITORY 1:N GITHUB_SYNC_CATEGORY_STATUS
GITHUB_REPOSITORY 1:N GITHUB_CONTRIBUTOR (deferred)
GITHUB_REPOSITORY 1:N GITHUB_COMMIT (deferred)

PROFILE/PROJECT 1:N ANALYTICS_EVENT
```

## User fields

`id`, `github_user_id` (unique), `github_login`, `email` (nullable, not unique), `created_at`.

Primary identifier is `github_user_id` (stable GitHub numeric id). See ADR-012-github-oauth-only-authentication.md.

## Auth session fields

`id`, `user_id` (FK → users), `token_hash` (unique), `created_at`, `expires_at`.

Cookie contains a random opaque token; only its hash is stored. Logout deletes the row. See ADR-012-github-oauth-only-authentication.md.

## Profile fields

`id`, `user_id` (unique, FK → users), `slug` (unique), `status` (PRIVATE/PUBLISHED), `display_name` (≤ 100), `headline` (≤ 160), `bio` (≤ 2000, plain text), `location` (≤ 100), `created_at`, `updated_at`.

The four text fields are nullable; stored values are trimmed and never blank. `updated_at` is set by application code when a value changes. See ADR-013-profile-editing-and-origin-check.md.

## GitHub account fields (current)

`id`, `user_id` (unique, FK → users), `avatar_url` (nullable, ≤ 2048, GitHub data refreshed on login), `created_at`. No token columns: V1 stores no user GitHub token (ADR-016-github-access-v1.md). Repositories do not belong to a GitHub account.

## GitHub repository fields (ADR-017)

`id`, `github_repo_id` (BIGINT, unique), `owner_github_id` (BIGINT), `owner_login` (TEXT), `name` (TEXT), `full_name` (TEXT), `html_url` (TEXT, `https://github.com/...` only), `description` (TEXT, nullable), `is_fork` (BOOLEAN), `parent_full_name` (TEXT, nullable), `is_archived` (BOOLEAN), `pushed_at` (nullable), `languages` (JSONB object `{"language": bytes}`, nullable until the first sync), `unavailable_since` (nullable), `created_at`, `updated_at`.

Text from GitHub has no length limit: GitHub is the authority and the API client checks what it accepts. CHECKs hold the platform's invariants only: `ck_github_repositories_names` (`owner_login` and `name` not blank), `ck_github_repositories_full_name` (`full_name = owner_login || '/' || name`), `ck_github_repositories_html_url` (`starts_with(html_url, 'https://github.com/')`), `ck_github_repositories_languages` (`languages` is NULL or a JSON object).

Shared by all users: one row per GitHub repository, whoever links it. `unavailable_since` is set after two 404s in a row and cleared by a successful sync (ADR-018); it is a repository fact, not sync status. Rows that no project links are kept (cleanup is an open question of ADR-017).

## Project repository fields (ADR-017)

`id`, `project_id` (unique), `owner_id` (the project's owner), `github_repository_id` (FK → github_repositories, `ON DELETE RESTRICT`), `relation` (VARCHAR(20): OWNER/CONTRIBUTOR/NONE, `ck_project_repositories_relation`), `relation_checked_at`, `created_at`.

`(project_id, owner_id)` is a foreign key to `projects (id, owner_id)` with `ON DELETE CASCADE`; `projects` carries `UNIQUE (id, owner_id)` (`uq_projects_id_owner`) as its target. Deleting a project or its user removes the link; the repository row stays.

One repository per project. A user links a given repository to at most one of their projects: `UNIQUE (owner_id, github_repository_id)` (`uq_project_repositories_owner_repository`); the composite foreign key keeps `owner_id` equal to the project's owner. The contributor list used for `relation` is not stored.

## GitHub sync fields (ADR-009, ADR-018)

`github_sync_jobs`: `id`, `github_repository_id` (FK → github_repositories, `ON DELETE CASCADE`), `status` (VARCHAR(20): QUEUED/SYNCING/SYNCED/FAILED, default QUEUED, `ck_github_sync_jobs_status`), `attempt_count` (INTEGER, default 0, `>= 0`, `ck_github_sync_jobs_attempt_count`), `scheduled_at` (default `now()`), `last_error` (TEXT, nullable), `created_at`, `updated_at`. One row per logical sync request; retries reuse it. `updated_at` is set on every status change, and the watchdog finds a stale `SYNCING` job by it.

Indexes: `uq_github_sync_jobs_active` (unique `github_repository_id` WHERE status IN ('QUEUED', 'SYNCING')) — one active job per repository, and an enqueue is `INSERT ... ON CONFLICT (github_repository_id) WHERE status IN ('QUEUED', 'SYNCING') DO NOTHING`; `ix_github_sync_jobs_claim` (`scheduled_at` WHERE status = 'QUEUED') — the worker's claim with `SKIP LOCKED`; `ix_github_sync_jobs_repository_created` (`github_repository_id`, `created_at`) — the latest job (the status shown), the 10-minute manual pause and the 24-hour schedule.

`github_sync_category_status`: `id`, `github_repository_id` (FK → github_repositories, `ON DELETE CASCADE`), `category` (VARCHAR(20): metadata/languages, `ck_github_sync_category_status_category`), `last_success_at`, `last_error` (TEXT), `last_error_at`, all three nullable; `UNIQUE (github_repository_id, category)` (`uq_github_sync_category_status_repository_category`); `last_error` and `last_error_at` are set together (`ck_github_sync_category_status_error_time`). A row appears with the category's first attempt.

`last_error` in both tables is a fixed label such as `NOT_FOUND`, matching `^[A-Z_]{1,64}$` (`ck_github_sync_jobs_last_error`, `ck_github_sync_category_status_last_error`); GitHub's text is never stored. Both tables cascade from `github_repositories`: a repository that a project links cannot be deleted (`RESTRICT` above), and when an unlinked one is, its sync records go with it. Links made before step 6.1 have no rows: no job means `NOT_SYNCED`. Finished jobs are kept (retention is an open question of ADR-018).

## Project fields (Phase 3)

`id`, `owner_id` (FK → users, `ON DELETE CASCADE`), `status` (VARCHAR(20): DRAFT/PUBLISHED/ARCHIVED, default DRAFT), `visibility` (VARCHAR(20): PUBLIC/PRIVATE, default PRIVATE), `title` (≤ 100), `summary` (≤ 300), `description` (≤ 5000), `problem` (≤ 2000), `results` (≤ 2000), `role` (≤ 100), `contribution` (≤ 2000), `created_at`, `updated_at`.

The seven text fields are nullable `TEXT` with CHECK constraints; stored values are trimmed and never blank. `updated_at` is set by application code when a value changes. Demo, screenshots, repository link and further fields come in later phases. See ADR-015-project-model.md.

## Technology fields

`id`, `name` (`TEXT`, ≤ 50 by CHECK; trimmed, inner whitespace collapsed), `created_at`. Shared by all users; unique ignoring case. The stored spelling is the one used when the row was created.

## Project technology fields

`id`, `project_id` (FK → projects, `ON DELETE CASCADE`), `technology_id` (FK → technologies, `ON DELETE RESTRICT`: technologies are not deleted in V1, and a used one cannot be), `position` (`SMALLINT`, 1..20, the developer's order).

## Project showcase fields

`id`, `project_id` (unique, FK → projects, `ON DELETE CASCADE`), `profile_id` (FK → profiles, `ON DELETE CASCADE`), `position` (`SMALLINT`, 1..3, no gaps), `created_at`. A row means the project is featured. Showcase description and highlights come later. See ADR-015-project-model.md.

## Constraints

- user.github_user_id unique
- user.email nullable, not unique
- profile.user_id unique
- profile.slug unique (lowercase letters, digits, hyphens; length 3–39; reserved words excluded)
- profile.status is one of PRIVATE, PUBLISHED (see ADR-005-project-lifecycle-and-visibility.md)
- profile.display_name / headline / bio / location: CHECK `char_length(x) <= limit AND btrim(x) <> ''` (`ck_profiles_<field>`)
- profile published only when complete: CHECK `status <> 'PUBLISHED' OR (display_name IS NOT NULL AND headline IS NOT NULL)` (`ck_profiles_published_complete`) — see ADR-013
- auth_session.token_hash unique
- auth_session.expires_at enforced at application level
- project belongs to an owner: project.owner_id FK → users `ON DELETE CASCADE`
- project.status is one of DRAFT, PUBLISHED, ARCHIVED (see ADR-005-project-lifecycle-and-visibility.md)
- project.visibility is one of PUBLIC, PRIVATE
- project (status, visibility) is one of (DRAFT, PRIVATE), (PUBLISHED, PUBLIC), (PUBLISHED, PRIVATE), (ARCHIVED, PRIVATE) (`ck_projects_state`) — see ADR-015-project-model.md
- project.title / summary / description / problem / results / role / contribution: CHECK `char_length(x) <= limit AND btrim(x) <> ''` (`ck_projects_<field>`)
- project published only with text fields complete: CHECK `status <> 'PUBLISHED' OR (title, summary, role, contribution IS NOT NULL)` (`ck_projects_published_complete`); "at least one technology" is enforced in the domain only
- at most 50 projects per user: enforced in the domain under a lock on the owner's profile row
- technology.name: CHECK `char_length(name) <= 50 AND btrim(name) <> ''`; unique index on `lower(name)` (`uq_technologies_name_lower`)
- project_technology: unique (project_id, technology_id); unique (project_id, position); position CHECK 1..20 (at most 20 per project)
- project_showcase.project_id unique (a project is featured at most once)
- featured project count <= 3: project_showcase.position CHECK 1..3 and unique (profile_id, position), declared `DEFERRABLE INITIALLY IMMEDIATE` so a reorder is one UPDATE statement — see ADR-015
- only a PUBLISHED + PUBLIC project is featured: enforced in the domain (crosses tables)
- GitHub user/repository external IDs unique (github_repository.github_repo_id unique)
- no GitHub user token is stored in V1 (ADR-016); if one ever is, it is encrypted at rest (ADR-003)
- project_repository.project_id unique; project_repository.relation is one of OWNER, CONTRIBUTOR, NONE; github_repository_id `ON DELETE RESTRICT`
- one repository per user's projects: project_repository unique (owner_id, github_repository_id) (`uq_project_repositories_owner_repository`); (project_id, owner_id) FK → project (id, owner_id) `ON DELETE CASCADE`, with project unique (id, owner_id) (`uq_projects_id_owner`) — ADR-017
- timestamps on mutable entities
- github_sync_job: at most one row with status in (QUEUED, SYNCING) per github_repository (`uq_github_sync_jobs_active`, partial unique index) — see ADR-009-github-sync-worker-execution-model.md; columns and indexes in "GitHub sync fields"
- github_sync_category_status: unique on (github_repository_id, category) — one row per pair; V1 categories are `metadata` and `languages` (ADR-018)
- sync errors are labels (`^[A-Z_]{1,64}$`), never GitHub's text; sync rows cascade from github_repository
- sync status (status, attempt_count, scheduled_at, last_error, timestamps) lives only on github_sync_job, never duplicated on github_repository — see ADR-009-github-sync-worker-execution-model.md; `github_repository.unavailable_since` is a repository fact, not sync status (ADR-017)
- github_contributor (deferred, not created in V1 — ADR-018): unique on (github_repository_id, github_user_id); `github_user_id` is the GitHub numeric user id; `login` is a regular field; snapshot data, upsert + delete missing — see ADR-011-partial-sync-success.md
- github_commit (deferred, not created in V1 — ADR-018): unique on (github_repository_id, sha); never automatically deleted; the 100-most-recent limit applies per sync run's fetch, not to total stored rows — see ADR-010-github-evidence-data-model-v1.md

## Analytics

Events should include:
- event type
- profile/project reference when applicable
- timestamp
- privacy-safe session/context metadata

## Indexing priorities

Consider indexes for:
- user.github_user_id (unique)
- auth_session.token_hash (unique)
- auth_session.user_id
- profile.slug
- project.owner_id (every project query starts from the owner; at most 50 rows per owner, so status and visibility need no separate indexes)
- technology lower(name) (unique)
- project_technology project_id + position (unique)
- project_showcase project_id (unique)
- project_showcase profile_id + position (unique, deferrable)
- github_repository github_repo_id (unique)
- project_repository project_id (unique), github_repository_id (public profile and periodic sync queries)
- github_sync_job github_repository_id WHERE status IN (QUEUED, SYNCING) (unique, partial); scheduled_at WHERE status = QUEUED (the SKIP LOCKED claim); github_repository_id + created_at (the latest job, the manual pause, the daily schedule)
- github_sync_category_status (repository_id, category) unique
- github_contributor (repository_id, github_user_id) (unique), when contributors return
- github_commit repository_id + sha (unique), when commits return
- analytics profile/project + timestamp

Exact SQLAlchemy models and indexes must be reviewed before migrations.
