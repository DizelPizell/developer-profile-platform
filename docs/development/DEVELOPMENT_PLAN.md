# Development Plan

## V1 and the remaining work

Decided by the owner on 2026-11-04. What V1 is: `docs/product/PRD.md` ("V1 scope", "Success criteria").

The remaining work goes in this order, which replaces the numeric order of the phases below. Each step still starts when the previous one is merged.

1. GitHub: 6.6 and F-GH1.6, then 6.7 and F-GH2.
2. The deployment skeleton: 9.1–9.3. It comes before Phase 4, so the production topology is known early: it decides whether CORS stays and how `FRONTEND_URL` is set (ADR-014).
3. Phase 4 - Demo and Media.
4. Contacts: C.1–C.2.
5. Before the launch: 8.3, 8.4 and 9.4–9.7.
6. The launch: 9.8.
7. V1.1: Phase 7, right after the launch.

Launch blockers, besides the scope of V1:
- rate limiting, 8.3 (ADR-013), without the event ingestion;
- the security review, 8.4;
- deployment, 9.1–9.4 and 9.8;
- backups, 9.5;
- monitoring, 9.6;
- account deletion and the data policy, 9.7.

V1.1: analytics, Phase 7, with every event: `CONTACT_CLICK` and the click analytics of Phase 4 too.

After V1:
- the read-only project workspace (the file explorer, the code viewer and the file tree it needs, ADR-018);
- experience, skills and education on the profile; the question of skills in ADR-015 stays open;
- what ADR-010 keeps out of V1, and the V2 list of the PRD.

Open questions:
- **Contacts**: which contacts, where they are shown, and what "contact visibility" (PRD) means in the minimal form. Needed before C.1.
- **8.1, 8.2 and 8.5** are not named as launch blockers: whether the launch waits for them.
- **README, contributors and commits**: ADR-018 returns them with the public project page, and the workspace, which needs the file tree, is now after V1. Whether README comes before the V1 launch is not decided.
- **Production storage in 9.3**: nothing uses object storage before Phase 4. Whether it is part of the skeleton or finished with Phase 4.
- **Goals, architecture and highlights** of a project (ADR-015, "Fields of later phases"): whether they are in V1.

Sizes of the steps in Phases 7–9 and of C.1–C.2 are estimates, by the number of commits and tests of the past steps; each step gets its details when it is planned.

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
- click analytics: moved to V1.1 (step 7.3)

## Phase 5 - GitHub Repositories, Linking and Import

Decisions: ADR-016-github-access-v1.md (public data with the app's credentials, no user token), ADR-017-repository-linking-and-import.md. Contract: `docs/api/API_CONTRACT.md` ("GitHub"), `docs/api/openapi.yaml`. No OAuth consent for repository access and no token storage (ADR-016 replaces those items of the earlier plan).

Steps, in order, each its own change with tests; a step starts when the previous one is merged. Sizes: S up to a day, M one to three days, L more.

- **5.1 Models and migration** (S–M) [done]: `github_repositories` (shared, unique `github_repo_id`, the ADR-017 field list) and `project_repositories` (unique `project_id`, `relation` CHECK, cascades and `RESTRICT` per ADR-017; `owner_id` with unique `(owner_id, github_repository_id)` and a composite foreign key to `projects (id, owner_id)`). Schema only. Tests: upgrade and downgrade; each constraint rejects what it must.
- **5.2 GitHub API client** (M) [done]: read-only client for `https://api.github.com` with Basic app credentials, timeouts, rate-limit headers parsed into a typed result, errors mapped to `GITHUB_UNAVAILABLE` and `GITHUB_RATE_LIMITED`, the `owner/name` patterns, redirects never followed (a redirect to `/repositories/{id}` is reported as moved, ADR-016), no bodies or credentials in logs. The request budget of ADR-018: the per-user budget in process memory (`GITHUB_USER_REQUESTS_PER_HOUR`, 429 `GITHUB_USER_LIMIT_REACHED` before any request) and the backend's pause until the reset after an exhausted limit. JSON fixtures written by hand from GitHub's documentation and the existing `MockTransport` pattern. Includes a **manual check without a user token** of the behaviors ADR-016, ADR-017 and ADR-018 mark as not verified; its results are recorded in those ADRs (2026-10-30). Review fixes (5.2b) [done]: bounded and validated rate-limit waits, the budget settled only through `spend()`, shared constants in `app/github/constants.py`.
- **5.3 Repository list** (S–M) [done]: `GET /integrations/github/repositories` with pages and `linked_project_id`, and the 5-minute in-memory page cache (ADR-017); a cached page costs no budget, `linked_project_id` is read on every call. An outdated stored login is 409 `GITHUB_LOGIN_OUTDATED`, and items of another GitHub account are not returned (decided in this step, ADR-017).
- **5.4 Link and unlink** (M) [done]: `POST` and `DELETE /projects/{id}/repository`, the relation check (at most 7 requests: the repository, once more by id for an old name, and 5 contributor pages), `GITHUB_REPOSITORY_ALREADY_LINKED` from the database unique `uq_project_repositories_owner_repository` (step 5.1), `github` in `ProjectResponse` (with `sync.status = NOT_SYNCED` until Phase 6). A link by an old name (a 301 to `/repositories/{id}`) reads the repository by that id (decided in this step, ADR-017). No sync job is queued yet: step 6.2 adds it at the marked place in the link route. Tests: every error code, another user's project is 404, no request to GitHub on an invalid name, nothing stored on any error.
- **5.5 Import** (S–M) [done]: `POST /integrations/github/repositories/{id}/import`: a `DRAFT` + `PRIVATE` project titled after the repository and its link in one transaction; the project limit and the link errors apply. The repository is read by id (at most 6 requests); the project limit and an existing link are checked before GitHub as well as in the write transaction (decided in this step, ADR-017). No sync job is queued yet: step 6.2 adds it at the marked place in the import route. Also in this step: the repository list ends its read transaction before calling GitHub, as linking does.
- **5.6 The repository in the project list** (S) [done]: `github` in `ProjectSummary` of `GET /projects`, `null` or `{full_name, html_url}` from the stored repository (contract, decided 2026-10-31 for F-GH1). No relation, languages or sync state; not hidden for an unavailable repository or `NONE`. No GitHub call and no schema change. Tests: `null` without a link; the values after a link, an import, a replacement and an unlink; another user's link to the same repository does not show; the number of SQL queries of `GET /projects` is the same for 1 and 30 projects, with and without links. Done before the F-GH1 code: the GitHub label on «Мои проекты» and the line «Уже привязан к …» in the link dialog rely on it. Implemented as one more batched query next to technologies and featured positions, filtered by the owner and the listed project ids; a direct test of that query covers both filters, since the route passes only the user's own ids.

## Phase 6 - GitHub Sync and Public GitHub Data

Decisions: ADR-009, ADR-018-github-sync-v1.md (V1 syncs only metadata and languages; narrows ADR-010 and ADR-011), ADR-019-public-github-data.md.

- **6.1 Sync tables** (S) [done]: `github_sync_jobs` (status, attempt and error CHECKs, the partial unique index on active jobs, the partial claim index on `scheduled_at`, an index on repository and `created_at`) and `github_sync_category_status` (unique repository and category, metadata and languages). Errors are labels by CHECK, both tables cascade from `github_repositories`, the watchdog uses `updated_at`, and existing links get no job and stay `NOT_SYNCED` (decided in this step, ADR-018). Schema only. Tests: each constraint rejects what it must, the idempotent enqueue with `ON CONFLICT`, the cascade, upgrade and downgrade, and links made before the migration surviving them.
- **6.2 Queueing and status** (S–M) [done]: a job queued with each link and import (in `store_link`, which both use, in their write transactions), which also record their metadata read as a metadata success in `github_sync_category_status` (ADR-018, decided in step 6.1); `POST /integrations/github/repositories/{id}/sync` with the 10-minute pause per repository (`GITHUB_SYNC_TOO_SOON`) and 7 requests counted against the user's budget for a new job (`GITHUB_USER_LIMIT_REACHED`); `github.sync` in `ProjectResponse`. Tests: an active job is reused, the pause and `Retry-After`. Done: the checks in the order of ADR-018 ("Queueing and manual syncs", decided in this step), the repository row lock before the pause is read, the charge after the insert, `GITHUB_MANUAL_SYNC_COOLDOWN_SECONDS`, and `now` from `get_now` in every route that returns `ProjectResponse`. Tests: the enqueue, link and import writes, the status fields at the pause's edges, the endpoint's errors, two-transaction races (two syncs, a sync during a link, a job finished before the first commit) and 16 mutations.
- **6.3 Worker core** (L) [done]: a separate process with `run_once(db, client, now)`: claim with `SKIP LOCKED`, retries with backoff, the watchdog for stale `SYNCING`, rate-limit answers that reschedule to the reset without an attempt and pause claiming, no claims while the remaining budget is at or below `GITHUB_WORKER_RESERVE` (ADR-018), the startup credential check (exit on 401 or an unauthenticated limit). Tests on two transactions: one job is claimed once; the watchdog takes over a stale job; a rate-limited job keeps `attempt_count`. Done (ADR-018, "Worker core", decided in this step): `SyncWorker.run_once(db)` with the processor given as a function, the outcome fenced by the claimed attempt, five error labels, the attempt given back on a rate limit and on a 401, `run_forever` with SIGTERM and SIGINT, the `GITHUB_WORKER_*` settings and `get_rate_limit` in the client; one worker process in V1. No processor that reads GitHub and no entry point yet: both in 6.4. Tests: the claim, outcomes and backoff, rate limits and the reserve, the watchdog and the fence, two sessions with locked rows, the loop with recorded waits, and 42 mutations.
- **6.4 Categories** (M) [done]: the processor and the worker's entry point (`python -m app.github.worker`); metadata and languages with ADR-010 reconciliation (fetch outside, short write transaction per category), the relation recomputed from metadata and up to 5 contributor pages without storing them (a failure keeps the previous relation). Tests: a failed fetch leaves stored data unchanged; owner, contributor and `NONE`. Done (ADR-018, "Processor", decided in this step): metadata by id, then languages under the name just read, contributor pages only for developers who are not the owner, in one pass for all links; a failed category records its label and keeps its data; a contributor failure keeps the relations and does not fail the job; language names with control characters are malformed; `python -m app.github.worker` and the README's manual run; no ETags in V1. Renamed repositories already get their names from the metadata read by id. Tests: both categories, partial success, each failure, transfer, relations of several links, 7 requests at most, no transaction during requests, the entry point, and 35 mutations.
- **6.5 Periodic syncs and missing repositories** (M) [done; manual check pending]: the worker queues repositories linked to a `PUBLISHED` project every 24 hours; two 404s in a row set `unavailable_since`, a success clears it; renames refresh `full_name` by `github_repo_id` (done by the metadata read of 6.4; 6.5 adds the test through a periodic job). Done (ADR-018, "Periodic syncs and missing repositories", decided in this step with the owner): one `INSERT ... SELECT` with `ON CONFLICT DO NOTHING` in the worker's iteration, at most once a minute and at most 30 jobs (`GITHUB_PERIODIC_SYNC_SECONDS`, `GITHUB_PERIODIC_SYNC_BATCH`), nothing queued during a hold, hidden projects included, old active jobs left out of the selection; the second 404 read under the repository row lock after GitHub answered, `final` from the processor, `unavailable_since` keeping its first date. No migration and no contract change. Checked with 1319 test cases (42 new), 23 mutations (all fail tests), and lint, format and tests in a clean clone. The two-transaction tests hold one connection: `sync_repository` ends its transactions, and a pooled session hung the first full run. The manual check is the backend README's "Manual periodic sync check"; it has not been run yet. Its first attempt ran an image built before this step, and the periodic code was not in it: no bug in the step, but nothing showed the cause. So the manual check now starts by asking the image's settings, the worker's start line names the period and the batch, and an end-to-end test runs the loop with the real processor, `SessionLocal` and the settings from the environment.
- **6.6 Worker service** (S): a `github-worker` service in `docker-compose.yml` on the backend image, after `migrate`, with the backend's environment; README and `.env.example` notes.
- **6.7 Public API** (S–M): the nullable `github` object on public project cards with the ADR-019 whitelist, hidden for no sync yet, unavailable or `NONE`; one batched query. Tests: the whitelist, the four `null` cases, the same query count for 1 and 30 projects.

Not in Phases 5–6 (deferred by ADR-018): README, file tree, code viewer, contributors, commits. They return after the public project page (Phase 4) together with a decision on how README is shown safely (ADR-019). The project "architecture" field belongs with the project page work.

### Frontend for Phases 5–6

Numbered after the Phase 4 frontend steps in `docs/frontend/FRONTEND_PLAN.md`; each starts when its backend steps are merged.

- **F-GH1 Cabinet** (M–L; F-GH1.1–F-GH1.3 after 5.3–5.6 (F-GH1.4 folded into F-GH1.3), F-GH1.5 after 6.4; substeps in `docs/frontend/FRONTEND_PLAN.md`): the repository list with import, link by `owner/name` and unlink in the project form, the relation and unavailable states, «Обновить» with the pause and polling while `QUEUED` or `SYNCING` (F-GH1.5), the sync message of an unavailable repository (F-GH1.6, after 6.5). Also the login screen note from `docs/frontend/DESIGN.md`, which changes the F2 text. The repository list handles 409 `GITHUB_LOGIN_OUTDATED`: «Войдите заново: логин на GitHub изменился».
- **F-GH2 Public** (M, after 6.7): the GitHub block on project cards and on the project page with «Источник: GitHub», the relation and fork texts and language shares (ADR-019).

## Contacts (V1)

Minimal contacts of a profile, so that a visitor can contact the developer (US-025). Decided by the owner on 2026-11-04. The contract does not exist yet; see "Open questions" above. No analytics event in V1: `CONTACT_CLICK` comes with V1.1.

- **C.1 Backend** (S–M): the model, the API and the visibility of contacts, in the cabinet and in the public profile DTO.
- **C.2 Frontend** (S–M, after C.1): contacts in the cabinet and on the public page.

## Phase 7 - Analytics (V1.1)

Released as V1.1, right after the V1 launch (decided by the owner on 2026-11-04).

- **7.0 Decisions** (S): an ADR on privacy-safe tracking, sessions and how long events are kept.
- **7.1 Event ingestion** (M, after 7.0): the model and `POST /analytics/events`, with its rate limit.
- **7.2 Profile and project analytics** (M, after 7.1): the aggregates and the cabinet API.
- **7.3 Events from the frontend** (M, after 7.1): profile and project views, demo, GitHub and contact clicks.
- **7.4 The analytics screen** (M, after 7.2): profile and project analytics and the funnel.

## Phase 8 - Quality and Security

- **8.1 Manual checks** (S): the checks marked pending in this plan and in `docs/frontend/FRONTEND_PLAN.md`.
- **8.2 End-to-end tests** (M–L): Playwright on the main flows (ADR-014).
- **8.3 Rate limiting** (S–M) [launch blocker]: where required (ADR-013), without the event ingestion, which gets its limit in 7.1.
- **8.4 Security review** (M) [launch blocker]: the review and its fixes.
- **8.5 Logging, performance and type checks** (S–M).

## Phase 9 - Production

Steps 9.1–9.3 are the deployment skeleton and come before Phase 4 ("V1 and the remaining work"). Every step here is a launch blocker.

- **9.1 Production topology** (S): an ADR on one origin behind Nginx or a separate API host (ADR-014).
- **9.2 Images, reverse proxy, HTTPS** (M, after 9.1): production Docker for the frontend and the backend, Nginx, HTTPS.
- **9.3 Production environment** (M, after 9.1): production Compose, storage and secrets.
- **9.4 CI/CD** (M, after 9.2 and 9.3).
- **9.5 Backups** (S–M, after 9.3).
- **9.6 Monitoring** (M, after 9.3).
- **9.7 Account deletion and the data policy** (M): ADR-012 leaves account deletion undecided.
- **9.8 Release** (S, last): the release process and the launch.

A phase is complete only when its Definition of Done is satisfied.
