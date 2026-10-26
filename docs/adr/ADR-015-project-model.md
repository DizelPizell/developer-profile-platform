# ADR-015: Project Model, Technologies and Featured Projects

## Status

Accepted for the decisions below. The items under "Open questions" are not decided.

Amends ADR-005-project-lifecycle-and-visibility.md (allowed state combinations and transitions) and ADR-013-profile-editing-and-origin-check.md (projects in the public profile, `DELETE` in CORS).

## Context

DEVELOPMENT_PLAN Phase 3 adds projects: the model, technologies, lifecycle and visibility, CRUD, validation, the showcase with up to three featured projects and their order (US-007, US-012–US-014, US-018–US-021).

The existing documents fix only parts of this:

- ADR-005 separates lifecycle (`DRAFT`, `PUBLISHED`, `ARCHIVED`) from visibility (`PUBLIC`, `PRIVATE`) and says invalid combinations must be rejected, but does not list the valid ones.
- ADR-004 makes `role` and `contribution` plain fields on the project.
- DOMAIN_MODEL lists publish validation as "name, description, role, contribution, at least one technology", while the PRD separates a short and a full description. Which description is required was ambiguous.
- ARCHITECTURAL_DIALOGUE §18–19 makes the limit of three featured projects a business invariant that must hold under concurrent requests, and models the showcase separately from the project.
- API_CONTRACT lists the project and showcase paths without bodies, statuses or error codes. CORS (ADR-013) does not allow `DELETE`, which `DELETE /projects/{id}` needs.

## Decision

### Owner and access

- `projects.owner_id` references `users.id` with `ON DELETE CASCADE`. The showcase row references the profile (see "Featured projects").
- Every cabinet endpoint acts only on the current user's projects. A project of another user, a missing project and a malformed id all return the same 404 `NOT_FOUND` as an unknown URL; only `request_id` differs. This is the rule ADR-013 applies to private profiles.
- A user has at most **50** projects. Creating one more gives 409 `PROJECT_LIMIT_REACHED` with `details.limit = 50`. Creation locks the owner's profile row (`SELECT ... FOR UPDATE`) before counting, so two concurrent requests cannot both create the 50th project.

### States

Lifecycle (`projects.status`) and visibility (`projects.visibility`) stay separate (ADR-005). Only four pairs are allowed:

| `status` | `visibility` | Meaning |
|---|---|---|
| `DRAFT` | `PRIVATE` | Being prepared. Every new project starts here. |
| `PUBLISHED` | `PUBLIC` | Published and shown on the public profile. |
| `PUBLISHED` | `PRIVATE` | Published but hidden by the developer. |
| `ARCHIVED` | `PRIVATE` | Archived; never public. |

The domain rejects any other pair, and the database repeats it with a CHECK (`ck_projects_state`).

Transitions are idempotent `POST` actions:

| Action | From | To | Notes |
|---|---|---|---|
| `POST /projects/{id}/publish` | `DRAFT`, `ARCHIVED` | `PUBLISHED` + `PUBLIC` | Completeness check (below). Already `PUBLISHED` (either visibility): 200 without changes; a hidden project stays hidden. |
| `POST /projects/{id}/archive` | `PUBLISHED` | `ARCHIVED` + `PRIVATE` | Already `ARCHIVED`: 200 without changes. From `DRAFT`: 409 `PROJECT_TRANSITION_INVALID`. |
| `POST /projects/{id}/visibility` | `PUBLISHED` | `PUBLISHED` + the requested visibility | Body `{"visibility": "PUBLIC" \| "PRIVATE"}`. The same value: 200 without changes. In `DRAFT` or `ARCHIVED`: 409 `PROJECT_TRANSITION_INVALID`, whatever the value. |

The lifecycle follows DOMAIN_MODEL: `DRAFT → PUBLISHED → ARCHIVED`, plus re-publishing an archived project. Phase 3 has no way back from `PUBLISHED` to `DRAFT` (see "Open questions").

`PROJECT_TRANSITION_INVALID` carries `details.status` (the current lifecycle state), so the client can tell that its view is stale.

Mutations of one project lock its row (`SELECT ... FOR UPDATE`). An operation that also changes featured projects locks the profile row first, then the project row; this fixed order prevents deadlocks.

### Public visibility

A project appears in public output only when all three hold:

- `status = PUBLISHED`;
- `visibility = PUBLIC`;
- the owner's profile is `PUBLISHED`.

Unpublishing the profile hides all its projects from public output. Project states and featured projects do not change, so republishing the profile shows the same projects in the same order.

A profile can be published without projects; ADR-013's publication rule is unchanged.

### Fields (Phase 3)

| Field | Max length | Line breaks | Required to publish |
|---|---|---|---|
| `title` | 100 | no | yes |
| `summary` | 300 | no | yes |
| `description` | 5000 | yes | no |
| `problem` | 2000 | yes | no |
| `results` | 2000 | yes | no |
| `role` | 100 | no | yes |
| `contribution` | 2000 | yes | yes |

Plus `technologies`: at least one is required to publish.

- All are plain text: no markdown, never rendered as HTML.
- Normalization is the ADR-013 rule: trim, an empty result becomes `null`, control characters (`Cc`) give 422 `VALIDATION_ERROR`, `\r\n` becomes `\n` in fields that allow line breaks, and length is counted after trimming.
- Columns are nullable `TEXT`. CHECK constraints repeat the length and reject blank values (`ck_projects_<field>`).
- `POST /projects` accepts any subset of the fields, including none; a new project is `DRAFT` + `PRIVATE`.
- This resolves the DOMAIN_MODEL ambiguity: `summary` (short) is required to publish and `description` (full) is optional.

Completeness:

- `publish` with any required field empty gives 422 `PROJECT_INCOMPLETE` with `details.missing_fields`. The list is a subset of `title`, `summary`, `role`, `contribution`, `technologies`.
- A `PATCH` that would leave a `PUBLISHED` project incomplete (clearing a required field or setting `technologies` to `[]`) is rejected with the same error. `DRAFT` and `ARCHIVED` projects may be left incomplete; publishing checks them again.
- The database repeats the text part: `ck_projects_published_complete`, `status <> 'PUBLISHED' OR (title, summary, role and contribution are NOT NULL)`. "At least one technology" lives in another table, so only the domain enforces it, under the project row lock.

Fields for later phases: goals, architecture, highlights (Phase 4 or later, with the project page), demo and screenshots (Phase 4), the repository link (Phase 5).

### Technologies

- `technologies` is one table shared by all users: `id`, `name` (≤ 50), `created_at`.
- A name is trimmed and runs of whitespace become one space. It must then be 1–50 characters with no control characters. Any other printable character is allowed ("C#", "C++", "Node.js", "ASP.NET Core", Cyrillic).
- Uniqueness is case-insensitive: a unique index on `lower(name)` (`uq_technologies_name_lower`). The spelling shown is the one used when the row was created. A name is looked up or created with `INSERT ... ON CONFLICT DO NOTHING` followed by a `SELECT`, which is safe under concurrent requests.
- `project_technologies` links projects and technologies: `id`, `project_id`, `technology_id`, `position` 1..20. Constraints:
  - UNIQUE (`project_id`, `technology_id`);
  - UNIQUE (`project_id`, `position`).
  The `position` range together with the second constraint holds the limit of **20 technologies per project** in the database.
- The order is the developer's: the request list order. The first technology is the one shown in a compact row («Другие проекты» on the public page).
- `technologies` in a request body is a list that replaces the project's whole list. In one transaction the rows are deleted and re-inserted in the new order. Omitting the field keeps the list. More than 20 entries, or two names equal ignoring case, give 422 `VALIDATION_ERROR`; nothing is merged silently.
- Unused technology rows are kept; they are never shown on their own.
- **Skills are not part of Phase 3.** This is a deferred, unresolved direction: show the technologies of published projects as confirmed by projects, without self-assessment.

### Featured projects

- A row in `project_showcases` means the project is featured. Columns:
  - `id`;
  - `project_id` (UNIQUE, FK → projects, `ON DELETE CASCADE`);
  - `profile_id` (FK → profiles, `ON DELETE CASCADE`);
  - `position` (CHECK 1..3);
  - `created_at`.
- UNIQUE (`profile_id`, `position`). With the `position` range this caps a profile at three featured projects in the database itself. Even if application code ignored the limit, a fourth row could not be written.
- Only a `PUBLISHED` + `PUBLIC` project can be featured; otherwise 409 `PROJECT_NOT_FEATURABLE` with `details.status` and `details.visibility`. When three are already featured: 409 `FEATURED_LIMIT_REACHED` with `details.limit = 3`. The profile may be `PRIVATE`, so featured projects can be prepared before publishing it.
- Featuring adds the project after the last one. Featuring an already featured project returns 200 without changes.
- Archiving, hiding (`visibility = PRIVATE`) and deleting a project remove it from featured projects. Making it public or publishing it again does not restore it.
- Positions have no gaps: after a removal the remaining rows are renumbered 1..n in their old order, in the same transaction.
- Operations on featured projects lock the profile row first. The limit does not depend on this lock; it keeps the set stable while gaps are closed and while a reorder request is compared with the current set.
- The showcase description and highlights (ARCHITECTURAL_DIALOGUE §19) come later; this table has no presentation fields yet.

**Reordering under UNIQUE (`profile_id`, `position`).** The constraint is declared `DEFERRABLE INITIALLY IMMEDIATE`. PostgreSQL then checks it at the end of each statement, not after every row. A reorder, or the renumbering after a removal, is one `UPDATE ... SET position = CASE ... END` over the profile's rows. Swapping positions 1 and 2 passes, because the check sees only the final state. No `SET CONSTRAINTS ... DEFERRED` is needed.

- Why not a permutation through temporary values: the CHECK 1..3 forbids temporary positions such as 4–6 or negative numbers. Relaxing it for the shuffle would weaken the database limit.
- Why not delete and re-insert all rows: it works, but it loses row identity and `created_at`. Once the showcase gains a description and highlights, every reorder would have to copy them.
- Cost: a deferrable unique constraint cannot be the arbiter of `INSERT ... ON CONFLICT`, and foreign keys cannot reference it. Neither is needed here. Featuring uses the profile lock and `max(position) + 1`.

`project_id` UNIQUE stays an ordinary, immediate constraint.

### Deletion

- `DELETE /projects/{id}` is a hard delete, allowed in every state, and returns 204.
- The cascade removes the showcase row and the `project_technologies` rows. Every table added later with a `project_id` must use `ON DELETE CASCADE` or say otherwise in its own decision.
- The remaining featured projects are renumbered in the same transaction.
- Deleting screenshots from object storage belongs to Phase 4. What happens to analytics events of a deleted project belongs to Phase 7.

### Cabinet API

All endpoints require a session (401 `UNAUTHORIZED`). Mutations require the `Origin` header (403 `CSRF_ORIGIN_INVALID`, ADR-013). The full contract is in `docs/api/API_CONTRACT.md` and `docs/api/openapi.yaml`.

| Endpoint | Success |
|---|---|
| `GET /projects` | 200 `ProjectListResponse` (`items`, newest first by `created_at`, at most 50, no pagination) |
| `POST /projects` | 201 `ProjectResponse` |
| `GET /projects/{id}` | 200 `ProjectResponse` |
| `PATCH /projects/{id}` | 200 `ProjectResponse` (partial update, `null` clears a field) |
| `DELETE /projects/{id}` | 204 |
| `POST /projects/{id}/publish` | 200 `ProjectResponse` |
| `POST /projects/{id}/archive` | 200 `ProjectResponse` |
| `POST /projects/{id}/visibility` | 200 `ProjectResponse` |
| `POST /projects/{id}/showcase` | 200 `FeaturedProjectsResponse` (feature) |
| `DELETE /projects/{id}/showcase` | 200 `FeaturedProjectsResponse` (unfeature; not featured → 200 without changes) |
| `POST /profile/featured-projects/reorder` | 200 `FeaturedProjectsResponse` |

- `PATCH /projects/{id}/showcase` is removed from the contract until the showcase has its own fields.
- `status` and `visibility` change only through the actions; a body that contains them gives 422 `extra_forbidden`, as for unknown fields.
- `ProjectResponse` and the list items carry `featured_position` (1..3 or `null`), so the cabinet needs no separate featured endpoint.
- `FeaturedProjectsResponse` is `{"items": [{"project_id", "position"}]}` in order.
- The reorder body is `{"project_ids": [...]}`: the complete featured set in the new order. A malformed list (not UUIDs, duplicates, more than three) gives 422 `VALIDATION_ERROR`. A list that differs from the current set gives 409 `FEATURED_ORDER_MISMATCH`; the client reloads.

Error codes:

| HTTP | Code | When |
|---|---|---|
| 404 | `NOT_FOUND` | Missing, foreign or malformed project id |
| 422 | `VALIDATION_ERROR` | Lengths, control characters, more than 20 technologies, duplicate technologies, unknown fields, malformed reorder list |
| 422 | `PROJECT_INCOMPLETE` | Publish without the required fields, or a `PATCH` that empties them on a `PUBLISHED` project; `details.missing_fields` |
| 409 | `PROJECT_LIMIT_REACHED` | Creating a 51st project; `details.limit` |
| 409 | `PROJECT_TRANSITION_INVALID` | Archive from `DRAFT`, visibility change outside `PUBLISHED`; `details.status` |
| 409 | `PROJECT_NOT_FEATURABLE` | Featuring a project that is not `PUBLISHED` + `PUBLIC`; `details.status`, `details.visibility` |
| 409 | `FEATURED_LIMIT_REACHED` | Featuring a fourth project; `details.limit` |
| 409 | `FEATURED_ORDER_MISMATCH` | Reorder list is not the current featured set |

- Incompleteness uses 422, like `PROFILE_INCOMPLETE`: the client can fix the data and retry.
- Limits and state conflicts use 409: the request is valid, but the current state of the resource does not allow it.

### Public API

`GET /public/profiles/{slug}` (ADR-013) gains two arrays:

- `featured`: featured public projects in `position` order, each with `position`;
- `other`: the remaining public projects, newest first by `created_at`.

Each project carries only this whitelist: `id`, `title`, `summary`, `role`, `technologies` (names in the developer's order), plus `position` in `featured`. Nothing else is returned: no `status`, `visibility`, `description`, `contribution`, owner or timestamps. Both arrays are empty when the profile has no public projects.

A separate public project page, at the frontend address `/u/{slug}/projects/{id}`, and its endpoint belong to Phase 4. Nothing in Phase 3 links to it.

### CORS

`DELETE` joins the allowed methods: `GET`, `POST`, `PATCH`, `DELETE`, `OPTIONS` (ADR-013). The code change in `backend/app/main.py` is part of the Phase 3 implementation. Until then the code allows only the four old methods, and a browser `DELETE` fails at preflight.

## Consequences

### Positive

- Every state invariant the database can see is enforced twice, in the domain and in the database:
  - the state pairs;
  - the text completeness of published projects;
  - the limit of three featured projects;
  - the limit of 20 technologies.
- The featured limit holds without relying on application locks.
- The public DTO stays a whitelist. One public condition ("published + public + profile published") decides visibility everywhere.
- Hard delete with cascades leaves no orphan rows in Phase 3.

### Negative

- "At least one technology" and "only `PUBLISHED` + `PUBLIC` can be featured" cross tables, so only the domain enforces them, not a CHECK. Every code path that changes state must keep them; tests have to cover each transition.
- The database does not check that `project_showcases.profile_id` is the profile of the project's owner. The domain sets it from the owner.
- The spelling of a shared technology belongs to whoever created it first. "javascript" typed first is what everyone sees.
- A developer who unpublishes a project by mistake must hide it, not return it to draft; there is no draft-again action yet.
- A deferrable unique constraint is less common and must be declared explicitly in the migration (Alembic does not infer it).

## Alternatives considered

- **Visibility as a field of `PATCH /projects/{id}`**: mixes content edits with a state change that has its own rules and errors. A separate action keeps `PATCH` free of state.
- **Featured flag and position on `projects`**: no separate table, but the "three per profile" limit would need a partial unique index per position or a lock. It also contradicts ARCHITECTURAL_DIALOGUE §19, which keeps presentation data apart from the project.
- **Featured limit by counting under a lock only**: works, but the limit then depends on every code path taking the lock. The `position` range with UNIQUE makes the database the guarantee.
- **Technologies as a text array on `projects`**: simpler, but no shared spelling, no case-insensitive identity, and no basis for confirmed skills later.
- **Per-user technology names**: avoids the shared-spelling problem but loses one identity per technology across profiles.
- **Soft delete**: keeps data for analytics and undo, but every query must filter it, and nothing in Phase 3 needs it.

## Open questions

- **Back to draft**: whether a published project can return to `DRAFT`, and what happens to its featured position.
- **Skills**: deferred, unresolved direction: technologies of published projects shown as confirmed by projects, without self-assessment. No skills table, endpoint or UI in Phase 3.
- **Technology spelling and curation**: whether names need a curated list, aliases ("JS" / "JavaScript"), merging, or cleanup of unused rows.
- **Showcase presentation**: showcase description and highlights (ARCHITECTURAL_DIALOGUE §19), and whether `PATCH /projects/{id}/showcase` returns for them.
- **Fields of later phases**: goals, architecture, highlights, demo, screenshots, repository link; which of them become required to publish.
- **Public project page** (Phase 4): the endpoint, its whitelist, and the frontend address `/u/{slug}/projects/{id}`.
- **Imported projects** (Phase 5): which fields a GitHub import fills and how imported values stay distinguishable from developer-provided ones.
- **Deletion side effects**: object storage cleanup (Phase 4) and analytics events of deleted projects (Phase 7).
- **Markdown** in long project fields, together with the same question for `bio` (ADR-013).
- **Limits**: 50 projects and 20 technologies are starting values; revisit with real usage. Rate limiting of project mutations is part of the general rate-limiting question (ADR-013).
