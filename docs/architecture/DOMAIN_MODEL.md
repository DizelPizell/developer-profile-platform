# Domain Model and Use Cases

## Bounded contexts

### Identity
GitHub OAuth login (register and login unified), logout, sessions, current user.

### Profile
Professional profile, slug, publication state, experience, education, skills, featured projects.

### Projects
Project lifecycle, context, technologies, screenshots, demo, repository association, showcase.

### GitHub
Public repository listing, linking, import, synchronization, normalized technical data. Public data only, read with the app's credentials; no user token (ADR-016).

### Analytics
Event collection, profile metrics, project metrics and funnel metrics.

### Files
Object storage, uploads and access policy.

## Main workflow

```text
GitHub OAuth login -> Profile -> Public repository list
-> Import repository, or link an existing project -> Enrich project -> Showcase
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
- ListOwnProjects
- GetOwnProject
- CreateProject
- UpdateProject
- DeleteProject
- PublishProject
- ArchiveProject
- ChangeProjectVisibility
- FeatureProject
- UnfeatureProject

GitHub:
- ListPublicRepositories
- LinkRepository
- UnlinkRepository
- ImportRepository
- RequestRepositorySync
- SynchronizeRepository (worker)

ConnectGitHub and DisconnectGitHub are not part of V1: the user grants no repository access (ADR-016).

Analytics:
- TrackEvent
- GetProfileAnalytics
- GetProjectAnalytics

## User and session

User fields: `id`, `github_user_id` (unique, stable GitHub numeric id), `github_login` (convenience, not stable), `email` (nullable, not unique), `created_at`.

One User has exactly one GitHub Account (1:1). In V1 it holds no token: repository data is public and read with the app's credentials (ADR-016-github-access-v1.md). If a token is ever stored, ADR-003-github-token-storage.md applies.

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

Jobs are created on link and import, by a manual sync (at most every 10 minutes per repository) and every 24 hours by the worker for repositories linked to a `PUBLISHED` project. A rate-limit answer is not a failure: the job waits for the limit's reset without using an attempt, and the worker claims nothing until then. Two 404s in a row mark the repository unavailable (`github_repositories.unavailable_since`, a repository fact, not sync status). The cabinet project response carries `github.sync`; there is no separate status endpoint. See ADR-018-github-sync-v1.md.

External GitHub identifiers are unique.

## Repository link

A project links at most one repository; a repository is shared and may be linked by projects of several users. A link records the developer's relation to the repository from GitHub data: `OWNER` (the repository owner's id is the user's `github_user_id`), `CONTRIBUTOR` (the user is in the contributor list) or `NONE` (found by a later sync). Linking is refused unless the relation is `OWNER` or `CONTRIBUTOR`. With `NONE` or an unavailable repository the link stays, and the GitHub data is hidden publicly. See ADR-017-repository-linking-and-import.md and ADR-019-public-github-data.md.

## GitHub Evidence categories

V1 synchronizes only repository metadata and programming languages (ADR-018-github-sync-v1.md). The other categories are deferred, not rejected; the table gives the classification they keep when they return (ADR-011).

| Category | In V1 | Classification | Failure behaviour |
|---|---|---|---|
| Repository metadata | Yes | Mandatory | Job retry → FAILED |
| Programming languages | Yes | Mandatory | Job retry → FAILED |
| README | Deferred | Mandatory | Job retry → FAILED |
| File tree metadata | Deferred | Mandatory | Job retry → FAILED |
| Contributors | Deferred (the list is read only for the relation, not stored) | Optional | Tolerated; existing data preserved; job may still reach SYNCED |
| Commits | Deferred | Optional (history, not snapshot) | Tolerated; existing commits preserved (append-only, ADR-010); job may still reach SYNCED |

Each successfully fetched category (snapshot or history) is committed in its own short transaction. No single transaction covers the entire job. See ADR-011-partial-sync-success.md.

## GitHub Evidence storage shape

- **Repository metadata**: columns on `github_repositories` (field list: ADR-017).
- **README** (deferred): TEXT column on `github_repositories`, replaced wholesale (ADR-011).
- **Languages**: JSONB column on `github_repositories`, replaced wholesale.
- **File tree** (deferred): JSONB column on `github_repositories`, replaced wholesale on each successful fetch. Configurable entry limit; truncation is a final outcome, not a retry trigger — see ADR-011-partial-sync-success.md.
- **Contributors** (deferred): separate table `github_contributors` (snapshot, upsert + delete missing per successful fetch).
- **Commits** (deferred): separate table `github_commits` (history, append-only, `ON CONFLICT DO NOTHING`).

Full evidence scope, of which V1 keeps metadata and languages (ADR-018): repository metadata, README, languages, file tree metadata (`path`, `type`, `sha`, `size`, no content), contributors, commits (up to 100 most recent per sync run). Dependencies, Pull Requests, Releases and CI/CD are not part of the required V1 scope; file content is not stored in V1. See ADR-010-github-evidence-data-model-v1.md and ADR-011-partial-sync-success.md.

## Project import

Importing a repository creates an Imported Project: a `DRAFT` + `PRIVATE` project whose title is the repository name, with every other field empty, linked to the repository. The developer enriches it with role, contribution, description and other context. GitHub's own data stays in the GitHub block and is not copied into project fields (ADR-017).

Role and contribution are plain fields on the Project (`projects.role`, `projects.contribution`), not a separate entity — see ADR-004-project-contribution.md.

## Project ownership

A Project belongs to one User (`projects.owner_id`). A user has at most 50 projects (`PROJECT_LIMIT_REACHED`). A project of another user is indistinguishable from a missing one (same 404). See ADR-015-project-model.md.

## Project lifecycle and visibility

Project lifecycle:

```text
DRAFT -> PUBLISHED -> ARCHIVED
            ^             |
            +-- publish --+
```

Project visibility (a separate concept from lifecycle):

```text
PUBLIC
PRIVATE
```

Lifecycle describes preparation/publication state. Visibility describes whether a published project is publicly exposed. See ADR-005-project-lifecycle-and-visibility.md.

Allowed combinations (ADR-015-project-model.md); any other is rejected in the domain layer and by a database CHECK:

| Lifecycle | Visibility |
|---|---|
| DRAFT | PRIVATE |
| PUBLISHED | PUBLIC |
| PUBLISHED | PRIVATE |
| ARCHIVED | PRIVATE |

Transitions (idempotent):

- **PublishProject**: DRAFT or ARCHIVED → PUBLISHED + PUBLIC, after the completeness check. Already PUBLISHED: no change.
- **ArchiveProject**: PUBLISHED → ARCHIVED + PRIVATE. Already ARCHIVED: no change. DRAFT: `PROJECT_TRANSITION_INVALID`.
- **ChangeProjectVisibility**: only while PUBLISHED; otherwise `PROJECT_TRANSITION_INVALID`.

There is no transition back to DRAFT in Phase 3.

A project is public only when it is PUBLISHED + PUBLIC and its owner's profile is PUBLISHED. Unpublishing the profile hides its projects without changing their states or featured positions.

## Project fields and technologies

Phase 3 fields (plain text, all optional while DRAFT): `title`, `summary` (short description), `description` (full description), `problem`, `results`, `role`, `contribution`. Technologies are a shared catalogue; a project has 0–20 of them in the developer's order, names compared ignoring case. See ADR-015-project-model.md.

## Featured projects

A featured project is a Project Showcase record: the project, its owner's profile and a position 1..3 without gaps. At most three per profile, enforced by the database. Only a PUBLISHED + PUBLIC project can be featured (`PROJECT_NOT_FEATURABLE`); a fourth gives `FEATURED_LIMIT_REACHED`. Archiving, hiding or deleting a project removes it from featured projects and closes the gap. ReorderFeaturedProjects takes the complete featured set in the new order (`FEATURED_ORDER_MISMATCH` otherwise). See ADR-015-project-model.md.

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

Minimum, to move a project from DRAFT or ARCHIVED to PUBLISHED:
- title
- summary (the short description)
- role
- contribution
- at least one technology

`description` (the full description), `problem` and `results` are optional. Demo, GitHub and screenshots are optional. Otherwise `PROJECT_INCOMPLETE` with the missing fields.

A PUBLISHED project cannot lose a required field through an update (same error). Publishing always makes the project PUBLIC; visibility is changed afterwards and is not part of publish validation. See ADR-015-project-model.md.
