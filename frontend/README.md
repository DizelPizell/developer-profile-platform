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

## Manual repositories check

The backend rebuilt with the GitHub code (`docker compose up -d --build` in the repository root), here `npm run dev`, signed in through GitHub, on `http://localhost:3000` (not `127.0.0.1`). Keep DevTools → Network open. The account needs public repositories on github.com; a fork and an archived one make the labels visible. The backend keeps a list page for 5 minutes and counts GitHub requests per user per hour in memory: `docker compose restart backend` clears both.

1. «Мои проекты» → «Импорт из GitHub» (left of «Новый проект») → `/me/repositories`. One request each to `/profile`, `/projects` and `/integrations/github/repositories?page=1`. «Загрузка…» until the list arrives, then the top panel with «Источник: GitHub».
2. The cards match your public repositories on github.com, most recently pushed first: the name opens the repository in a new tab, «Форк» and «В архиве на GitHub» where they apply, «Обновлён: <date>», the description cut after two lines or «У этого репозитория нет описания на GitHub». No stars, counters, languages or scores anywhere.
3. Paging: «Назад» is disabled on page 1. With 100 repositories or fewer «Вперёд» is disabled too; real paging needs an account with more than 100 public repositories and is otherwise covered by tests only. By hand: open `/me/repositories?page=2` → «Страница 2», «На этой странице репозиториев нет.», «Назад» goes to `?page=1`. Open `?page=abc`, `?page=0`, `?page=101` → page 1 (the request is `?page=1`), no crash.
4. Import: «Импортировать как проект» on an unlinked repository → the button reads «Импортируем…» and every button on the page is disabled; then the form of the new project opens with «Проект создан» and «Из репозитория <owner/name> создан черновик «<name>»…». The address has no `?imported=1` left. Reload → the panel is gone. Edit a field and save → the panel closes. The project is «Черновик» in «Мои проекты».
5. Back on `/me/repositories` (reload: the list page is cached for 5 minutes, but `linked_project_id` is read fresh) → the imported repository shows «Привязан · Проект: <title>» with no buttons, the link opens the project.
6. Import twice: open the list in two tabs, import a repository in the first, then import the same one in the second → «Репозиторий уже привязан», «…к вашему проекту «<title>»», «Открыть проект» opens it; the card in that tab becomes «Привязан».
7. Link: «Привязать к проекту…» → a dialog «Привязать к проекту» with the repository name, focus on the first project, every project with its state badge; under a project that already has a repository: «Уже привязан к <owner/name>. Новая привязка заменит старую.» «Привязать» is disabled until a project is chosen. Escape and «Отмена» close it with no request.
8. Choose a project without a repository → «Привязать» → the dialog closes, «Репозиторий привязан» appears above the list and takes the focus, the card shows «Привязан · Проект: <title>». In Network: `POST /projects/<id>/repository` with `{"full_name": …}` and one more `GET /projects`; the repository list is not requested again. The project's status, visibility and texts in its form are unchanged.
9. Replace a link: link another repository to the same project (the dialog shows «Уже привязан к …» under it) → the new card shows «Привязан», the previously linked card loses the badge and gets its buttons back.
10. Double-click «Импортировать как проект» or «Привязать» quickly → one request in Network.
11. Empty list: on an account with no public repositories (a test account) → the dashed panel «На вашем аккаунте GitHub нет публичных репозиториев…» and «Создать проект вручную» → `/me/projects/new`.
12. Changed login: in the dev database set a login that does not exist on GitHub, for example `docker exec -it developer-platform-postgres psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "UPDATE users SET github_login = 'no-such-login-dpp' WHERE github_login = '<your-login>'"`, then `docker compose restart backend` (clears the cached page) → «Логин на GitHub изменился» with «Войти через GitHub»; signing in again restores the login and the list.
13. Your request limit: set `GITHUB_USER_REQUESTS_PER_HOUR=7` (the minimum) in the root `.env`, `docker compose up -d backend`, then import or link until «Слишком много обращений к GitHub» appears → the import and link buttons are disabled, «Повторить через N мин» is disabled; the minutes count down. The full wait is up to an hour; to see the end, keep the page open or trust the fake-timer tests. Put the value back and restart.
14. GitHub unavailable: disconnect the computer from the internet (the browser still reaches `localhost`) and import or link → «GitHub сейчас недоступен» with «Повторить»; reconnect and press it → the same request is sent again.
15. Narrow screen (DevTools device mode, 375 px): cards, buttons and the dialog fit without horizontal scroll.
16. «Выйти» → `/login`; `/me/repositories` then redirects to `/login`.

`GITHUB_RELATION_NOT_FOUND` cannot come from this page (the list holds only your own repositories, so a link or import from it is always as the owner); it is checked by hand when linking by name in the project form ("Manual project repository check").

Not checked by hand, only by tests: 503 `GITHUB_RATE_LIMITED` (the platform-wide GitHub limit cannot be reached on purpose), 409 `PROJECT_LIMIT_REACHED` from the API (at 50 projects the page disables import before a request; reaching the API error needs 50 projects and a second tab), 404 `NOT_FOUND` on import (a repository deleted on GitHub within the 5 minutes its page is cached), 500 `INTERNAL_ERROR` with «Код запроса», and the countdown reaching its end.

## Manual project repository check

The same setup as above (backend rebuilt, `npm run dev`, signed in, `http://localhost:3000`, DevTools → Network open), with at least one saved project and your own public repositories on github.com.

1. «Новый проект» → `/me/projects/new`: the «Репозиторий GitHub» block shows only «Репозиторий можно привязать после первого сохранения.» The line under the form is «Демо и скриншоты добавим в следующих версиях.»
2. Open a project without a repository: «Источник: GitHub», «Необязательно», the text about facts from GitHub, the input with «владелец/репозиторий», «Привязать» disabled while it is empty, and «выберите из своего списка» → `/me/repositories`.
3. Type `not a name` and press «Привязать», then Enter → «Формат: владелец/репозиторий.» each time; no request in Network, and Enter does not save the form.
4. Change «Название» without saving. Type ` <your-login>/<your-repo> ` (spaces around) and «Привязать» → the button reads «Проверяем на GitHub…» and the form's buttons are disabled; then the panel: the name opens the repository in a new tab, «Обновлён: <date>», the description, «Владелец репозитория», «Форк …» or «В архиве на GitHub» where they apply, and the placeholder «Языки и другие данные появятся после первой синхронизации…». The request body is `{"full_name": "<your-login>/<your-repo>"}` without the spaces. The changed title is still in the field, «Сохранить» is active, no `PATCH` was sent.
5. A repository of another account where you are in the contributors list (if you have one) → «В списке контрибьюторов (по данным GitHub)». Without one this label is checked by tests only.
6. Relation not found: «Заменить репозиторий» → `octocat/Hello-World` → «Связь с репозиторием не найдена», the block keeps the input; «Отмена» → the linked panel is still the old repository (a reload confirms it).
7. Repository not found: «Заменить репозиторий» → `<your-login>/does-not-exist-123` → «Репозиторий не найден» with the spelling hint.
8. Replace: «Заменить репозиторий» → another of your repositories → the panel shows it; on `/me/repositories` the old one has its buttons back and the new one is «Привязан».
9. Already linked: in a second project link a repository the first project uses → «Репозиторий уже привязан», «…к вашему проекту «<title>»» and «Открыть проект», which opens the first project. Network shows one `GET /projects` after the error.
10. Unlink: «Отвязать» → the dialog «Отвязать репозиторий?» with the repository name, the focus on «Отмена»; Escape and «Отмена» send nothing. «Отвязать» in the dialog → `DELETE /projects/<id>/repository`, the block shows the input with the focus in it, unsaved edits stay.
11. «Мои проекты»: a linked project's card shows «GitHub» and the repository name (opens GitHub) under the technologies, in every state: publish, hide and archive one linked project to see it each time; a card without a repository has no such line. Unlink in the form and go back → the line is gone.
12. Double-click «Привязать» quickly → one request in Network.
13. The project's 404: open a draft in two tabs, delete it from «Мои проекты» in one, link in the other → «Проект не найден» with «Мои проекты».
14. Your request limit: `GITHUB_USER_REQUESTS_PER_HOUR=7` in the root `.env`, `docker compose up -d backend`; a link costs up to 7 requests, so the second link gives «Слишком много обращений к GitHub», «Привязать» disabled and «Повторить через N мин» counting down. Put the value back and restart.
15. GitHub unavailable: disconnect the computer from the internet and link → «GitHub сейчас недоступен». Reconnect, change the text in the input, press «Повторить» → the request carries the first name.
16. «Выйти» → the login screen note reads «Мы читаем только публичные данные GitHub: логин, аватар, email, если он открыт, и публичные репозитории, которые вы привяжете к проектам. Доступа к приватным репозиториям нет.»
17. Narrow screen (375 px): the block, the input and its buttons fit without horizontal scroll.

Not checked by hand, only by tests: the `unavailable` and `relation: "NONE"` warnings (only a sync sets them, Phase 6), 503 `GITHUB_RATE_LIMITED`, 422 `VALIDATION_ERROR` from the API (the client check sends no invalid name), 500 `INTERNAL_ERROR` with «Код запроса», an unlink error, and the countdown reaching its end.

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
