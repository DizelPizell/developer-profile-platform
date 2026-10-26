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

## Manual sign-in check

Needs a GitHub OAuth app whose callback is `http://localhost:8000/api/v1/auth/github/callback`.

1. Backend `.env`: `APP_ENV=development`, `FRONTEND_URL=http://localhost:3000`, the OAuth app's `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`, `GITHUB_CALLBACK_URL` as above. Start PostgreSQL and the backend on port 8000.
2. Here: `.env.local` from `.env.example`, then `npm run dev`. Open `http://localhost:3000` in the same browser host (`localhost`, not `127.0.0.1`, or the Origin check rejects requests).
3. `/` → `/me` → `/login` (no session). The button links to `http://localhost:8000/api/v1/auth/github/login`.
4. Sign in on GitHub → back on `/me` with `@your-login`.
5. Open `/login` again → it redirects to `/me`.
6. «Выйти» → `/login`; opening `/me` again redirects to `/login`.
7. Start sign-in and press "Cancel" on GitHub → `/login?error=ACCESS_DENIED` with its text.
8. Open `/login?error=WHATEVER` → the neutral text, the value is not shown.

## Manual cabinet check

Signed in as above, on `http://localhost:3000/me`:

1. The header shows the avatar, `@your-login` with «Источник: GitHub» and «Выйти»; the status is «Черновик · PRIVATE»; the address `/u/<slug>` is plain text.
2. «Сохранить» is disabled. Type into «Имя» → it becomes active; restore the old value → disabled again.
3. Enter «Имя» with spaces around it and save → «Сохранено», the value is shown trimmed. In DevTools → Network the `PATCH` body has only that field.
4. Reload the page → the saved values are there.
5. With «Заголовок» empty press «Опубликовать» → «Нельзя опубликовать» naming «Заголовок», the field is highlighted, the status stays PRIVATE.
6. Change a field without saving → «Опубликовать» is disabled with the hint to save.
7. Fill «Заголовок», save, publish → «В сети · PUBLISHED», the address becomes a link to the public page, «Скрыть» is active.
8. Clear «Имя» and save → «Нельзя сохранить», nothing changes on the server (reload to check).
9. «Скрыть» → «Черновик · PRIVATE», the link is plain text again.
10. Limits: «Имя» and «Локация» stop at 100 characters, «Заголовок» at 160, «О себе» at 2000; the counters match.
11. Stop the backend and press «Сохранить» → «Не удалось связаться с сервером.», the entered text stays.
12. «Выйти» → `/login`.

## Manual public page check

Backend running, a published profile with slug `<slug>`. Use a private window (no session) for steps 1–8.

1. `http://localhost:3000/u/<slug>` → name, `@login`, «Класс» with the headline, location if set, «О себе» with «От автора» if set, avatar and login with «Источник: GitHub», «Войти через GitHub» at the top.
2. Without JavaScript (DevTools → Settings → Disable JavaScript, or `curl -s http://localhost:3000/u/<slug>`) the name and headline are in the HTML.
3. The tab title is «<name> — <headline>».
4. «GitHub» opens `https://github.com/<login>` in a new tab.
5. `/u/<SLUG>` in uppercase → redirected to the lowercase address.
6. In the cabinet put `<b>x</b>` and two lines into «О себе», save → the public page shows the tags as text and keeps the line break.
7. `/u/no-such-profile`, `/u/bad_slug` and `/u/a` → «Профиль не найден», status 404 (`curl -s -o /dev/null -w "%{http_code}" …`). `/whatever` → «Страница не найдена», 404.
8. «Скрыть» in the cabinet, reload the public page → the same «Профиль не найден» as for a missing slug.
9. Stop the backend, reload a profile → «Не удалось загрузить профиль», status 500; start it again, «Повторить» → the profile.

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
