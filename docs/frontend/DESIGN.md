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
| `/u/[slug]` | Public profile | Server (SSR) |
| anything else | 404 | — |

## Screens

### Public profile — `/u/[slug]`

Data: `GET /api/v1/public/profiles/{slug}` → `slug`, `display_name`, `headline`, `bio`, `location`, `avatar_url`, `github_login`.

Blocks:

| Block | Data | Notes |
|---|---|---|
| Header | — | «DEV.PROFILE» and «Войти через GitHub», a link to `/login` (the mockup's top bar). |
| Hero | `avatar_url`, `display_name`, `headline`, `location`, `github_login` | Round avatar, loaded only when `avatar_url` starts with `https://`; otherwise (including `null`) the default pixel avatar. `display_name` in Pixelify Sans (a long name, Typography rule), `@github_login` under it. `headline` follows the badge «Класс». «Локация: …»; empty `location` is hidden. Avatar and login each carry «Источник: GitHub». The «GitHub» button links to `https://github.com/{github_login}` in a new tab with `rel="noopener noreferrer"`. The mockup's «Проекты» button waits for Phase 3. |
| «О себе» | `bio` | Marked «От автора». Plain text with line breaks (`white-space: pre-line`). Empty `bio` hides the block. |
| «Скилы» | — | Pending: no backend source yet, phase not assigned. A plain list in future; never levels or bars. |
| «Главные проекты» | — | Pending backend Phase 3 (Projects). Up to 3 featured projects. |
| «Данные GitHub» | — | Pending backend Phases 5–6 (GitHub import and sync). Always marked «Источник: GitHub». |
| «Другие проекты» | — | Pending backend Phase 3. |

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

If a mockup and this guide disagree, raise the conflict instead of silently picking one.
