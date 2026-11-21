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

- **Press Start 2P** (`font-heading`): only large headings — «DEV.PROFILE», section titles, page titles, the 404 code. Not for sentences, labels, form values or long names.
  - The face is drawn on an 8 px grid and is crisp only at multiples of 8: section titles and the brand mark 16 px (`text-base`), page and screen titles 24 px (`text-2xl`), the 404 code 64 px. Other sizes give uneven strokes.
- **Tektur** (`font-sans`): body text, form fields, buttons, names, and small labels.
  - Small labels — the «Класс» label, «От автора», «Главный N», «Источник: GitHub», form labels, status and state badges, dialog and message titles — use the `caps-label` utility (`globals.css`): Tektur, 16 px, uppercase, letter spacing 0.04em.
- **Decision (2026-11-10)**: Tektur replaced Pixelify Sans. Pixelify Sans draws Cyrillic «д», «в», «з», «ы», «ь» close to Latin «a», «б», «э», «bl», «b», so «делал» read as «аелал» at every size. Tektur is a smooth face with a game, sci-fi character, so the pixel world stays in the headings and the hard shadows while text reads cleanly. Tiny5, a pixel face, was tried first and rejected by the owner as too pixel. Small labels moved from Press Start 2P to Tektur: at 10–12 px Press Start 2P is off its grid and hard to read.
- **Decision**: buttons with an important action (sign-in) are written in normal case, in Tektur, at a large size. Uppercase in Press Start 2P reads poorly.
- Type scale: 14 px (`text-sm`) for metadata and hints, 16 px (`text-base`) body, 18 px (`text-lg`) larger body, 20 px (`text-xl`) card titles and the sign-in text, 24 px headings, 36 px the profile name. Nothing below 14 px.
- Long text keeps a readable measure: «О себе» on the public page is at most 70 characters wide.
- Both fonts must include the Cyrillic subset (`fonts.test.ts` checks it).

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
- Blocks with GitHub data always carry a source mark «Источник: GitHub». This applies to `avatar_url` and `github_login`, which come from GitHub. On the public page, a block of developer-written text carries «От автора» (mockup `public-profile.png`), so the two sources stay distinguishable (CLAUDE.md); form fields in the cabinet have no mark. On a public project card both meet: the section keeps «От автора» for the developer's fields, and the GitHub block inside the card carries its own «Источник: GitHub».
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
| `/me/repositories` | «Репозитории GitHub» (F-GH1) | Client |
| `/me/analytics` | «Аналитика» (7.4) | Client |
| `/u/[slug]` | Public profile | Server (SSR) |
| `/u/[slug]/projects/[id]` | Public project page (4.6) | Server (SSR) |
| `/privacy` | «Политика данных» (9.7b) | Server (static) |
| anything else | 404 | — |

## Screens

### Public profile — `/u/[slug]`

Data: `GET /api/v1/public/profiles/{slug}` → `slug`, `display_name`, `headline`, `bio`, `location`, `avatar_url`, `github_login`, and since Phase 3 `featured` and `other` (projects with `id`, `title`, `summary`, `role`, `technologies`, plus `position` in `featured`; ADR-015). Since backend step 6.7 each project also carries a nullable `github` object (ADR-019), shown since F-GH2 (see "GitHub on public cards").

Blocks:

| Block | Data | Notes |
|---|---|---|
| Header | — | «DEV.PROFILE» and «Войти через GitHub», a link to `/login` (the mockup's top bar). |
| Hero | `avatar_url`, `display_name`, `headline`, `location`, `github_login` | Round avatar, loaded only when `avatar_url` starts with `https://`; otherwise (including `null`) the default pixel avatar. `display_name` in Tektur (a long name, Typography rule), `@github_login` under it. `headline` follows the badge «Класс». «Локация: …»; empty `location` is hidden. Avatar and login each carry «Источник: GitHub». The «GitHub» button links to `https://github.com/{github_login}` in a new tab with `rel="noopener noreferrer"`. «Проекты» (secondary) links to the project area and is shown only when there is a public project (see "Projects on the public page"). «Контакты» (secondary) links to `#contacts` and is shown only when there is a contact (see "Contacts on the public page"). |
| «Контакты» | `contacts` | Marked «От автора», next to «О себе». No contacts: no section. See "Contacts on the public page". |
| «О себе» | `bio` | Marked «От автора». Plain text with line breaks (`white-space: pre-line`). Empty `bio` hides the block. |
| «Скилы» | — | Pending: no backend source yet, phase not assigned. A plain list in future; never levels or bars. |
| «Главные проекты» | `featured` | Up to 3 cards in `position` order, marked «От автора». See "Projects on the public page". |
| «Данные GitHub» | — | The block drawn in `public-profile.png` is not built in V1: GitHub data lives on project cards (the nullable `github` object, see "GitHub on public cards") and on the project page, not in a profile-level block, and nothing is totalled across the profile (ADR-019). Any GitHub data is always marked «Источник: GitHub». |
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
- Each section heading has the square marker (`label` for featured, `text-muted` for other), the title, a rule and «От автора» on the right: every project field is written by the developer (content rules). The GitHub block inside a card is the exception and has its own mark.
- **«Главные проекты»** — a card per featured project, in `position` order (sorted when the response is read). One column on narrow screens, two from `sm`, three from `lg`:
  - the label «Главный N» (N = `position`), `caps-label` on `label`;
  - `title` in Tektur, wrapped at any point when a word is too long;
  - `summary`, at most four lines (`line-clamp`), then cut;
  - up to three technology chips, in the developer's order; the rest are not shown;
  - «Моя роль: {role}» at the bottom of the card, with the GitHub block, when there is one, under it. Cards of a line keep one height: the role and the block are pushed down together.
  - The mockup's striped image area and «Открыть проект ›» are not rendered. The title links to the project page (see "Public project page").
- **«Другие проекты»** — a row per project, in API order (newest first):
  - `title`, wrapped like on cards;
  - `summary` on one line, cut with an ellipsis;
  - a badge with the first technology (the developer's order, ADR-015). It sits on the right from `sm` (at most 40% of the row) and under the text on narrow screens, so a long name does not squeeze the title. A project without technologies cannot be public, but the row still renders without a badge.
- An empty `featured` or `other` hides its section, heading included. With no public projects at all, the project area is not rendered.
- The hero «Проекты» button (secondary) is an in-page link to `#projects`. It is rendered only when there is at least one public project.
- Every value is rendered as text. `featured` and `other` are required in the response; a missing array or a project of the wrong shape is an unexpected body (error screen). Project fields outside the whitelist (`id`, `title`, `summary`, `role`, `technologies`, `github`, `position`) are dropped. A wrong `github` does not count as a project of the wrong shape: it hides only the block (see below).

#### GitHub on public cards (F-GH2)

The layout comes from `public-cards.png`. The block is a Server Component (`app/u/[slug]/project-github.tsx`, no `"use client"`) with a `div` as its root, under a 4 px `outline` line. `github: null` shows nothing: no block, no line, no stub. `null` means no link, no complete sync, an unavailable repository or a lost relation (ADR-019), and the page does not say which. The maximum of featured projects stays 3; the six cards of the mockup only illustrate the states.

A featured card, under «Моя роль», top to bottom:

1. «Источник: GitHub», `caps-label` on no background, `text-muted`.
2. `full_name`, a link in `text-muted` opening `html_url` in a new tab (`rel="noopener noreferrer"`). Only a URL starting with `https://github.com/` is a link; anything else stays plain text.
3. The relation in `text`: «Владелец репозитория» or «В списке контрибьюторов (по данным GitHub)». The API never sends `NONE` here.
4. Chips, when they apply: «Форк {parent_full_name}» («Форк» when there is no parent) and «В архиве на GitHub».
5. `description`, at most two lines, then cut. `null` or an empty text hides the line without a stub.
6. The caption «Доля кода в байтах, по данным GitHub» over the languages: the first 3 as chips «Python 62 %», the rest as one «Другие — N %» in `text-muted`. Shares follow the cabinet's rules ("Languages" under F-GH1.5 below), from the same function. An empty list hides the languages and the caption, without the cabinet's placeholder.
7. «Данные GitHub от 01.11.2026».

A row of «Другие проекты» becomes a column: the former row, unchanged, and under it the line and one wrapping line of source, `full_name`, relation, chips and date. No description and no languages. The date wraps to the next line when the rest fills the row.

Rules for both:

- All chips use the chip style of the public page (`CHIP`: `bg-bg`, a 2 px `outline` border, `text-sm`), as in the mockup, not the cabinet's status badge.
- The date is `synced_at` as the day in UTC, without the time (`Intl.DateTimeFormat` `ru-RU` with `timeZone: "UTC"`), in `<time dateTime={synced_at}>`. The server and the reader see the same text, so nothing depends on the time zone, and old data reads as old. The cabinet shows the same moment in the user's zone, so near midnight the two dates can differ.
- `pushed_at` is in the contract, but it is not read and not shown on the public page.
- Text from GitHub is rendered as text. Long names wrap at any point. No stars, forks, commit counts, bars or levels, and none of «подтверждено», «проверено», «верифицирован» (ADR-019).
- `github` is read through a whitelist (`readPublicGitHub`). A wrong shape (not an object, a field of a wrong type or missing, a relation other than `OWNER` or `CONTRIBUTOR`, a wrong language, `synced_at` that is not a date-time with an offset) gives `github: null`: the card and the profile keep working. The block is an addition to the card, so unlike a broken project it does not take the error screen. A wrong shape writes one line to the server log per project per request, with the project's id and the name of the first wrong field, never a value. A `github` field missing altogether is `null` without a log.

#### Contacts on the public page (C.2)

The layout and texts come from `profile-contacts.png` (seven states and a rules card). Data: `contacts` of the profile response, and `GET /public/profiles/{slug}/contacts?type=EMAIL|PHONE` on a click (ADR-0020).

- The section is «Контакты» with «От автора», `id="contacts"`. Without contacts there is no section, no hero button and no empty block.
- Each contact is a small `text-muted` caption («Telegram», «LinkedIn», «Email», «Телефон», «Другое») over its value, in API order. The cabinet sends Telegram, LinkedIn, Email, Телефон, then «Другое», the order of the mockup.
- Rendered on the server (`app/u/[slug]/profile-contacts.tsx`): Telegram as «@name», LinkedIn as «in/slug», «Другое» as «Название · хост». The host is `new URL(url).host`, so an IDN reads as punycode and the name cannot hide where the link leads.
- A value is a link only after its check, otherwise it stays text: Telegram — `url` starts with `https://t.me/`; LinkedIn — with `https://www.linkedin.com/in/`; «Другое» — the URL parses and its protocol is `http:` or `https:` (no host is shown otherwise).
- Links open a new tab with `rel="noopener noreferrer nofollow ugc"`. `mailto:` and `tel:` links have no `target`.
- Email and phone are one client component (`contact-reveal.tsx`) with the props `type` and `slug` only: the value is never in the HTML or the props. States:

| State | Shown |
|---|---|
| Rest | The button «Показать email» / «Показать телефон» (secondary) |
| Loading | The button reads «Загрузка…» and is disabled |
| Shown | A link `mailto:` / `tel:` with the value as its text; it takes the focus, since the button is gone |
| Error | «Не удалось получить email.» / «Не удалось получить телефон.» (`error`) and «Повторить» |

- The loading and error texts sit in a live region (`role="status"`). The answer is checked before it is shown: the type is the requested one and `url` equals `mailto:` or `tel:` plus the value; anything else is the error state. The browser log names only the field (`Contact EMAIL: request failed`).
- Long values wrap at any point (state 7). Every value is React text.
- `contacts` is read through a whitelist (`readContacts`), like `github` of a project: a missing field is `[]` without a log; a wrong shape (not a list, an unknown type, a public contact without `value` or `url`, «Другое» without a name) is `[]` and one server log line per profile with the first wrong field, never a value. The profile keeps working. For `EMAIL` and `PHONE` the reader always sets `value`, `label` and `url` to `null`, whatever the body holds.

Decisions where the mockup differs (the owner, 2026-11-16):

- **Place.** The mockup puts the block in a right column under «Инвентарь», which the page does not have. From `lg` «О себе» is on the left and «Контакты» on the right (20rem); below `lg` the section goes under «О себе»; without `bio` it takes the row alone.
- **Hero button.** The mockup draws no hero; ADR-0020 requires the button.
- **Phone.** The mockup shows «+7 999 123-45-67»; the page shows the E.164 value as the API returns it. Formatting international numbers without a library would be a guess.

### Public project page — `/u/[slug]/projects/[id]` (4.6)

Spec for the mockup `project-page.png` (step 4.4), drawn after this text; where the drawing differs, the conflict is raised, not silently picked. Data: `GET /api/v1/public/profiles/{slug}/projects/{id}` → `PublicProjectPage` (step 4.3): `id`, `title`, `summary`, `description`, `problem`, `results`, `role`, `contribution`, `technologies`, `demo_url`, `screenshots` (`url`, `caption`, `width`, `height`), `github`, `owner` (`slug`, `display_name`, `avatar_url`). Server rendered (SSR), one API call per request, like the profile.

Principle: **demo first** (PRD, ADR-0023). When the project has a demo, the demo block is the first large element after the title. There is no iframe: a preview and a link.

Blocks, top to bottom:

| Block | Data | Notes |
|---|---|---|
| Header | — | The profile page's top bar, unchanged. |
| Back link | `owner` | «‹ {display_name}», a link to `/u/{owner.slug}`. No avatar: the name is enough to say where it leads. |
| Title | `title`, `summary`, `technologies`, `role` | `title` in Tektur (`h1`, wraps at any point), `summary` under it, then all technology chips (`CHIP`) in the developer's order, then «Моя роль: {role}». Marked «От автора». |
| «Демо» | `demo_url`, first of `screenshots` | Only when `demo_url` passes the link check below. See "Demo block". |
| «Скриншоты» | `screenshots` | See "Screenshots". No screenshots left to show: no section. |
| «Задача» | `problem` | «От автора», plain text, `white-space: pre-line`. `null` hides the block. |
| «Мой вклад» | `contribution` | The same; never empty for a public project. |
| «Результат» | `results` | The same; `null` hides it. |
| «Подробнее» | `description` | The same; `null` hides it. |
| «Данные GitHub» | `github` | The featured-card GitHub block of F-GH2 (source, `full_name`, relation, chips, description, languages, date), the same component and whitelist reader. `null`: no section, no stub. |

The order of the texts — task, contribution, result, details — puts the evidence of the developer's own work before the long description. No block is drawn empty and none says «нет демо» or «нет скриншотов»: a project needs neither (CLAUDE.md).

#### Demo block

- A panel with the heading «Демо», the preview and the main button «Открыть демо ↗» (accent, `lg`).
- The preview is the first screenshot: `<img>` with its `width` and `height` (no layout shift), scaled to the panel width, `alt` from its caption. The image itself is not a link: one link per target keeps the tab order short.
- Without screenshots the panel shows the host of the demo in large text instead of the preview, and the same button.
- Under the button: «{host} · откроется в новой вкладке» in `text-muted`, where host is `new URL(demo_url).host` (an IDN reads as punycode, so the text cannot hide where the link leads), and «Ссылку указал автор, платформа сайт демо не проверяет.» (ADR-0023: the server never requests the URL).
- Link check, as for «Другое» in contacts: the URL parses and its protocol is `http:` or `https:`. Otherwise the whole block is hidden and one server log line names the project id and the field, never the value.
- The link opens a new tab with `rel="noopener noreferrer nofollow ugc"`.
- With a demo, the first screenshot is the preview and the «Скриншоты» section starts from the second. Without a demo it shows all of them.

#### Screenshots

- Section «Скриншоты», «От автора». One column; two from `sm` when there are two or more.
- Each is a `figure`: `<img>` with `width`, `height`, `loading="lazy"` (the demo preview is not lazy), `alt` = `caption`, or «Скриншот N проекта «{title}»» when there is none. A caption is also shown under the image in `text-muted`.
- The image is a link to its own `url` in a new tab, named «Открыть скриншот N в полном размере»: no lightbox and no client JavaScript in V1.
- A screenshot is used only when `url` starts with `/media/` (a path on the site's own origin) and `width` and `height` are integers from 1 to 2560; otherwise it is dropped with one server log line (project id, field). The page keeps working.

Rules:

- Every value is rendered as text. The response is read through a whitelist (`readPublicProjectPage`); fields outside `PublicProjectPage` are dropped. A missing required field or a wrong type of a project field is an unexpected body (error screen); a wrong `github` hides only its section, like on the cards.
- No scores, counters, views or «проверено» marks. GitHub data stays in its own marked section (content rules).

Address:

- The slug follows the profile rules (lowercased, the same pattern; uppercase → 308 to `/u/{lowercase}/projects/{id}`).
- `id` must be a canonical UUID (8-4-4-4-12 hex, as the API's `parse_canonical_uuid`); anything else is the project 404 without calling the API. Uppercase hex redirects (308) to lowercase together with the slug, so a project has one address.

Metadata: title «{title} — {owner.display_name}», description `summary`. No Open Graph image in V1.

States:

| API response | Result |
|---|---|
| 200 | Project page |
| 404, malformed slug or id | Project 404 screen, HTTP status 404: «Проект не найден» and «Возможно, он скрыт, ещё не опубликован или ссылка неверна.» No link back: the profile may be private too, and the one 404 must not tell which case it is (step 4.3) |
| Any other error | «Не удалось загрузить проект» with «Повторить», HTTP status 500, as on the profile |

Responsive: at 375 px everything is one column; the demo button takes the full width.

Links from the profile (part of 4.6): on a featured card and in an «Другие проекты» row the `title` becomes a link to `/u/{slug}/projects/{id}`. There is no separate «Открыть проект ›»: a second link to the same place adds a tab stop and nothing else. The cards get no image: the card whitelist has no screenshots (ADR-019), and the mockup's striped area is dropped in V1.

### Cabinet — `/me`

Data: `GET /api/v1/profile` → `slug`, `status`, `display_name`, `headline`, `bio`, `location`, `avatar_url`, `github_login`, `contacts`. The cabinet does not call `/auth/me`: the profile response carries everything it shows, and its 401 means there is no session.

The mockup `cabinet.png` sets the layout and texts. Where it differs from the rules above, the decisions are:

- the cabinet labels `headline` «Заголовок»; the public page keeps «Класс»;
- buttons stay in Tektur, normal case (Typography decision), with the mockup's colors: «Сохранить» accent, «Опубликовать» `label` fill with `outline` text, «Скрыть» panel;
- the header keeps «Источник: GitHub» under the login, although the mockup omits it;
- the mockup's «Состояния статуса» legend is an annotation and is not built; its sentence sits under the public address.

Blocks:

| Block | Data | Notes |
|---|---|---|
| Header | `avatar_url`, `github_login` | «DEV.PROFILE» on the left. On the right: round avatar (`null` → default pixel avatar), `@github_login` with «Источник: GitHub», «Выйти» (secondary). While loading or after a load error only «Выйти» is shown. |
| «Мой профиль» | `slug`, `status` | «Публичный адрес: /u/{slug} (не меняется)» and «Опубликованный профиль видят все по этой ссылке.» The address is a link to the public page only while `PUBLISHED`. On the right «Статус» and a badge: `PRIVATE` → «Черновик · PRIVATE» (`label`), `PUBLISHED` → «В сети · PUBLISHED» (`success`). |
| Form | `display_name`, `headline`, `bio`, `location` | Fields in mockup order, labels in `caps-label` (Tektur uppercase), required ones marked «*» (required for publication, not for saving). Each has a hint and a counter «N / limit». Buttons «Сохранить», «Опубликовать», «Скрыть» and the saved message. |

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

#### «Удаление аккаунта» (9.7b)

A section under the profile form: a heading with a grey marker, then a panel with «Удалятся профиль, контакты, проекты со скриншотами и привязки репозиториев. Публичная страница перестанет открываться. Отменить нельзя.», «Что мы храним и как долго — в политике данных.» (a link to `/privacy`) and «Удалить аккаунт» (`error` fill). No mockup: one panel and one dialog, built from the parts of the project deletion.

«Удалить аккаунт» opens an `AlertDialog` (focus on «Отмена»):

- «Удалить аккаунт?», «Профиль, контакты, проекты и скриншоты удалятся сразу и навсегда. Отменить нельзя.»;
- «Доступ приложения к GitHub отзывается отдельно — в настройках GitHub.»: the link opens `https://github.com/settings/applications` in a new tab. We hold no user token, so the app cannot revoke it (ADR-0016);
- the field «Введите логин «{github_login}», чтобы подтвердить»; «Удалить навсегда» (`error` fill) is disabled until the field equals the login, ignoring case and surrounding spaces; Enter sends only then;
- «Отмена» and Escape close the dialog and clear the field.

«Удалить навсегда» sends `DELETE /api/v1/auth/me` once and reads «Удаляем…» meanwhile, with the field and both buttons disabled. 204 → `/login`. 401 → `/login` too. Any other failure stays in the dialog with the cabinet's network or generic text and the request id (ADR-0028).

#### Contacts in the profile form (C.2)

Mockup `profile-contacts.png`, states A–D. The block «Контакты» sits inside the profile form, above the buttons, and is saved by the same «Сохранить» (ADR-0020).

The note at the top follows the status:

- `PRIVATE`: «Контакты станут видны на публичной странице после публикации профиля. Email и телефон показываются только по клику.»
- `PUBLISHED`: «Профиль опубликован: сохранённые контакты сразу видны на публичной странице. Email и телефон показываются только по клику.»

Fields, in this order:

| Type | Label | Placeholder | Hint | `maxLength` |
|---|---|---|---|---|
| `EMAIL` | «Email» | «name@example.com» | «Латиницей, без пробелов» | 254 |
| `TELEGRAM` | «Telegram» | «@username» | «Имя пользователя или ссылка t.me/…» | 64 |
| `LINKEDIN` | «LinkedIn» | «linkedin.com/in/…» | «Ссылка на профиль вида linkedin.com/in/имя» | 150 |
| `PHONE` | «Телефон» | «+79991234567» | «Формат: +79991234567, пробелы и скобки уберём» | 32 |

- `maxLength` is wider than the stored limit where the field also takes a link. The server's validation is not repeated on the client.
- Contact fields have no counter «N / limit» (`FormField` with `counter={false}`), as in the mockup.
- «+ Другие способы связи» adds a row «Другой способ N»: «Название» (placeholder «Например: Мой блог», hint «До 40 символов»), «Ссылка» (hint «Только http и https») and «Удалить». Under the button «Добавлено N из 3»; with three rows the button is disabled and the text is «Максимум 3 других способа связи» (`label`).
- The list is built by one function (`buildContacts`): an empty standard field and a fully empty row are not sent; the order is Telegram, LinkedIn, Email, Телефон, then the rows. `contacts` goes into the PATCH only when this list differs from the same list built from the stored contacts, so an untouched form is never "changed". Clearing everything sends `[]`.
- After a save the fields show the response: Email and Телефон — `value`, Telegram — «@» and `value`, LinkedIn — `url`, a row — `label` and `url`. LinkedIn takes `url` because the server stores the slug but accepts only `linkedin.com/in/{slug}`: a slug in the field would fail the next save.
- A stored standard contact shows «Сохранено как: …» (the email, «@name», «in/slug», the number) instead of the hint while its field is untouched; an edited field shows the usual hint again.
- Errors: the index in `loc` is the place in the list that was sent, so the form keeps the form key of every sent item and puts the error under that field or row, with the red outline, `aria-invalid` and `aria-describedby`.

| Error | Text |
|---|---|
| `invalid_email` | «Укажите адрес латиницей: кириллические домены пока не поддерживаются.» |
| `invalid_telegram` | «Нужно имя пользователя или ссылка на профиль, а не приглашение.» |
| `invalid_linkedin` | «Нужна ссылка на профиль вида linkedin.com/in/имя.» |
| `invalid_phone` | «Укажите номер с плюсом, например +79991234567.» |
| `invalid_url` | «Допустимы только ссылки http и https.» |
| `string_too_short` on a link (a row with a name only) | «Укажите ссылку.» |
| `missing` on a name | «Укажите название.» |
| `string_too_long` on a name | «Не больше 40 символов.» |
| `control_characters` on a name | «Недопустимые символы.» |
| Any other type on a field | «Некорректное значение.» |
| A list error (`too_many_other_contacts`, `duplicate_contact_type`, `too_long`) | The generic error with «Код запроса»: the form cannot send such a list |

- Adding or removing a row clears the contact errors: row errors are kept by place.

Decision where the mockup differs (the owner, 2026-11-16): state B keeps the typed text in the field and the normalized value only in the caption; the form shows the value from the response, like its other fields, and keeps the caption.

### Projects in the cabinet — `/me/projects` (F5)

Mockups `my-projects.png` (list) and `project-form.png` (form) set the layout and texts. The general rules above (tokens, typography, focus, content rules) apply. Where the mockups differ from them, the cabinet decisions hold: buttons in Tektur, normal case; the header keeps «Источник: GitHub».

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

Top panel: «Новый проект» or «Проект», the state badge (once saved) and «Публичная страница проекта появится позже» (from 4.5 a link or a note, see "«Демо и скриншоты» in the project form"). Fields in mockup order; «*» means required for publication, not for saving. `role` and `technologies` sit side by side, as do `problem` and `results`; on narrow screens they stack.

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
- Under the form: «Демо, скриншоты и репозиторий GitHub добавим в следующих версиях.» From F-GH1 the line changes (see "GitHub in the cabinet"); from 4.5 it is gone.

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

#### «Демо и скриншоты» in the project form (4.5)

Spec for the mockup `project-media.png` (step 4.4: the block in its states and a rules card), drawn after this text. API: `demo_url` in `ProjectWrite` / `ProjectResponse` (step 4.1, ADR-0023) and the "Screenshots" section of `docs/api/API_CONTRACT.md` (step 4.2a, ADR-0022).

Place: after «Результат», before «Репозиторий GitHub» (demo first, as on the public page). Heading «Демо и скриншоты», «Необязательно». It replaces the line «Демо и скриншоты добавим в следующих версиях.» under the form; that line goes away with nothing in its place.

The top panel's «Публичная страница проекта появится позже» changes:

- a `PUBLISHED` + `PUBLIC` project of a `PUBLISHED` profile: the link «Открыть публичную страницу ↗» to `/u/{slug}/projects/{id}`, in a new tab (the slug and status come from `GET /profile`, already read for the header);
- otherwise: «Публичная страница появится, когда проект и профиль будут опубликованы.»

**Demo link** — an ordinary form field, saved by «Сохранить» with the other fields:

| Field | Label | Placeholder | Hint | `maxLength` |
|---|---|---|---|---|
| `demo_url` | «Ссылка на демо» | «https://demo.example.com» | «Только http и https. У посетителя откроется в новой вкладке; превью — первый скриншот» | 2048 |

- No counter (like contact links). An emptied field is sent as `null`: the API rejects a blank string (contract). The field shows the stored value after a save (the scheme in lower case).
- Errors under the field: `invalid_url` → «Допустимы только ссылки http и https.» (the contact text), `string_too_long` → «Не больше 2048 символов.», any other → «Некорректное значение.».
- The client does not check the URL before sending; the server is the source of truth.

**Screenshots** — work at once, like linking a repository, and do not depend on «Сохранить».

- On `/me/projects/new`: only «Скриншоты можно добавить после первого сохранения.» (an upload needs a project id).
- The note: «Скриншоты сохраняются сразу и не зависят от кнопки «Сохранить». Файл открывается по прямой ссылке у любого, кто её знает, даже пока проект — черновик.» The second sentence is the contract's rule (ADR-0022), said to the owner before they upload.
- «Скриншотов: N из 6» and «Добавить скриншот» (`label`). The button opens a file picker (`accept="image/jpeg,image/png,image/webp"`, one file). Hint: «JPEG, PNG или WebP, до 5 МБ. Метаданные (EXIF, в том числе место съёмки) удаляются.»
- Before sending, two checks without a request: over 5 MB → «Файл больше 5 МБ.»; a type other than the three → «Подходят JPEG, PNG и WebP.» The server still decides by the content.
- At 6 the button is disabled with «Можно добавить не больше 6 скриншотов.»
- Upload sends `POST /projects/{id}/screenshots` with the file and no caption. Meanwhile the button reads «Загружаем…», and all form buttons are disabled (a request at a time, as everywhere). No progress bar: `fetch` does not report upload progress, and 5 MB does not need one.
- An empty list shows «[Пока нет скриншотов]».

A row per screenshot, in order:

- the position N in a `label` square; the first row also carries «Превью демо» while a demo link is saved;
- a thumbnail (`url`, 160 px wide, `object-contain`, `width`/`height` set), `alt` = caption or «Скриншот N»;
- «Подпись» (placeholder «Что на скриншоте», hint «Для тех, кто не видит картинку. До 200 символов», counter, one line) and «Сохранить подпись» (secondary), active when the text differs from the stored one. Enter in the field saves the caption, not the form. It sends `PATCH …/screenshots/{screenshot_id}`; an emptied caption is `null`;
- ▲ and ▼ with the names «Выше: скриншот N» and «Ниже: скриншот N» (disabled on the edges, no drag-and-drop, as for featured projects). A move sends `POST …/screenshots/reorder` with the whole set in the new order;
- «Удалить» (red text on a panel) asks in an `AlertDialog` (focus on «Отмена»): «Удалить скриншот?», «Файл удалится навсегда. Отменить нельзя.», «Удалить» (`error` fill), «Отмена».

Behavior:

- Every screenshot call returns `ScreenshotListResponse`; the form replaces its list with it and touches nothing else, so unsaved field edits stay.
- Focus: after an upload — the new row's caption field; after a delete — the next row's «Удалить», or «Добавить скриншот» when none is left; after a move — the same arrow in the row's new place (or the other arrow when it became disabled).
- Results and errors are announced in a live region of the block (`role="status"`): «Загружаем скриншот…», «Скриншот добавлен.», «Подпись сохранена.», «Скриншот удалён.», «Порядок изменён.», and the error texts below. An upload error also names the file.

Errors, shown inside the block (under the upload button, or under the row they belong to):

| Response | Text |
|---|---|
| 422 `invalid_image` on `file` | «Не получилось прочитать картинку. Подходят JPEG, PNG и WebP.» |
| 422 `image_too_large` on `file`, or 413 from Nginx (an HTML body, read by the status) | «Файл больше 5 МБ.» |
| 422 `too_many_pixels` on `file` | «Слишком большое изображение: не больше 40 мегапикселей.» |
| 422 on `caption` | «Не больше 200 символов.», «Недопустимые символы.» or «Некорректное значение.» |
| 409 `SCREENSHOT_LIMIT_REACHED` | «Можно добавить не больше 6 скриншотов. Список загружен заново.»; the list is reloaded from `GET /projects/{id}` (only `screenshots` taken) |
| 409 `SCREENSHOT_ORDER_MISMATCH` | «Список скриншотов изменился, порядок загружен заново.»; reloaded the same way |
| 404 `NOT_FOUND` | One code for a missing screenshot and a missing project, so the form reloads `GET /projects/{id}`: 200 → «Скриншот не найден. Список загружен заново.»; 404 → the «Проект не найден» panel |
| 401, network, 500 | The form's usual handling (`/login`, the cabinet texts with «Код запроса») |

### GitHub in the cabinet (F-GH1)

Mockups: `repositories.png` (the repository list), `github-states.png` (messages and confirmations), the «Репозиторий GitHub» block of `project-form.png`, and the «Импорт из GitHub» button and GitHub label of the updated «Мои проекты» mockup. API: the GitHub section of `docs/api/API_CONTRACT.md` (ADR-016, ADR-017, ADR-018). Where a mockup differs from the contract, the contract wins; the differences are listed for the mockup owner, not built.

The general cabinet rules apply: tokens, typography, buttons in Tektur in normal case, the header from `GET /profile` with «Источник: GitHub», focus, a second click during a request sends nothing.

Sync is not part of F-GH1.1–F-GH1.3 (FRONTEND_PLAN; F-GH1.4 is folded into F-GH1.3). The sync status, the languages, «Обновить данные» with its pause and polling while `QUEUED` or `SYNCING` are F-GH1.5 ("Sync status, languages and «Обновить данные»" below). The public «Данные GitHub» data on project cards is F-GH2.

#### Wording

- Every block with GitHub data carries «Источник: GitHub»: the top panel of `/me/repositories`, the form block, and the «GitHub» chip in front of a repository name on a project card.
- The relation states the fact (ADR-017, ADR-019):
  - `OWNER` → «Владелец репозитория»;
  - `CONTRIBUTOR` → «В списке контрибьюторов (по данным GitHub)»;
  - `NONE` → no label, the explanation from "States of a linked repository" instead.
- The words «подтверждено», «проверено» and «верифицирован» are not used anywhere: a link confirms only the relation, not the project's text.
- A fork: «Форк {parent_full_name}», or «Форк» when `parent_full_name` is `null` (the list items carry no parent). An archived repository: «В архиве на GitHub».
- Before the first successful sync (`synced_at = null`) the block shows an honest placeholder instead of languages: «Языки и другие данные появятся после первой синхронизации с GitHub. Сейчас данные ещё не загружены.» Nothing is guessed or filled in on the client.
- Languages, once a sync has read them, are shares of GitHub's byte counts labelled «Доля кода в байтах, по данным GitHub» (ADR-019; F-GH1.5 below). They are not skills and are never levels, scales or bars.
- No other numbers are shown: no stars, forks, commit counts or totals (CLAUDE.md, ADR-019).
- `pushed_at` is «Обновлён: {date}», the date only in the user's time zone (`ru-RU`, `30.10.2026`). A `null` value hides the line. This is the cabinet only: the public page does not show it.
- A `null` `description` is «У этого репозитория нет описания на GitHub». A long description is cut after two lines.
- Text from GitHub (`full_name`, `description`, `parent_full_name`) is rendered as text, never as HTML.
- `full_name` links to `html_url` in a new tab with `rel="noopener noreferrer"`, only when `html_url` starts with `https://github.com/`; otherwise it is plain text.

#### Entry points

- «Импорт из GitHub» (secondary) on «Мои проекты», left of «Новый проект», opens `/me/repositories`. It stays active at 50 projects: linking still works there.
- In the project form, the link «выберите из своего списка» under the repository input opens `/me/repositories`.
- The cabinet gets no third tab. `/me/repositories` has no tabs, only «‹ Назад к проектам» (`/me/projects`), like the form.

#### «Репозитории GitHub» — `/me/repositories`

Data:

- `GET /integrations/github/repositories?page=N`.
- `GET /projects`, for three things: project titles for «Проект: {title}», the projects in the link dialog, and the project count for the 50 limit.
- `GET /profile`, for the header.

The page number lives in the address (`/me/repositories?page=2`). A missing or invalid value (not a plain 1..100) means page 1; the address is left as it is.

Top panel:

- «Репозитории GitHub» with «Источник: GitHub».
- «Ваши публичные репозитории. Мы только читаем данные, ничего не меняем на GitHub.»
- «Привязать можно репозиторий, в котором вы владелец или входите в список контрибьюторов. Список обновляется раз в 5 минут: новый репозиторий появится не сразу.»

The 5 minutes is the backend's page cache (contract). The page has no «Обновить список» button: it would return the same cached page.

A card per item, in API order (most recently pushed first):

- `full_name` (the link rule above), the labels «Форк» and «В архиве на GitHub» when they apply, and «Обновлён: {date}» on the right.
- `description` or the empty-description text.
- Without `linked_project_id`:
  - «Импортировать как проект» (`label`) and «Привязать к проекту…» (secondary);
  - the hint «Импорт создаёт черновик с названием репозитория. Остальное вы заполняете сами.»
  - Forks and archived repositories can be imported and linked (ADR-017).
- With `linked_project_id`:
  - the badge «Привязан» and «Проект: {title}», a link to `/me/projects/{linked_project_id}`;
  - the title comes from `GET /projects`, «[Без названия]» when `null`, and «Открыть проект» when the project is not in that list;
  - no import or link buttons: both would answer 409 `GITHUB_REPOSITORY_ALREADY_LINKED`.

Pagination:

- «‹ Назад», «Страница N», «Вперёд ›».
- «Назад» is disabled on page 1. «Вперёд» is disabled when `next_page` is `null`.
- A page change loads only the repository list.

A later empty page (typed into the address) shows «На этой странице репозиториев нет.» with the pagination, so «Назад» leads back.

An empty page 1 shows a dashed panel:

- «На вашем аккаунте GitHub нет публичных репозиториев. Приватные мы не показываем. Проект можно создать и без репозитория.»
- The link «Создать проект вручную» to `/me/projects/new`.

Import:

- At 50 projects (counted from `GET /projects`) the import buttons are disabled with «Можно создать не больше 50 проектов.». The API stays the source of truth (`PROJECT_LIMIT_REACHED`).
- «Импортировать как проект» sends `POST /integrations/github/repositories/{github_repo_id}/import`.
  - The import reads GitHub and may take a few seconds. The button reads «Импортируем…», and every action on the page is disabled.
- 201 moves to `/me/projects/{id}` of the new project. The form shows a success panel at the top:
  - «Проект создан» and «Из репозитория {full_name} создан черновик «{title}». Заполните «Коротко о проекте», «Роль», «Ваш вклад» и «Технологии», чтобы опубликовать его.»;
  - the values come from the project response;
  - the panel is shown once, after the import (a marker in the address that the form removes), and closes on the next save.
- The mockup's banner on the repository page with «Открыть проект» is not built.

Link from the list:

- «Привязать к проекту…» opens an accessible modal dialog (focus starts on the first project, Escape closes it).
  - Title: «Привязать к проекту», then «Репозиторий: {full_name}», since a modal hides the card it was opened from.
  - A radio list of all the user's projects from `GET /projects`, in API order: `title` (or «[Без названия]») and the state badge from «Мои проекты».
  - Under a project whose `github` is not `null`: «Уже привязан к {github.full_name}. Новая привязка заменит старую.» (`label` text).
  - The note «Привязка не меняет статус, видимость и тексты проекта.»
  - «Привязать» (accent; disabled until a project is chosen) and «Отмена».
  - With no projects: «[Пока нет проектов]» and only «Отмена».
- «Привязать» sends `POST /projects/{id}/repository` with `{"full_name": item.full_name}`. The button reads «Проверяем на GitHub…», and Escape and «Отмена» wait for the answer. Errors are shown inside the dialog, which stays open.
- On 200:
  - the dialog closes and the card shows «Привязан · Проект: {title}»;
  - another card that pointed to the same project loses its badge, since the link replaced it;
  - the project's `github` in the loaded project list takes `full_name` and `html_url` from the response;
  - the confirmation from `github-states.png` appears above the list: «Репозиторий привязан», «Проект «{title}» привязан к {full_name}. Статус, видимость и тексты проекта не менялись.»;
  - the confirmation takes the focus, since the card's «Привязать к проекту…» is gone;
  - `GET /projects` is read again for the titles and the «Уже привязан к …» lines (decided with the owner in F-GH1.2); the repository list is not reloaded, its cards change locally. If that read fails, the locally updated project list stays.

Action errors (import, link from the list) appear in an alert above the list, scrolled into view. Load errors of the list replace the cards.

#### «Репозиторий GitHub» in the project form — `/me/projects/[id]`

The block sits after «Результат», before the form buttons.

- Its heading is «Репозиторий GitHub» with «Источник: GitHub» and «Необязательно».
- On `/me/projects/new` it shows only «Репозиторий можно привязать после первого сохранения.»: a link needs a project id.

Not linked (`github` is `null`):

- «Привяжите репозиторий, и в проекте появятся факты из GitHub. Привязать можно репозиторий, в котором вы владелец или входите в список контрибьюторов.»
- An input with the placeholder «владелец/репозиторий» and «Привязать» (accent).
- The hint «Только публичные репозитории. Формат: имя владельца, косая черта, имя репозитория. Или выберите из своего списка.» The last words are the link to `/me/repositories`.
- The value is trimmed. A value that does not match the contract's `owner/name` pattern shows «Формат: владелец/репозиторий.» without a request. The API stays the source of truth: its 422 `VALIDATION_ERROR` shows the same hint. «Привязать» is disabled while the input is empty, and Enter in the input links instead of submitting the form.
- «Привязать» sends `POST /projects/{id}/repository`. The link reads GitHub and may take a few seconds, so the button reads «Проверяем на GitHub…».

Linked:

- The panel shows `full_name` (link rule), «Обновлён: {date}», `description`, and the labels: relation, fork, archived.
- Under the labels sit the sync message, the languages (or the placeholder while `synced_at` is `null`) and the data date: "Sync status, languages and «Обновить данные»" below.
- Under the panel: «Заменить репозиторий» (secondary) and «Отвязать» (red text on a panel).
  - «Заменить репозиторий» shows the input again with «Отмена». A successful link replaces the previous one (contract).
  - «Отвязать» asks in an `AlertDialog` (focus starts on «Отмена»): «Отвязать репозиторий?», «Проект и его тексты останутся. Пропадёт только связь с {full_name}. Привязать можно снова.», «Отвязать» (`error` fill) and «Отмена». Confirming closes the dialog and sends `DELETE /projects/{id}/repository`; the button reads «Отвязываем…» meanwhile, and an error is shown under the buttons with the cabinet texts (unlink does not read GitHub).

States of a linked repository (ADR-017):

| Field | Shown in the block |
|---|---|
| `unavailable: true` | Warning «Репозиторий недоступен: удалён или стал приватным. Публично данные GitHub не показываются.» The rest of the panel shows the stored data. |
| `relation: "NONE"` | Warning «По данным GitHub вы сейчас не владелец репозитория и не в списке его контрибьюторов. Публично данные GitHub не показываются, пока связь не найдётся снова.» No relation label. |

Behavior:

- Link and unlink work at once and do not depend on «Сохранить». The note under the block says: «Привязка и отвязка работают сразу и не зависят от кнопки «Сохранить». Они не меняют статус, видимость и тексты проекта.»
- Link and unlink return the whole `ProjectResponse`. The form takes only `github` from it, so unsaved edits in the text fields stay.
- While a link or unlink runs, all form buttons are disabled, as for every request.
- The line under the form becomes «Демо и скриншоты добавим в следующих версиях.»
- Link errors are shown inside the block, under the input. For `GITHUB_REPOSITORY_ALREADY_LINKED` the form reads `GET /projects` once, only on that error, to name the other project (decided with the owner in F-GH1.3).
- After a link the focus moves to the linked panel; after an unlink, to the input (their triggers are gone).

#### Sync status, languages and «Обновить данные» (F-GH1.5)

Mockup: `repository-sync.png` (11 states and a rules card). It does not draw an unavailable repository: that state follows the tables here. API: `sync`, `synced_at` and `languages` of `ProjectGitHub`, and `POST /integrations/github/repositories/{github_repo_id}/sync` (contract, GitHub; ADR-018, ADR-019). Decided with the owner on 2026-11-01. The mockup draws each state in one frame; the panel keeps its border from `project-form.png`, and the new elements take the mockup's order.

Order, top to bottom. Inside the panel: `full_name` and «Обновлён: {date}», the description, the labels, the sync message, the languages or a placeholder, «Данные GitHub от {date}», the `unavailable` and `NONE` warnings. Under the panel: «Обновить данные» on its own row, «Заменить репозиторий» and «Отвязать», the pause hint while a pause runs, the note on link and unlink.

The sync message, at most one, by `sync.status` and `synced_at`. Its tones are those of the GitHub messages (`label` or `error` border on `bg`); it sits in a live region (`role="status"`), so a change is announced. The job's error is never shown: the API does not return it (ADR-018).

| State | Message |
|---|---|
| `QUEUED` or `SYNCING` (one message: a failed attempt returns to `QUEUED`) | «Получаем данные с GitHub…» with three squares that step through brightness (static with `prefers-reduced-motion`); a `text-muted` border on `panel` |
| `NOT_SYNCED` (links made before backend step 6.2) | «Ещё не синхронизирован с GitHub.»; the same box without the squares |
| `SYNCED` | None: the data date says it |
| `FAILED`, `synced_at` set | «Не удалось обновить данные с GitHub. Показаны данные от {date}.» (`error`) |
| `FAILED`, `synced_at` `null` | «Не удалось получить данные с GitHub. Попробуйте обновить позже.» (`error`) |
| `FAILED` with `unavailable: true` (F-GH1.6) | None: the `unavailable` warning says it, and a job of an unavailable repository ends `FAILED` every day |
| Polling stopped after its 24 reads | «Синхронизация идёт дольше обычного. Проверьте позже.» and «Проверить снова» (`label`: the job may still finish) |
| Three failed reads in a row | «Не удалось узнать статус синхронизации.» and «Проверить снова» (`error`) |

The `unavailable` warning has a live region of its own, `aria-live="polite"` with `aria-atomic`, mounted while it is empty, so it is announced when a sync ends with it. That is what `role="status"` implies; the panel keeps one `role="status"`, the sync message.

Languages (ADR-019):

- Shown once `synced_at` is set, under the caption «Доля кода в байтах, по данным GitHub».
- A share is a language's bytes over the sum of all the repository's languages, as a whole percent (`Math.round`); a share under 0.5 % reads «<1 %». Shares are not adjusted to add up to 100.
- The first 6 languages in the API's order (bytes descending) are chips «Python 62 %» (status badge style, `text` on `panel`, a non-breaking space before «%»). The rest, when there are any, make one chip «Другие — N %» from their summed bytes, with the same rounding, in `text-muted` on `frame`.
- No bars, scales, levels or byte totals.
- A sum of 0 bytes (the contract allows it) shows the names without shares.
- An empty list with `synced_at` set: «GitHub не нашёл в репозитории кода на известных ему языках.» in the dashed box of the placeholder.
- With `synced_at` `null` the existing placeholder stays, whatever the status.
- Language names from GitHub are text; a long name wraps.
- The shares are computed in `src/lib/github-languages.ts`. The public cards use the same function with 3 chips instead of 6, in their own chip style ("GitHub on public cards").

The data date:

- «Данные GitHub от 01.11.2026, 12:30» from `synced_at`: the date and time in the user's time zone (`ru-RU`). It is shown whenever `synced_at` is set, also with `FAILED`, so old data reads as old (ADR-019). «Обновлён: {date}» stays the date of the last push (`pushed_at`).
- `sync.last_success_at` holds the same time; the panel reads `synced_at`.
- The public cards show the same `synced_at` as a day in UTC, without the time ("GitHub on public cards").

«Обновить данные» (accent):

- Sends `POST /integrations/github/repositories/{github_repo_id}/sync`. Meanwhile it reads «Ставим в очередь…», and every block and form button is disabled, as for a link.
- Disabled, with its usual text, while the status is `QUEUED` or `SYNCING`, while any form or block request runs, and while a countdown of a message runs.
- The pause: when the status is not `QUEUED` or `SYNCING` and `next_manual_sync_at` is later than the browser's clock, the button is disabled and reads «Обновить через {N} мин» (`N` rounded up, at least 1, recounted every second like the message countdown), and «Данные одного репозитория можно обновлять раз в 10 минут.» is shown under «Заменить репозиторий» and «Отвязать». When the pause ends the button becomes active without a request.
- The pause belongs to the repository and is shared by everyone who linked it, so its texts never say «вы». A link or an import starts it: right after them the button waits up to 10 minutes.
- It works for an unavailable repository and a `NONE` relation too: a sync is how they recover (ADR-018).
- 202 `GitHubSync`: the block takes it as `github.sync` when the panel still shows the same `github_repo_id`, and polls while it is `QUEUED` or `SYNCING`. The focus moves to the panel, since the button becomes disabled.
- Errors are shown under the button, as the table below says. A 404 `NOT_FOUND` means none of the user's projects links the repository any longer (unlinked or replaced elsewhere): the form reads `GET /projects/{id}` once and takes only `github`, without a message; a 404 of that read is «Проект не найден».

Polling (ADR-018):

- While `sync.status` is `QUEUED` or `SYNCING`, the form reads `GET /projects/{id}` every 5 seconds and takes only `github`, as for a link, so unsaved edits stay. The first read comes 5 seconds after the status became active: when the form opens, after a link or import, after «Обновить данные».
- It stops at any other status, when the repository is unlinked or replaced, and when the form unmounts.
- A hidden tab sends nothing; when the tab is shown again, one read goes out at once.
- At most 24 reads in a row (2 minutes of a visible tab). Three failed reads in a row (network or a 5xx) also stop it. «Проверить снова» sends one read at once and starts a new series if the status is still active.
- 401 goes to `/login`; a 404 is «Проект не найден». Other failed reads show nothing until the third.
- A form or block request cancels a read in flight. An answer is taken only for the same `github_repo_id` and when no form or block request has started since it was sent, so a late answer cannot bring back an unlinked repository.

«Мои проекты» and `/me/repositories` show no sync state: `ProjectSummary.github` and the repository list carry none (contract).

#### GitHub label on «Мои проекты»

A card of a project whose `github` (in `GET /projects`, backend step 5.6) is not `null` shows a line under the technologies: the «GitHub» chip (`label` text on `bg`), which is the source mark, and `full_name` (the link rule above). The label says only which repository is linked: no relation, languages or sync state, and it is shown in every project state. `github: null` hides the line. The project list is not reloaded for the label; link and unlink elsewhere change it on the next load of «Мои проекты».

#### Responses → message → user action

The code in small type above a message in `github-states.png` is a mockup annotation and is not shown to the user. Titles are `caps-label`, texts Tektur.

| Code | Can come from | Title and text | User action |
|---|---|---|---|
| 401 | any, also a polling read | — | Redirect to `/login` |
| 409 `GITHUB_LOGIN_OUTDATED` | list | «Логин на GitHub изменился». «Мы запомнили ваш прежний логин и не видим ваши репозитории. Войдите заново, и мы обновим его.» | «Войти через GitHub»: a full-page navigation to the login URL, as on `/login` |
| 422 `GITHUB_RELATION_NOT_FOUND` | link, import | «Связь с репозиторием не найдена». «Вы не владелец этого репозитория и не входите в список его контрибьюторов по данным GitHub. Если вы делали коммиты с личной почтой, GitHub может вас не показывать.» | None; another repository can be chosen |
| 409 `GITHUB_REPOSITORY_ALREADY_LINKED` | link, import | «Репозиторий уже привязан». «Этот репозиторий уже привязан к вашему проекту «{title}». Один репозиторий можно привязать только к одному вашему проекту.» `{title}` is found by `details.project_id` in `GET /projects`; when it is not there, «к другому вашему проекту» | «Открыть проект» → `/me/projects/{details.project_id}`. On the list page the card is marked «Привязан» locally |
| 422 `GITHUB_REPOSITORY_NOT_FOUND` | link | «Репозиторий не найден». «Такого публичного репозитория нет. Проверьте написание: «владелец/репозиторий». Приватные репозитории мы не читаем.» | Fix the name and repeat |
| 404 `NOT_FOUND` | import (the repository) | «Репозиторий не найден». «GitHub больше не отдаёт этот репозиторий: его могли удалить или сделать приватным. Список обновится в течение 5 минут.» | None |
| 404 `NOT_FOUND` | link, unlink, a polling read (the project) | As in the project form: «Проект не найден» | Link «Мои проекты» |
| 404 `NOT_FOUND` | sync (the repository is no longer linked) | None: the form reads the project once and takes only `github` | — |
| 422 `VALIDATION_ERROR` | link (`full_name`); list (`page`) | Link: «Формат: владелец/репозиторий.» under the input. List: not reachable from the page (the page number is checked first); handled as page 1 | Fix the name |
| 409 `PROJECT_LIMIT_REACHED` | import | «Достигнут лимит проектов». «У вас уже {details.limit} проектов, это максимум. Удалите ненужный проект, чтобы импортировать репозиторий.» | «К моим проектам» → `/me/projects` |
| 429 `GITHUB_SYNC_TOO_SOON` | sync | «Данные недавно обновлялись». «Этот репозиторий недавно синхронизировался. Обновить можно через {N} мин.» | Same countdown |
| 429 `GITHUB_USER_LIMIT_REACHED` | list, link, import, sync | «Слишком много обращений к GitHub». «Вы много раз обращались к GitHub за последний час. Повторите через {N} мин.» | Disabled «Повторить через {N} мин» with a countdown, then «Повторить» |
| 503 `GITHUB_RATE_LIMITED` | list, link, import | «GitHub ограничил запросы платформы». «Это не ваша вина: лимит общий на всех. Попробуйте через {N} мин.» | Same countdown |
| 502 `GITHUB_UNAVAILABLE` | list, link, import | «GitHub сейчас недоступен». «Не получилось связаться с GitHub. Повторите чуть позже.» | «Повторить» repeats the same request once per click; there is no automatic retry |
| 500 `INTERNAL_ERROR` | any | As in the cabinet: «Что-то пошло не так. Попробуйте ещё раз.» and «Код запроса: <request_id>» | Repeat the action |
| Network error, unreadable 403 `CSRF_ORIGIN_INVALID` | any | As in the cabinet: «Не удалось связаться с сервером.» | Repeat the action |

The countdown for 429 and 503 (a sync can get only the two 429s: it does not call GitHub):

- `{N}` comes from `details.retry_after_seconds`, rounded up to whole minutes, at least 1. The `Retry-After` header cannot be read by the browser: CORS exposes only `X-Request-ID` (contract, Principles).
- While it runs, the action that failed stays disabled: list paging for the list, import and link buttons for an action, «Обновить данные» (with its usual text) for a sync.
- When it ends, the button becomes «Повторить». For the list it reloads the page. For an action it closes the message, and the user repeats the action.
- Without a valid `details.retry_after_seconds` the text ends with «Попробуйте позже.» and «Повторить» is active at once.

### Analytics — `/me/analytics` (7.4)

Mockup `analytics.png` (7.4a). Data: `GET /api/v1/analytics/profile?days=N` for the screen, `GET /api/v1/analytics/projects/{id}?days=N` for the opened project (step 7.2, ADR-0029); the header through `useAccount`, whose `GET /profile` also gives the profile status for the empty state. Every number is a sum of events, not people, and the screen says so.

The cabinet tabs become «Профиль», «Проекты», «Аналитика»; the analytics tab is the third.

Blocks, top to bottom, in one panel:

| Block | Data | Notes |
|---|---|---|
| Title and period | `period` | «Аналитика»; under it «С {start} по {end} · дни по UTC, сегодня включительно» (`ДД.ММ.ГГГГ`). On the right a group «Период» of three buttons «7 дней», «30 дней», «90 дней» (`aria-pressed`, the active one accent), 30 by default. The period lives in the screen's state, not in the address. |
| «Воронка» | `totals` | Four tiles on `bg`, numbers in Press Start 2P: «Профиль» = `profile_views` («просмотров профиля»), «Проекты» = `project_views` («просмотров проектов»), «Демо и GitHub» = `demo_clicks + github_clicks` («демо N · GitHub N»), «Контакты» = `contact_clicks` («кликов по контактам»), joined by «›». No percentages between stages and no colour that grades a number. Under it: «Это суммы событий за период, а не люди: одно обновление страницы — ещё один просмотр. Ваши собственные просмотры не считаются. Посетители с блокировщиками не видны, поэтому цифры — нижняя граница.» |
| «Проекты» | `projects` | A table: «Проект», «Статус», «Просмотры», «Демо», «GitHub», and a button «По дням ▾» per row. Every own project in the API order (the order of «Мои проекты»), never sorted by a number: a sort would be a ranking. Zeros in `text-muted`. The status badge and its text are those of «Мои проекты» (`project-texts.tsx`). Under the table: «Счётчики идут только у опубликованных и видимых проектов. Порядок — как в «Мои проекты».» and «GitHub в воронке — это ещё и кнопка «GitHub» в шапке профиля, поэтому сумма может быть больше, чем по проектам.» |
| Project by day | `daily`, `totals` | «По дням» opens a panel under its row (`aria-expanded`, the button «По дням ▴» accent); one project at a time, a second click closes it. The panel: «{title} · просмотры по дням», «дни по UTC», the chart, «За N дней: X просмотров, Y по демо, Z по GitHub», and a `<details>` «Таблица по дням» with «День», «Просмотры», «Демо», «GitHub» for every day, oldest first. |

The chart:

- one series, `project_views` per day; the clicks are numbers under it and in the table, never a second scale;
- bars in `accent` on a `bg` box: on `panel` the accent has a contrast of 2.83:1, under the 3:1 a mark needs; the hovered or focused bar is `label`;
- bars anchored to the baseline with 4px rounded tops and a 2px gap (1px at 90 days); a day with zero is a 2px `frame` line on the axis, so the day is still there;
- the Y axis shows 0 and the period's maximum, with one dashed `frame` line at the maximum; the X axis shows the first, the middle and the last day as `ДД.ММ`;
- no legend: the heading names the series;
- hover or focus on a bar shows a tooltip «ДД.ММ · N просмотров», «демо N · GitHub N» above the bar; the bars are not tab stops one by one, the table is the keyboard and screen reader version;
- at 375 px the 90 bars are narrow; the table carries the exact numbers.

Dates are UTC days as the API returns them, never converted to the browser's time zone: otherwise "today" would not match the counter's day.

Under 640 px the funnel is a 2×2 grid without «›», and the table becomes rows: the title, the badge, the three numbers with their labels, «По дням».

States and errors:

| Case | Shown as |
|---|---|
| Loading | `LoadingPanel` |
| 401 from any call | Redirect to `/login` |
| Load fails | `LoadErrorPanel` with «Повторить» |
| Period change | The numbers stay until the answer; the period buttons and «По дням» are disabled; the previous request is aborted, so an older answer never replaces a newer one. An opened project is loaded again for the new period |
| All zeros | The funnel and the table stay, with zeros; above the table «За этот период событий нет.» and, for a `PRIVATE` profile, «Профиль скрыт — счётчики появятся после публикации.» with a link «Открыть профиль» to `/me`; for a published one «Счётчики растут, когда профиль открывают посетители.» |
| No projects | Instead of the table «Проектов пока нет.» and a link «Мои проекты» |
| Project 404 (deleted meanwhile) | Inside its panel «Проект не найден — возможно, он удалён.»; the table stays |
| Project load fails | Inside its panel the request error and «Повторить» |

### Sign-in — `/login`

Blocks (mockup `login.png`):

- the «DEV.PROFILE» mark above the panel;
- the default pixel avatar;
- the title «Новая игра» (Press Start 2P, shown in uppercase);
- «Профиль разработчика с проектами и данными из GitHub. Войдите, чтобы создать свой.»;
- the error block, when there is one;
- the button «Войти через GitHub» (Tektur, normal case, large);
- the note «Мы читаем только публичные данные GitHub: логин, аватар, email, если он открыт, и публичные репозитории, которые вы привяжете к проектам. Доступа к приватным репозиториям нет.» The mockup omits the email; the backend stores a public email (ADR-012), so the text names it. The repositories are named because Phase 5 reads them with the app's credentials, without any access granted by the user (ADR-016). The code has used this text since F-GH1.3.

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
| `RATE_LIMITED` | «Слишком много попыток входа. Подождите минуту и попробуйте снова.» |
| `INTERNAL_ERROR` | «Что-то пошло не так на нашей стороне. Попробуйте позже.» |

| Any other value, including an empty one | «Не удалось войти. Попробуйте ещё раз.» |

No `error` parameter: no error block. The texts come from this table only; the value of `error` is never shown.

Logout (from the cabinet): `POST /api/v1/auth/logout` → 204 → redirect to `/login`. A failure keeps the user on the page and shows the network or generic error text from the cabinet table.

The note ends with «Подробнее — в политике данных.», a link to `/privacy` (9.7b).

### «Политика данных» — `/privacy` (9.7b)

A static server page: «DEV.PROFILE» (a link to `/`), the title «Политика данных» (Press Start 2P), then six sections, each a heading with the yellow marker and a panel: «Что мы храним», «Что видят другие», «Технические данные», «Кому передаются данные», «Сроки и удаление», «Оператор и обращения». The text states only what the system does (ADR-0020, ADR-0026, ADR-0028); a change of behavior changes the page in the same PR.

The text is a draft. The operator and the address for requests are placeholders in the page (`OPERATOR`, `CONTACT`): the owner fills them in, and a lawyer checks the text before the launch (9.8).

Every page ends with a footer link «Политика данных» (the root layout).

### 404

Two screens with the layout of `not-found.png`: «DEV.PROFILE» above a panel with a large «404», a title (Press Start 2P), one line of text and buttons (Tektur, normal case, as all buttons). HTTP status 404.

| Case | Title | Text | Buttons |
|---|---|---|---|
| `/u/{slug}`: API 404 or malformed slug | «Профиль не найден» | «Такого профиля нет или он не опубликован. Проверьте ссылку.» | «На главную» (`/`), «Создать свой» (`/login`) |
| Any other unknown route | «Страница не найдена» | «Проверьте ссылку.» | «На главную» (`/`) |

The profile text names both cases together, so it never says which one applies: the API deliberately returns the same 404 for private, missing and malformed slugs (ADR-013).

## Mockups

Mockups are added manually to `docs/frontend/mockups/`. From 4.4 they can also be drawn as HTML in `mockups/src/` (shared `mockup.css`, local font files) and rendered with `node render.mjs <name>` (`CHROME` = a Chrome or headless-shell binary); the PNG stays the reference:

- `public-profile.png`
- `cabinet.png`
- `login.png`
- `not-found.png`
- `my-projects.png` (F5)
- `project-form.png` (F5; the version with the «Репозиторий GitHub» block is for F-GH1)
- `repositories.png` (F-GH1)
- `github-states.png` (F-GH1; the 429 `GITHUB_SYNC_TOO_SOON` card of F-GH1.5 is not in it yet, so the table above is the reference)
- `repository-sync.png` (F-GH1.5: the sync states of the form block and the rules card)
- `public-cards.png` (F-GH2: the GitHub block on public cards and rows; six featured cards only to show the states)
- `profile-contacts.png` (C.2: the contacts section of the public page, the block of the profile form and the rules card)
- `project-page.png` (4.4, for 4.6): the public project page at 1280 and 375 px in four states — demo with screenshots, demo without screenshots, screenshots without a demo, neither (texts and GitHub only); the project 404; a profile card and row with the title as a link
- `project-media.png` (4.4, for 4.5): the «Демо и скриншоты» block — a new project, empty, 1 screenshot with a demo link («Превью демо»), 6 of 6, uploading, an upload error, a `demo_url` error, the delete dialog; the top panel's link and note; a rules card
- `analytics.png` (7.4a, for 7.4b): the analytics screen at 1280 px with 30 days and an opened project (the tooltip on one bar), at 375 px with 7 days, the chart at 90 days at 1280 and 375 px with the day table open, no events with a hidden profile, loading, a load error and a deleted project; a rules card

The F-GH1 version of «Мои проекты» (with «Импорт из GitHub» and the GitHub label) is in the working tree as `my-projects.png.png`; the mockup owner decides whether it replaces `my-projects.png`.

The project blocks of the public page follow `public-profile.png`, except the card label: the image shows «Избранное N», the guide says «Главный N». The profile-level «Данные GitHub» block of that image is not built; the GitHub block of the cards follows `public-cards.png`.

If a mockup and this guide disagree, raise the conflict instead of silently picking one.
