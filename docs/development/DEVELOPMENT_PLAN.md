# Development Plan

## Phase 0 - Bootstrap
- repository [done]
- documentation [done]
- Git conventions [done]
- Docker Compose [done]
- PostgreSQL [done]
- FastAPI skeleton [done]
- environment configuration [done]
- CI skeleton [done]

Next.js skeleton moved to Phase 2.

## Frontend

Frontend stages F0–F5+ are planned in `docs/frontend/FRONTEND_PLAN.md` (stack: ADR-014-frontend-stack.md; screens: `docs/frontend/DESIGN.md`).

Order relative to the backend:
- F1–F4 build only on Phase 1 and the Phase 2 API, which are done. They cover the rest of Phase 2: the Next.js skeleton is F1, the public page is F4.
- F5+ follow backend Phases 3–6 and start only when the matching API contract exists.

## Phase 1 - Authentication and Profile
- User/Profile/AuthSession models (ADR-012) [done]
- migrations [done]
- GitHub OAuth login — register+login unified, auth_session table, 14-day lifetime (ADR-012) [done]
- logout [done]
- current user [done]
- profile editing/publication (ADR-013) [done]
- ownership tests [done]
- Origin check and CORS for state-changing requests (ADR-013) [done]

## Phase 2 - Public Profile
- Next.js skeleton (FRONTEND_PLAN F1) [done]
- public endpoint (ADR-013) [done]
- public DTOs (ADR-013) [done]
- public page (FRONTEND_PLAN F4)
- slug
- privacy
- featured project placeholders

## Phase 3 - Projects
- Project model
- technologies
- lifecycle and visibility (ADR-005)
- CRUD
- validation
- Showcase
- featured ordering
- max 3 invariant

## Phase 4 - Demo and Media
- demo
- screenshots
- S3/MinIO
- public project page
- demo-first UX
- click analytics

## Phase 5 - GitHub Integration and Import
- separate OAuth consent for repository access on top of existing login (ADR-012, ADR-003)
- encrypted token storage (ADR-003)
- repository listing
- import
- repository association

## Phase 6 - GitHub Sync and Technical Workspace
- GitHub Sync Worker as a separate process using PostgreSQL polling and SKIP LOCKED (ADR-009)
- sync jobs and per-category status tables (ADR-011)
- mandatory sync categories: metadata, README, languages, file tree
- optional sync categories: contributors, commits (failure does not block SYNCED, commits are append-only)
- normalized repository data
- idempotent synchronization
- file tree
- code viewer
- README
- architecture
- worker deployment task

## Phase 7 - Analytics
- event ingestion
- profile/project analytics
- funnel
- privacy-safe tracking

## Phase 8 - Quality and Security
- unit/integration/E2E tests
- lint/format/type checks
- security review
- rate limiting where required
- logging
- performance checks

## Phase 9 - Production
- production Docker
- reverse proxy
- HTTPS
- production storage
- secrets
- backups
- CI/CD
- monitoring
- release process

A phase is complete only when its Definition of Done is satisfied.
