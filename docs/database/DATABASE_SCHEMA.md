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
GITHUB_CONTRIBUTOR
GITHUB_COMMIT
ANALYTICS_EVENT
```

There is no separate `PROJECT_CONTRIBUTION` entity in V1. `role` and `contribution` are plain fields on `PROJECT` — see ADR-004-project-contribution.md.

README is stored as a TEXT column on `github_repositories`, replaced wholesale on each successful fetch. Programming languages are stored as a JSONB column, replaced wholesale on each successful fetch. File tree is stored as a JSONB column, replaced wholesale on each successful fetch (configurable entry limit; truncation is a final outcome, not a retry trigger) — see ADR-011-partial-sync-success.md.

Contributors are stored as a separate table `github_contributors` (snapshot, upsert + delete missing) — see ADR-011-partial-sync-success.md.

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

GITHUB_ACCOUNT 1:N GITHUB_REPOSITORY
GITHUB_REPOSITORY 0/1 PROJECT_REPOSITORY
GITHUB_REPOSITORY 1:N GITHUB_SYNC_JOB
GITHUB_REPOSITORY 1:N GITHUB_SYNC_CATEGORY_STATUS
GITHUB_REPOSITORY 1:N GITHUB_CONTRIBUTOR
GITHUB_REPOSITORY 1:N GITHUB_COMMIT

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

`id`, `user_id` (unique, FK → users), `avatar_url` (nullable, ≤ 2048, GitHub data refreshed on login), `created_at`. Token columns are added with the repository-access integration (ADR-003).

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
- GitHub user/repository external IDs unique
- GitHub token encrypted at rest
- timestamps on mutable entities
- github_sync_job: at most one row with status in (QUEUED, SYNCING) per github_repository (partial unique index) — see ADR-009-github-sync-worker-execution-model.md
- github_sync_job columns: `id`, `github_repository_id`, `status` (QUEUED/SYNCING/SYNCED/FAILED), `attempt_count`, `scheduled_at`, `last_error`, `created_at`, `updated_at`
- github_sync_category_status: unique on (github_repository_id, category) — one row per pair; columns: `id`, `github_repository_id`, `category`, `last_success_at`, `last_error`, `last_error_at`
- sync status (status, attempt_count, scheduled_at, last_error, timestamps) lives only on github_sync_job, never duplicated on github_repository — see ADR-009-github-sync-worker-execution-model.md
- github_contributor: unique on (github_repository_id, github_user_id); `github_user_id` is the GitHub numeric user id; `login` is a regular field; snapshot data, upsert + delete missing — see ADR-011-partial-sync-success.md
- github_commit: unique on (github_repository_id, sha); never automatically deleted; the 100-most-recent limit applies per sync run's fetch, not to total stored rows — see ADR-010-github-evidence-data-model-v1.md

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
- GitHub external IDs
- github_sync_job repository_id + status (for SKIP LOCKED claim query)
- github_sync_category_status (repository_id, category) unique
- github_contributor (repository_id, github_user_id) (unique)
- github_commit repository_id + sha (unique)
- analytics profile/project + timestamp

Exact SQLAlchemy models and indexes must be reviewed before migrations.
