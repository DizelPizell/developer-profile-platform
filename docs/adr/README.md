# Architecture Decision Records

Use an ADR for decisions affecting architecture, technology, security, data models with long-term impact, external integrations or operations.

Do not create an ADR for every implementation detail.

When an architectural decision changes, create a new ADR or supersede the existing one. Do not silently change architecture during implementation, and do not delete a superseded ADR — mark its status instead.

## Numbering

This repository contains two ADR naming conventions, created at different points in the project's history:

- **Legacy series** — bare numbers, no prefix: `001-modular-monolith.md` … `012-github-sync-model.md`. This series is frozen: no new ADRs are added to it.
- **Current series** — `ADR-NNN-slug.md`, starting at `ADR-001-modular-monolith.md`. This is the active convention.

The two series were numbered independently, so numbers repeat across them (for example, legacy `003-postgresql.md` and `ADR-003-github-token-storage.md` are unrelated decisions). To avoid ambiguity without renaming existing files:

- A bare reference such as "ADR-003" means the current-series file, `ADR-003-...`.
- The legacy series is always referred to by its full filename (e.g. "legacy ADR `003-postgresql.md`"), never by a bare number.
- **All new ADRs continue the current series.** It currently runs from `ADR-001-modular-monolith.md` to `ADR-019-public-github-data.md`; the next ADR is ADR-020. No new legacy-style (unprefixed) ADR is created.

This keeps every future "ADR-NNN" reference unambiguous without a mass rename. A one-time rename to unify both series into a single sequence was considered and rejected here — it would rewrite file history across every existing cross-reference for a cosmetic gain; if this is revisited, it should be a deliberate, discussed, separate change rather than an automatic one.

## Current status of every ADR

### Current series (`ADR-NNN-slug.md`)

| ADR | Title | Status |
|---|---|---|
| ADR-001-modular-monolith.md | Modular Monolith | Accepted |
| ADR-002-kafka-and-outbox.md | Kafka and Outbox for Asynchronous GitHub Synchronization | **Superseded by ADR-008-no-kafka-outbox-v1.md** |
| ADR-003-github-token-storage.md | Encrypted GitHub OAuth Token Storage | Accepted (not applied in V1: no user token is stored, see ADR-016) |
| ADR-004-project-contribution.md | Project Contribution as Project Fields in V1 | Accepted |
| ADR-005-project-lifecycle-and-visibility.md | Separate Project Lifecycle and Visibility | Accepted (allowed combinations and transitions fixed by ADR-015) |
| ADR-006-project-workspace-not-sandbox.md | Read-only Project Workspace in V1 | Accepted |
| ADR-007-github-is-source-of-technical-evidence.md | GitHub as Technical Evidence Source | Accepted |
| ADR-008-no-kafka-outbox-v1.md | No Kafka or Outbox in V1 | Accepted |
| ADR-009-github-sync-worker-execution-model.md | GitHub Sync Worker Execution Model | Accepted (triggers, rate limits and status contract refined by ADR-018) |
| ADR-010-github-evidence-data-model-v1.md | GitHub Evidence Data Model V1 | Accepted (narrowed for V1 by ADR-018: metadata and languages only) |
| ADR-011-partial-sync-success.md | Partial Sync Success — Mandatory and Optional Categories | Accepted (narrowed for V1 by ADR-018: metadata and languages only) |
| ADR-012-github-oauth-only-authentication.md | GitHub OAuth-Only Authentication | Accepted (CSRF question resolved by ADR-013; separate repository-access consent superseded by ADR-016) |
| ADR-013-profile-editing-and-origin-check.md | Profile Editing, Publication and Origin Check for State-Changing Requests | Accepted (public profile gains projects and CORS gains `DELETE` per ADR-015) |
| ADR-014-frontend-stack.md | Frontend Stack and Rendering Model | Accepted (open questions listed in the file) |
| ADR-015-project-model.md | Project Model, Technologies and Featured Projects | Accepted (amends ADR-005 and ADR-013; imported projects resolved by ADR-017; open questions listed in the file) |
| ADR-016-github-access-v1.md | GitHub Access in V1 — Public Data with App Credentials | Accepted (partly supersedes ADR-012; sets ADR-003 aside for V1) |
| ADR-017-repository-linking-and-import.md | Repository Linking and Import | Accepted (open questions listed in the file) |
| ADR-018-github-sync-v1.md | GitHub Synchronization in V1 | Accepted (narrows ADR-010 and ADR-011, refines ADR-009; open questions listed in the file) |
| ADR-019-public-github-data.md | Public GitHub Data | Accepted (README display policy open) |

### Legacy series (bare numbers, frozen)

| ADR | Title | Status |
|---|---|---|
| 001-modular-monolith.md | Modular Monolith | Superseded by ADR-001-modular-monolith.md |
| 002-nextjs.md | Next.js | Accepted |
| 003-postgresql.md | PostgreSQL | Accepted |
| 004-rest-api.md | REST API | Accepted |
| 005-authentication.md | HTTP-only Cookie Sessions and GitHub OAuth | Accepted (token-storage extended by ADR-003; login method superseded by ADR-012-github-oauth-only-authentication.md; session/cookie security requirements remain) |
| 006-github-source-of-truth.md | GitHub as Technical Evidence Source | Superseded by ADR-007-github-is-source-of-technical-evidence.md |
| 007-object-storage.md | S3-compatible Object Storage | Accepted |
| 008-no-microservices-v1.md | No Microservices in V1 | Superseded by ADR-001-modular-monolith.md |
| 009-analytics-first-class.md | Analytics as a First-Class Domain | Accepted (CV_DOWNLOAD amended to deferred — see note in the file) |
| 010-no-arbitrary-code-execution.md | No Arbitrary Repository Execution in V1 | Superseded by ADR-006-project-workspace-not-sandbox.md |
| 011-evidence-over-score.md | Evidence Over Scores | Accepted (GitHub-specific application formalized in ADR-007-github-is-source-of-technical-evidence.md) |
| 012-github-sync-model.md | Normalize GitHub Data Locally | Accepted (transport decision now in ADR-008-no-kafka-outbox-v1.md) |

A "Superseded" status means the decision itself has been replaced; the file is kept, unedited in substance, as the historical record of what was decided and why at the time. "Accepted" means the decision still holds, whether or not it has since been amended by a note or a later ADR; this is the status written in each ADR file.

## Open decisions requiring discussion

These are known gaps intentionally left unresolved, because resolving them would mean making a new architectural decision rather than reconciling existing ones:

- **File content retrieval for code viewer.** Whether file content is fetched on demand from GitHub with a short-lived cache, or stored locally. Provisional direction: on-demand. Not confirmed; a separate decision is required before implementation. See ADR-011-partial-sync-success.md. README and the file tree themselves are deferred in V1 (ADR-018).
- **README display policy.** Plain text or rendered markdown, HTML in markdown, images from other hosts. Required before README returns. See ADR-019.
- **GitHub follow-ups.** Private repositories through a GitHub App (ADR-016); cleanup of unlinked `github_repositories` rows and of the data of unavailable repositories (ADR-017); periodic syncs for repositories linked only to hidden projects (ADR-018); GitHub API behaviors not yet verified, checked in step 5.2 (ADR-016, ADR-017, ADR-018).
- **CV feature.** Whether V1 includes any CV generation/storage/download capability at all; `CV_DOWNLOAD` stays deferred until this is decided.
- **Profile follow-ups.** Markdown in `bio`, profile photo upload, slug change, rate limiting and the `__Host-` cookie prefix. See ADR-013.
- **Frontend follow-ups.** How server-side Next.js code sees the session cookie across ports; production topology (one origin behind Nginx or a separate API host); when Playwright is introduced; caching of public pages; sync status and file content for the IDE view (depends on ADR-009–011). See ADR-014.
- **Project follow-ups.** Returning a published project to draft; skills as technologies confirmed by published projects (deferred, unresolved); technology spelling and curation; showcase description and highlights; fields of later phases; the public project page (Phase 4); deletion side effects in object storage and analytics; markdown in project fields; the project and technology limits. See ADR-015.

Resolved by this round (no longer open): the GitHub sync worker/queue mechanism, GitHub sync status storage shape (ADR-009), and the storage shapes for README (TEXT column), languages (JSONB), file tree (JSONB) and contributors (ADR-011); contributor unique key `(github_repository_id, github_user_id)` (ADR-011); commits classified as optional history category — fetch failure does not block `SYNCED`, append-only model, freshness tracked in `github_sync_category_status` (ADR-011); GitHub OAuth as the only login mechanism, email nullable and not unique, USER 1:1 GITHUB_ACCOUNT, auth_sessions table with token_hash only, slug rules (ADR-012); session lifetime fixed at 14 days absolute via `SESSION_TTL_DAYS` (ADR-012); `github_login` and `email` refreshed from GitHub on every login (ADR-012); profile fields, publication rules, identical 404 for non-public profiles, Origin check instead of a CSRF token, and CORS policy (ADR-013); frontend stack, direct browser-to-API calls in development, SSR for the public profile and a client-side cabinet (ADR-014); project owner and 404 rule, the four allowed lifecycle/visibility pairs and the transitions, Phase 3 project fields and publish requirements, shared technologies, featured projects in `project_showcases` with a database-held limit of three and deferrable ordering, hard delete, the project limit, project error codes, projects in the public profile, `DELETE` in CORS (ADR-015); public GitHub data only, read with the app's credentials, no user token stored, no connect or disconnect flow (ADR-016); a shared `github_repositories` table with its V1 field list, `project_repositories`, the `OWNER`/`CONTRIBUTOR`/`NONE` relation, linking and import rules, forks, renames, unavailable repositories (ADR-017); V1 sync categories, sync triggers, rate-limit handling, the two-404 rule, the sync status contract (`github.sync` in the cabinet project response) and the worker service (ADR-018); the public `github` object on project cards and its whitelist (ADR-019).

## Deliberately deferred (not open questions — revisit only with a new decision)

- **Dependencies (GitHub Evidence).** Deferred pending a separate review of GitHub API behavior and availability — not a live open question, not rejected outright. See ADR-010-github-evidence-data-model-v1.md.
- **Pull Requests, Releases, CI/CD as separate synced entities, and storing GitHub file content in PostgreSQL.** Explicitly out of required V1 scope. See ADR-010.
- **README, file tree, contributors and commits.** Not fetched or stored in V1; they return with the public project page and a README display decision, under the rules of ADR-010 and ADR-011. See ADR-018.

## Where to look

- `docs/architecture/ARCHITECTURE.md` — current C4-style architecture and diagrams.
- `docs/architecture/ARCHITECTURAL_DIALOGUE.md` — the full decision narrative, including superseded reasoning kept for historical context.
- `docs/architecture/DOMAIN_MODEL.md` — domain rules, lifecycles, use cases.
- `docs/database/DATABASE_SCHEMA.md` and `docs/database/DATABASE_DECISIONS.md` — data model.
