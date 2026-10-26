# Frontend Plan

Stages of the V1 frontend. Stack and rendering: ADR-014-frontend-stack.md. Screens and visual rules: `DESIGN.md`. Every stage also satisfies `docs/development/DEFINITION_OF_DONE.md`.

## Order relative to the backend

- F1–F4 use only what the backend already has: GitHub login, `/auth/me`, logout, profile editing and publication, and the public profile (DEVELOPMENT_PLAN Phase 1 and the Phase 2 API).
- F5 and F6 are steps 3.4 and 3.5 of backend Phase 3 (DEVELOPMENT_PLAN). The Phase 3 contract is fixed (ADR-015, `docs/api/API_CONTRACT.md`). F5 starts when the cabinet API (step 3.2) is implemented, F6 when the public API (step 3.3) is.
- F7 and later start only when the matching backend phase has an API contract (Phases 4–6).

## F0 — Mockups [done]

**Goal**: agree on the visual direction before writing code.

**Done when**:
- `DESIGN.md` describes tokens, typography, states and the four screens.
- The mockups `public-profile.png`, `cabinet.png`, `login.png`, `not-found.png` are in `docs/frontend/mockups/` (added manually).

**Tests**: none.

## F1 — Next.js skeleton, tokens, API client, CI [done]

**Goal**: an empty but working application that later stages build on.

**Done when**:
- Next.js (App Router, TypeScript), Tailwind and shadcn/ui are set up; `npm run dev` starts the app on `http://localhost:3000`.
- The tokens from `DESIGN.md` are CSS variables mapped into the Tailwind theme; both fonts load with the Cyrillic subset.
- The API client:
  - takes its base URL from `NEXT_PUBLIC_API_URL` in the browser and `API_INTERNAL_URL` on the server;
  - sends `credentials: "include"` and JSON bodies with `Content-Type: application/json`;
  - turns the shared error format into a typed error with `code`, `message`, `details` and `request_id`;
  - reports a network failure (including an unreadable CORS response) as a separate error kind;
  - handles 204 without a body.
- Both API variables are documented in `frontend/.env.example` and checked at server start and during the build.
- Lint, typecheck, tests and build run in CI (`.github/workflows/frontend.yml`, ADR-014) and pass.

**Tests** (Vitest):
- API client: success JSON, error format parsing, 204, network failure, `credentials: "include"`.
- Address selection: `NEXT_PUBLIC_API_URL` in the browser, `API_INTERNAL_URL` on the server; missing and invalid values.
- Smoke test of the start page; the font configuration keeps the cyrillic subset.

Done in F1: Node 24 LTS, the shadcn/ui components Button, Input, Textarea and Label restyled with the tokens, and a stub start page.

## F2 — Sign-in via GitHub, current user, logout [done; manual check with GitHub pending]

**Goal**: a developer can sign in, the app knows who they are, and they can sign out.

**Done when**:
- `/login` matches `DESIGN.md`: it checks the session, and the button navigates to `/api/v1/auth/github/login`.
- `/login?error=<CODE>` shows the text for that code from `DESIGN.md`; the button stays active.
- `/` redirects to `/me`; `/me` calls `/auth/me` and shows `github_login` (the full cabinet is F3).
- A 401 redirects to `/login`.
- «Выйти» calls `POST /auth/logout` and redirects to `/login`; after that `/auth/me` returns 401.
- The full flow works against the local backend with `FRONTEND_URL=http://localhost:3000` (checked manually, noted in the PR).

**Tests**:
- `/login` with `/auth/me` returning 200 redirects to `/me`; with 401 it shows the button with the right address.
- `/login?error=<CODE>` renders the text for each of the six codes and never the raw value.
- `/me` with 401 redirects to `/login`.
- Logout sends `POST` with credentials and redirects on 204; a network error keeps the user on the page.

Done in F2: `/login` per `login.png` (without the example-profile link), the neutral text for an unknown `error` value, a temporary `/me` page (replaced by the F3 cabinet), `getMe` / `logout` / `githubLoginUrl` in the API client, and the restyled shadcn Alert. The full flow against GitHub is checked manually (`frontend/README.md`).

## F3 — Cabinet [done; manual check pending]

**Goal**: the developer edits their profile and controls its publication.

**Done when**:
- The cabinet matches `DESIGN.md`: header, status, a form with four fields (`display_name`, `headline`, `bio`, `location`), counters with the API limits.
- «Сохранить» sends only the changed fields; the form shows the normalized values from the response.
- Publish and unpublish work and update the status from the response; publish is disabled while the form has unsaved changes, unpublish is available only for a published profile.
- API errors are shown as in `DESIGN.md`: `VALIDATION_ERROR` per field, `PROFILE_INCOMPLETE` with the missing fields highlighted, network error (including the unreadable `CSRF_ORIGIN_INVALID`) with entered data kept, 5xx with `request_id`, 401 → `/login`.

**Tests**:
- `PATCH` body contains only the changed fields.
- Each error state from the `DESIGN.md` table renders as described.
- Publish is disabled while the form is dirty; the status changes from the response.

Done in F3: the cabinet per `cabinet.png` with the decisions recorded in `DESIGN.md` (labels, badges, three buttons, no status legend), `getProfile` / `updateProfile` / `publishProfile` / `unpublishProfile` in the API client, the `FormField` component, and a yellow `label` button variant. The temporary F2 session page is gone. Unpublish keeps unsaved edits; a second click during a request sends nothing. The manual check against the backend is in `frontend/README.md`.

## F4 — Public page `/u/[slug]` [done; manual check with the backend pending]

**Goal**: a published profile is visible to anyone at its address.

**Done when**:
- The page renders on the server from `GET /public/profiles/{slug}` via `API_INTERNAL_URL`, without a session cookie, and is not cached.
- An API 404 gives the 404 screen with HTTP status 404; other failures give the error screen, not a 404.
- Only the whitelisted public fields are used; GitHub data carries the source mark; empty optional fields are hidden; pending blocks are not rendered.
- `bio` is shown as plain text with line breaks.

**Tests**:
- Data loading: 200 → profile, 404 → not found, 500 or network failure → error.
- Hero renders with `avatar_url = null` and `location = null`.
- `bio` containing HTML-like text is shown as text.
- End-to-end checks with Playwright are an open question in ADR-014.

Done in F4: `getPublicProfile` (5 s timeout, `cache: "no-store"`, whitelist, 404 → `null`), the page per `public-profile.png` with only the API blocks and «От автора» on «О себе», a malformed slug as 404 without an API call, a 308 redirect for uppercase slugs, the profile 404 and a separate 404 for unknown routes, the error page with «Повторить» (HTTP 500), and `generateMetadata`. Status codes, one API call per request (also on errors), no cookie forwarding and the escaped HTML were checked against a built server and a mock API; the check against the real backend is in `frontend/README.md`.

## F5 — Projects in the cabinet

**Goal**: the developer creates, edits, publishes, hides, archives and deletes projects and chooses up to three featured projects in their order.

**Before starting**: a cabinet mockup for the project screens (`DESIGN.md` marks them «макет ожидается»); backend step 3.2 implemented.

**Done when**:
- The «Мои проекты» list, the create/edit screen and the featured controls match `DESIGN.md` and the mockup.
- The list shows every own project from `GET /projects` (newest first) with its state badge and featured position.
- Creating sends `POST /projects`; saving sends `PATCH /projects/{id}` with only the changed fields (an emptied field as `null`, `technologies` as the whole list in the entered order). The form then shows the normalized values from the response.
- Field limits mirror the API (`maxLength`, at most 20 technologies of up to 50 characters); the API stays the source of truth.
- Publish, archive, hide and show call their actions. Each control is available only in the states where the action is allowed (ADR-015). The state and featured position update from the response.
- Add to and remove from featured projects, and reorder them. After any change, positions come from `FeaturedProjectsResponse`. A reorder sends the complete featured set in the new order.
- Delete asks for confirmation first and removes the project from the list on 204.
- Errors are shown as in `DESIGN.md`:
  - `VALIDATION_ERROR` per field (including technologies);
  - `PROJECT_INCOMPLETE` with the missing fields highlighted;
  - `PROJECT_LIMIT_REACHED`, `PROJECT_TRANSITION_INVALID`, `PROJECT_NOT_FEATURABLE`, `FEATURED_LIMIT_REACHED`;
  - `FEATURED_ORDER_MISMATCH`, which reloads the list;
  - 404 as «Проект не найден»;
  - network and 5xx errors as in the profile form;
  - 401 → `/login`.
- The project text fields are plain text: shown as text, never as HTML.

**Tests**:
- `PATCH` body contains only the changed fields; `technologies` keeps the entered order.
- Each action button is enabled exactly in its allowed states (all four state pairs).
- Each error code renders as described; `FEATURED_ORDER_MISMATCH` reloads.
- Featured positions after add, remove and reorder come from the response; a reorder sends the full list.
- Delete sends nothing without confirmation.
- A second click during a request sends nothing.

## F6 — Projects on the public page

**Goal**: visitors see the developer's featured and other public projects on `/u/[slug]`.

**Before starting**: backend step 3.3 implemented; the open points under "Projects on the public page" in `DESIGN.md` decided.

**Done when**:
- «Главные проекты» renders `featured` in `position` order as cards per `public-profile.png`; «Другие проекты» renders `other` as rows.
- An empty array hides its block. With no public projects neither block nor the hero «Проекты» button is rendered.
- Only the whitelisted project fields are read (`id`, `title`, `summary`, `role`, `technologies`, `position`); anything else in the response is dropped.
- Elements that depend on Phase 4 are not rendered: the image area and «Открыть проект».
- The page still makes one API call per request (the profile response carries the projects).

**Tests**:
- Featured cards follow `position`, not the array order; the other rows keep the API order.
- Empty `featured` or `other` hides the block; an unexpected field is not rendered.
- Markup in `title`, `summary`, `role` and technology names is shown as text.
- A row shows the first technology; a project without one never reaches the page (the API publishes only projects with technologies), but the row still renders without a badge.
- The response without `featured`/`other` arrays is treated as an unexpected body (error screen), like any other invalid response.

## F7+ — Demos, GitHub data, IDE view

**Goal**: add project pages and technical evidence as the backend provides them.

- The public project page `/u/{slug}/projects/{id}`, demos and screenshots — after backend Phase 4.
- «Данные GitHub», import and sync status — after backend Phases 5–6.
- Read-only IDE view — after backend Phase 6; depends on the open questions about sync status and file content (ADR-014, ADR-009–011).

Each of these gets its own goal, done criteria and tests when its backend contract exists.
