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

`ProfileUpdate` (request body of `PATCH /profile`): any subset of the fields below. A field that is present changes; `null` clears it; unknown fields (including `slug`, `status`, `avatar_url`) give 422 `extra_forbidden`. Values are trimmed, blank becomes `null`, control characters are rejected (`bio` allows newlines).

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
      "position": 1
    }
  ],
  "other": [
    {
      "id": "uuid",
      "title": "string",
      "summary": "string",
      "role": "string",
      "technologies": ["string"]
    }
  ]
}
```

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

All require a session and act only on the current user's projects. A missing project, another user's project and a malformed id all return the same 404 `NOT_FOUND` as an unknown URL (only `request_id` differs). See ADR-015-project-model.md.

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

`ProjectWrite` (request body of `POST /projects` and `PATCH /projects/{id}`): any subset of the fields below; `POST` may send `{}`. On `PATCH` a field that is present changes, `null` clears it. Unknown fields (including `status`, `visibility`, `id`) give 422 `extra_forbidden`. Text values are trimmed, blank becomes `null`, control characters are rejected; `description`, `problem`, `results` and `contribution` allow newlines (`\r\n` → `\n`).

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
  "featured_position": "1 | 2 | 3 | null"
}
```

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

`FeaturedReorderRequest`: `{"project_ids": ["uuid"]}`, the complete current featured set in the new order (0–3 unique UUIDs). A list that is not the current set gives 409 `FEATURED_ORDER_MISMATCH`; the client should reload.

## GitHub

```http
GET    /integrations/github/connect
GET    /integrations/github/callback
GET    /integrations/github/repositories
POST   /integrations/github/repositories/{id}/import
POST   /integrations/github/repositories/{id}/sync
DELETE /integrations/github
```

Open question: how a client learns that an asynchronous sync job has finished (a dedicated status endpoint, a `sync_status` field on the repository list, or another mechanism) is not decided. Do not assume a specific mechanism until this is resolved.

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
- CORS allows only the frontend origin, with credentials; methods `GET`, `POST`, `PATCH`, `DELETE`, `OPTIONS` (`DELETE` added by ADR-015; the code change in `backend/app/main.py` comes with the Phase 3 implementation); request header `Content-Type`; `X-Request-ID` is exposed to the frontend.

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

This is the preliminary contract. Exact schemas should be finalized during implementation and reflected in generated OpenAPI.
