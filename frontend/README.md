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

## Manual projects cabinet check

Signed in as above, with a published profile, on `http://localhost:3000/me/projects`. Keep DevTools → Network open.

1. The tabs show «Проекты» as current; «Профиль» goes to `/me` and back. With no projects: «Проектов: 0 из 50 · Главных: 0 из 3», «[Пока нет проектов]», the free slot «3 из 3».
2. «Новый проект» → `/me/projects/new`, «Сохранить» is disabled, «Опубликовать» and «В архив» are disabled with their hints.
3. Fill «Название» only and save → the address becomes `/me/projects/<id>`, the badge «Черновик». The `POST` body has only `title`.
4. Add technologies: `Python` with Enter, `  Fast   API ` with «Добавить» (stored as `Fast API`), then `python` → `«python» уже есть в списке.` Remove one with ×. Save → the `PATCH` body has only `technologies`, in the entered order.
5. «Опубликовать» → «Нельзя опубликовать» naming the missing fields, they are highlighted, the error block scrolls into view, the badge stays «Черновик».
6. Change a field without saving → «Опубликовать» is disabled with «Сохраните изменения, чтобы опубликовать проект.»
7. Fill all required fields, save, publish → «Опубликован», «В архив» becomes active.
8. Clear «Роль» and save → «Нельзя сохранить», reload → the role is still stored.
9. Back to the list. Create a second draft with a title only and press «Опубликовать» on its card → «Чтобы опубликовать, не хватает: …» on that card.
10. Publish two more complete projects. «Сделать главным» on three of them → rows 1–3 in «Главные проекты», no free slot; on the fourth published card «Сделать главным» is disabled with «В главных уже 3 проекта…».
11. ▲ on the first row and ▼ on the last are disabled. ▼ on row 1 → the order changes; the `POST /profile/featured-projects/reorder` body has all three ids. Reload → the order is kept. Tab to the arrows and press Enter → they work from the keyboard.
12. In a second tab remove one project from the featured list, then reorder in the first tab → «Список главных изменился, порядок загружен заново.» and the list is reloaded.
13. «Скрыть» on a featured project → «Скрыт», it leaves «Главные проекты», «Показать» brings it back as «Опубликован» but not featured. «В архив» on a featured project → «В архиве», it leaves the featured list.
14. «Удалить» is shown only on drafts and archived projects. Press it → the dialog with the title in the text, focus on «Отмена»; Escape and «Отмена» send nothing. «Удалить навсегда» → `DELETE`, the card disappears, the counter drops.
15. Limits: «Название» stops at 100 characters, «Коротко о проекте» at 300, «Роль» at 100, «Ваш вклад», «Какую задачу решали» and «Результат» at 2000, «Подробное описание» at 5000; a technology at 50 characters; after 20 technologies the input is read-only with «Не больше 20 технологий.».
16. `/me/projects/00000000-0000-0000-0000-000000000000` → «Проект не найден» with a link to «Мои проекты».
17. Double-click «Сохранить», «Опубликовать» or an arrow quickly → one request in Network.
18. Stop the backend and press «Сохранить» → «Не удалось связаться с сервером.», the entered text stays; reload the list → the error with «Повторить».
19. «Выйти» → `/login`; `/me/projects` then redirects to `/login`.

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

## Manual public projects check

Backend running, signed in, a published profile with slug `<slug>`. Open the public page in a private window (no session) and reload it after each change in the cabinet.

1. With no published projects → no «Главные проекты», no «Другие проекты», no «Проекты» button in the hero.
2. In the cabinet create and publish two complete projects (title, summary, role, contribution, technologies) → both appear under «Другие проекты», newest first, each with its first technology; «Главные проекты» is still absent; the hero «Проекты» button jumps to the projects.
3. Make one featured → it moves to «Главные проекты» with «Главный 1», title, summary, up to three technologies and «Моя роль: …»; «Другие проекты» keeps the other one. Both headings carry «От автора».
4. Make the second one featured, then ▼ on row 1 in the cabinet → on the public page «Главный 1» and «Главный 2» swap.
5. A third project left as a draft is not shown. «Скрыть» on a published one → it disappears from the public page (and from «Главные проекты»); «Показать» brings it back under «Другие проекты». «В архив» → it disappears.
6. A project with `<script>alert(1)</script>` in the title and `<b>x</b>` in the summary → shown as text, no alert. A 100-character title wraps inside its card; a 300-character summary is cut after four lines on a card and after one line in a row.
7. Without JavaScript (`curl -s http://localhost:3000/u/<slug>`) the project titles are in the HTML. In the backend log the page makes one request to `/api/v1/public/profiles/<slug>` per load.
8. At 375 px wide (DevTools device mode) there is no horizontal scroll; cards are in one column, the row badge sits under the text.
9. «Скрыть» on the profile in the cabinet → the public page gives «Профиль не найден» (404), the projects keep their states in the cabinet; publish the profile again → the projects are back.

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
