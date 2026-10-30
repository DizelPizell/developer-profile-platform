# API Contract V1

Base path: `/api/v1`

## Auth

```http
GET  /auth/github/login
GET  /auth/github/callback
POST /auth/logout
GET  /auth/me
```

| Endpoint | Success | Errors |
|---|---|---|
| `GET /auth/github/login` | 302 to GitHub, sets `oauth_state` cookie | 500 `INTERNAL_ERROR` |
| `GET /auth/github/callback` | 302 to the frontend, sets the session cookie | 302 to `{FRONTEND_URL}/login?error=<CODE>`, no JSON body (see below) |
| `POST /auth/logout` | 204, deletes the session and clears the cookie | 403 `CSRF_ORIGIN_INVALID`; 500 `INTERNAL_ERROR` |
| `GET /auth/me` | 200 `MeResponse` | 401 `UNAUTHORIZED`; 500 `INTERNAL_ERROR` |

The session is an HttpOnly cookie set by the callback (ADR-012). Its name comes from `SESSION_COOKIE_NAME`: `developer_session` in `.env.example`, `session` when the variable is unset. OpenAPI declares it as the `cookieAuth` security scheme. Login, callback, logout and `GET /public/profiles/{slug}` need no session (logout clears one if present); every other implemented endpoint requires it and answers 401 `UNAUTHORIZED` without it.

The callback deletes the `oauth_state` cookie on every response, including errors.

Callback errors are redirects, not JSON (ADR-012), because the user arrives by browser navigation. `<CODE>` is one of:

| Code | Cause |
|---|---|
| `ACCESS_DENIED` | GitHub returned `error` (the user declined) |
| `INVALID_STATE` | `state` missing, or not equal to the `oauth_state` cookie |
| `MISSING_CODE` | No `code` in the callback |
| `OAUTH_CODE_INVALID` | GitHub rejected the code (expired or already used) |
| `GITHUB_UNAVAILABLE` | GitHub timed out, returned an error status, or an unexpected response |
| `INTERNAL_ERROR` | Any other failure |

Nothing from the request or from GitHub is copied into the redirect URL. No session cookie is set. The response carries `X-Request-ID`. This is the only endpoint whose errors are not JSON.

`MeResponse`:

```json
{
  "id": "uuid",
  "github_login": "string",
  "email": "string | null",
  "profile_slug": "string | null"
}
```

## Profile

```http
GET   /profile
PATCH /profile
POST  /profile/publish
POST  /profile/unpublish
```

All four require a session and act on the current user's profile; there is no id in the path. See ADR-013-profile-editing-and-origin-check.md.

| Endpoint | Success | Errors |
|---|---|---|
| `GET /profile` | 200 `OwnProfileResponse` | 401 `UNAUTHORIZED` |
| `PATCH /profile` | 200 `OwnProfileResponse` | 401; 403 `CSRF_ORIGIN_INVALID`; 422 `VALIDATION_ERROR`; 422 `PROFILE_INCOMPLETE` (clearing `display_name`/`headline` of a published profile) |
| `POST /profile/publish` | 200 `OwnProfileResponse` (idempotent) | 401; 403 `CSRF_ORIGIN_INVALID`; 422 `PROFILE_INCOMPLETE` |
| `POST /profile/unpublish` | 200 `OwnProfileResponse` (idempotent) | 401; 403 `CSRF_ORIGIN_INVALID` |

Every endpoint may also return 500 `INTERNAL_ERROR`.

`ProfileUpdate` (request body of `PATCH /profile`): any subset of the fields below. A field that is present changes; `null` clears it; unknown fields (including `slug`, `status`, `avatar_url`) give 422 `extra_forbidden`. Values are trimmed, blank becomes `null`, control characters are rejected (`bio` allows newlines); the single-line fields also reject the line and paragraph separators U+2028 and U+2029 (`control_characters`).

```json
{
  "display_name": "string (≤ 100) | null",
  "headline": "string (≤ 160) | null",
  "bio": "string (≤ 2000, plain text) | null",
  "location": "string (≤ 100) | null"
}
```

`OwnProfileResponse`:

```json
{
  "slug": "string",
  "status": "PRIVATE | PUBLISHED",
  "display_name": "string | null",
  "headline": "string | null",
  "bio": "string | null",
  "location": "string | null",
  "avatar_url": "string | null",
  "github_login": "string"
}
```

`PROFILE_INCOMPLETE` details: `{"missing_fields": ["display_name", "headline"]}` (only the missing ones).

## Public

```http
GET /public/profiles/{slug}
```

| Endpoint | Success | Errors |
|---|---|---|
| `GET /public/profiles/{slug}` | 200 `PublicProfileResponse` | 404 `NOT_FOUND`; 500 `INTERNAL_ERROR` |

No session needed. Only `PUBLISHED` profiles; the slug is case-insensitive. A private profile, a missing profile and a malformed slug return the same 404 body as an unknown URL (only `request_id` differs).

`PublicProfileResponse` (whitelist — never email, internal user/profile ids or status):

```json
{
  "slug": "string",
  "display_name": "string | null",
  "headline": "string | null",
  "bio": "string | null",
  "location": "string | null",
  "avatar_url": "string | null",
  "github_login": "string",
  "featured": [
    {
      "id": "uuid",
      "title": "string",
      "summary": "string",
      "role": "string",
      "technologies": ["string"],
      "position": 1,
      "github": "PublicGitHub | null"
    }
  ],
  "other": [
    {
      "id": "uuid",
      "title": "string",
      "summary": "string",
      "role": "string",
      "technologies": ["string"],
      "github": "PublicGitHub | null"
    }
  ]
}
```

`PublicGitHub` (whitelist, ADR-019 — GitHub data about the project's linked repository; nothing else is returned):

```json
{
  "full_name": "string",
  "html_url": "string (https://github.com/...)",
  "description": "string | null",
  "languages": [{"name": "string", "bytes": 0}],
  "pushed_at": "date-time | null",
  "is_fork": false,
  "parent_full_name": "string | null",
  "is_archived": false,
  "relation": "OWNER | CONTRIBUTOR",
  "synced_at": "date-time"
}
```

`github` is `null` when the project has no linked repository, the repository has not been synced successfully yet, the repository is unavailable (two 404s in a row), or the developer is no longer its owner or a contributor (ADR-017, ADR-018). `languages` is ordered by bytes, descending, and may be empty. Date-times are ISO 8601 in UTC (`2026-10-30T12:00:00Z`). Never returned: internal or GitHub ids, ETags, sync states or errors, the file tree, README.

`featured` and `other` contain only projects that are `PUBLISHED` + `PUBLIC` (ADR-015). `featured` is ordered by `position` (1..3); `other` holds the remaining public projects, newest first. Both are empty arrays when there are none. A project carries only the fields shown; never `status`, `visibility`, `description`, `contribution` or timestamps. `technologies` are names in the developer's order. The public project page (`/u/{slug}/projects/{id}` on the frontend) and its endpoint come in Phase 4.

## Projects

```http
GET    /projects
POST   /projects
GET    /projects/{id}
PATCH  /projects/{id}
DELETE /projects/{id}
POST   /projects/{id}/publish
POST   /projects/{id}/archive
POST   /projects/{id}/visibility
```

All require a session and act only on the current user's projects. A missing project, another user's project and a malformed id all return the same 404 `NOT_FOUND` as an unknown URL (only `request_id` differs). A project id is accepted only in the canonical form `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (hex, either case); anything else, including forms without hyphens, in braces or with a `urn:uuid:` prefix, is malformed. See ADR-015-project-model.md.

| Endpoint | Success | Errors |
|---|---|---|
| `GET /projects` | 200 `ProjectListResponse` | 401 |
| `POST /projects` | 201 `ProjectResponse` | 401; 403 `CSRF_ORIGIN_INVALID`; 409 `PROJECT_LIMIT_REACHED`; 422 `VALIDATION_ERROR` |
| `GET /projects/{id}` | 200 `ProjectResponse` | 401; 404 `NOT_FOUND` |
| `PATCH /projects/{id}` | 200 `ProjectResponse` | 401; 403; 404; 422 `VALIDATION_ERROR`; 422 `PROJECT_INCOMPLETE` (emptying a required field of a published project) |
| `DELETE /projects/{id}` | 204 | 401; 403; 404 |
| `POST /projects/{id}/publish` | 200 `ProjectResponse` (idempotent) | 401; 403; 404; 422 `PROJECT_INCOMPLETE` |
| `POST /projects/{id}/archive` | 200 `ProjectResponse` (idempotent) | 401; 403; 404; 409 `PROJECT_TRANSITION_INVALID` (from `DRAFT`) |
| `POST /projects/{id}/visibility` | 200 `ProjectResponse` (idempotent) | 401; 403; 404; 409 `PROJECT_TRANSITION_INVALID` (not `PUBLISHED`); 422 `VALIDATION_ERROR` |

Every endpoint may also return 500 `INTERNAL_ERROR`.

States (ADR-015): a new project is `DRAFT` + `PRIVATE`. Allowed pairs: `DRAFT`+`PRIVATE`, `PUBLISHED`+`PUBLIC`, `PUBLISHED`+`PRIVATE`, `ARCHIVED`+`PRIVATE`.

- publish: `DRAFT` or `ARCHIVED` → `PUBLISHED` + `PUBLIC`; already `PUBLISHED` → no change (a hidden project stays hidden).
- archive: `PUBLISHED` → `ARCHIVED` + `PRIVATE`; already `ARCHIVED` → no change; `DRAFT` → 409.
- visibility: only while `PUBLISHED`; the same value → no change.
- Archiving, hiding and deleting remove the project from featured projects.

`ProjectWrite` (request body of `POST /projects` and `PATCH /projects/{id}`): any subset of the fields below; `POST` may send `{}`. On `PATCH` a field that is present changes, `null` clears it. Unknown fields (including `status`, `visibility`, `id`) give 422 `extra_forbidden`. Text values are trimmed, blank becomes `null`, control characters are rejected; `description`, `problem`, `results` and `contribution` allow newlines (`\r\n` → `\n`); `title`, `summary` and `role` also reject U+2028 and U+2029 (`control_characters`). Technology names collapse any whitespace run, line breaks included, to one space.

```json
{
  "title": "string (≤ 100) | null",
  "summary": "string (≤ 300) | null",
  "description": "string (≤ 5000, plain text) | null",
  "problem": "string (≤ 2000, plain text) | null",
  "results": "string (≤ 2000, plain text) | null",
  "role": "string (≤ 100) | null",
  "contribution": "string (≤ 2000, plain text) | null",
  "technologies": ["string (1–50)"]
}
```

`technologies` replaces the whole list in the given order (at most 20). It cannot be `null`; `[]` clears it. Names are trimmed and inner whitespace is collapsed; two names equal ignoring case give 422 `VALIDATION_ERROR`. A name that already exists ignoring case is linked to the existing technology and shown in its stored spelling.

`ProjectResponse`:

```json
{
  "id": "uuid",
  "status": "DRAFT | PUBLISHED | ARCHIVED",
  "visibility": "PUBLIC | PRIVATE",
  "title": "string | null",
  "summary": "string | null",
  "description": "string | null",
  "problem": "string | null",
  "results": "string | null",
  "role": "string | null",
  "contribution": "string | null",
  "technologies": ["string"],
  "featured_position": "1 | 2 | 3 | null",
  "github": "ProjectGitHub | null"
}
```

`github` is the project's linked repository, or `null` when there is none; see "GitHub" below.

`ProjectListResponse`: `{"items": [ProjectSummary]}`, newest first by creation time, at most 50 items (the project limit), no pagination. `ProjectSummary`:

```json
{
  "id": "uuid",
  "status": "DRAFT | PUBLISHED | ARCHIVED",
  "visibility": "PUBLIC | PRIVATE",
  "title": "string | null",
  "summary": "string | null",
  "technologies": ["string"],
  "featured_position": "1 | 2 | 3 | null"
}
```

`ProjectVisibilityUpdate` (body of `POST /projects/{id}/visibility`): `{"visibility": "PUBLIC | PRIVATE"}`.

`PROJECT_INCOMPLETE` details: `{"missing_fields": ["title", "summary", "role", "contribution", "technologies"]}` (only the missing ones).

## Showcase (featured projects)

```http
POST   /projects/{id}/showcase
DELETE /projects/{id}/showcase
POST   /profile/featured-projects/reorder
```

A featured project is a showcase record with a position 1..3 without gaps; at most three per profile (ADR-015). The profile may be private. `PATCH /projects/{id}/showcase` is not part of the contract until the showcase has its own fields (description, highlights).

| Endpoint | Success | Errors |
|---|---|---|
| `POST /projects/{id}/showcase` | 200 `FeaturedProjectsResponse`; adds the project last; already featured → no change | 401; 403; 404; 409 `PROJECT_NOT_FEATURABLE`; 409 `FEATURED_LIMIT_REACHED` |
| `DELETE /projects/{id}/showcase` | 200 `FeaturedProjectsResponse`; the rest move up; not featured → no change | 401; 403; 404 |
| `POST /profile/featured-projects/reorder` | 200 `FeaturedProjectsResponse` | 401; 403; 409 `FEATURED_ORDER_MISMATCH`; 422 `VALIDATION_ERROR` |

`FeaturedProjectsResponse`:

```json
{
  "items": [
    {"project_id": "uuid", "position": 1}
  ]
}
```

`FeaturedReorderRequest`: `{"project_ids": ["uuid"]}`, the complete current featured set in the new order (0–3 unique UUIDs in the canonical form; anything else gives 422 `VALIDATION_ERROR`). A list that is not the current set gives 409 `FEATURED_ORDER_MISMATCH`; the client should reload.

## GitHub

```http
GET    /integrations/github/repositories
POST   /integrations/github/repositories/{id}/import
POST   /integrations/github/repositories/{id}/sync
POST   /projects/{id}/repository
DELETE /projects/{id}/repository
```

V1 reads only public GitHub data, with the platform's app credentials; the user grants no repository access, so there is no connect, callback or disconnect endpoint (ADR-016). All endpoints require a session; `POST` and `DELETE` require the frontend `Origin` (ADR-013). `{id}` under `/integrations/github/repositories/` is GitHub's numeric repository id (`github_repo_id`) as a positive decimal integer; anything else is 404 `NOT_FOUND`. `{id}` under `/projects/` is the project id, as for every project endpoint. Linking, import and sync rules: ADR-017 and ADR-018.

| Endpoint | Success | Errors |
|---|---|---|
| `GET /integrations/github/repositories?page=N` | 200 `GitHubRepositoryListResponse` | 401; 409 `GITHUB_LOGIN_OUTDATED`; 422 `VALIDATION_ERROR` (`page` not an integer 1..100); 429 `GITHUB_USER_LIMIT_REACHED`; 502 `GITHUB_UNAVAILABLE`; 503 `GITHUB_RATE_LIMITED` |
| `POST /integrations/github/repositories/{id}/import` | 201 `ProjectResponse`: a new `DRAFT` + `PRIVATE` project titled after the repository, linked to it | 401; 403; 404 `NOT_FOUND` (malformed id, or the repository is not found or not public); 409 `PROJECT_LIMIT_REACHED`; 409 `GITHUB_REPOSITORY_ALREADY_LINKED`; 422 `GITHUB_RELATION_NOT_FOUND`; 429 `GITHUB_USER_LIMIT_REACHED`; 502 `GITHUB_UNAVAILABLE`; 503 `GITHUB_RATE_LIMITED` |
| `POST /integrations/github/repositories/{id}/sync` | 202 `GitHubSync`; an active job is reused | 401; 403; 404 `NOT_FOUND` (malformed id, or none of the user's projects links this repository); 429 `GITHUB_SYNC_TOO_SOON`; 429 `GITHUB_USER_LIMIT_REACHED` |
| `POST /projects/{id}/repository` | 200 `ProjectResponse`; replaces the project's previous link; the same repository again re-checks the relation | 401; 403; 404 `NOT_FOUND` (project); 409 `GITHUB_REPOSITORY_ALREADY_LINKED`; 422 `VALIDATION_ERROR`; 422 `GITHUB_REPOSITORY_NOT_FOUND`; 422 `GITHUB_RELATION_NOT_FOUND`; 429 `GITHUB_USER_LIMIT_REACHED`; 502 `GITHUB_UNAVAILABLE`; 503 `GITHUB_RATE_LIMITED` |
| `DELETE /projects/{id}/repository` | 200 `ProjectResponse` with `github: null`; not linked → no change | 401; 403; 404 `NOT_FOUND` |

Every endpoint may also return 500 `INTERNAL_ERROR`.

On every error of link and import nothing is stored, and an existing link stays as it was. A link or import queues a sync job; a link reads GitHub in the request (the repository, once more by id when the name is an old one that GitHub redirects, and at most 5 pages of its contributors), so it may take a few seconds. A link by an old name links the repository under its current name (ADR-017).

The repository list is not stored in the database; a page GitHub returned is kept in the backend's memory for 5 minutes, and `linked_project_id` is read on every call (ADR-017).

`RepositoryLinkRequest` (body of `POST /projects/{id}/repository`): `{"full_name": "owner/name"}`. `owner` matches `^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$`; `name` matches `^[A-Za-z0-9._-]{1,100}$` and is not `.` or `..`. Anything else, and unknown fields, give 422 `VALIDATION_ERROR` before GitHub is called.

`GitHubRepositoryListResponse`: the current user's own public repositories, read from GitHub in the request, 100 per page, most recently pushed first; nothing is stored. `next_page` is `null` on the last page. The list is read by the login stored at sign-in; items owned by another GitHub account are not returned (ADR-017).

```json
{
  "items": [
    {
      "github_repo_id": 0,
      "full_name": "string",
      "html_url": "string",
      "description": "string | null",
      "is_fork": false,
      "is_archived": false,
      "pushed_at": "date-time | null",
      "linked_project_id": "uuid | null"
    }
  ],
  "next_page": "integer | null"
}
```

`linked_project_id` is the user's own project that links the repository, if any. Repositories the user does not own but contributed to are linked by name through `POST /projects/{id}/repository`.

`ProjectGitHub` (the `github` object of `ProjectResponse`, cabinet only):

```json
{
  "github_repo_id": 0,
  "full_name": "string",
  "html_url": "string",
  "description": "string | null",
  "languages": [{"name": "string", "bytes": 0}],
  "pushed_at": "date-time | null",
  "is_fork": false,
  "parent_full_name": "string | null",
  "is_archived": false,
  "relation": "OWNER | CONTRIBUTOR | NONE",
  "unavailable": false,
  "synced_at": "date-time | null",
  "sync": "GitHubSync"
}
```

- `relation`: `NONE` means a sync found the developer neither the owner nor in the contributor list; the GitHub block is hidden publicly until a later sync finds the relation again.
- `unavailable`: GitHub answered 404 twice in a row (deleted or made private); the GitHub block is hidden publicly.
- `synced_at`: the older of the times metadata and languages were last read successfully; `null` before the first successful sync. `languages` is `[]` until then.

`GitHubSync` (also the body of the 202 answer of `POST .../sync`):

```json
{
  "status": "NOT_SYNCED | QUEUED | SYNCING | SYNCED | FAILED",
  "last_success_at": "date-time | null",
  "next_manual_sync_at": "date-time | null"
}
```

`status` is the latest sync job's state, `NOT_SYNCED` when there is none. `next_manual_sync_at` is when `POST .../sync` is allowed again (10 minutes after the repository's latest job was created), `null` if allowed now. Job errors are not returned. The client polls `GET /projects/{id}` while the status is `QUEUED` or `SYNCING`; there is no separate status endpoint (ADR-018).

## Analytics

```http
POST /analytics/events
GET  /analytics/profile
GET  /analytics/projects/{id}
```

## Principles

- Explicit request/response schemas.
- Never expose ORM/domain entities directly.
- Server-side ownership checks.
- Public endpoints expose only public information.
- Sensitive values are never returned.
- Every `POST`, `PUT`, `PATCH` and `DELETE` must carry an `Origin` header equal to the frontend origin (from `FRONTEND_URL`); otherwise 403 `CSRF_ORIGIN_INVALID`. `GET`, `HEAD` and `OPTIONS` are not checked. See ADR-013.
- CORS allows only the frontend origin, with credentials; methods `GET`, `POST`, `PATCH`, `DELETE`, `OPTIONS` (`DELETE` added by ADR-015); request header `Content-Type`; `X-Request-ID` is exposed to the frontend.

## Error shape

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Not found",
    "details": {},
    "request_id": "uuid"
  }
}
```

Every error response, including framework errors, uses this shape:

- `request_id` equals the `X-Request-ID` response header. Every response carries this header. An incoming `X-Request-ID` is reused only if it is a canonical UUID; otherwise a new one is generated.
- 422 `VALIDATION_ERROR`: `details.fields` is a list of `{"loc": [...], "type": "..."}`. Input values are never echoed.
- 404 / 405 and other HTTP errors: `code` is the HTTP status name (`NOT_FOUND`, `METHOD_NOT_ALLOWED`).
- 403 `CSRF_ORIGIN_INVALID`: missing or foreign `Origin` on a state-changing request. The response has `Vary: Origin` and `X-Request-ID` but no `Access-Control-Allow-Origin`.
- 422 `PROFILE_INCOMPLETE`: `details.missing_fields` lists the fields required for publication that are empty.
- 422 `PROJECT_INCOMPLETE`: `details.missing_fields` lists the project fields required for publication that are empty (ADR-015).
- 409 `PROJECT_LIMIT_REACHED`: the user already has the maximum number of projects; `details.limit` (50).
- 409 `PROJECT_TRANSITION_INVALID`: the action is not allowed in the project's current state; `details.status`.
- 409 `PROJECT_NOT_FEATURABLE`: only a `PUBLISHED` + `PUBLIC` project can be featured; `details.status`, `details.visibility`.
- 409 `FEATURED_LIMIT_REACHED`: three projects are already featured; `details.limit` (3).
- 409 `FEATURED_ORDER_MISMATCH`: the reorder list is not the current featured set.
- 502 `GITHUB_UNAVAILABLE`: GitHub timed out, answered with an error status or an unexpected body during the request. GitHub's response is not copied into the error.
- 503 `GITHUB_RATE_LIMITED`: the platform's GitHub request budget is exhausted; `Retry-After` header and `details.retry_after_seconds` (ADR-018).
- 422 `GITHUB_REPOSITORY_NOT_FOUND`: the named repository does not exist or is not public (GitHub does not tell the two apart).
- 422 `GITHUB_RELATION_NOT_FOUND`: the developer is neither the repository's owner nor in its contributor list according to GitHub (ADR-017).
- 409 `GITHUB_REPOSITORY_ALREADY_LINKED`: another of the user's projects already links this repository; `details.project_id`.
- 409 `GITHUB_LOGIN_OUTDATED`: GitHub has no user with the login stored at sign-in, or that login now belongs to another GitHub account; the user renamed their GitHub account since signing in, and signing in again refreshes the login (ADR-017).
- 429 `GITHUB_SYNC_TOO_SOON`: a manual sync of this repository was requested less than 10 minutes after its latest job; `Retry-After` header and `details.retry_after_seconds`.
- 429 `GITHUB_USER_LIMIT_REACHED`: the user's GitHub request budget for the last 60 minutes (60 requests by default) does not cover the operation (a list page 1, a link up to 7, an import up to 6, a new manual sync job 7); GitHub is not called; `Retry-After` header and `details.retry_after_seconds` (ADR-018).
- A resource owned by another user returns the same 404 `NOT_FOUND` as a missing one; a malformed id in a project path is also `NOT_FOUND`, not `VALIDATION_ERROR`.
- 500 `INTERNAL_ERROR`: generic message, empty `details`; the exception is logged server-side with the `request_id`.

## Status codes

- 200 OK
- 201 Created
- 202 Accepted
- 204 No Content
- 400 Bad Request
- 401 Unauthorized
- 403 Forbidden
- 404 Not Found
- 409 Conflict
- 422 Validation Error
- 429 Too Many Requests
- 500 Internal Server Error
- 502 Bad Gateway (upstream GitHub failure)
- 503 Service Unavailable (the platform's GitHub rate limit is exhausted)

This is the preliminary contract. Exact schemas should be finalized during implementation and reflected in generated OpenAPI.
