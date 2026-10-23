# ADR-005: HTTP-only Cookie Sessions and GitHub OAuth

Status: **Accepted**

## Decision
Use secure HTTP-only cookie sessions for application authentication. GitHub OAuth is a separate account integration.

## Requirements
- Secure cookies in production
- appropriate SameSite policy
- CSRF protection where needed
- GitHub access tokens encrypted at rest
- secrets outside source control
- tokens never logged

## Note (2026-10-03)

GitHub token encryption detail is now specified separately in `ADR-003-github-token-storage.md`. This ADR remains the source of truth for the session/cookie authentication model itself and is still active.
