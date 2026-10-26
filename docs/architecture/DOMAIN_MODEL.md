# Domain Model and Use Cases

## Bounded contexts

### Identity
GitHub OAuth login (register and login unified), logout, sessions, current user.

### Profile
Professional profile, slug, publication state, experience, education, skills, featured projects.

### Projects
Project lifecycle, context, technologies, screenshots, demo, repository association, showcase.

### GitHub
OAuth connection, repository listing, import, synchronization, normalized technical data.

### Analytics
Event collection, profile metrics, project metrics and funnel metrics.

### Files
Object storage, uploads and access policy.

## Main workflow

```text
GitHub OAuth login -> Profile -> Connect GitHub (repo access) -> Repository list
-> Import repository -> Create/enrich project -> Showcase
-> Featured project -> Publish profile
```

## Use cases

Identity:
- LoginWithGitHub
- LogoutUser
- GetCurrentUser

Profile:
- GetOwnProfile
- UpdateProfile
- PublishProfile
- UnpublishProfile
- ReorderFeaturedProjects
- GetPublicProfile

Projects:
- CreateProject
- UpdateProject
- DeleteProject
- PublishProject
- ArchiveProject
- ConfigureProjectShowcase

GitHub:
- ConnectGitHub
- DisconnectGitHub
- ListRepositories
- ImportRepository
- SynchronizeRepository

Analytics:
- TrackEvent
- GetProfileAnalytics
- GetProjectAnalytics

## User and session

User fields: `id`, `github_user_id` (unique, stable GitHub numeric id), `github_login` (convenience, not stable), `email` (nullable, not unique), `created_at`.

One User has exactly one GitHub Account (1:1). A GitHub Account holds the repository-access token, stored encrypted per ADR-003-github-token-storage.md.

Sessions are stored server-side in `auth_sessions`: `id`, `user_id`, `token_hash` (unique), `created_at`, `expires_at`. The session cookie contains a random opaque token; only its hash is stored. See ADR-012-github-oauth-only-authentication.md.

## GitHub sync

```text
NOT_SYNCED -> QUEUED -> SYNCING -> SYNCED
                            \-> FAILED (attempts exhausted, terminal)
                                       ^
                            retryable failure -> QUEUED (with scheduled_at backoff)
```

Synchronization is asynchronous and must be idempotent. It does not use Kafka, Outbox or Redis in V1 — see ADR-008-no-kafka-outbox-v1.md. The worker is a separate process that claims jobs via PostgreSQL polling and `SELECT ... FOR UPDATE SKIP LOCKED` — see ADR-009-github-sync-worker-execution-model.md. Within this lifecycle, `FAILED` is only ever a terminal state (attempts exhausted); a retryable failure transitions the same row directly back to `QUEUED` with a future `scheduled_at`, never resting in `FAILED` while retries remain.

Persisted on `github_sync_jobs` — the single source of truth for job status, never duplicated on `github_repositories`: `status`, `attempt_count`, `scheduled_at`, `last_error`, timestamps.

Per-category freshness is tracked separately in `github_sync_category_status` — one row per `(github_repository_id, category)`: `last_success_at`, `last_error`, `last_error_at`. See ADR-011-partial-sync-success.md.

External GitHub identifiers are unique.

## GitHub Evidence categories

| Category | Classification | Failure behaviour |
|---|---|---|
| Repository metadata | Mandatory | Job retry → FAILED |
| README | Mandatory | Job retry → FAILED |
| Programming languages | Mandatory | Job retry → FAILED |
| File tree metadata | Mandatory | Job retry → FAILED |
| Contributors | Optional | Tolerated; existing data preserved; job may still reach SYNCED |
| Commits | Optional (history, not snapshot) | Tolerated; existing commits preserved (append-only, ADR-010); job may still reach SYNCED |

Each successfully fetched category (snapshot or history) is committed in its own short transaction. No single transaction covers the entire job. See ADR-011-partial-sync-success.md.

## GitHub Evidence storage shape

- **Repository metadata**: columns on `github_repositories`.
- **README**: column (or JSONB field) on `github_repositories`, replaced wholesale.
- **Languages**: JSONB column on `github_repositories`, replaced wholesale.
- **File tree**: JSONB column on `github_repositories`, replaced wholesale on each successful fetch. Configurable entry limit; truncation is a final outcome, not a retry trigger — see ADR-011-partial-sync-success.md.
- **Contributors**: separate table `github_contributors` (snapshot, upsert + delete missing per successful fetch).
- **Commits**: separate table `github_commits` (history, append-only, `ON CONFLICT DO NOTHING`).

Scope: repository metadata, README, languages, file tree metadata (`path`, `type`, `sha`, `size`, no content), contributors, commits (up to 100 most recent per sync run). Dependencies, Pull Requests, Releases and CI/CD are not part of the required V1 scope; file content is not stored in V1. See ADR-010-github-evidence-data-model-v1.md and ADR-011-partial-sync-success.md.

## Project import

Importing a repository creates an Imported Project. The developer enriches it with role, contribution, description and other context.

Role and contribution are plain fields on the Project (`projects.role`, `projects.contribution`), not a separate entity — see ADR-004-project-contribution.md.

## Project lifecycle and visibility

Project lifecycle:

```text
DRAFT -> PUBLISHED -> ARCHIVED
```

Project visibility (independent of lifecycle):

```text
PUBLIC
PRIVATE
```

Lifecycle describes preparation/publication state. Visibility describes whether a project is publicly exposed. Invalid combinations must be rejected in the domain layer. See ADR-005-project-lifecycle-and-visibility.md.

## Profile lifecycle

```text
PRIVATE <-> PUBLISHED
```

Unpublishing a profile returns it to PRIVATE. There is no separate UNPUBLISHED state. See ADR-005-project-lifecycle-and-visibility.md.

## Profile fields and publication

Developer-provided fields: `display_name`, `headline`, `bio` (plain text), `location` — all optional while the profile is PRIVATE. `avatar_url` and `github_login` are GitHub data. The slug cannot be changed in V1.

Publish validation (PRIVATE → PUBLISHED): `display_name` and `headline` must be non-empty; otherwise `PROFILE_INCOMPLETE`. A published profile cannot clear either field. Publish and unpublish are idempotent.

A public profile is visible only while PUBLISHED. Private, missing and malformed slugs are indistinguishable (same 404). See ADR-013-profile-editing-and-origin-check.md.

## Publish validation

Minimum, to move a project from DRAFT to PUBLISHED:
- name
- description
- role
- contribution
- at least one technology

Demo, GitHub and screenshots are optional.

This validation governs the DRAFT -> PUBLISHED lifecycle transition only. Visibility (PUBLIC/PRIVATE) is set independently and is not part of publish validation.
