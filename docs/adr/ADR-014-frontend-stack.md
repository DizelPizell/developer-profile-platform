# ADR-014: Frontend Stack and Rendering Model

## Status

Accepted for the decisions below. The items under "Open questions" are not decided.

## Context

Legacy ADR `002-nextjs.md` chose Next.js + TypeScript for public profiles, the dashboard and the technical workspace, but fixed nothing else: router, styling, components, tests, how the browser reaches the API, or which pages render where.

The backend now has GitHub login, the current user, profile editing and publication, and the public profile endpoint (ADR-012, ADR-013). The API protects state-changing requests with an `Origin` check and allows CORS only from the frontend origin, with credentials (ADR-013). The frontend is the next step (DEVELOPMENT_PLAN Phase 2, `docs/frontend/FRONTEND_PLAN.md`).

## Decision

### Stack

- **Next.js with the App Router** and **TypeScript**.
- **Tailwind CSS** for styling.
- **shadcn/ui** as the base for components (dialogs, inputs, buttons). Its default look is not used: colors, fonts, borders and shadows are overridden with the design tokens from `docs/frontend/DESIGN.md`.
- **Vitest** with **React Testing Library** for unit and component tests. Playwright stays in the project stack (CLAUDE.md); when it is introduced is an open question.

### How the browser reaches the API

- In local development the browser calls the API directly at `http://localhost:8000` with `fetch(..., { credentials: "include" })`. The frontend runs at `http://localhost:3000`, which is `FRONTEND_URL`, so CORS and the `Origin` check from ADR-013 accept its requests.
- Two variables hold the API address:
  - `NEXT_PUBLIC_API_URL` — used by code running in the browser (already in `.env.example`);
  - `API_INTERNAL_URL` — used by server-side Next.js code; inside Docker it points to the backend service name instead of `localhost`.
  While the frontend runs outside Docker, both are `http://localhost:8000`.
- The frontend never sets `Origin` itself; the browser does. It sends JSON with `Content-Type: application/json`, the only request header CORS allows.
- This is a decision for local development. `docs/architecture/ARCHITECTURE.md` shows production traffic as Browser → Nginx → Next.js → FastAPI behind one origin; which production topology V1 uses is an open question below.

### Rendering

- **Public profile `/u/[slug]`** renders on the server (SSR). The server calls `GET /api/v1/public/profiles/{slug}` without a session cookie. A 404 from the API renders the 404 page with HTTP status 404. Any other failure renders an error page, not a 404. The response is not cached by Next.js in V1, so unpublishing hides the page immediately.
- **Cabinet** (the developer's own profile) runs on the client. It calls `GET /api/v1/auth/me`; on 401 it redirects to the sign-in screen. Any later 401 (an expired session) does the same.
- Sign-in is a full-page navigation to `GET /api/v1/auth/github/login`, not a `fetch`. A failed login comes back as a redirect to `/login?error=<CODE>` from a closed list (ADR-012).

Routes and screens are described in `docs/frontend/DESIGN.md`.

- Both addresses are checked when the server starts and during `next build` (which inlines `NEXT_PUBLIC_API_URL`); a missing or non-http(s) value stops the process.

### Running locally

For now the frontend runs with `npm run dev` on the host, not in Docker Compose.

### Versions (fixed in F1)

- **Node.js 24 LTS** (`frontend/.nvmrc`, `engines: ">=24 <25"`). Node 20 is end-of-life, and the current Vitest, jsdom, ESLint and Vite releases no longer support it.
- **npm**, with `package-lock.json` committed; exact library versions are in the lock file.
- Next.js 16.4, React 19.3, TypeScript 5 (the version Next.js supports; TypeScript 7 is not used yet), Tailwind CSS 4, ESLint 9 with `eslint-config-next`, Vitest 5 with React Testing Library and jsdom.
- Next.js `cacheComponents` and `partialPrefetching` are off: they change the caching model, which is still open (see "Caching of public pages").

### Frontend CI

A separate workflow, `.github/workflows/frontend.yml`, runs on changes to `frontend/**` and to the workflow itself, with `permissions: contents: read`. It uses the Node version from `.nvmrc` with the npm cache and runs `npm ci`, lint, typecheck, test and build. It is separate from the backend workflow so each runs only when its own code changes.

## Consequences

### Positive

- Public pages render on the server: they show content without client JavaScript, have correct status codes and can be indexed.
- The cabinet never renders user data on the server, so it does not depend on the server seeing the session cookie (see the first open question).
- ADR-013's protections work unchanged: the browser always sends the real `Origin`, and credentials go only to the allowed origin.

### Negative

- Two API address variables must be kept consistent.
- shadcn/ui components need their styles overridden; the default theme cannot be used as is.
- A direct cross-origin call in development may differ from the production topology until that is decided.

## Alternatives considered

- **Next.js Pages Router**: older routing model; App Router is the current default and supports server rendering per route.
- **Proxying the API through Next.js (one origin)**: no CORS, but Next.js becomes part of every API call and the `Origin`/CORS setup of ADR-013 is no longer exercised in development. Not chosen for local development; part of the open production-topology question.
- **Rendering the cabinet on the server**: needs the server to see the session cookie, which is not settled.
- **A component library with its own fixed look (MUI, Ant Design)**: harder to bend to the pixel style in `DESIGN.md` than shadcn/ui, whose components are copied into the project.

## Open questions

- **Session cookie on the server**: how server-side Next.js code sees the session cookie when the frontend and the API run on different ports (and, later, different hosts). Needed only if a server-rendered page must know the user.
- **Production topology**: one origin behind Nginx as in `ARCHITECTURE.md`, or a separate API host; this decides whether CORS stays and how `FRONTEND_URL` is set.
- **Playwright**: when end-to-end tests are introduced (sign-in in F2 or the SSR 404 in F4).
- **Caching of public pages**: whether to cache or statically regenerate `/u/[slug]`, and how unpublishing invalidates it.
- **Sync status and file content for the IDE view**: how the frontend learns the GitHub sync status and loads file contents for the read-only code viewer. Depends on ADR-009, ADR-010 and ADR-011, where these are still open.
- **Risk: one API call per request on `/u/[slug]` relies on undocumented Next.js behavior.** After an error, Next.js renders the error page in a second pass with an empty React `cache()`, so `generateMetadata` would call the API again. The page keys the call by the request's `headers()` object, which stays the same across both passes in Next.js 16.4. This is not documented. If it changes, the page still works but makes two API calls on errors (and waits up to two timeouts). Check it when upgrading Next.js: the 500 case should still show one API call.
- **ESLint 9**: npm marks ESLint 9 as no longer supported. Upgrade when `eslint-config-next` supports the next major version.
- **TypeScript 5**: the project is pinned to TypeScript 5.x (`^5`). Moving to TypeScript 7 is a separate decision.
