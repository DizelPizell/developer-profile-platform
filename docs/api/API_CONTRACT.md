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
| `GET /auth/github/callback` | 302 to the frontend, sets the session cookie | 400 `ACCESS_DENIED`, `INVALID_STATE`, `MISSING_CODE`, `OAUTH_CODE_INVALID`; 502 `GITHUB_UNAVAILABLE`; 500 `INTERNAL_ERROR` |
| `POST /auth/logout` | 204, deletes the session and clears the cookie | 403 `CSRF_ORIGIN_INVALID`; 500 `INTERNAL_ERROR` |
| `GET /auth/me` | 200 `MeResponse` | 401 `UNAUTHORIZED`; 500 `INTERNAL_ERROR` |

The callback deletes the `oauth_state` cookie on every response, including errors. `GITHUB_UNAVAILABLE` covers a GitHub timeout, an error status, and an unexpected response body; no GitHub response details are returned.

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

`PublicProfileResponse` (whitelist — never email, internal ids or status):

```json
{
  "slug": "string",
  "display_name": "string | null",
  "headline": "string | null",
  "bio": "string | null",
  "location": "string | null",
  "avatar_url": "string | null",
  "github_login": "string"
}
```

## Projects

```http
GET    /projects
POST   /projects
GET    /projects/{id}
PATCH  /projects/{id}
DELETE /projects/{id}
```

## Showcase

```http
POST   /projects/{id}/showcase
PATCH  /projects/{id}/showcase
DELETE /projects/{id}/showcase
POST   /profile/featured-projects/reorder
```

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
- CORS allows only the frontend origin, with credentials; methods `GET`, `POST`, `PATCH`, `OPTIONS`; request header `Content-Type`; `X-Request-ID` is exposed to the frontend.

## Error shape

```json
{
  "error": {
    "code": "PROJECT_NOT_FOUND",
    "message": "Project was not found",
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
