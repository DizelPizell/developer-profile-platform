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

- **Press Start 2P**: only short headings and labels (section titles, the «Класс» label, status badges). Not for sentences, form values or long names.
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

- Placeholder text is written in square brackets: `[Пока без описания]`.
- No invented scores, ratings, levels, experience points or progress bars, even though the style is game-like (CLAUDE.md, ADR-007). «Класс» shows the developer's own `headline` and nothing else.
- Blocks with GitHub data always carry a source mark «Источник: GitHub». Data entered by the developer has no such mark. This applies to `avatar_url` and `github_login`, which come from GitHub.
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
| Hero | `avatar_url`, `display_name`, `headline`, `location`, `github_login` | Round avatar; `null` avatar shows a default pixel avatar. `headline` is shown under the label «Класс». `github_login` links to `https://github.com/{github_login}`. Avatar and login carry «Источник: GitHub». Empty `location` is hidden. |
| «О себе» | `bio` | Plain text with line breaks. Empty `bio` hides the block. |
| «Скилы» | — | Pending: no backend source yet, phase not assigned. A plain list in future; never levels or bars. |
| «Главные проекты» | — | Pending backend Phase 3 (Projects). Up to 3 featured projects. |
| «Данные GitHub» | — | Pending backend Phases 5–6 (GitHub import and sync). Always marked «Источник: GitHub». |
| «Другие проекты» | — | Pending backend Phase 3. |

`display_name` and `headline` are never empty here: a profile can be published only with both (ADR-013).

`slug` is used for the page address and the canonical link.

Pending blocks are drawn in mockups with a bracketed placeholder. The F4 implementation does not render them on the public page until their data exists.

States:

| API response | Result |
|---|---|
| 200 | Profile page |
| 404 | 404 screen, HTTP status 404 |
| Any other error or API unreachable | Error screen `[Профиль временно недоступен]`, no internal details |

### Cabinet — `/me`

Data: `GET /api/v1/auth/me`, then `GET /api/v1/profile` → `slug`, `status`, `display_name`, `headline`, `bio`, `location`, `avatar_url`, `github_login`.

Blocks:

| Block | Data | Notes |
|---|---|---|
| Header | `avatar_url`, `github_login`, `slug` | Round avatar and login with «Источник: GitHub»; link to the public page `/u/{slug}`; «Выйти» button. |
| Status | `status` | `PRIVATE` → «Скрыт», `PUBLISHED` → «Опубликован». «Опубликовать» or «Скрыть» button (`POST /profile/publish`, `POST /profile/unpublish`). |
| Form | `display_name`, `headline`, `bio`, `location` | Four fields; `headline` is labelled «Класс». Character counters with the limits 100 / 160 / 2000 / 100. «Сохранить» button. |

Behavior:

- «Сохранить» sends `PATCH /profile` with only the changed fields. The form shows the values from the response, which are normalized by the server (trimmed, blank → `null`).
- Publish and unpublish use the stored values, so their button is disabled while the form has unsaved changes.
- The status and the form are updated from the `OwnProfileResponse` that every call returns.
- Client-side limits mirror the API, but the API is the source of truth.

States and errors:

| Case | Shown as |
|---|---|
| Loading | Panel placeholders |
| 401 from any call | Redirect to `/login` (the session is missing or expired) |
| 422 `VALIDATION_ERROR` | Error under each field from `details.fields` (`loc` `["body", "<field>"]`; `type` such as `string_too_long`, `control_characters`) |
| 422 `PROFILE_INCOMPLETE` | Fields from `details.missing_fields` are highlighted with «Для публикации заполните: …». Comes from publish, and from a save that clears `display_name` or `headline` of a published profile |
| 403 `CSRF_ORIGIN_INVALID` | Cannot be read by the browser: the response has no `Access-Control-Allow-Origin` (ADR-013), so `fetch` fails like a network error. Shown as the network error below. In practice it means `FRONTEND_URL` does not match the frontend's origin (for example `127.0.0.1` instead of `localhost`) |
| Network error or API unreachable | «Не удалось связаться с сервером.», with a retry; entered data is kept |
| 500 `INTERNAL_ERROR`, other errors | «Что-то пошло не так. Попробуйте ещё раз.» and «Код запроса: <request_id>» from the error body (or `X-Request-ID`) when present |
| Saved | Short success message in `success` |

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

### Temporary session page — `/me` in F2

Until the F3 cabinet, `/me` only proves the session:

| Case | Shown as |
|---|---|
| Loading | «Загрузка…» |
| 200 | «Вы вошли как», `@github_login` with «Источник: GitHub», the «Выйти» button |
| 401 | Redirect to `/login` |
| Network error | «Не удалось связаться с сервером.» and «Повторить» |
| Other API error | «Что-то пошло не так. Попробуйте ещё раз.», «Код запроса: <request_id>» when present, and «Повторить» |

### 404

Shown for unknown routes and when the public profile API returns 404. HTTP status 404.

The text says only that the page was not found. It never says that a profile exists or is private: the API deliberately returns the same 404 for private, missing and malformed slugs (ADR-013).

Blocks: a short title (Press Start 2P), one line of text, a link to the start page.

## Mockups

Mockups are added manually to `docs/frontend/mockups/`:

- `public-profile.png`
- `cabinet.png`
- `login.png`
- `not-found.png`

If a mockup and this guide disagree, raise the conflict instead of silently picking one.
