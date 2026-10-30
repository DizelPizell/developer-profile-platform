# ADR-016: GitHub Access in V1 — Public Data with App Credentials

## Status

Accepted.

Partly supersedes ADR-012-github-oauth-only-authentication.md (the separate repository-access consent) and sets aside ADR-003-github-token-storage.md for V1 (no user token is stored). Both keep their original text with a note.

## Context

Phases 5–6 read repository data from GitHub. ADR-012 planned a second OAuth consent (`/integrations/github/connect`) for repository access, and ADR-003 required the resulting token to be stored encrypted.

What GitHub documents (docs.github.com, read on 2026-10-28; the pages on REST rate limits, OAuth app scopes, and GitHub Apps compared with OAuth apps):

- An OAuth app has no read-only repository scope. `public_repo` grants read **and write** access to public repositories; `repo` grants full read and write access to public and private repositories. An OAuth token does not expire by default.
- Unauthenticated REST requests are limited to 60 per hour per IP address. Requests authenticated with an OAuth app's `client_id` and `client_secret` may read public data at 5,000 per hour per app. A user token has 5,000 per hour per user, shared with every other app and token of that user.
- A GitHub App can request read-only permissions on repositories the user selects, and its tokens are short-lived.

The product shows evidence on public pages. Data from a private repository could not be shown there without disclosing it, and NDA projects already work without GitHub (ADR-015). The login screen promises that the platform has no access to the user's repositories (`docs/frontend/DESIGN.md`).

## Decision

### Public data only

V1 reads only public GitHub data. A repository that GitHub does not return to an unprivileged reader does not exist for the platform (ADR-017 and ADR-018 define what happens when a linked repository disappears).

### App credentials, no user token

- Server-side requests to the GitHub REST API are authenticated with the platform's OAuth App credentials, `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` (the same app as login), sent in an HTTP Basic `Authorization` header. They are never sent as query parameters.
- The platform does not request, receive or store a user token for repository access. The login flow of ADR-012 is unchanged: empty scope, and the login token is discarded.
- ADR-003 is not applied in V1: there is no token column, no encryption key and no key rotation. ADR-003 remains the rule if a GitHub token is ever stored.
- `GET /integrations/github/connect`, `GET /integrations/github/callback` and `DELETE /integrations/github` are removed from the contract: there is nothing to connect or disconnect.

### Credentials are mandatory and checked

- The backend and the sync worker both refuse to start without `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` (the backend settings already require them).
- At startup the worker calls `GET /rate_limit` with the credentials. A 401, or a reported core limit equal to the unauthenticated 60 per hour, is logged at ERROR and the worker exits with a non-zero code. The platform never falls back to unauthenticated requests.
- A 401 during normal work is a configuration error, not a job failure: the worker logs it at ERROR, does not charge the job an attempt, and exits.
- `GITHUB_CLIENT_SECRET` lives only in the environment of the backend and the worker. It is never logged, never put into a URL, never returned by the API and never sent to the frontend.

### Request safety

- Requests go only to the fixed base URL `https://api.github.com`. No URL is built from user input other than path segments that passed validation.
- A repository named by the user is accepted only as `owner/name`, where `owner` matches `^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$` and `name` matches `^[A-Za-z0-9._-]{1,100}$` and is not `.` or `..`. Anything else is a validation error before any request is made. These patterns are a safety filter; GitHub stays the authority on whether the repository exists.
- Repository ids are integers. Redirects are never followed. A redirect whose `Location` is `https://api.github.com/repositories/{id}` (what GitHub answers for a renamed repository) is reported to the caller as a moved repository with that id, and the caller decides whether to read it by id; any other redirect is an unexpected answer. Decided in step 5.2, 2026-10-30.
- Logs carry the request id, the GitHub HTTP status and a fixed reason label, as the login client does today (`app/identity/github_client.py`). Response bodies, headers with credentials and README text are never logged.

### Private repositories later

If private repositories are needed, they come through a GitHub App with read-only permissions on repositories the user selects, under a new ADR. The OAuth `repo` and `public_repo` scopes are not used for this.

## Consequences

### Positive

- No per-user secret is stored, so there is nothing to encrypt, rotate, revoke or leak.
- No write access is requested for a read-only need.
- No second consent screen; the login promise stays true.
- One credential pair for login and data, already present in every environment.

### Negative

- Private repositories, including private organization repositories, cannot be used in V1.
- The whole platform shares one budget of 5,000 requests per hour. One user can affect others; ADR-018 limits manual syncs, and ADR-017 bounds the requests a link makes.
- Without a user token the platform cannot prove who the user is on GitHub beyond the login identity; the relation to a repository is derived from public data (ADR-017), which has false negatives.

## Alternatives considered

- **A user OAuth token with `public_repo` or `repo`, encrypted per ADR-003.** Rejected: both scopes grant write access, the token does not expire, and it needs encryption, key management and organization approval. Its only gain, private repositories, cannot be shown publicly.
- **A GitHub App now.** Rejected for V1: a private key, JWT signing and an installation flow for a capability V1 does not need. It is the path for private repositories later.
- **Unauthenticated requests.** Rejected: 60 requests per hour per IP is not enough for one active user.

## Checked by hand

Checked in step 5.2 on 2026-10-30, with the platform's app credentials and no user token, by one run of `backend/scripts/github_smoke.py`:

- The credentials are accepted: `GET /rate_limit` reports a core limit of 5,000, not the unauthenticated 60. `/rate_limit` itself did not spend the limit.
- A `304 Not Modified` answer to a request with Basic app credentials and `If-None-Match` did not spend the primary limit: `x-ratelimit-used` was 2 on the request before it, 2 on the 304 and 3 on the next request. This is one observation on an otherwise idle budget. Whether syncs send conditional requests is an open question of ADR-018.
- Public repositories of an organization (`github`) are readable.

## Not verified

- Whether public repositories of an organization that restricts OAuth app access are readable with app credentials (the documentation says only that private resources are not). The run used an organization not known to restrict access. The design does not rely on it.

## Not decided by this ADR

- Repository linking, import and the repository model: ADR-017.
- Sync triggers, categories, rate-limit handling: ADR-018.
- What is shown publicly: ADR-019.
