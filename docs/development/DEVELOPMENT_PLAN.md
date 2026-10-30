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
- **3.5 Public blocks** (FRONTEND_PLAN F6) [done; manual check with the backend pending]: «Главные проекты» and «Другие проекты» on `/u/[slug]`.

Phase 3 does not include skills, demos, screenshots, the public project page or GitHub import (ADR-015).

Order relative to later phases:
- Phase 4 starts after Phase 3. It adds demo, screenshots and the public project page `/u/{slug}/projects/{id}` (the «Открыть проект» link and the image area of featured cards). It also covers object storage cleanup when a project is deleted.
- Phase 5 builds on the Phase 3 model: an import creates a `DRAFT` project that the developer completes and publishes as usual (ADR-017).
- Phase 6 shows GitHub data on the cards of projects that have a linked repository (ADR-019); it does not change the Phase 3 rules.

## Phase 4 - Demo and Media
- demo
- screenshots
- S3/MinIO
- object storage cleanup when a project is deleted (ADR-015)
- public project page (`/u/{slug}/projects/{id}`, ADR-015)
- demo-first UX
- click analytics

## Phase 5 - GitHub Repositories, Linking and Import

Decisions: ADR-016-github-access-v1.md (public data with the app's credentials, no user token), ADR-017-repository-linking-and-import.md. Contract: `docs/api/API_CONTRACT.md` ("GitHub"), `docs/api/openapi.yaml`. No OAuth consent for repository access and no token storage (ADR-016 replaces those items of the earlier plan).

Steps, in order, each its own change with tests; a step starts when the previous one is merged. Sizes: S up to a day, M one to three days, L more.

- **5.1 Models and migration** (S–M) [done]: `github_repositories` (shared, unique `github_repo_id`, the ADR-017 field list) and `project_repositories` (unique `project_id`, `relation` CHECK, cascades and `RESTRICT` per ADR-017; `owner_id` with unique `(owner_id, github_repository_id)` and a composite foreign key to `projects (id, owner_id)`). Schema only. Tests: upgrade and downgrade; each constraint rejects what it must.
- **5.2 GitHub API client** (M) [done]: read-only client for `https://api.github.com` with Basic app credentials, timeouts, rate-limit headers parsed into a typed result, errors mapped to `GITHUB_UNAVAILABLE` and `GITHUB_RATE_LIMITED`, the `owner/name` patterns, redirects never followed (a redirect to `/repositories/{id}` is reported as moved, ADR-016), no bodies or credentials in logs. The request budget of ADR-018: the per-user budget in process memory (`GITHUB_USER_REQUESTS_PER_HOUR`, 429 `GITHUB_USER_LIMIT_REACHED` before any request) and the backend's pause until the reset after an exhausted limit. JSON fixtures written by hand from GitHub's documentation and the existing `MockTransport` pattern. Includes a **manual check without a user token** of the behaviors ADR-016, ADR-017 and ADR-018 mark as not verified; its results are recorded in those ADRs (2026-10-30). Review fixes (5.2b) [done]: bounded and validated rate-limit waits, the budget settled only through `spend()`, shared constants in `app/github/constants.py`.
- **5.3 Repository list** (S–M) [done]: `GET /integrations/github/repositories` with pages and `linked_project_id`, and the 5-minute in-memory page cache (ADR-017); a cached page costs no budget, `linked_project_id` is read on every call. An outdated stored login is 409 `GITHUB_LOGIN_OUTDATED`, and items of another GitHub account are not returned (decided in this step, ADR-017).
- **5.4 Link and unlink** (M) [done]: `POST` and `DELETE /projects/{id}/repository`, the relation check (at most 7 requests: the repository, once more by id for an old name, and 5 contributor pages), `GITHUB_REPOSITORY_ALREADY_LINKED` from the database unique `uq_project_repositories_owner_repository` (step 5.1), `github` in `ProjectResponse` (with `sync.status = NOT_SYNCED` until Phase 6). A link by an old name (a 301 to `/repositories/{id}`) reads the repository by that id (decided in this step, ADR-017). No sync job is queued yet: step 6.2 adds it at the marked place in the link route. Tests: every error code, another user's project is 404, no request to GitHub on an invalid name, nothing stored on any error.
- **5.5 Import** (S–M): `POST /integrations/github/repositories/{id}/import`: a `DRAFT` + `PRIVATE` project titled after the repository and its link in one transaction; the project limit and the link errors apply.

## Phase 6 - GitHub Sync and Public GitHub Data

Decisions: ADR-009, ADR-018-github-sync-v1.md (V1 syncs only metadata and languages; narrows ADR-010 and ADR-011), ADR-019-public-github-data.md.

- **6.1 Sync tables** (S): `github_sync_jobs` (partial unique index on active jobs, claim index) and `github_sync_category_status`.
- **6.2 Queueing and status** (S–M): a job queued with each link (at the place marked in `link_repository`, in its write transaction) and import; `POST /integrations/github/repositories/{id}/sync` with the 10-minute pause per repository (`GITHUB_SYNC_TOO_SOON`) and 7 requests counted against the user's budget for a new job (`GITHUB_USER_LIMIT_REACHED`); `github.sync` in `ProjectResponse`. Tests: an active job is reused, the pause and `Retry-After`.
- **6.3 Worker core** (L): a separate process with `run_once(db, client, now)`: claim with `SKIP LOCKED`, retries with backoff, the watchdog for stale `SYNCING`, rate-limit answers that reschedule to the reset without an attempt and pause claiming, no claims while the remaining budget is at or below `GITHUB_WORKER_RESERVE` (ADR-018), the startup credential check (exit on 401 or an unauthenticated limit). Tests on two transactions: one job is claimed once; the watchdog takes over a stale job; a rate-limited job keeps `attempt_count`.
- **6.4 Categories** (M): metadata and languages with ADR-010 reconciliation (fetch outside, short write transaction per category), the relation recomputed from metadata and up to 5 contributor pages without storing them (a failure keeps the previous relation). Tests: a failed fetch leaves stored data unchanged; owner, contributor and `NONE`.
- **6.5 Periodic syncs and missing repositories** (M): the worker queues repositories linked to a `PUBLISHED` project every 24 hours; two 404s in a row set `unavailable_since`, a success clears it; renames refresh `full_name` by `github_repo_id`.
- **6.6 Worker service** (S): a `github-worker` service in `docker-compose.yml` on the backend image, after `migrate`, with the backend's environment; README and `.env.example` notes.
- **6.7 Public API** (S–M): the nullable `github` object on public project cards with the ADR-019 whitelist, hidden for no sync yet, unavailable or `NONE`; one batched query. Tests: the whitelist, the four `null` cases, the same query count for 1 and 30 projects.

Not in Phases 5–6 (deferred by ADR-018): README, file tree, code viewer, contributors, commits. They return after the public project page (Phase 4) together with a decision on how README is shown safely (ADR-019). The project "architecture" field belongs with the project page work.

### Frontend for Phases 5–6

Numbered after the Phase 4 frontend steps in `docs/frontend/FRONTEND_PLAN.md`; each starts when its backend steps are merged.

- **F-GH1 Cabinet** (M–L, after 5.3–5.5 and 6.2): the repository list with import, link by `owner/name` and unlink in the project form, the relation and unavailable states, «Обновить» with the pause and polling while `QUEUED` or `SYNCING`. Also the login screen note from `docs/frontend/DESIGN.md`, which changes the F2 text. The repository list handles 409 `GITHUB_LOGIN_OUTDATED`: «Войдите заново: логин на GitHub изменился».
- **F-GH2 Public** (M, after 6.7): the GitHub block on project cards and on the project page with «Источник: GitHub», the relation and fork texts and language shares (ADR-019).

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
