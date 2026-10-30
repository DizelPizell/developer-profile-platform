# ADR-012: GitHub OAuth-Only Authentication

## Status

Accepted

Note (2026-10-30): partly superseded by ADR-016-github-access-v1.md. The separate repository-access consent (`/integrations/github/connect`) and its stored token are not part of V1: repository data is read with the app's credentials, and no user token is stored. Login itself is unchanged.

## Context

Legacy ADR `005-authentication.md` established HTTP-only cookie sessions as the session mechanism and described GitHub OAuth as "a separate account integration." This left the primary login method — email + password, GitHub OAuth, or both — unspecified. The PRD listed "registration", "login", and "recovery" as authentication features, implying email-based credentials.

The platform's core value is showing real developer work backed by GitHub evidence. Requiring a separate email + password credential adds implementation cost (password storage, hashing, recovery flow) without user-facing benefit: the target audience universally has GitHub accounts. GitHub OAuth-only simplifies the authentication path and removes the need for a password field on `users`.

## Decision

### GitHub OAuth as the only login mechanism

V1 supports login via GitHub OAuth exclusively. There is no email + password registration and no password recovery flow.

Registration and login are unified: a developer authenticating for the first time has an account created automatically. On subsequent logins the existing account is retrieved by `github_user_id`.

Recruiters and public visitors do not authenticate in V1.

### Minimal scopes at login; separate consent for repository access

The login OAuth flow requests **no scopes** (empty scope). GitHub still returns a user profile including `id`, `login`, and `email` (if public) with a no-scope token, which is sufficient to identify the user. The GitHub access token issued during login is **not stored**.

Repository access (required for the import/sync features) is requested through a separate OAuth consent flow during the GitHub integration phase (`/integrations/github/connect`). That token is stored encrypted per ADR-003-github-token-storage.md.

### OAuth state parameter is required

The `state` parameter must be generated and validated on callback to prevent CSRF attacks against the OAuth flow.

Implementation: `state` is `secrets.token_urlsafe(32)` and is kept in the browser in an **HttpOnly cookie** `oauth_state` (`Path=/api/v1/auth/github`, `SameSite=Lax`, `Max-Age=600`, `Secure` outside development). The server keeps no record of it. On callback the query `state` is compared with the cookie using `secrets.compare_digest`. The cookie is deleted on every callback exit, including errors. A replayed callback fails because the cookie is gone and GitHub accepts an authorization code only once.

### Callback errors redirect to the frontend

The user reaches `GET /auth/github/callback` by browser navigation, so a JSON error body would be shown to them raw. Every error of the callback therefore ends with a redirect to `{FRONTEND_URL}/login?error=<CODE>`, with the same status as the successful redirect (302).

- `<CODE>` comes from a closed list: `ACCESS_DENIED`, `INVALID_STATE`, `MISSING_CODE`, `OAUTH_CODE_INVALID`, `GITHUB_UNAVAILABLE`, `INTERNAL_ERROR`. Any other failure (for example `SLUG_CONFLICT` or an unexpected exception) is sent as `INTERNAL_ERROR`.
- Nothing from the request or from GitHub goes into the URL: no `state`, `code`, `error`, `error_description`, response bodies or exception texts. The address is built from `FRONTEND_URL` alone.
- The `oauth_state` cookie is deleted, no session cookie is set, and database changes of the failed attempt are rolled back.
- Logging is unchanged: the 502 reason at WARNING with request id, exception type and GitHub status; unexpected exceptions at ERROR with the traceback. The redirect carries `X-Request-ID`.
- Only the callback behaves this way; every other endpoint, including `GET /auth/github/login`, keeps JSON errors.

### User identifier

The primary identifier of a User is `github_user_id` (GitHub's stable numeric user id). Users who rename their GitHub login are still identified correctly.

`github_login` is stored as a convenience field but is not treated as a stable identifier.

`email` is optional (GitHub users may keep their email private) and is **not unique**. The `users.email unique` constraint is removed.

### User — GitHub Account relationship is 1:1

One User has exactly one linked GitHub Account in V1. The earlier `USER 1:N GITHUB_ACCOUNT` schema relationship is replaced with `USER 1:1 GITHUB_ACCOUNT`.

### Session storage

Sessions are stored server-side in a PostgreSQL table `auth_sessions`. A random opaque token is issued to the browser via an **HttpOnly cookie** (`Path=/`, `SameSite=Lax`, `Secure` in every environment except development — `APP_ENV` is required and is one of `development`, `test`, `production`); only the SHA-256 hash of that token is stored in the database. This prevents session token theft from a database dump.

`auth_sessions` columns: `id`, `user_id`, `token_hash` (unique), `created_at`, `expires_at`.

Logout deletes the session row.

Every login issues a new token. If the login request carries a session cookie, the session with that token is deleted in the same transaction that creates the new one.

Session lifetime is **14 days absolute** — the session expires 14 days after creation regardless of activity. The value is configured via the `SESSION_TTL_DAYS` environment variable.

Session cookies remain HTTP-only, Secure in production, with an appropriate SameSite policy — consistent with legacy ADR `005-authentication.md`.

### Profile slug generation

A profile slug is generated automatically from `github_login` at account creation:

- Characters: lowercase letters, digits, and hyphens only.
- Length: 3–39 characters.
- On conflict: a random 6-character hex suffix is appended (e.g. `alice-3f9a1c`), up to 5 attempts.
- A configurable list of reserved words may not be used as slugs (e.g. `admin`, `api`, `static`).

The slug cannot be changed in V1 (ADR-013-profile-editing-and-origin-check.md); whether to allow it later is an open question there.

## Consequences

### Positive

- No password storage, hashing, or recovery flow required.
- Developers do not need a separate credential; a GitHub account is sufficient.
- `github_user_id` as the stable identifier is robust to GitHub login renames.
- Simpler `users` schema: no `password_hash` column.

### Negative

- Developers without a GitHub account cannot register. This is accepted: the platform's value proposition requires GitHub evidence.
- Two-step OAuth consent (login + separate integration for repository access) adds UX complexity in the import flow.
- GitHub outages or OAuth service disruptions block login entirely.
- Revoking the application's access on GitHub does not end an existing session: it lives until `expires_at`. This follows from not storing the login access token — the server has nothing to re-validate against GitHub.

## Not decided by this ADR

- **Behavior on GitHub login change**: implemented as update-on-next-login (`github_login` and `email` are refreshed from the GitHub API on every login). This resolves the open question from the initial ADR text; the user's slug is never changed automatically.
- **Account deletion**: how a user deletes their account and what happens to their data is not decided.
- **Database settings isolation**: `Settings` requires `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_CALLBACK_URL`, and `FRONTEND_URL` at startup, so Alembic migrations (which only need `DATABASE_URL`) also require the GitHub keys to be present in the environment. Whether to split settings into a minimal `DatabaseSettings` (for migrations) and a full `AppSettings` (for the running app) is not decided.
- **CSRF protection**: resolved for V1 by ADR-013-profile-editing-and-origin-check.md — every `POST`, `PUT`, `PATCH` and `DELETE` (including `/auth/logout`) must carry the frontend's `Origin`; no CSRF token.
- **`__Host-` cookie prefix**: whether to name the session cookie `__Host-session` in production (requires `Secure`, `Path=/`, no `Domain`) is not decided.
- **Expired session cleanup**: expired rows in `auth_sessions` are filtered out but never deleted, and there is no index on `expires_at`. A cleanup mechanism and the index are not decided.
- **Session limit per user**: there is no limit on concurrent sessions per user and no "log out everywhere".
- **`id` in `/auth/me`**: the response includes the internal `users.id`. Whether the frontend needs it is not decided.
- **Secure cookies behind a reverse proxy**: `Secure` is set from `APP_ENV`, not from the request scheme. End-to-end behavior behind nginx (TLS termination, forwarded headers) has not been verified.
- **DateTime vs timestamptz**: `auth_sessions.expires_at` and `auth_sessions.created_at` use SQLAlchemy `DateTime` (naive, no timezone) backed by PostgreSQL `TIMESTAMP WITHOUT TIME ZONE`. The application normalises all timestamps to naive UTC via `_utcnow()`. Consider migrating to `TIMESTAMP WITH TIME ZONE` (`timestamptz`) for correctness if the database server timezone ever changes or a timezone-aware ORM layer is adopted.

## Refines / Supersedes

- **Supersedes the login-method part of legacy ADR `005-authentication.md`**: that ADR described GitHub OAuth as "a separate account integration" and left the primary login method unspecified. This ADR replaces that part: GitHub OAuth is now the only login mechanism. The session/cookie security requirements from that ADR (HTTP-only, Secure, SameSite, CSRF protection) remain in full.
- **Does not affect ADR-003-github-token-storage.md**, which governs the repository-access token stored during the integration flow — that flow is unchanged.
