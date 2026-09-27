# API Contract V1

Base path: `/api/v1`

## Auth

```http
POST /auth/register
POST /auth/login
POST /auth/logout
GET  /auth/me
```

## Profile

```http
GET   /profile
PATCH /profile
POST  /profile/publish
POST  /profile/unpublish
```

## Public

```http
GET /public/profiles/{slug}
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

## Error shape

```json
{
  "error": {
    "code": "PROJECT_NOT_FOUND",
    "message": "Project was not found"
  }
}
```

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

This is the preliminary contract. Exact schemas should be finalized during implementation and reflected in generated OpenAPI.
