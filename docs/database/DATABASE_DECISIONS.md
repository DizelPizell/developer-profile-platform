# Database Decisions

## Purpose

This document records database-level decisions from architecture discussions.

## Source of truth

PostgreSQL is the application state source of truth.

## Core entities

```text
users
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
github_commits

analytics_events

files
```

Proposed, not yet confirmed (see ADR-010-github-evidence-data-model-v1.md and Open Decisions in `docs/adr/README.md`): a README entity, a languages entity, a file-tree-entries entity, a contributors entity. Their storage shape (separate table vs field/JSONB) and the exact `github_repositories` field list are not fixed by this document.

GitHub sync status storage is resolved: `github_sync_jobs` is the single source of truth, one row per logical sync job, retries reuse the same row (`attempt_count`) — see ADR-009-github-sync-worker-execution-model.md. `github_repositories` does not duplicate sync status. `outbox_events` remains removed; it existed only to support the Kafka-based transport rejected in ADR-008-no-kafka-outbox-v1.md.

## Important constraints

- `users.email` is unique.
- One user has one profile.
- `profiles.slug` is unique.
- One project has at most one showcase record.
- One project has at most one Demo.
- One project has at most one linked GitHub repository in V1.
- GitHub external IDs are unique.
- Featured projects are limited to three per profile.
- `projects.status` is one of DRAFT, PUBLISHED, ARCHIVED (see ADR-005-project-lifecycle-and-visibility.md).
- `projects.visibility` is one of PUBLIC, PRIVATE, independent of `projects.status`.
- GitHub sync must be idempotent.
- `github_sync_jobs` allows at most one row with `status IN ('QUEUED','SYNCING')` per `github_repository_id` (partial unique index) — see ADR-009-github-sync-worker-execution-model.md.
- `github_commits` is unique on `(github_repository_id, sha)`; inserted idempotently (`ON CONFLICT ... DO NOTHING`); never automatically deleted; the 100-most-recent limit applies per sync run's fetch, not to the total rows stored for a repository — see ADR-010-github-evidence-data-model-v1.md.
- Snapshot GitHub data (repository metadata, README, languages, file tree, contributors) and history GitHub data (commits) have different deletion rules: snapshot rows absent from a complete, successful fetch are deleted; history rows are never automatically deleted — see ADR-010-github-evidence-data-model-v1.md.

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
