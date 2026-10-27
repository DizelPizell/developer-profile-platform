# Frontend Design Guide

Visual rules and screen descriptions for the V1 frontend. Stack and rendering: ADR-014-frontend-stack.md. API: `docs/api/API_CONTRACT.md`. Plan: `FRONTEND_PLAN.md`.

## Style

- A game-style character profile in pixel style.
- Purple is required: the accent and the background are purple.
- The avatar is round. It is the only round element; everything else has square corners.

## Tokens

Colors are defined once as tokens (CSS variables, mapped into the Tailwind theme) and are not written as raw values in components. shadcn/ui components use these tokens instead of their default theme.

| Token | Value | Use |
|---|---|---|
| `--color-bg` | `#150d2e` | Page background |
| `--color-grid` | `#1b1140` | Grid lines on the page background |
| `--color-panel` | `#231650` | Panels and cards |
| `--color-frame` | `#3b2a80` | Inner frame of panels |
| `--color-outline` | `#0b0620` | Outer outline and hard shadows |
| `--color-accent` | `#7c3aed` | Primary buttons, active states, highlights |
| `--color-label` | `#ffd23f` | Labels, badges, focus ring |
| `--color-text` | `#f3edff` | Main text |
| `--color-text-muted` | `#b8a9e8` | Secondary text, input borders |
| `--color-error` | `#ff5d8f` | Errors |
| `--color-success` | `#22c55e` | Success states |

Allowed accent alternatives: `#a855f7`, `#6366f1`, `#d946ef`. Only one accent is used across the product at a time.

### Contrast

WCAG contrast ratios for the palette (AA: 4.5 for normal text, 3 for large text and UI boundaries):

| Foreground | on `bg` | on `grid` | on `panel` |
|---|---|---|---|
| `text` `#f3edff` | 16.3 | 15.3 | 14.1 |
| `text-muted` `#b8a9e8` | 8.8 | 8.2 | 7.6 |
| `label` `#ffd23f` | 12.9 | 12.1 | 11.2 |
| `error` `#ff5d8f` | 6.4 | 6.0 | 5.5 |
| `success` `#22c55e` | 8.2 | 7.7 | 7.1 |
| `accent` `#7c3aed` | 3.3 | 3.1 | 2.8 |
| `frame` `#3b2a80` | 1.6 | 1.5 | 1.4 |

Text on accent fills:

| Accent | `text` on it | `outline` on it |
|---|---|---|
| `#7c3aed` | 5.0 | 3.5 |
| `#a855f7` | 3.5 | 5.0 |
| `#6366f1` | 3.9 | 4.4 |
| `#d946ef` | 3.0 | 5.7 |

Rules that follow:

- `accent` is never used for text on dark backgrounds; it is a fill and border color.
- Light text on the default accent `#7c3aed` is fine. With `#a855f7`, `#6366f1` or `#d946ef`, light text on the accent is allowed only for large text; otherwise use dark text (`outline`).
- `frame` is decoration only; it is never the only visible boundary of an interactive element. Inputs use a `text-muted` border.

## Typography

- **Press Start 2P**: only short headings and labels (section titles, the «Класс» label, form labels, status badges). Not for sentences, form values or long names.
- **Pixelify Sans**: body text, form fields, buttons, names.
- **Decision**: buttons with an important action (sign-in) are written in normal case, in Pixelify Sans, at a large size. Uppercase in Press Start 2P reads poorly.
- Both fonts must include the Cyrillic subset; check this when the fonts are added (F1).

## Borders, shadows and states

- Outline: 4px solid `outline`. Panels add a 4px inner frame in `frame`.
- No border radius, except the round avatar.
- Hard shadows without blur, e.g. `4px 4px 0 var(--color-outline)`.
- Hover is stepped: the element moves up-left by a few pixels and the shadow grows; pressed moves it down-right and the shadow shrinks. Transitions use steps, not smooth easing. With `prefers-reduced-motion` only the color changes.
- Focus is always visible: `:focus-visible` draws a 4px `label` ring with an offset. Focus is never removed without a replacement.
- Text contrast follows the table above.

## Content rules

- Placeholder text is written in square brackets: `[Пока без описания]`. Mockups use brackets for sample data; the implementation shows real values or hides the block.
- No invented scores, ratings, levels, experience points or progress bars, even though the style is game-like (CLAUDE.md, ADR-007). «Класс» shows the developer's own `headline` and nothing else.
- Blocks with GitHub data always carry a source mark «Источник: GitHub». This applies to `avatar_url` and `github_login`, which come from GitHub. On the public page, a block of developer-written text carries «От автора» (mockup `public-profile.png`), so the two sources stay distinguishable (CLAUDE.md); form fields in the cabinet have no mark.
- `bio` is plain text: line breaks are preserved, markdown is not interpreted, and it is never rendered as HTML (ADR-013).

## Routes

| Route | Screen | Rendering |
|---|---|---|
| `/` | Redirects to `/me` | Client |
| `/login` | Sign-in | Client |
| `/me` | Cabinet | Client |
| `/me/projects` | «Мои проекты» (F5) | Client |
| `/me/projects/new` | New project (F5) | Client |
| `/me/projects/[id]` | Edit project (F5) | Client |
| `/u/[slug]` | Public profile | Server (SSR) |
| anything else | 404 | — |

## Screens

### Public profile — `/u/[slug]`

Data: `GET /api/v1/public/profiles/{slug}` → `slug`, `display_name`, `headline`, `bio`, `location`, `avatar_url`, `github_login`, and since Phase 3 `featured` and `other` (projects with `id`, `title`, `summary`, `role`, `technologies`, plus `position` in `featured`; ADR-015).

Blocks:

| Block | Data | Notes |
|---|---|---|
| Header | — | «DEV.PROFILE» and «Войти через GitHub», a link to `/login` (the mockup's top bar). |
| Hero | `avatar_url`, `display_name`, `headline`, `location`, `github_login` | Round avatar, loaded only when `avatar_url` starts with `https://`; otherwise (including `null`) the default pixel avatar. `display_name` in Pixelify Sans (a long name, Typography rule), `@github_login` under it. `headline` follows the badge «Класс». «Локация: …»; empty `location` is hidden. Avatar and login each carry «Источник: GitHub». The «GitHub» button links to `https://github.com/{github_login}` in a new tab with `rel="noopener noreferrer"`. «Проекты» (secondary) links to the project area and is shown only when there is a public project (see "Projects on the public page"). |
| «О себе» | `bio` | Marked «От автора». Plain text with line breaks (`white-space: pre-line`). Empty `bio` hides the block. |
| «Скилы» | — | Pending: no backend source yet, phase not assigned. A plain list in future; never levels or bars. |
| «Главные проекты» | `featured` | Up to 3 cards in `position` order, marked «От автора». See "Projects on the public page". |
| «Данные GitHub» | — | Pending backend Phases 5–6 (GitHub import and sync). Always marked «Источник: GitHub». |
| «Другие проекты» | `other` | One row per project, in API order, marked «От автора». See "Projects on the public page". |

`display_name` and `headline` are never empty here: a profile can be published only with both (ADR-013). If one is missing anyway, the name falls back to `@github_login` and the «Класс» line is hidden.

Pending blocks are drawn in mockups with a bracketed placeholder. The F4 implementation does not render them on the public page until their data exists. The mockup's footer is an annotation and is not built.

Every value is rendered as text; fields outside the public whitelist are dropped when the response is read.

Address:

- The slug must match `^[a-z0-9][a-z0-9-]{1,37}[a-z0-9]$` (3–39 characters, the database CHECK) after lowercasing; otherwise the 404 screen is shown without calling the API.
- A slug with uppercase letters redirects (308) to its lowercase address, because the API ignores case. Each profile has one address; there is no canonical tag in V1.

Metadata: title «{display_name} — {headline}», description `headline`. No Open Graph image. The 404 and error screens keep the neutral title «Developer Profile Platform» (Next.js takes 404 metadata only from the root `not-found`). Next.js adds `noindex` to both.

States:

| API response | Result |
|---|---|
| 200 | Profile page |
| 404, or malformed slug | Profile 404 screen, HTTP status 404 |
| Any other error: API unreachable, timeout (5 s), 5xx, unexpected body | Error screen «Не удалось загрузить профиль» with «Повторить», no internal details, HTTP status 500. It is drawn by the browser (`error.tsx` is a client component), so without JavaScript the page is empty |

The page makes one API call per request. After an error Next.js renders the error page in a second pass, so the call is shared through the request's `headers()` object rather than React `cache()`.

#### Projects on the public page (F6)

The layout comes from `public-profile.png`; only what the Phase 3 API provides is built. The mockup image still labels the cards «Избранное N»; the label is «Главный N», like «главные» in the cabinet.

- The project area holds «Главные проекты» and then «Другие проекты», after «О себе». It has `id="projects"`.
- Each section heading has the square marker (`label` for featured, `text-muted` for other), the title, a rule and «От автора» on the right: every project field is written by the developer (content rules).
- **«Главные проекты»** — a card per featured project, in `position` order (sorted when the response is read). One column on narrow screens, two from `sm`, three from `lg`:
  - the label «Главный N» (N = `position`), Press Start 2P on `label`;
  - `title` in Pixelify Sans, wrapped at any point when a word is too long;
  - `summary`, at most four lines (`line-clamp`), then cut;
  - up to three technology chips, in the developer's order; the rest are not shown;
  - «Моя роль: {role}» at the bottom of the card.
  - The mockup's striped image area and «Открыть проект ›» wait for Phase 4 (screenshots and the public project page) and are not rendered. No element links to a project.
- **«Другие проекты»** — a row per project, in API order (newest first):
  - `title`, wrapped like on cards;
  - `summary` on one line, cut with an ellipsis;
  - a badge with the first technology (the developer's order, ADR-015). It sits on the right from `sm` (at most 40% of the row) and under the text on narrow screens, so a long name does not squeeze the title. A project without technologies cannot be public, but the row still renders without a badge.
- An empty `featured` or `other` hides its section, heading included. With no public projects at all, the project area is not rendered.
- The hero «Проекты» button (secondary) is an in-page link to `#projects`. It is rendered only when there is at least one public project.
- Every value is rendered as text. `featured` and `other` are required in the response; a missing array or a project of the wrong shape is an unexpected body (error screen). Project fields outside the whitelist (`id`, `title`, `summary`, `role`, `technologies`, `position`) are dropped.

### Cabinet — `/me`

Data: `GET /api/v1/profile` → `slug`, `status`, `display_name`, `headline`, `bio`, `location`, `avatar_url`, `github_login`. The cabinet does not call `/auth/me`: the profile response carries everything it shows, and its 401 means there is no session.

The mockup `cabinet.png` sets the layout and texts. Where it differs from the rules above, the decisions are:

- the cabinet labels `headline` «Заголовок»; the public page keeps «Класс»;
- buttons stay in Pixelify Sans, normal case (Typography decision), with the mockup's colors: «Сохранить» accent, «Опубликовать» `label` fill with `outline` text, «Скрыть» panel;
- the header keeps «Источник: GitHub» under the login, although the mockup omits it;
- the mockup's «Состояния статуса» legend is an annotation and is not built; its sentence sits under the public address.

Blocks:

| Block | Data | Notes |
|---|---|---|
| Header | `avatar_url`, `github_login` | «DEV.PROFILE» on the left. On the right: round avatar (`null` → default pixel avatar), `@github_login` with «Источник: GitHub», «Выйти» (secondary). While loading or after a load error only «Выйти» is shown. |
| «Мой профиль» | `slug`, `status` | «Публичный адрес: /u/{slug} (не меняется)» and «Опубликованный профиль видят все по этой ссылке.» The address is a link to the public page only while `PUBLISHED`. On the right «Статус» and a badge: `PRIVATE` → «Черновик · PRIVATE» (`label`), `PUBLISHED` → «В сети · PUBLISHED» (`success`). |
| Form | `display_name`, `headline`, `bio`, `location` | Fields in mockup order, labels in Press Start 2P uppercase, required ones marked «*» (required for publication, not for saving). Each has a hint and a counter «N / limit». Buttons «Сохранить», «Опубликовать», «Скрыть» and the saved message. |

Fields:

| Field | Label | Placeholder | Hint | Limit |
|---|---|---|---|---|
| `display_name` | «Имя *» | «Как вас называть» | «Обязательно для публикации» | 100 |
| `location` | «Локация» | «Город, страна» | «Необязательно» | 100 |
| `headline` | «Заголовок *» | «Например: Fullstack-разработчик, Python и TypeScript» | «Одна строка под именем. Обязательно для публикации» | 160 |
| `bio` | «О себе» (multi-line) | «Чем занимаетесь, что умеете, какие задачи решаете лучше всего» | «Простой текст, без разметки» | 2000 |

Input placeholders are hints for typing, so they have no square brackets; the bracket rule is for placeholders shown in place of missing content.

Behavior:

- «Сохранить» is active only when a field differs from the stored value. It sends `PATCH /profile` with only the changed fields; an emptied field is sent as `null`. The form then shows the values from the response, which are normalized by the server (trimmed, blank → `null`), and «Сохранено» appears in `success` until the next edit.
- «Опубликовать» is active only in `PRIVATE` without unsaved changes, because publish checks the stored values. With unsaved changes it shows «Сохраните изменения, чтобы опубликовать профиль.»
- «Скрыть» is active only in `PUBLISHED`; in `PRIVATE` it shows the hint `«Скрыть» доступно, когда профиль опубликован.` Unpublish does not use the form, so unsaved edits do not block it and stay in the form.
- While a request runs, all three buttons are disabled and the fields are read-only. A second click or Enter during a request sends nothing.
- The status is updated from the `OwnProfileResponse` that every call returns.
- Client-side limits (`maxLength`) mirror the API, but the API is the source of truth.
- Errors stay until the next save, publish or unpublish.

States and errors:

| Case | Shown as |
|---|---|
| Loading | «Загрузка…» in a panel |
| 401 from any call | Redirect to `/login` (the session is missing or expired) |
| Load fails | The network or generic text below, and «Повторить» |
| 422 `VALIDATION_ERROR` | Error under each field from `details.fields` (`loc` `["body", "<field>"]`): `string_too_long` → «Не больше N символов.», `control_characters` → «Недопустимые символы.», any other type → «Некорректное значение.». Entries for other locations are ignored; without any field entry the generic text is shown |
| 422 `PROFILE_INCOMPLETE` from publish | Alert «Нельзя опубликовать» with «Заполните обязательные поля: «Имя» и «Заголовок».» (or «Заполните обязательное поле: «Имя».»), listing `details.missing_fields`; those fields are highlighted |
| 422 `PROFILE_INCOMPLETE` from save | A save that clears `display_name` or `headline` of a published profile. Alert «Нельзя сохранить» with the same list and «Очистить их можно только у скрытого профиля.»; the fields are highlighted |
| 403 `CSRF_ORIGIN_INVALID` | Cannot be read by the browser: the response has no `Access-Control-Allow-Origin` (ADR-013), so `fetch` fails like a network error. Shown as the network error below. In practice it means `FRONTEND_URL` does not match the frontend's origin (for example `127.0.0.1` instead of `localhost`) |
| Network error or API unreachable | «Не удалось связаться с сервером.»; entered data is kept and the action can be repeated |
| 500 `INTERNAL_ERROR`, other errors | «Что-то пошло не так. Попробуйте ещё раз.» and «Код запроса: <request_id>» from the error body (or `X-Request-ID`) when present |
| Saved | «Сохранено» in `success` |

### Projects in the cabinet — `/me/projects` (F5)

Mockups `my-projects.png` (list) and `project-form.png` (form) set the layout and texts. The general rules above (tokens, typography, focus, content rules) apply. Where the mockups differ from them, the cabinet decisions hold: buttons in Pixelify Sans, normal case; the header keeps «Источник: GitHub».

Data: `GET /api/v1/projects` for the list, `GET /api/v1/projects/{id}` for editing, and the actions in `docs/api/API_CONTRACT.md` (ADR-015). The header (avatar, login, «Выйти») comes from `GET /profile`, as on `/me`.

The cabinet has two tabs under the header, «Профиль» (`/me`) and «Проекты» (`/me/projects`); the current one is in `accent` with `aria-current="page"`. The form screens have no tabs, only the link «‹ Назад к проектам».

The mockups call featured projects «главные»: «Главные проекты», «Сделать главным», «Убрать из главных», the badge «Главный: N» and the counter «Главных: N из 3». The mockup image still shows «В избранном» in the counter; the text here wins.

#### «Мои проекты» — list

Top panel: «Мои проекты», «Проектов: N из 50 · Главных: N из 3» and «Новый проект» (`label`), a link to `/me/projects/new`. At 50 projects the button is disabled with «Можно создать не больше 50 проектов.»; the API stays the source of truth (`PROJECT_LIMIT_REACHED`).

«Главные проекты» (yellow square marker):

- The text «Покажутся на публичной странице первыми, в этом порядке. Не больше 3. Опубликованный и видимый проект можно сделать главным. Если проект скрыть, отправить в архив или удалить, он пропадёт отсюда.»
- One row per featured project in `position` order: the position in a `label` square, `title` (or «[Без названия]»), `summary` on one line, ▲ and ▼, «Убрать из главных». ▲ on the first row and ▼ on the last are disabled. The arrows are buttons with the names «Выше: {title}» and «Ниже: {title}», so the order can be changed from the keyboard. There is no drag-and-drop.
- While fewer than 3 are featured, a dashed row «Свободное место для главного проекта: K из 3».

«Все проекты» (muted square marker), newest first (API order). Each card shows `title` (or «[Без названия]»), the state badge, «Главный: N» when featured, `summary` and the technologies when present, and the actions for its state:

| `status` + `visibility` | Badge (fill) | Actions |
|---|---|---|
| `DRAFT` + `PRIVATE` | «Черновик» (`frame`) | «Редактировать», «Опубликовать», «Удалить» |
| `PUBLISHED` + `PUBLIC` | «Опубликован» (`success`) | «Редактировать», «Сделать главным» (when not featured), «Скрыть», «В архив» |
| `PUBLISHED` + `PRIVATE` | «Скрыт» (`text-muted`) | «Редактировать», «Показать», «В архив»; the note «Опубликован, но не виден посетителям. Из главных убран.» (hiding removes a project from featured, ADR-015) |
| `ARCHIVED` + `PRIVATE` | «В архиве» (`bg`, muted text) | «Редактировать», «Опубликовать снова», «Удалить» |

- «Редактировать» opens `/me/projects/{id}`. «Опубликовать» and «Сделать главным» are `label`, «Удалить» is red text on a panel, the rest are secondary.
- «Сделать главным» is shown only on a `PUBLISHED` + `PUBLIC` project that is not featured. With 3 featured it is disabled with «В главных уже 3 проекта. Уберите один, чтобы добавить другой.» Hidden, draft and archived cards do not show it.
- A featured card has the note `«Скрыть» и «В архив» уберут проект из главных.`.
- «Удалить» is offered only for `DRAFT` and `ARCHIVED` (mockup decision): a published project is archived or hidden first. The API itself allows deleting in any state.
- A draft has no hint about missing fields until its publish fails: then the card shows «Чтобы опубликовать, не хватает: роль, технологии, вклад.» from `details.missing_fields` of `PROJECT_INCOMPLETE`. The list response does not carry the fields needed to compute it in advance.
- An empty list shows «[Пока нет проектов]».

Delete asks in an accessible modal dialog (`AlertDialog`, focus starts on «Отмена», Escape closes it): title «Удалить проект?», text «Проект «{title}» удалится навсегда вместе со своими данными. Отменить нельзя.» It says nothing about featured projects or the archive: only drafts and archived projects can be deleted here, and they are never featured, buttons «Удалить навсегда» (`error` fill) and «Отмена». Nothing is sent before confirmation; on 204 the project leaves the list (and the featured rows).

Behavior:

- After a feature, unfeature or reorder, featured positions come from `FeaturedProjectsResponse`, not computed locally.
- A reorder swaps two neighbours and sends the complete featured set in the new order.
- Hide, archive or delete of a featured project reloads the list, since the API removes it from the featured set.
- While a request runs, all actions on the screen are disabled; a second click sends nothing.

#### New and edit project — `/me/projects/new`, `/me/projects/[id]`

Top panel: «Новый проект» or «Проект», the state badge (once saved) and «Публичная страница проекта появится позже». Fields in mockup order; «*» means required for publication, not for saving. `role` and `technologies` sit side by side, as do `problem` and `results`; on narrow screens they stack.

| Field | Label | Placeholder | Hint | Limit | Lines |
|---|---|---|---|---|---|
| `title` | «Название *» | «Как называется проект» | «Обязательно для публикации» | 100 | one |
| `summary` | «Коротко о проекте *» | «Одна-две строки: что это и зачем» | «Показывается в карточке проекта. Обязательно для публикации» | 300 | one |
| `role` | «Роль *» | «Например: бэкенд-разработчик» | «Обязательно для публикации» | 100 | one |
| `technologies` | «Технологии *» | «Например: Python» | «До 20. Первая показывается в списке проектов на публичной странице» | 20 × 50 | chips |
| `contribution` | «Ваш вклад *» | «Что именно сделали вы лично» | «Обязательно для публикации» | 2000 | many |
| `description` | «Подробное описание» | «Расскажите о проекте подробнее» | «Необязательно» | 5000 | many |
| `problem` | «Какую задачу решали» | «Какая была проблема» | «Необязательно» | 2000 | many |
| `results` | «Результат» | «К чему пришли» | «Необязательно» | 2000 | many |

- Every field has a counter «N / limit». Text is plain: no markup, line breaks kept in multi-line fields.
- Technologies are chips. A name is added with Enter or «Добавить» and removed with × («Удалить «{name}»»). The name is trimmed and inner whitespace collapsed, as the API does. A blank name is ignored. A name equal to an existing one ignoring case is not added: `«{name}» уже есть в списке.`. At 20 the input is read-only with «Не больше 20 технологий.». Technologies keep the entered order.
- Under the form: «Демо, скриншоты и репозиторий GitHub добавим в следующих версиях.»

Actions (buttons under the form):

| Action | Available when | Label |
|---|---|---|
| Save | A field differs from the stored value | «Сохранить» (accent) |
| Publish | Saved, `DRAFT` or `ARCHIVED`, no unsaved changes | «Опубликовать» (`label`) |
| Archive | `PUBLISHED` | «В архив» (secondary) |

- On `/me/projects/new` «Сохранить» sends `POST /projects` and moves to `/me/projects/{id}` of the created project; the button stays disabled until the page changes.
- On an existing project «Сохранить» sends `PATCH /projects/{id}` with only the changed fields: an emptied text field as `null`, `technologies` as the whole list in the entered order. The form then shows the normalized values from the response, and «Сохранено» appears in `success` until the next edit.
- With unsaved changes publish shows «Сохраните изменения, чтобы опубликовать проект.» Outside `PUBLISHED`, «В архив» is disabled with `«В архив» доступно у опубликованного проекта`; for a featured project it shows `«В архив» уберёт проект из главных.`. Archive does not use the form, so unsaved edits stay.
- Hide, show, feature and delete live on the list, as in the mockup.
- While a request runs, all buttons are disabled and the fields are read-only. A second click or Enter during a request sends nothing.
- The error block sits above the form and is scrolled into view when it appears, because the buttons are at the bottom of a long form.

States and errors (list and form):

| Case | Shown as |
|---|---|
| Loading, load failure, 401, network error, 500 | As in the profile cabinet table above: «Загрузка…»; the error text and «Повторить»; redirect to `/login`; «Не удалось связаться с сервером.»; «Что-то пошло не так. Попробуйте ещё раз.» with «Код запроса: …» |
| 404 `NOT_FOUND` on the form | A panel «Проект не найден», «Такого проекта нет среди ваших.» and a link «Мои проекты» |
| 404 `NOT_FOUND` from a list action | «Проект не найден. Данные загружены заново.»; the list is reloaded |
| 422 `VALIDATION_ERROR` | Under each field from `details.fields`: «Не больше N символов.», «Недопустимые символы.», «Некорректное значение.». Technology entries: «Не больше 50 символов в названии технологии.», «Некорректное название технологии.», «Технологии не должны повторяться, даже с другим регистром букв.», «Не больше 20 технологий.» |
| 422 `PROJECT_INCOMPLETE` from publish (form) | Alert «Нельзя опубликовать» with «Заполните обязательные поля: «Роль», «Технологии», «Ваш вклад».» (or «Заполните обязательное поле: …»). The fields are highlighted with «Заполните это поле», technologies with «Нужна хотя бы одна» |
| 422 `PROJECT_INCOMPLETE` from save | A save that clears a required field of a published project. «Нельзя сохранить», the same list and «Опубликованный проект должен оставаться заполненным.» |
| 422 `PROJECT_INCOMPLETE` from publish (list) | «Чтобы опубликовать, не хватает: …» on that card |
| 409 `PROJECT_LIMIT_REACHED` | «Можно создать не больше 50 проектов.» |
| 409 `PROJECT_TRANSITION_INVALID` | «Это действие недоступно в текущем состоянии проекта. Данные загружены заново.»; the data is reloaded (the form keeps its edits) |
| 409 `PROJECT_NOT_FEATURABLE` | «Главным можно сделать только опубликованный и видимый проект. Данные загружены заново.»; the list is reloaded |
| 409 `FEATURED_LIMIT_REACHED` | «В главных уже 3 проекта. Уберите один, чтобы добавить другой.»; the list is reloaded |
| 409 `FEATURED_ORDER_MISMATCH` | «Список главных изменился, порядок загружен заново.»; the list is reloaded |

### Sign-in — `/login`

Blocks (mockup `login.png`):

- the «DEV.PROFILE» mark above the panel;
- the default pixel avatar;
- the title «Новая игра» (Press Start 2P, shown in uppercase);
- «Профиль разработчика с проектами и данными из GitHub. Войдите, чтобы создать свой.»;
- the error block, when there is one;
- the button «Войти через GitHub» (Pixelify Sans, normal case, large);
- the note «Мы получаем только публичные данные GitHub: логин, аватар и email, если он открыт. Доступа к вашим репозиториям нет.» The mockup omits the email; the backend stores a public email (ADR-012), so the text names it.

The mockup's link «Посмотреть пример профиля» is left out until a public page (F4) and an example profile exist.

Behavior:

- On open the screen calls `GET /api/v1/auth/me`; 200 redirects to `/me`.
- The button is a full-page navigation to `{NEXT_PUBLIC_API_URL}/api/v1/auth/github/login`.
- After a successful login the API redirects to `FRONTEND_URL` (`/`), which leads to `/me`.
- After a failed login the API redirects to `/login?error=<CODE>` (ADR-012). The screen shows the text for the code above the button; the button stays active.

States and errors:

| Case | Shown as |
|---|---|
| Checking the session | Button disabled |
| No session (401) | Button active |
| API unreachable while checking | Button active and «Не удалось связаться с сервером.» |
| Any other API error while checking | Button active, no message |

Texts for `?error=<CODE>`:

| Code | Text |
|---|---|
| `ACCESS_DENIED` | «Вход отменён на стороне GitHub. Попробуйте ещё раз.» |
| `INVALID_STATE` | «Сеанс входа устарел или был прерван. Начните вход заново.» |
| `MISSING_CODE` | «GitHub не вернул код входа. Начните вход заново.» |
| `OAUTH_CODE_INVALID` | «Код входа истёк или уже использован. Начните вход заново.» |
| `GITHUB_UNAVAILABLE` | «GitHub сейчас недоступен. Попробуйте позже.» |
| `INTERNAL_ERROR` | «Что-то пошло не так на нашей стороне. Попробуйте позже.» |

| Any other value, including an empty one | «Не удалось войти. Попробуйте ещё раз.» |

No `error` parameter: no error block. The texts come from this table only; the value of `error` is never shown.

Logout (from the cabinet): `POST /api/v1/auth/logout` → 204 → redirect to `/login`. A failure keeps the user on the page and shows the network or generic error text from the cabinet table.

### 404

Two screens with the layout of `not-found.png`: «DEV.PROFILE» above a panel with a large «404», a title (Press Start 2P), one line of text and buttons (Pixelify Sans, normal case, as all buttons). HTTP status 404.

| Case | Title | Text | Buttons |
|---|---|---|---|
| `/u/{slug}`: API 404 or malformed slug | «Профиль не найден» | «Такого профиля нет или он не опубликован. Проверьте ссылку.» | «На главную» (`/`), «Создать свой» (`/login`) |
| Any other unknown route | «Страница не найдена» | «Проверьте ссылку.» | «На главную» (`/`) |

The profile text names both cases together, so it never says which one applies: the API deliberately returns the same 404 for private, missing and malformed slugs (ADR-013).

## Mockups

Mockups are added manually to `docs/frontend/mockups/`:

- `public-profile.png`
- `cabinet.png`
- `login.png`
- `not-found.png`
- `my-projects.png` (F5)
- `project-form.png` (F5)

The project blocks of the public page follow `public-profile.png`, except the card label: the image shows «Избранное N», the guide says «Главный N».

If a mockup and this guide disagree, raise the conflict instead of silently picking one.
