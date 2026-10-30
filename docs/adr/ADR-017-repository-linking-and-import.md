# ADR-017: Repository Linking and Import

## Status

Accepted.

Resolves the "Imported projects (Phase 5)" open question of ADR-015-project-model.md and fixes the `github_repositories` field list left open by ADR-010 and ADR-011 for V1. Builds on ADR-016-github-access-v1.md.

## Context

A project may point to the GitHub repository it was built in (DEVELOPMENT_PLAN Phase 5). The earlier schema documents modeled repositories as owned by a GitHub account (`GITHUB_ACCOUNT 1:N GITHUB_REPOSITORY`) while also requiring GitHub external ids to be unique. With both rules, two developers who worked on the same repository could not both link it.

Without a user token (ADR-016) the platform cannot ask GitHub which repositories the user can access. What it can read is public: the repository owner's numeric id and the repository's contributor list. Anyone could also type the name of a famous repository, so a link must say how the developer is related to it, in facts and not as a verdict.

## Decision

### Model

- `github_repositories` is shared by all users: one row per GitHub repository, unique on `github_repo_id` (GitHub's numeric repository id). It is not owned by a user or a GitHub account.
- `project_repositories` links a project to a repository: `project_id` is unique (one repository per project), `github_repository_id` references `github_repositories`. Many projects, of different users, may link the same repository.
- A user links a given repository to at most one of their own projects. The database holds this rule (decided in step 5.1, 2026-10-30), as it holds the featured limit (ADR-015): `project_repositories.owner_id` repeats the project's owner, `UNIQUE (owner_id, github_repository_id)` allows one link per user and repository, and the composite foreign key `(project_id, owner_id) → projects (id, owner_id)` keeps `owner_id` equal to the project's owner (it needs `UNIQUE (id, owner_id)` on `projects`). A second link gives 409 `GITHUB_REPOSITORY_ALREADY_LINKED` with `details.project_id`; the API maps the unique violation to this code, as it maps the featured position CHECK to `FEATURED_LIMIT_REACHED`.
- `github_repositories` fields in V1: `id`, `github_repo_id` (BIGINT, unique), `owner_github_id` (BIGINT), `owner_login`, `name`, `full_name`, `html_url`, `description` (nullable), `is_fork`, `parent_full_name` (nullable), `is_archived`, `pushed_at` (nullable), `languages` (JSONB, nullable until the first sync), `unavailable_since` (nullable; see "Unavailable repositories"), `created_at`, `updated_at`. README and the file tree are not stored in V1 (ADR-018).
- `project_repositories` fields: `id`, `project_id` (unique, `ON DELETE CASCADE`), `owner_id` (the project's owner, see above), `github_repository_id` (`ON DELETE RESTRICT`), `relation` (`OWNER`, `CONTRIBUTOR` or `NONE`), `relation_checked_at`, `created_at`.
- Text from GitHub is stored as `TEXT` without length limits: GitHub is the authority, and the API client checks what it accepts (step 5.2). The database checks only the platform's own invariants: `owner_login` and `name` are not blank, `full_name = owner_login || '/' || name`, `html_url` starts with `https://github.com/`, and `languages` is a JSON object in GitHub's shape (`{"language": bytes}`); the order shown is made when it is read.
- `html_url` is stored only when it starts with `https://github.com/`; otherwise it is built from `full_name`.

### Relation

The relation is a fact about the developer and the repository, taken from GitHub data:

- `OWNER` — the repository's `owner.id` equals `users.github_user_id`;
- `CONTRIBUTOR` — the developer's `github_user_id` is in the repository's contributor list (`GET /repos/{owner}/{repo}/contributors`, without anonymous contributors);
- `NONE` — neither, found during a later sync.

The contributor list is read only to compute the relation and is not stored. At most 5 pages of 100 are read (GitHub links at most the first 500 author emails to accounts); if the developer is not found in them, the relation is not `CONTRIBUTOR`.

Public wording states the fact: «Владелец репозитория» or «В списке контрибьюторов (по данным GitHub)». The word «подтверждено» is not used: a link confirms only this relation, not the project's text.

### Linking an existing project

`POST /projects/{id}/repository` with `{"full_name": "owner/name"}` (`POST`, like the showcase actions, so CORS needs no new method):

1. The owner and name are validated against the patterns of ADR-016 before any request.
2. The backend reads the repository (one request) and, if the developer is not its owner, the contributor list (up to 5 requests). This is a bounded check of at most 6 requests, not a synchronization: ADR-008 rules out long syncs inside a request, and nothing here loops over repository content.
3. Not found or not public: 422 `GITHUB_REPOSITORY_NOT_FOUND`. Neither owner nor contributor: 422 `GITHUB_RELATION_NOT_FOUND`, with a message saying that the developer is neither the owner nor in the repository's contributor list according to GitHub. GitHub unreachable: 502 `GITHUB_UNAVAILABLE`. GitHub's rate limit exhausted: 503 `GITHUB_RATE_LIMITED`. In all these cases nothing is stored.
4. On success the repository row is created or updated with the metadata just read, the link is stored with its relation, and a sync job is queued (ADR-018).

Linking replaces the project's previous link. Linking the same repository again re-checks the relation. The project may be in any state. Linking does not change the project's status, visibility or text.

`DELETE /projects/{id}/repository` removes the link; the shared repository row stays. Not linked: 200 without changes.

### Import

`POST /integrations/github/repositories/{id}/import`, where `{id}` is the numeric `github_repo_id` (from the repository list):

- Creates a `DRAFT` + `PRIVATE` project whose `title` is the repository's `name` (at most 100 characters, as GitHub allows); every other project field is empty, and there are no technologies. GitHub's description is not copied into the project: it stays GitHub data, shown in the GitHub block (ADR-019).
- Links the new project as above, with the same checks and errors, in one transaction with the project creation, except that a repository that is not found or not public is 404 `NOT_FOUND`, because it is the resource named in the path. The project limit (50) and `GITHUB_REPOSITORY_ALREADY_LINKED` apply.
- Returns 201 with the project.

Import is a convenience over "create project + link"; an imported project follows every rule of ADR-015.

### Repository list

`GET /integrations/github/repositories` returns the current user's public repositories, read from GitHub in the request (`GET /users/{github_login}/repos`, owner repositories only), one GitHub page per call. Each item carries whether the user already links it to a project. The list is not stored. Repositories the user contributed to but does not own are linked by name through `POST /projects/{id}/repository`.

### Forks

A fork may be linked. It is always shown with «Форк {parent_full_name}», because its languages and description mostly come from the original project. The relation rules are the same.

### Renamed and transferred repositories

The key is `github_repo_id`; `owner_login`, `name`, `full_name` and `html_url` are refreshed by every sync. A transfer changes `owner_github_id`, so the relation is recomputed (ADR-018).

### Unavailable repositories

A repository that GitHub answers with 404 twice in a row is unavailable: `github_repositories.unavailable_since` is set (ADR-018 defines when). This is a fact about the repository, like `is_archived`, not a sync status; ADR-009's rule that sync status lives only in `github_sync_jobs` still holds. While it is set, the GitHub block is hidden publicly and the cabinet shows «Репозиторий недоступен: удалён или стал приватным». A later successful sync clears it.

### Lost relation

If a sync finds the developer neither owner nor contributor, the link stays with `relation = NONE`: the GitHub block is hidden publicly and the cabinet explains why. A later sync that finds the relation again restores it. The link is never removed automatically.

## Consequences

### Positive

- Several developers can link the same repository, and it is synced once for all of them.
- A developer cannot present a repository they are not related to; the public text says exactly what GitHub shows.
- No contributor data about other people is stored.

### Negative

- False negatives: commits under an email not linked to the developer's account, or beyond GitHub's first 500 emails, do not make them a contributor; such a developer cannot link the repository in V1.
- Linking makes up to 6 GitHub requests inside an HTTP request; a slow GitHub makes the link slow (each request has the client timeout).
- Repository rows that no project links any more stay in the table (see "Open questions").

## Alternatives considered

- **Repositories owned by a GitHub account** (the earlier schema): rejected — the same repository could not be linked by two developers without breaking the unique external id.
- **Any public repository, with the relation only displayed**: rejected — a famous repository could be attached to any profile.
- **Storing the contributor list**: rejected for V1 — it is other people's data and is needed only for the relation check.
- **Computing the relation asynchronously after linking**: rejected — the developer would not get an immediate, clear refusal.

## Not verified

To be checked by hand in step 5.2 (DEVELOPMENT_PLAN), without a user token:

- whether `GET /repositories/{id}` reads a public repository by numeric id with app credentials (import and sync rely on it; if it does not work, import takes `owner/name` instead and the contract changes);
- what the API answers for a renamed or transferred repository (the documentation lists `301 Moved Permanently` without details);
- that `GET /users/{username}/repos` with `type=owner` returns only public repositories when called with app credentials.

## Open questions

- Cleanup of `github_repositories` rows that no project links.
- Whether the data of an unavailable repository is deleted after some time.
- Repositories the developer contributed to through an organization, when the contributor list does not show them.
