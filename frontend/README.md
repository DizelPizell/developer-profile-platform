# Frontend

Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui. Stack and rendering: `docs/adr/ADR-014-frontend-stack.md`. Visual rules: `docs/frontend/DESIGN.md`. Stages: `docs/frontend/FRONTEND_PLAN.md`.

## Requirements

Node.js 24 LTS (`.nvmrc`) and npm.

## Install

```bash
cd frontend
npm ci
cp .env.example .env.local
```

## Variables

| Variable | Used by | Local value |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Code in the browser; inlined at build time | `http://localhost:8000` |
| `API_INTERNAL_URL` | Server-side code; the backend service name inside Docker | `http://localhost:8000` |

Both are the API base address without `/api/v1`. `npm run build` and `npm run typecheck` (both load `next.config.ts`) fail if either is missing, and the server exits at start if either is missing or not an http(s) URL. `npm run lint` and `npm test` do not need them. The backend must have `FRONTEND_URL=http://localhost:3000`, otherwise CORS and the Origin check reject the frontend's requests (ADR-013).

## Run

```bash
npm run dev        # http://localhost:3000
npm run build && npm run start
```

## Checks

```bash
npm run lint
npm run typecheck  # generates route types, then tsc
npm test           # Vitest + React Testing Library (jsdom)
```

## Layout

- `src/app/` — routes, root layout, fonts (`fonts.ts`), design tokens (`globals.css`).
- `src/components/ui/` — shadcn/ui components restyled for `DESIGN.md`. Add new ones with `npx shadcn@latest add <name>` and restyle them the same way.
- `src/lib/api/` — API client: `apiFetch`, `ApiError` (error response in the shared format), `NetworkError` (no readable response, including a 403 `CSRF_ORIGIN_INVALID` without CORS headers).
