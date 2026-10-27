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

Frontend stages F0–F6 and F7+ are planned in `docs/frontend/FRONTEND_PLAN.md` (stack: ADR-014-frontend-stack.md; screens: `docs/frontend/DESIGN.md`).

Order relative to the backend:
- F1–F4 build only on Phase 1 and the Phase 2 API, which are done. They cover the rest of Phase 2: the Next.js skeleton is F1, the public page is F4.
- F5 (projects in the cabinet) and F6 (projects on the public page) are part of Phase 3 and follow its backend steps.
- F7+ follow backend Phases 4–6 and start only when the matching API contract exists.

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
- public page (FRONTEND_PLAN F4) [done; manual check with the backend pending]
- slug
- privacy
- featured projects: moved to Phase 3 (step 3.5); F4 renders no placeholders

## Phase 3 - Projects

Decisions: ADR-015-project-model.md. Contract: `docs/api/API_CONTRACT.md`, `docs/api/openapi.yaml`.

Steps, in order. Each step is its own change with tests; a step starts when the previous one is merged.

- **3.1 Models and migration**
  - Tables `projects`, `technologies`, `project_technologies`, `project_showcases` with every constraint from ADR-015:
    - the state pair CHECK;
    - length and blank CHECKs;
    - `ck_projects_published_complete`;
    - unique `lower(name)`;
    - position ranges;
    - UNIQUE (`profile_id`, `position`) `DEFERRABLE INITIALLY IMMEDIATE`;
    - cascades.
  - Schema only: no endpoints.
  - Tests: the migration upgrades and downgrades on an empty database. Each constraint rejects what it must, including a fourth featured row, a 21st technology, an invalid state pair, a published project with an empty title, and a duplicate technology name in another case. A reorder by one `UPDATE` passes.
- **3.2 Cabinet API**, in two parts. Rules and error codes per ADR-015; ownership checks; locks (profile row, then project row).
  - **3.2a Projects** [done]
    - Project CRUD, publish/archive/visibility, technologies in the project body.
    - Archive, hide and delete remove the project from featured projects and close the gap.
    - `DELETE` added to CORS in `backend/app/main.py`.
    - Tests:
      - every transition and every project error code;
      - another user's project is 404;
      - the 50-project and 20-technology limits;
      - featured: no gaps after archive, hide or delete;
      - the CORS preflight for `DELETE`;
      - the technology get-or-create race with two transactions.
  - **3.2b Featured projects** [done]
    - Feature, unfeature and reorder (`/projects/{id}/showcase`, `/profile/featured-projects/reorder`), under the profile lock, then the project lock.
    - A rejected insert from the database's position CHECK is reported as `FEATURED_LIMIT_REACHED`, not 500.
    - Project ids in the path and in the reorder body are accepted only in the canonical UUID form; a malformed path id is 404.
    - Tests:
      - `PROJECT_NOT_FEATURABLE`, `FEATURED_LIMIT_REACHED`, `FEATURED_ORDER_MISMATCH`;
      - idempotent feature and unfeature;
      - reorder: permutations, mismatch, malformed lists;
      - races on two transactions: two features for the last slot give one success and one `FEATURED_LIMIT_REACHED`; two reorders leave no gaps or duplicates; a reorder after a concurrent unfeature is a mismatch.
- **3.3 Public API** [done]
  - `featured` and `other` in `GET /public/profiles/{slug}`; three SQL queries for any number of projects and technologies.
  - Tests:
    - only `PUBLISHED` + `PUBLIC` projects of a `PUBLISHED` profile;
    - the whitelist (no extra fields);
    - order;
    - empty arrays;
    - unpublishing the profile hides projects and keeps their states;
    - the same query count for 1 and 30 projects.
  - Also: the project routes that change featured projects or count projects (feature, unfeature, reorder, archive, hide, delete, create) are tested over HTTP to wait on the owner's profile lock.
- **3.4 Cabinet frontend** (FRONTEND_PLAN F5) [done; manual check with the backend pending]: «Мои проекты», create/edit, publish/archive/visibility, featured projects and their order, per mockups `my-projects.png` and `project-form.png`.
- **3.5 Public blocks** (FRONTEND_PLAN F6): «Главные проекты» and «Другие проекты» on `/u/[slug]`. Needs 3.3; can run in parallel with 3.4.

Phase 3 does not include skills, demos, screenshots, the public project page or GitHub import (ADR-015).

Order relative to later phases:
- Phase 4 starts after Phase 3. It adds demo, screenshots and the public project page `/u/{slug}/projects/{id}` (the «Открыть проект» link and the image area of featured cards). It also covers object storage cleanup when a project is deleted.
- Phase 5 builds on the Phase 3 model: an import creates a `DRAFT` project that the developer completes and publishes as usual.
- Phase 6 shows GitHub data for projects that have a linked repository; it does not change the Phase 3 rules.

## Phase 4 - Demo and Media
- demo
- screenshots
- S3/MinIO
- object storage cleanup when a project is deleted (ADR-015)
- public project page (`/u/{slug}/projects/{id}`, ADR-015)
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
