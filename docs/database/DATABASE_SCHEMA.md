# Database Schema V1

This document is reconciled with `docs/database/DATABASE_DECISIONS.md` and the ADRs in `docs/adr/`. Where the two database documents could drift, `DATABASE_DECISIONS.md` records the decision and this file records the resulting shape.

## Entities

```text
USER
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
GITHUB_COMMIT
ANALYTICS_EVENT
```

There is no separate `PROJECT_CONTRIBUTION` entity in V1. `role` and `contribution` are plain fields on `PROJECT` — see ADR-004-project-contribution.md.

Proposed, not yet confirmed (see ADR-010-github-evidence-data-model-v1.md): a README entity, a languages entity, a file-tree-entries entity, a contributors entity. Storage shape (separate table vs field/JSONB) is not decided.

## Relationships

```text
USER 1:1 PROFILE
USER 1:N EXPERIENCE
USER 1:N EDUCATION
USER 1:N SKILL
USER 1:N GITHUB_ACCOUNT

PROFILE 1:N PROJECT_SHOWCASE
PROJECT 1:0/1 PROJECT_SHOWCASE

PROJECT 1:N PROJECT_TECHNOLOGY
TECHNOLOGY 1:N PROJECT_TECHNOLOGY
PROJECT 1:N PROJECT_SCREENSHOT
PROJECT 0/1 PROJECT_DEMO
PROJECT 0/1 PROJECT_REPOSITORY

GITHUB_ACCOUNT 1:N GITHUB_REPOSITORY
GITHUB_REPOSITORY 0/1 PROJECT_REPOSITORY
GITHUB_REPOSITORY 1:N GITHUB_SYNC_JOB
GITHUB_REPOSITORY 1:N GITHUB_COMMIT

PROFILE/PROJECT 1:N ANALYTICS_EVENT
```

## Constraints

- user.email unique
- profile.user_id unique
- profile.slug unique
- project belongs to an owner
- project.status is one of DRAFT, PUBLISHED, ARCHIVED (see ADR-005-project-lifecycle-and-visibility.md)
- project.visibility is one of PUBLIC, PRIVATE, independent of project.status
- featured project count <= 3
- GitHub user/repository external IDs unique
- GitHub token encrypted at rest
- timestamps on mutable entities
- github_sync_job: at most one row with status in (QUEUED, SYNCING) per github_repository (partial unique index) — see ADR-009-github-sync-worker-execution-model.md
- github_commit: unique on (github_repository_id, sha); never automatically deleted; the 100-most-recent limit applies per sync run's fetch, not to total stored rows — see ADR-010-github-evidence-data-model-v1.md
- sync status (status, attempt_count, timestamps, last error) lives only on github_sync_job, never duplicated on github_repository

## Analytics

Events should include:
- event type
- profile/project reference when applicable
- timestamp
- privacy-safe session/context metadata

## Indexing priorities

Consider indexes for:
- profile.slug
- project.owner_id
- project.status
- project.visibility
- showcase profile + order
- GitHub external IDs
- github_sync_job repository_id + status (for SKIP LOCKED claim query)
- github_commit repository_id + sha (unique)
- analytics profile/project + timestamp

Exact SQLAlchemy models and indexes must be reviewed before migrations.
