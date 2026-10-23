# Architectural Dialogue and Decisions

## 1. Purpose

This document records the architectural discussion and decisions made during product discovery and architecture design for **Developer Professional Profile Platform**.

It is a decision record, not implementation documentation.

The purpose is to preserve:
- what problem we are solving;
- what alternatives were discussed;
- why a decision was made;
- what was deliberately excluded from V1;
- which decisions are still open.

Claude Code should use this document together with the project PRD, CLAUDE.md, API documentation and ADRs as architectural context.

---

## 2. Product Principle

> **Не рассказывай, что ты умеешь. Покажи.**

The platform is a professional developer profile platform where a developer can demonstrate real work through projects, live demos, GitHub evidence, technical context and personal contribution.

The platform is not intended to become a LinkedIn/HH clone in V1.

V1 validates the core concept:

> A structured professional profile with evidence and real projects can communicate a developer's experience better than a static resume alone.

The platform does not attempt to prove that a developer is "good". It provides structured information and evidence so that another person can evaluate the developer independently.

---

## 3. Product Scope

### V1

V1 includes:

- developer registration and authentication;
- public developer profile;
- profile information;
- experience;
- education;
- skills;
- projects;
- project descriptions;
- developer role and contribution;
- technologies;
- screenshots;
- Demo URL;
- GitHub repository connection;
- GitHub repository import;
- GitHub synchronization;
- project showcase;
- up to three featured projects;
- public profile;
- recruiter-oriented view;
- technical project view;
- read-only Project Workspace;
- analytics;
- privacy/visibility controls.

### V2

Potential V2 functionality:

- recruiter accounts;
- candidate search;
- candidate filters;
- saved candidates;
- vacancies;
- applications;
- messaging;
- matching/recommendations;
- more advanced AI-assisted analysis.

V2 functionality must not be implemented inside V1 merely because the data model could support it.

---

# 4. Product Decisions

## 4.1 Demo-first project presentation

When a project has a working Live Demo, the demo is the primary content of the project page.

Preferred presentation:

1. Live Demo
2. concise project context
3. technical/project details
4. code/GitHub

If embedding is blocked by CSP or `X-Frame-Options`, the platform shows a preview and provides an external link.

The platform does not attempt to bypass the target site's embedding restrictions.

---

## 4.2 Project Workspace is a viewer, not an arbitrary code execution environment

V1 does not execute arbitrary GitHub repositories.

The Project Workspace is a read-only technical viewer similar in presentation to an IDE.

It can contain:

- file tree;
- source code viewer;
- README;
- architecture;
- tests;
- Git information;
- documentation;
- technical analytics.

The purpose is to make technical evidence easier to inspect.

A managed execution sandbox is explicitly postponed.

A future sandbox would require isolation, resource limits, network restrictions, lifecycle management and security controls. It is not part of V1.

---

## 4.3 GitHub is evidence, not the whole project

GitHub provides technical evidence (V1 scope, see section 30 and ADR-010-github-evidence-data-model-v1.md):

- repository (metadata);
- README;
- languages;
- file tree (metadata only — no file content in V1);
- contributors (GitHub's own reported data, no derived scores);
- commits (up to 100 most recent per sync).

Not part of the required V1 scope: pull requests, releases, dependencies (deferred pending a separate GitHub API review), Docker/tests/CI as separate entities.

The developer provides contextual information:

- role;
- contribution;
- business/problem context;
- goals;
- results;
- screenshots;
- demo URL.

The UI should distinguish GitHub-derived information from information provided by the developer.

The system must not invent contribution percentages or artificial skill scores.

Examples of deliberately rejected concepts:

- `Python = 9.4/10`;
- `Developer Score = 8.7`;
- contribution percentage inferred from commit count.

Evidence should be presented instead of pseudo-precision.

---

# 5. Architecture Direction

## 5.1 Modular monolith

The selected architecture is a **modular monolith**.

Initial stack:

- Frontend: Next.js + TypeScript
- UI: Tailwind CSS + shadcn/ui
- Backend: FastAPI + Python
- Database: PostgreSQL
- ORM: SQLAlchemy 2
- Migrations: Alembic
- Backend tests: pytest
- Frontend tests: Vitest + React Testing Library
- E2E: Playwright
- Authentication: HTTP-only session cookies
- OAuth: GitHub OAuth
- Object storage: S3-compatible storage
- Local object storage: MinIO
- Containers: Docker
- CI/CD: GitHub Actions
- Reverse proxy: Nginx
- API: REST
- Documentation: OpenAPI + Markdown/ADR

The rule is:

> No technology is added without a concrete problem it solves.

---

## 5.2 Why not microservices

V1 does not require independent deployability of every domain.

The domain boundaries are still modeled explicitly, but they live in one backend application.

Initial logical contexts:

- Identity
- Profile
- Projects
- GitHub
- Analytics
- Files

Workers are an infrastructure/asynchronous processing mechanism, not an additional business bounded context. V1 does not use Kafka — see section 28 and ADR-008-no-kafka-outbox-v1.md.

---

# 6. Backend Logical Flow

The intended backend dependency direction is:

```text
HTTP/API
   ↓
Controller/API layer
   ↓
Application / Use Case layer
   ↓
Domain
   ↓
Repository
   ↓
Infrastructure
```

The project should not implement an excessively elaborate version of Clean Architecture.

The architecture exists to protect business rules and boundaries, not to create abstraction for its own sake.

---

# 7. Authentication Decision

## 7.1 Session model

Authentication uses HTTP-only cookies.

The browser should not store the authentication token in `localStorage`.

Production cookies are expected to use:

- `HttpOnly`;
- `Secure`;
- appropriate `SameSite` policy.

The exact CSRF strategy must be explicitly implemented and documented before authentication is considered complete.

---

## 7.2 Same-origin deployment

The intended production routing is:

```text
Browser
   ↓
Nginx
 ├── /      → Next.js
 └── /api/* → FastAPI
```

This keeps the frontend and API under one public origin and simplifies cookie handling.

CORS should not be used as a substitute for an explicit authentication/CSRF design.

---

## 7.3 GitHub OAuth

GitHub OAuth is separate from the platform's own authentication.

Expected flow:

```text
GET /api/v1/integrations/github/connect
        ↓
GitHub
        ↓
GET /api/v1/integrations/github/callback
```

The OAuth callback must validate the OAuth `state`.

---

# 8. GitHub Token Storage

GitHub access tokens must never be stored in plaintext.

The application stores an encrypted token.

The encryption key must be supplied through environment/secret-management infrastructure rather than stored in the repository or database.

Tokens must never be:

- returned by API DTOs;
- written to logs;
- exposed to frontend code.

The exact encryption implementation is an implementation decision that must satisfy the above architectural requirement.

---

# 9. GitHub Synchronization

GitHub synchronization is asynchronous.

The API should not perform a potentially long synchronization during the original HTTP request.

Lifecycle:

```text
NOT_SYNCED
    ↓
QUEUED
    ↓
SYNCING
   ↙   ↘
SYNCED  FAILED
          ↓
        QUEUED
```

A sync operation must be idempotent.

Duplicate delivery of an event must not create duplicate repository data or corrupt state.

A sync job stores:

- status;
- retry count;
- timestamps;
- last error.

This section fixes the lifecycle and the idempotency requirement only. GitHub synchronization does not use Kafka or an Outbox pattern in V1 — see section 28 and ADR-008-no-kafka-outbox-v1.md. The worker claims jobs via PostgreSQL polling and `SELECT ... FOR UPDATE SKIP LOCKED` — see section 29 and ADR-009-github-sync-worker-execution-model.md. Whether the API exposes a sync-status endpoint remains an open decision.

---

> **Superseded (2026-10-03):** sections 10-12 describe Kafka and the Outbox pattern, which were adopted and then rejected for V1. See section 28 and ADR-008-no-kafka-outbox-v1.md. These sections are retained as the historical record of the original reasoning.

# 10. Kafka Decision

> **Historical — superseded by ADR-008-no-kafka-outbox-v1.md (2026-10-03).** The decision described here was reversed in section 28. Retained as the original reasoning.

Kafka was considered because GitHub synchronization is asynchronous and because the project is intentionally being used to learn production-oriented architecture.

Kafka is adopted as an **event transport**, not as a replacement for REST or PostgreSQL.

Normal CRUD remains synchronous:

```text
Frontend → FastAPI → PostgreSQL
```

Asynchronous workflow:

```text
FastAPI
   ↓
PostgreSQL
   ↓
Outbox
   ↓
Kafka
   ↓
Worker
   ↓
PostgreSQL
```

Kafka is not a bounded context and does not imply a microservice architecture.

---

# 11. Outbox Pattern

> **Historical — superseded by ADR-008-no-kafka-outbox-v1.md (2026-10-03).** The Outbox pattern was rejected for V1 together with Kafka. See section 28. Retained as the original reasoning.

The project uses an Outbox Pattern for reliable publication of asynchronous events.

The problem being solved is the dual-write failure:

```text
Database commit succeeds
Kafka publish fails
```

or:

```text
Kafka publish succeeds
Database commit fails
```

The chosen flow is:

```text
single PostgreSQL transaction
    ├── business state change
    └── outbox event
              ↓
        outbox relay
              ↓
            Kafka
```

PostgreSQL is the durable source of truth.

Kafka is the transport mechanism.

---

# 12. Kafka Scope

> **Historical — superseded by ADR-008-no-kafka-outbox-v1.md (2026-10-03).** The scope described here was superseded when Kafka was removed from V1. See section 28. Retained as the original reasoning.

### V1

Kafka is used for GitHub synchronization.

Primary event:

```text
github.sync.requested.v1
```

The event contains an event ID and enough information to identify the sync job/repository.

### Analytics

Analytics is intentionally kept synchronous in V1:

```text
Frontend → FastAPI → PostgreSQL
```

Kafka for analytics was discussed but rejected for V1 because the additional infrastructure does not solve a sufficiently important current problem.

If analytics volume later creates a concrete need for asynchronous processing, Kafka can be introduced for that workload separately.

---

# 13. Worker Model

> **Note (2026-10-03):** the GitHub Sync Worker still exists in V1, but it no longer consumes Kafka events — see section 28. The description below of workers "consuming events" refers to the original Kafka-based design and is historical.

Workers are separate processes, but they remain part of the modular-monolith codebase.

Initial worker:

```text
GitHub Sync Worker
```

Potential later worker:

```text
Analytics Worker
```

Workers consume events and execute application/domain operations.

They must be safe against duplicate event delivery.

---

# 14. Project Model

A project is independent from GitHub and Demo.

A project can exist for:

- commercial work;
- NDA work;
- educational work;
- personal projects;
- projects without a public repository.

Therefore:

```text
Project
 ├── optional GitHub repository
 └── optional Demo
```

is required.

---

# 15. Project Contribution Decision

The initial model contained a separate `PROJECT_CONTRIBUTION` entity.

After discussion, this was considered unnecessary for V1.

For V1, the developer's role and contribution are fields directly on the project:

```text
Project
 ├── role
 └── contribution
```

A separate contributor model can be introduced in a future version if a project needs to represent multiple contributors.

This avoids designing team/collaboration functionality before the product requires it.

---

# 16. Project Lifecycle and Visibility

Lifecycle and visibility are different concepts.

### Project lifecycle

```text
DRAFT
PUBLISHED
ARCHIVED
```

### Project visibility

```text
PUBLIC
PRIVATE
```

Lifecycle describes the state of the project in the product.

Visibility describes whether it can be exposed publicly.

The implementation must validate invalid or meaningless combinations explicitly.

---

# 17. Profile Lifecycle

Profile publication is simpler:

```text
PRIVATE
   ↕
PUBLISHED
```

"Unpublish" is represented by returning the profile to `PRIVATE`.

A separate `UNPUBLISHED` state is not required for V1.

---

# 18. Featured Projects

A profile can have a maximum of three featured projects.

The developer controls:

- which projects are featured;
- their order;
- showcase-specific presentation.

The showcase is therefore modeled separately from the project itself.

```text
Project
   │
   └── Project Showcase
```

The maximum of three featured projects is a business invariant.

It must be protected against race conditions, not only checked in frontend code.

---

# 19. Project Showcase

A project and its presentation in a profile are separate concepts.

`Project` contains the project itself.

`Project Showcase` contains profile presentation data such as:

- featured status;
- ordering;
- showcase description;
- highlights.

This separation allows a project to exist independently from whether it is currently featured.

---

# 20. Files

Files are a separate infrastructure/domain context because multiple features need file storage.

Potential V1 file types:

- profile avatar;
- project screenshots;
- potentially CV.

Physical files are stored in S3-compatible storage.

PostgreSQL stores metadata and references to the stored objects.

Local development uses MinIO.

---

# 21. CV Decision

`CV_DOWNLOAD` was initially included as an analytics event, but the actual V1 CV generation/storage flow must be explicitly defined.

The system must not expose a "CV download" metric without an actual CV feature.

If CV generation is not included in V1, `CV_DOWNLOAD` should be removed from the active analytics contract until the feature exists.

**Resolved (2026-10-03):** V1 does not define a CV generation/storage feature. Therefore `CV_DOWNLOAD` is deferred and excluded from the active V1 analytics contract until a CV feature is specified in a future decision.

---

# 22. Analytics

Analytics is not critical-path functionality.

Events (active in V1):

```text
PROFILE_VIEW
PROJECT_VIEW
DEMO_CLICK
GITHUB_CLICK
CONTACT_CLICK
```

Deferred, not part of the active V1 contract (see section 21):

```text
CV_DOWNLOAD
```

The primary funnel is:

```text
Profile
   ↓
Project
   ↓
Demo
   ↓
Contact
```

The developer should be able to see which projects receive attention.

Analytics must not block navigation to a Demo or public profile.

Privacy requirements still need to define:

- collected metadata;
- retention;
- privacy implications;
- whether consent is required for any particular analytics mechanism.

---

# 23. Database Principles

PostgreSQL is the source of truth for application state.

The database should enforce important invariants through:

- primary keys;
- foreign keys;
- unique constraints;
- indexes;
- appropriate check constraints;
- transactions.

Application-level validation is still required for business rules that cannot be represented cleanly as a database constraint.

---

# 24. Current Database Domains

The current conceptual model contains:

```text
users
profiles
experiences
educations
skills

projects
project_showcases
technologies
project_technologies
project_screenshots
project_demo

github_accounts
github_repositories
project_repository

github_sync_jobs
github_commits

analytics_events

files
```

Proposed, not yet confirmed (see ADR-010-github-evidence-data-model-v1.md and Open Decisions in `docs/adr/README.md`): a README entity, a languages entity, a file-tree-entries entity, a contributors entity. Their storage shape and the exact `github_repositories` field list are not decided.

`outbox_events` has been removed following the rejection of Kafka/Outbox for V1 — see section 28 and ADR-008-no-kafka-outbox-v1.md. GitHub sync status storage is resolved: `github_sync_jobs` is the single source of truth, one row per logical sync job — see section 29 and ADR-009-github-sync-worker-execution-model.md.

The exact SQL schema is maintained separately in `docs/database/DATABASE_SCHEMA.md` and `docs/database/DATABASE_DECISIONS.md`.

---

# 25. What Is Explicitly Not in V1

Do not add the following without a new product/architecture decision:

- recruiter accounts;
- candidate search;
- vacancies;
- applications;
- messaging;
- matching;
- AI candidate scoring;
- arbitrary repository execution;
- Kubernetes;
- microservices;
- Kafka or Outbox in V1 (see ADR-008-no-kafka-outbox-v1.md);
- GitHub Dependencies, Pull Requests, Releases or CI/CD as separate synced entities in V1 (see ADR-010-github-evidence-data-model-v1.md);
- storing GitHub file content in PostgreSQL in V1 (see ADR-010-github-evidence-data-model-v1.md);
- Redis without a concrete requirement;
- a full IDE;
- automatic skill scoring;
- automatic contribution scoring.

---

# 26. Architecture Review Principles

When proposing a new component, answer:

1. What problem does it solve?
2. Why can't the current architecture solve it?
3. What operational complexity does it add?
4. What failure modes does it introduce?
5. Does it belong in V1?
6. How will it be tested?
7. How will it be observed in production?
8. Can it be removed later?

Technology must follow the problem, not the other way around.

---

# 27. Current Stage

The project is currently at the architecture/bootstrap stage.

Existing infrastructure:

- repository;
- Docker;
- PostgreSQL;
- project documentation;
- backend skeleton;
- Claude Code environment.

Next implementation stage:

```text
Database architecture
        ↓
SQLAlchemy models
        ↓
Alembic migration
        ↓
FastAPI ↔ PostgreSQL
        ↓
tests
```

Claude Code is responsible for implementation.

Architecture decisions should be changed through discussion and documentation rather than silently changing the model during implementation.

---

# 28. Kafka and Outbox Removed from V1 (2026-10-03)

After further discussion, Kafka and the Outbox pattern (sections 10-12) were reconsidered.

## Decision

V1 does not use Kafka.

V1 does not use the Outbox pattern.

GitHub synchronization remains asynchronous and idempotent, with the lifecycle described in section 9, but V1 implements it without a message broker or an outbox relay.

## Reason

The operational complexity Kafka and an Outbox relay add — brokers, consumer groups, an additional relay component, additional failure modes, additional monitoring surface — is disproportionate to the current V1 requirement. CLAUDE.md's own guidance is that Redis, Kafka and Kubernetes are not part of V1 unless a concrete requirement appears. The requirement used to justify Kafka in section 10 (reliable asynchronous delivery) can be met directly against PostgreSQL, which is already the system's durable source of truth.

## What this does not decide

This reversal does not decide the worker/queue mechanism that replaces Kafka. Whether sync jobs are claimed by a worker through polling, `LISTEN/NOTIFY`, or another mechanism, how retries are scheduled, and whether the API exposes a sync-status endpoint, remain open decisions — see Open Decisions.

## Formal record

See ADR-008-no-kafka-outbox-v1.md, which supersedes ADR-002-kafka-and-outbox.md. Sections 10-12 are retained unchanged as the historical record of the original adoption.

---

# 29. GitHub Sync Worker Execution Model (2026-10-12)

Resolves the open question left by section 28 and ADR-008: the exact worker/queue mechanism.

## Decision

The GitHub Sync Worker runs as a separate process. It claims pending work from `github_sync_jobs` using PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`, polling at a configurable interval. No broker, no Outbox relay, no Redis.

One `github_sync_jobs` row represents one logical sync request, not one physical attempt. Automatic retries reuse the same row and increment `attempt_count`. `github_sync_jobs` is the single source of truth for sync status — `github_repositories` does not duplicate it.

At most one active job per repository: enforced with a partial unique index on `github_repository_id` for `status IN ('QUEUED', 'SYNCING')`.

`FAILED` is strictly terminal. A transient failure with attempts remaining transitions the same row directly back to `QUEUED` with a future `scheduled_at`, in the same operation as the failure handling — the row is never left resting in `FAILED` while a retry is still pending. This is what keeps the partial unique index correct.

## Starting configuration (V1, configurable)

- Maximum attempts: 5
- Polling interval: 5 seconds
- Base retry delay: 30 seconds
- Maximum retry delay: 30 minutes
- Abandoned-`SYNCING` threshold: 10 minutes

Backoff is exponential between the base and maximum delay. GitHub HTTP request timeouts are configured separately from these values. A watchdog recovers jobs stuck in `SYNCING` past the abandoned threshold, subject to the same attempt limit and the same `SKIP LOCKED` concurrency protection as normal processing.

## Formal record

See ADR-009-github-sync-worker-execution-model.md.

---

# 30. GitHub Evidence Data Model V1 (2026-10-12)

## Decision

V1 GitHub Evidence is split into:

- **Snapshot** (current GitHub state, reconciled on each successful sync): repository metadata, README, languages, file tree metadata (`path`, `type`, `sha`, `size` — no file content), contributors (GitHub's own reported data, no derived scores/percentages).
- **History** (append-only): commits — up to 100 most recent per sync run, keyed by `(github_repository_id, sha)`, `ON CONFLICT DO NOTHING`, never automatically deleted.

Snapshot reconciliation, identical for every snapshot category: fetch a complete snapshot first (if the fetch fails or is incomplete/truncated, do not touch existing data); then, in one short transaction with no network calls inside it, upsert everything present and delete everything no longer present.

**Documented limitation**: because each commit sync only fetches the 100 most recent commits, a repository accumulating more than 100 new commits between two syncs will have a permanent gap in stored history. Accepted for V1, not silently worked around.

Out of required V1 scope: Dependencies (deferred, not rejected — pending a separate GitHub API review), Pull Requests, Releases, CI/CD as a separate entity, and storing file content in PostgreSQL.

## Not decided here — require separate confirmation

- README: separate table or field on `github_repositories`.
- Languages: normalized table or `JSONB` column.
- Contributors: separate table (recommended, not confirmed).
- Exact `github_repositories` field list.
- Sync Status API endpoint contract.

## Formal record

See ADR-010-github-evidence-data-model-v1.md.

---

# 31. Partial Sync Success — Mandatory and Optional Categories (2026-10-23)

Resolves the open question from ADR-010 and section 30: what happens when individual category fetches fail, and what the storage shapes for README, languages and contributors are.

## Decision

### Mandatory vs optional categories

Not all categories have the same weight regarding job outcome.

**Mandatory** (metadata, README, languages, file tree): a fetch failure triggers retry per ADR-009; after attempts are exhausted the job transitions to `FAILED`.

**Optional** (contributors): a fetch failure is tolerated. The job may complete with `SYNCED` even when contributors data could not be fetched. Existing contributors rows are preserved on failure, consistent with ADR-010's rule for incomplete fetches.

### Per-category transactions

Each successfully fetched category is committed in its own short PostgreSQL transaction, not one transaction for the whole job. Partial success is intentional: a job may reach `SYNCED` with different data freshness per category. The transaction-boundary rule from ADR-010 still applies per category.

### No sub-statuses on github_sync_jobs

`github_sync_jobs.status` continues to follow the ADR-009 lifecycle — single status, no sub-statuses. Per-category freshness is tracked in a separate table `github_sync_category_status`: natural key `(github_repository_id, category)`, fields `last_success_at`, `last_error`, `last_error_at`.

### Storage shape decisions (closing ADR-010 open questions)

- **README**: column (or JSONB field) on `github_repositories`, replaced wholesale.
- **Languages**: JSONB column on `github_repositories`, replaced wholesale.
- **Contributors**: separate table `github_contributors`, snapshot, upsert + delete missing.
- **File tree**: not decided here — depends on Project Workspace UX.

### Sync status API — provisional direction only

A `GET` endpoint returning the latest `github_sync_jobs` row together with `github_sync_category_status` rows is the provisional direction. This is not confirmed; a separate decision is required before implementation.

## What this does not decide

- File tree storage shape (flat table vs lazy-load by folder).
- Sync status API endpoint exact contract.

## Formal record

See ADR-011-partial-sync-success.md.
