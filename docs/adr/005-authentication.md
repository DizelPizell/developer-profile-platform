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
