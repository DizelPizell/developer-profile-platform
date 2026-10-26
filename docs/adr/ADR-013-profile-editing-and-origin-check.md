# ADR-013: Profile Editing, Publication and Origin Check for State-Changing Requests

## Status

Accepted

## Context

After ADR-012 a profile has only a `slug` and a `status`. V1 needs a developer to fill in a profile, publish it and show it on a public page (US-004, US-005, US-006, US-022).

These are the first state-changing endpoints beyond `POST /auth/logout`. ADR-012 left CSRF protection open until that point: the session cookie is `SameSite=Lax`, which stops cross-site requests from carrying it, but not requests from a sibling subdomain (same-site).

## Decision

### Profile fields

| Field | Max length | Notes |
|---|---|---|
| `display_name` | 100 | |
| `headline` | 160 | |
| `bio` | 2000 | Plain text, no markdown; newlines allowed |
| `location` | 100 | |

All four are nullable. `avatar_url` is GitHub data and lives on `github_accounts`, not on `profiles`: it is refreshed from GitHub's user response on every login. A login response without a usable avatar keeps the stored value. Only `https://` URLs up to 2048 characters are accepted; anything else is treated as absent.

### Normalization

Applied to every text field on input:

- leading and trailing whitespace is trimmed;
- an empty result becomes `null`;
- control characters (Unicode category `Cc`) are rejected with 422; `bio` allows `\n`, and `\r\n` is normalized to `\n`;
- length is checked after trimming, in characters.

The database repeats the length limits and rejects blank values with CHECK constraints (`ck_profiles_<field>`).

### Editing

- `PATCH /profile` is a partial update: only fields present in the body change; an explicit `null` clears a field.
- Unknown fields are rejected (422, `extra_forbidden`). `slug`, `status` and `avatar_url` cannot be set through `PATCH`.
- **The slug cannot be changed in V1.** It is generated at account creation (ADR-012) and is the stable public address.
- `updated_at` is maintained by application code, only when a value actually changes.

### Publication

- `POST /profile/publish` requires non-empty `display_name` and `headline`. Otherwise: 422 `PROFILE_INCOMPLETE` with `details.missing_fields`.
- Publishing a `PUBLISHED` profile and unpublishing a `PRIVATE` one return 200 without changes.
- Clearing `display_name` or `headline` on a published profile is rejected with the same error.
- The invariant is duplicated in the database: `ck_profiles_published_complete` — `status <> 'PUBLISHED' OR (display_name IS NOT NULL AND headline IS NOT NULL)`.
- Profile mutations lock the row (`SELECT ... FOR UPDATE`), so the check runs against the row that is written; a concurrent publish and clear cannot both succeed.

### Own and public profile

- `GET /profile`, `PATCH /profile`, `POST /profile/publish`, `POST /profile/unpublish` require a valid session (401 otherwise) and always act on the current user's profile; there is no id in the path.
- `GET /public/profiles/{slug}` returns only `PUBLISHED` profiles. The slug is lowercased first.
- A private profile, a missing profile and a malformed slug all return the same 404 as an unknown URL (`NOT_FOUND`); only `request_id` differs. This prevents probing which slugs exist or are private.
- The public DTO is a whitelist: `slug`, `display_name`, `headline`, `bio`, `location`, `avatar_url`, `github_login`. Never email, internal ids or status.

### Origin check instead of a CSRF token

Every `POST`, `PUT`, `PATCH` and `DELETE` (including `/auth/logout`) must carry an `Origin` header equal to the origin of `FRONTEND_URL` (scheme, host and port, compared after normalization). A missing or different `Origin` gives 403 `CSRF_ORIGIN_INVALID` in the shared error format. `GET`, `HEAD` and `OPTIONS` are not checked and must not change state.

Why this is enough for V1:

- The frontend is a single known origin and talks to the API with `fetch`. Browsers send `Origin` on every non-GET/HEAD `fetch` and form submission, and page scripts cannot set or forge it.
- `SameSite=Lax` already stops cross-site requests from carrying the session cookie. The Origin check also covers same-site attackers (a sibling subdomain), which SameSite does not.
- There is no token to generate, store, rotate or attach to every request.

Non-browser clients without an `Origin` header cannot make state-changing requests with a session cookie. That is intended in V1.

What would change this decision: a frontend served from a different domain or several origins, third-party or non-browser clients using cookie sessions, or a need to support clients that omit `Origin`. Any of these requires a CSRF token (synchronizer or double-submit).

### CORS

`CORSMiddleware` allows only the frontend origin, with credentials, methods `GET`, `POST`, `PATCH`, `OPTIONS`, request header `Content-Type`, and exposes `X-Request-ID`.

Middleware order, outermost first: request id, CORS, Origin check, unhandled-error handler, routes.

- CORS answers preflight requests before the Origin check runs.
- 401, 403 and 500 responses pass through CORS and carry `X-Request-ID`.
- The 500 handler is a middleware inside CORS. A Starlette `Exception` handler runs outside all user middleware, so its responses would have no CORS headers.
- A 403 `CSRF_ORIGIN_INVALID` never carries `Access-Control-Allow-Origin`, because the request's origin is by definition not allowed. It carries `Vary: Origin` and `X-Request-ID`.

## Consequences

### Positive

- A profile can be filled in, published and shown publicly with server-side guarantees: ownership, a whitelisted public DTO, and an invariant enforced in both the domain and the database.
- CSRF protection for V1 without token infrastructure.
- Error responses keep CORS headers and the request id, so the frontend can read and report them.

### Negative

- Requests without `Origin` (curl, scripts, some proxies that strip it) cannot change state with a cookie session.
- `avatar_url` cannot be changed by the developer; it always mirrors GitHub.
- No markdown in `bio` for now.

## Alternatives considered

- **CSRF token (synchronizer or double-submit cookie)**: robust for any client, but adds state and plumbing that a single-origin SPA does not need yet.
- **`SameSite=Strict` session cookie**: a visitor arriving from an external link would look logged out, and it still does not cover same-site attackers.
- **`Referer` check**: `Referer` is stripped more often than `Origin` (referrer policies, privacy settings), so it would reject legitimate requests.

## Not decided by this ADR

- **Markdown in `bio`**: whether to support it, and how to render it safely.
- **Profile photo upload**: a developer-provided photo instead of the GitHub avatar (needs object storage, ADR legacy `007-object-storage.md`).
- **Slug change**: whether a developer may change the slug, and what happens to old links.
- **Rate limiting** on profile mutations and the public endpoint.
- **`__Host-` cookie prefix** for the session cookie in production (also listed in ADR-012).
