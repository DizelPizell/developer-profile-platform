\# Developer Profile Platform



\## Project



Developer Professional Profile Platform.



Core principle:



> Не рассказывай, что ты умеешь. Покажи.



The platform allows developers to create professional profiles backed by real projects, GitHub evidence, live demos, architecture and technical information.



V1 is NOT a LinkedIn or HeadHunter clone.



V1 focuses on:

\- developer profiles

\- projects

\- featured projects

\- public profiles

\- GitHub integration

\- live demos

\- technical project workspace

\- analytics



Recruiter search, vacancies, matching and messaging are V2.



\---



\## Product principle



We do not assign artificial developer scores or rankings.



Evidence is more important than scores.



Do not invent:

\- skill scores

\- developer ratings

\- contribution percentages

\- quality scores

\- arbitrary rankings



GitHub data and developer-provided context must remain distinguishable.



\---



\## Architecture



Architecture style:



Modular monolith.



Backend:

\- Python

\- FastAPI

\- SQLAlchemy 2

\- PostgreSQL

\- Alembic

\- pytest



Frontend:

\- Next.js

\- TypeScript

\- Tailwind CSS

\- shadcn/ui

\- Vitest

\- React Testing Library

\- Playwright



Infrastructure:

\- Docker

\- Docker Compose

\- GitHub Actions

\- Nginx



Storage:

\- a named Docker volume on the host (media), written by the backend and served by Nginx under /media/ — not S3 and not MinIO in V1 (MinIO CE is no longer shipped). See ADR-0022-media-on-host-volume.md; S3 returns with a second host, a full disk or a CDN



External integration:

\- GitHub API



Redis, Kafka and Kubernetes are NOT part of V1 unless a concrete requirement appears. Kafka and an Outbox pattern were evaluated for GitHub synchronization and explicitly rejected for V1 — see docs/release/v1/adr/0008-no-kafka-v1.md.



Do not introduce new infrastructure technologies without explaining the problem they solve.



\---



\## Backend architecture



Use a modular monolith.



Logical flow:



HTTP

↓

API / Controller

↓

Application / Use Case

↓

Domain

↓

Repository

↓

Infrastructure



Do not over-engineer Clean Architecture.



Avoid unnecessary abstractions and interfaces.



Do not create abstractions only for theoretical purity.



\---



\## Domain contexts



Main bounded contexts:



\- Identity

\- Profile

\- Projects

\- GitHub

\- Analytics

\- Files



Main aggregate roots:



\- User

\- Profile

\- Project

\- Analytics



\---



\## Important business rules



\### Profile



Each User has exactly one Profile.



Profile has a unique public slug.



Profile lifecycle:



PRIVATE

PUBLISHED

Unpublishing a profile returns it to PRIVATE. There is no separate UNPUBLISHED state in V1. See docs/release/v1/adr/0005-project-lifecycle-visibility.md.



\### Project



Project lifecycle:



DRAFT

PUBLISHED

ARCHIVED

Project visibility (a separate concept from lifecycle):



PUBLIC

PRIVATE

Lifecycle describes whether the project is being prepared, published or archived. Visibility describes whether a published project is publicly exposed. Invalid combinations must be rejected in the domain layer. See docs/release/v1/adr/0005-project-lifecycle-visibility.md.



A Project does not require GitHub.



A Project does not require a Demo.



Projects may represent:

\- commercial work

\- freelance work

\- educational projects

\- open-source projects

\- NDA work



\### Featured projects



A profile can have a maximum of 3 featured projects.



This is a backend business invariant, not only a frontend limitation.



\### GitHub



GitHub is the source of truth for technical repository data.



Developer is the source of truth for:

\- role

\- contribution

\- business context

\- problem

\- results

\- screenshots

\- demo URL



Never infer contribution percentages from commits.



Never calculate artificial skill scores from GitHub activity.



GitHub repository import is NOT the same thing as a Project.



Import creates an imported project which the developer can enrich with context.



GitHub sync must be idempotent.



GitHub synchronization is asynchronous but does not use Kafka, Outbox or Redis in V1. The worker is a separate process using PostgreSQL polling and SKIP LOCKED. See docs/release/v1/adr/0008-no-kafka-v1.md and docs/release/v1/adr/0009-sync-worker-skip-locked.md.



GitHub Evidence V1 scope (snapshot data vs history data, and reconciliation rules) is defined in docs/release/v1/adr/0010-github-evidence-model.md.

ADR-010 is narrowed for V1 by ADR-018: contributors, commits, README and the file tree are deferred (not fetched or stored in V1); only repository metadata and languages are synced.

GitHub V1 decisions: docs/release/v1/adr/0016-github-public-only.md (public data only, app credentials, no user token), docs/release/v1/adr/0017-repository-linking.md (shared repositories, linking, import, relation), docs/release/v1/adr/0018-github-sync-v1.md (sync scope and schedule), docs/release/v1/adr/0019-public-github-on-cards.md (what is shown publicly).



GitHub tokens must never be stored as plaintext.



\---



\## API



API prefix:



`/api/v1`



API style:



REST.



JSON request/response bodies.



Use explicit DTOs.



Never expose database entities directly through public endpoints.



Public DTOs must be whitelisted.



Never expose:

\- password hashes

\- session secrets

\- GitHub access tokens

\- private settings

\- internal database fields



Error format:



```json

{

&#x20; "error": {

&#x20;   "code": "VALIDATION\_ERROR",

&#x20;   "message": "Invalid request",

&#x20;   "details": {},

&#x20;   "request\_id": "uuid"

&#x20; }

}

API contract is defined in:



/docs/api/



OpenAPI is the source of truth for the API contract.



Do not silently change API behavior without updating the contract.



Database



PostgreSQL is the primary database.



Use SQLAlchemy 2.



Use Alembic migrations.



Do not modify production schema manually.



Every schema change must have a migration.



Security



Authentication:



HTTP-only cookies

Secure cookies in production

SameSite policy

CSRF protection

GitHub OAuth — the only login mechanism in V1 (ADR-012); sessions stored server-side in auth_sessions table with token_hash only



Authorization must be checked on the backend.



Never trust frontend authorization.



Every resource owned by a user must have an ownership check.



Never log secrets or access tokens.



Validate all external input.



Analytics



Analytics is a non-critical subsystem.



If analytics fails, the main user operation must continue.



Never block navigation because analytics failed.



Do not make analytics unnecessarily invasive.



Development workflow



Before implementing a non-trivial feature:



Understand the requirement.

Check existing architecture.

Check API contract.

Check database model.

Identify affected domains.

Propose implementation plan.

Explain important trade-offs.

Wait for approval when the decision is architectural or irreversible.

Implement.

Add tests.

Run validation.

Review the diff.

Update documentation if necessary.

How Claude should work



Do NOT immediately generate code for a large task.



First analyze.



For non-trivial tasks provide:



Understanding



What you understand from the requirement.



Impact



Which parts of the system are affected.



Plan



Concrete implementation steps.



Risks



Potential problems or trade-offs.



Decision



What approach you recommend and why.



Then implement after approval.



For small, obvious tasks implementation can proceed directly.



Challenge the developer



Do not blindly agree with the developer.



If a proposed solution is:



over-engineered

insecure

inconsistent with architecture

unnecessarily expensive

difficult to maintain

premature

solving a problem that does not exist



say so clearly.



Explain the alternative.



The goal is not to make the developer feel correct.



The goal is to build a maintainable production-oriented system.



Teaching mode



The developer is using this project to learn software engineering and Tech Lead practices.



When making important decisions, explain:



why the decision is needed

what alternatives exist

why one option is preferred

what trade-offs exist

what would change the decision later



Do not explain every trivial line of code.



Focus explanations on engineering decisions.



Git



Use Conventional Commits.



Examples:



feat(auth): add user registration



fix(profile): validate public slug



test(auth): add registration tests



docs(api): update profile contract



Do not create meaningless commits.



Keep commits focused and logically grouped.



Quality



Definition of Done:



implementation complete

validation implemented

tests added

error handling implemented

security considered

documentation updated when required

lint passes

tests pass

API contract remains consistent

migration exists for schema changes

code has been reviewed



"Works on my machine" is not Definition of Done.



Current development stage



The repository has completed Phase 3 (projects). Phase 5 (GitHub repositories) is done, ahead of Phase 4: steps 5.1–5.6. Phase 6 (GitHub sync) is done in the backend: steps 6.1–6.7, with F-GH1.5, F-GH1.6 and F-GH2 in the frontend. Contacts are done: the backend (C.1) and the frontend (C.2).

V1 was narrowed by the owner on 2026-11-04 (PRD "V1 scope", docs/release/v1/scope/scope-v1.md), and this wins over the "V1 focuses on" list above: analytics is V1.1, right after the launch; the technical project workspace and experience, skills and education are after V1; minimal contacts are in V1.



Completed:



backend Phase 0: Docker Compose with PostgreSQL 17, FastAPI skeleton, settings, Dockerfile, CI (ruff lint, ruff format check, pytest)

backend Phase 1: GitHub OAuth login, server-side sessions, logout, current user (ADR-012); profile editing and publication, Origin check and CORS (ADR-013)

backend Phase 2: public profile endpoint with a whitelisted DTO (ADR-013)

backend Phase 3: projects, technologies and featured projects — models and migration, cabinet API, public projects in the profile response (ADR-015)

frontend F1–F6: Next.js skeleton, sign-in, cabinet, public page /u/[slug], projects cabinet, project blocks on the public page (ADR-014, ADR-015; manual checks against the backend pending)

backend Phase 5 step 5.1: github_repositories and project_repositories models and migration; the database holds "one repository per project" and "a user links a repository to at most one of their projects" (ADR-017)

backend Phase 5 steps 5.2–5.4: the GitHub API client with app credentials and the per-user request budget (ADR-016, ADR-018); the repository list with its in-memory page cache; linking and unlinking a project with the relation check (ADR-017)

backend Phase 5 step 5.5: import of a repository as a DRAFT + PRIVATE project linked to it, in one transaction (ADR-017)

backend Phase 5 step 5.6: the linked repository (github: null or full_name and html_url) in the items of GET /projects, in one batched query (ADR-017)

frontend F-GH1.1: the API client and types for the GitHub endpoints, with whitelist readers for GitHub data and typed GitHub error codes

frontend F-GH1.2: the repository page /me/repositories (list, paging, import, the link dialog, the GitHub error states with the countdown) and «Проект создан» in the project form (manual check against the backend pending)

frontend F-GH1.3 (with the former F-GH1.4): the repository block in the project form (link by name, replace, unlink, the GitHub error states with the countdown), the GitHub label on «Мои проекты» and the login note

backend Phase 6 step 6.1: the sync tables github_sync_jobs and github_sync_category_status, schema and migration only; links made before it have no job and stay NOT_SYNCED (ADR-018)

backend Phase 6 step 6.2: a sync job queued with each link and import (their metadata read recorded as a metadata success), POST /integrations/github/repositories/{id}/sync with the 10-minute pause per repository and 7 requests charged to the user, and github.sync in ProjectResponse (ADR-018); jobs stay QUEUED until the worker (6.3)

backend Phase 6 step 6.3: the worker core — claim with SKIP LOCKED, the outcome fenced by the attempt, retries with backoff, the watchdog, rate limits without an attempt, the reserve of 500, the startup credential check, the loop with graceful stop; one worker process; no GitHub processor or entry point yet, so jobs still stay QUEUED (ADR-009, ADR-018)

backend Phase 6 step 6.4: the processor — metadata by id and languages, each in its own short transaction with its category status, the relation of every link recomputed from up to 5 contributor pages; python -m app.github.worker, run by hand until 6.6 (ADR-018)

frontend F-GH1.5: the sync status, the language chips with shares and the data date in the project form, «Обновить данные» with the pause, and polling every 5 seconds while a job is active (visible tab only, at most 2 minutes)

frontend F-GH1.6: one warning for an unavailable repository, without the failed sync message, announced from its own live region

backend Phase 6 step 6.5: periodic syncs queued in the worker's iteration (at most once a minute, 30 jobs at a time, repositories of PUBLISHED projects with no job in 24 hours, nothing during a hold), the two-404 rule with unavailable_since keeping its first date (ADR-018)

backend Phase 6 step 6.6: the github-worker service in Compose on the backend image, always on, updated only with the whole stack (docker compose up -d --build), and a CI workflow that checks it (ADR-018)

backend Phase 6 step 6.7: the nullable github object on public project cards with its ten-field whitelist, null without a link, without a success of every category, for an unavailable repository or a lost relation; one batched query, no GitHub call, no cache (ADR-019)

frontend F-GH2: the GitHub block on public project cards and rows, server rendered, with the date as a day in UTC; a wrong github object hides only the block, with one log line per project (ADR-019)

backend C.1: contacts of the profile — the profile_contacts table and migration; contacts in PATCH /profile, replaced whole under the profile lock, normalized per type with links built by the server; contacts in both profile responses, EMAIL and PHONE public without values; GET /public/profiles/{slug}/contacts?type=EMAIL|PHONE with Cache-Control: no-store, no rate limit until 8.3 (ADR-020)

frontend C.2: the «Контакты» section of the public page with the hero button, links rendered only after a check by type, email and phone requested on a click by one client component that gets the type and the slug; the contacts block in the profile form, the list sent whole and only when it changed, server errors placed by the index of the sent list (ADR-020)

deployment Phase 9 step 9.1: the production topology ADR — one origin behind Nginx (/api/v1/* → FastAPI, the rest → Next.js, SSR to the API on the internal network), TLS on Nginx with Let's Encrypt, X-Forwarded-For replaced by Nginx and trusted only from it, only Nginx on 80/443, one host with Compose; documents only, no code (ADR-0021)

deployment Phase 9 step 9.2: the frontend image (Next.js standalone, built for one address), the nginx image (one origin, 80 → https except the ACME challenge, HSTS, X-Forwarded-For replaced, other hosts dropped, a self-signed certificate until Let's Encrypt issues one, reload every 6 hours), the certbot service, docker-compose.prod.yml with a fixed Nginx address that uvicorn trusts through FORWARDED_ALLOW_IPS, DEPLOY.md and CI checks of both images (ADR-0021)

deployment Phase 9 step 9.3: the production Compose — no published ports but Nginx's, rotated json-file logs on every service, COMPOSE_FILE in the server .env, secrets in .env (mode 600, not Compose secrets; env_file only on backend, migrate and github-worker), Settings with APP_ENV=production requiring an https FRONTEND_URL and GITHUB_CALLBACK_URL on the same origin, check_compose.py --production in CI, DEPLOY.md with the server, secret rotation, updates and rollback (ADR-0021)

Phase 4 step 4.0: the media and demo ADRs — screenshots in a host volume served by Nginx, uploaded through the backend and re-encoded to WebP with Pillow, at most 6 per project, files removed after commit with a manual sweep command (ADR-0022); the demo as a link with a preview, no iframe and no backend request to the demo URL, demo_url as a column of projects (ADR-0023)



Not yet started:



demo, screenshots, file storage and the public project page with its GitHub block — Phase 4 steps 4.1–4.6

the rest before the launch — steps 8.3, 8.4, 9.4–9.8

analytics — Phase 7, V1.1



Current next goal:



Phase 4 — Demo and Media, step by step: 4.1 demo_url on projects (ADR-0023); 4.2 screenshots — the media module with Pillow, project_screenshots, upload/caption/delete/reorder, cleanup, the media volume and /media/ in Nginx (ADR-0022); 4.3 the public project endpoint with its GitHub block; 4.4 the mockup; 4.5 the cabinet; 4.6 the public page /u/{slug}/projects/{id}, demo first. The full order is in docs/release/v1/scope/scope-v1.md, "Порядок реализации (оставшееся)".

Do not start a step before the previous one is merged.



Documentation



Important documentation:



/docs/product/

/docs/architecture/

/docs/api/

/docs/adr/



Read relevant documentation before making architectural changes.



If documentation conflicts with the code, identify the conflict instead of silently choosing one.



Important rule



Do not turn V1 into a distributed system.



Prefer:



simple

explicit

testable

maintainable



over:



complex

abstract

distributed

prematurely scalable

