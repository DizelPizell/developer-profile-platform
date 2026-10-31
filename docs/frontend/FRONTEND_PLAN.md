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

## F5 — Projects in the cabinet [done; manual check with the backend pending]

**Goal**: the developer creates, edits, publishes, hides, archives and deletes projects and chooses up to three featured projects in their order.

**Before starting**: mockups `my-projects.png` and `project-form.png`; backend step 3.2 implemented.

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

Done in F5: the cabinet tabs «Профиль» and «Проекты»; the project API calls with error parsing (`missing_fields`, per-field errors including technology items); the list per `my-projects.png` with featured rows, ▲▼ reorder, the free slot, state badges, per-state actions and the delete dialog; the form per `project-form.png` with technology chips, counters, create-then-redirect, `PATCH` of changed fields only, publish and archive. Decisions taken with the developer: «Удалить» only for drafts and archived projects; the draft hint comes from a failed publish; «Сделать главным» only on published and visible projects. Checked with Vitest and RTL (API mocked) and visually against the mockups at 1280 and 375 px with a mock API; the check against the real backend is in `frontend/README.md`.

## F6 — Projects on the public page [done; manual check with the backend pending]

**Goal**: visitors see the developer's featured and other public projects on `/u/[slug]`.

**Before starting**: backend step 3.3 implemented; the open points under "Projects on the public page" in `DESIGN.md` decided (source mark, technologies on cards, long values).

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

Done in F6: `getPublicProfile` reads `featured` and `other` (both required, whitelisted, featured sorted by `position`); «Главные проекты» cards with «Главный N», a four-line summary, up to three technology chips and «Моя роль»; «Другие проекты» rows with a one-line summary and the first technology; «От автора» on both headings; the hero «Проекты» link to `#projects`; empty sections and the whole area hidden when empty. The decisions on the open points are in `DESIGN.md`. Also in this stage: the cabinet texts «Из главных убран», «Главных: N из 3» and the shorter delete confirmation. Checked with Vitest and RTL (fetch mocked), the server HTML without JavaScript, and the layout at 1280 and 375 px against a mock API; the check against the real backend is in `frontend/README.md`.

## F-GH1 — GitHub in the cabinet

**Goal**: the developer sees their public repositories, imports one as a draft project, links a repository to a project by name or from the list, and unlinks it. All error states of the GitHub endpoints are understandable and say what to do.

**Before starting**: backend steps 5.3–5.5 merged (done). F-GH1.5 waits for backend step 6.2; its full manual check waits for the worker (6.3–6.6).

Screens, texts and the code → message table: "GitHub in the cabinet" in `DESIGN.md`. Each substep is its own PR in this order. Facts every substep relies on:

- The backend keeps a page of the repository list for 5 minutes. A repository created on GitHub appears only after that.
- Link and unlink act at once and do not depend on «Сохранить».
- Import creates a `DRAFT` + `PRIVATE` project and leads to its form.
- No sync job is queued yet (Phase 6). Every linked repository is `NOT_SYNCED` with `synced_at = null` and `languages = []`.
- The public «Данные GitHub» data on project cards is F-GH2, not F-GH1.

### F-GH1.1 — API client and types (S)

**What**:
- Types for `GitHubRepositoryListResponse`, `ProjectGitHub` and `GitHubSync`, and `github` in the project type.
- The calls `listRepositories(page)`, `importRepository(githubRepoId)`, `linkRepository(projectId, fullName)` and `unlinkRepository(projectId)`.
- The `owner/name` check that mirrors the contract's pattern.
- Error helpers:
  - `retry_after_seconds` from `details`;
  - `project_id` from `GITHUB_REPOSITORY_ALREADY_LINKED`;
  - `limit` from `PROJECT_LIMIT_REACHED`.
- The response is read with the existing whitelist approach: unknown fields are dropped, and a wrong shape is an unexpected body.
- `github_repo_id` is a number in JSON. GitHub's ids fit `Number.MAX_SAFE_INTEGER` today (about 10⁹). The client builds the import path from it without arithmetic.

**Tests** (Vitest):
- Each call:
  - its method and path; `page` in the query;
  - `credentials: "include"`;
  - the JSON body `{"full_name"}` for a link;
  - unlink reads its 200 `ProjectResponse` with `github: null`.
- The parsing:
  - a `github: null` and a full `ProjectGitHub`;
  - an unknown field dropped;
  - an unexpected `relation` or `sync.status` value as an unexpected body.
- The error helpers: present, missing and invalid `retry_after_seconds` (negative, string); the `owner/name` check on the contract's edge cases (39-character owner, `.`, `..`, a leading hyphen).

**Manual check**: none (no screen).

**Risks**:
- The ids are numbers. If GitHub ids ever pass 2⁵³, they would lose precision; this is far off, but noted in the type.
- An unexpected `relation` value is treated as an unexpected body. That is strict, but safer than showing a guess.

### F-GH1.2 — The repository page with import and the link dialog (M)

**What**:
- `/me/repositories` per `DESIGN.md`:
  - the top panel, cards, the «Привязан» badge with the project title;
  - pagination with the page in the address;
  - the empty state;
  - «‹ Назад к проектам».
- «Импорт из GitHub» on «Мои проекты».
- Import: the 50-project check from `GET /projects`, then a move to the form with the «Проект создан» panel.
- The «Привязать к проекту…» dialog with the radio list, then the local update of the cards.
- The `ALREADY_LINKED`, `RELATION_NOT_FOUND`, import 404 and `PROJECT_LIMIT_REACHED` messages. The waiting states are F-GH1.4; until then they use the generic error text.

**Tests** (Vitest + RTL, API mocked):
- Cards:
  - linked and unlinked cards have the right buttons;
  - fork and archived labels;
  - the empty description text; `pushed_at = null` hides the date;
  - `full_name` is a link only for `https://github.com/` URLs;
  - markup in the description is shown as text.
- Pagination: «Назад» is disabled on page 1, «Вперёд» when `next_page` is `null`, and the page number is taken from the address.
- Import:
  - the request goes to the right id; the route moves to the form with the panel;
  - at 50 projects the button is disabled and no request is sent;
  - a second click during the request sends nothing.
- Link dialog:
  - «Привязать» is disabled until a project is chosen;
  - the body is `{"full_name"}`;
  - on 200 the badge moves, and another card linked to the same project loses it;
  - errors stay inside the dialog;
  - Escape and «Отмена» send nothing.
- The import 404 text does not ask the user to check the spelling.

**Manual check** (real GitHub, local backend; needs the developer's own GitHub account with at least one public repository, ideally a fork, an archived repository and more than 100 repositories for paging, or a test account set up that way):
1. Sign in and open «Мои проекты» → «Импорт из GitHub». The list matches the public repositories on github.com, most recently pushed first, with fork and archive labels.
2. Import a repository. The browser moves to the form with «Проект создан»; the project is a draft titled after the repository; the list now shows the repository as «Привязан».
3. Import the same repository again from a second tab with the old list. The message is «Репозиторий уже привязан», and «Открыть проект» leads to it.
4. Link a repository to an existing project through the dialog. The badge moves; the project's status and texts are unchanged.
5. Create a new public repository on GitHub. It is not in the list at once, and appears within 5 minutes after a reload.
6. With 50 projects (a test database), the import buttons are disabled.
7. Narrow screen (375 px): cards and the dialog fit without horizontal scroll.

**Risks**:
- The page needs three requests (profile, projects, repositories), and the list call may wait on GitHub for seconds. The cards show «Загрузка…» until the list arrives. The projects call does not block the header.
- The 5-minute cache confuses users who just created a repository. The page text says so; there is no way to bypass it in V1.
- Each uncached list page costs one request of the user's 60 per hour. Paging back and forth is served from the backend cache.

### F-GH1.3 — The repository block in the project form and the login note (M)

**What**:
- The «Репозиторий GitHub» block per `DESIGN.md`:
  - not linked: the `owner/name` input with the client check;
  - linked: the panel with the relation, fork and archived labels and the languages placeholder;
  - «Заменить репозиторий»;
  - «Отвязать» with its confirmation;
  - the `unavailable` and `relation: "NONE"` warnings;
  - the hint on `/me/projects/new`.
- The form takes only `github` from link and unlink responses, so unsaved edits are kept.
- The line under the form becomes «Демо и скриншоты добавим в следующих версиях.»
- The login screen note switches to the `DESIGN.md` text that names the public repositories (planned since F2).

**Tests** (Vitest + RTL):
- The relation texts:
  - exactly «Владелец репозитория» and «В списке контрибьюторов (по данным GitHub)»;
  - no label for `NONE`;
  - the word «подтверждено» never appears in the rendered block.
- «Форк {parent}» and «Форк» when `parent_full_name` is `null`.
- The placeholder is shown while `synced_at` is `null`.
- Link from the form:
  - the client check sends nothing for an invalid name;
  - a valid name is trimmed and sent;
  - an unsaved title edit survives a successful link and an unlink.
- Unlink sends nothing without confirmation, and on 200 the block returns to the input.
- The `GITHUB_REPOSITORY_NOT_FOUND`, `RELATION_NOT_FOUND`, `ALREADY_LINKED` and project 404 messages render in the block.
- The login note test is updated to the new text.

**Manual check** (real GitHub, local backend):
1. Link your own repository by name. The block shows «Владелец репозитория», the description and the date; languages show the placeholder.
2. Link a public repository of another account where you are a contributor. The block shows «В списке контрибьюторов (по данным GitHub)».
3. Link a famous repository you are not related to (for example `torvalds/linux`). The message is «Связь с репозиторием не найдена», and nothing changes.
4. Type a missing name (`your-login/does-not-exist-123`). The message is «Репозиторий не найден», with the spelling hint.
5. Type `not a name`. The format hint appears without a request (check the network panel).
6. Edit the title without saving, then link and unlink. The edit is still in the field.
7. «Заменить репозиторий» with another repository. The block shows the new one; the repository page shows the old one as unlinked.
8. Link a repository that another project already uses. The message is «Репозиторий уже привязан» with a link to that project.
9. The login screen shows the new note.

The `unavailable` and `NONE` warnings cannot be produced before Phase 6. They are checked in tests only and manually in F-GH1.5.

**Risks**:
- Mixing an immediate action (link) into a form with a separate «Сохранить» can surprise users. The note under the block and the confirmation text are the mitigation, and taking only `github` from the response keeps edits safe.
- A link waits on GitHub for up to several seconds (up to 7 requests). The button text shows the wait, and every button is disabled meanwhile.

### F-GH1.4 — Waiting and failure states (S–M)

**What**:
- 409 `GITHUB_LOGIN_OUTDATED` on the list: the message and «Войти через GitHub».
- 429 `GITHUB_USER_LIMIT_REACHED` and 503 `GITHUB_RATE_LIMITED`: the countdown from `details.retry_after_seconds`, and the failed action disabled while it runs.
- 502 `GITHUB_UNAVAILABLE`: «Повторить», which repeats the same request once per click.
- One shared message component for the list page, the dialog and the form block, so the texts of the `DESIGN.md` table live in one place.

**Tests** (Vitest + RTL, fake timers):
- The countdown:
  - 125 seconds shows «3 мин», and 30 seconds shows «1 мин»;
  - the button stays disabled until the time passes, then reads «Повторить»;
  - a missing or invalid value gives «Попробуйте позже.» with an active button.
- The failed action is disabled during the countdown: paging on the list, import and link elsewhere.
- 502 «Повторить» repeats the same request, list or action. There is no automatic retry, so no request goes out without a click.
- 409 `GITHUB_LOGIN_OUTDATED` shows the button with the login URL.
- 500 shows «Код запроса».
- A countdown is cleared when the component unmounts (no timer left running).

**Manual check** (local backend):
1. Exhaust your budget: start the local backend with `GITHUB_USER_REQUESTS_PER_HOUR=7` (the minimum) and import or link until 429 appears. Check the countdown, then that the action works after it ends. The budget lives in the backend's memory, so a backend restart resets it.
2. 502 and 503 are hard to produce against the real GitHub; the client always calls `https://api.github.com`. 502 can be produced by cutting the backend's network while the page is open. 503 is checked in tests only. The check notes which way was used.
3. `GITHUB_LOGIN_OUTDATED`: rename the GitHub account of a test user after signing in (or change the stored login in the test database). The list shows the message; signing in again fixes it.

**Risks**:
- The countdown is a client timer: after a laptop sleeps it can be wrong. The API stays the source of truth, and a too-early retry just shows the message again.
- Renaming a real GitHub account breaks links to it elsewhere, so the login-outdated check uses a test account or the test database.

### F-GH1.5 — Sync status and «Обновить» (S–M; after backend 6.2)

**What**:
- `sync.status` in the form block.
- «Обновить» with `POST /integrations/github/repositories/{id}/sync` and the 10-minute pause from `next_manual_sync_at` and `GITHUB_SYNC_TOO_SOON`.
- Polling `GET /projects/{id}` while `QUEUED` or `SYNCING` (ADR-018).
- The languages list once `synced_at` is set.

Its texts and the polling interval are added to `DESIGN.md` when step 6.2 is merged. Not detailed further until then.

### Open questions

- **The repository of a project in `GET /projects`.** `ProjectSummary` carries no repository. So the «GitHub» label on «Мои проекты» and the line «Уже привязан к {репозиторий}» in the link dialog (both in the mockups) cannot be built from the contract. Options for the owner:
  - (a) add a nullable `github: {"full_name": "string"}` to `ProjectSummary`. One join in the list query; the contract and OpenAPI change.
  - (b) leave the contract as it is and drop both elements from the mockups.
  - Loading each project with `GET /projects/{id}` is ruled out (up to 50 requests).
  - Until decided, F-GH1 builds neither element; the dialog shows the general note «новая привязка заменит старую».
- **Opening the repository page for a specific project.** The form's «выберите из своего списка» opens `/me/repositories` without preselecting the project in the link dialog. A preselect (`?project={id}`) would save a step; it is left out of F-GH1 unless the owner asks for it.

## F7+ — Demos, GitHub data, IDE view

**Goal**: add project pages and technical evidence as the backend provides them.

- The public project page `/u/{slug}/projects/{id}`, demos and screenshots — after backend Phase 4.
- GitHub: the cabinet (repository list, import, link, sync status) and the GitHub block on project cards — steps F-GH1 and F-GH2 in DEVELOPMENT_PLAN, after backend Phases 5–6 (ADR-016–ADR-019). F-GH1 is planned above. There is no profile-level «Данные GitHub» block in V1.
- Read-only IDE view — not in V1 Phases 5–6: the file tree and README are deferred (ADR-018), and file content is still an open question (ADR-011).

Each of these gets its own goal, done criteria and tests when its backend contract exists.
