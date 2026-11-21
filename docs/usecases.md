# Сценарии использования

Живой документ: описывает текущий `main`. Обновляется в том же PR, что меняет поведение.

Группы: **A** — Аккаунт, **B** — Профиль, **C** — Проекты, **D** — GitHub, **E** — Публичный просмотр.

---

## A. Аккаунт и сессии

### UC-A1. Вход через GitHub OAuth

- **Актор:** неаутентифицированный пользователь. **С релиза:** v1.
- **Поток:** открывает `GET /api/v1/auth/github/login` → редирект на GitHub OAuth → GitHub редиректит на `GET /api/v1/auth/github/callback?code=…` → сервер обменивает code на access token → получает `github_user_id`, `github_login`, email → upsert `users` и `github_accounts` → удаляет просроченные `auth_sessions` всех пользователей → создаёт `auth_sessions`, пишет `token_hash` → устанавливает HttpOnly cookie → редирект на `/me`.
- **Отклонения:** любая ошибка callback — редирект на `/login?error=<CODE>` (`ACCESS_DENIED`, `INVALID_STATE`, `MISSING_CODE`, `OAUTH_CODE_INVALID`, `GITHUB_UNAVAILABLE`, `RATE_LIMITED`, `INTERNAL_ERROR`), экран входа показывает текст по коду. Больше 20 запросов `login` и `callback` в минуту с одного IP → `RATE_LIMITED` («Слишком много попыток входа. Подождите минуту и попробуйте снова.»), `state` не выдаётся и не проверяется.
- **ADR:** [ADR-0012](release/v1/adr/0012-github-oauth-only.md), [ADR-0024](release/v1/adr/0024-rate-limit-in-process.md) — лимит.

### UC-A2. Получение текущего пользователя

- **Актор:** аутентифицированный пользователь. **С релиза:** v1.
- **Поток:** `GET /api/v1/auth/me` → сервер читает cookie → проверяет `token_hash` в `auth_sessions` → возвращает `{id, github_login, email}`.
- **Отклонения:** нет cookie или сессия не найдена → `401 UNAUTHORIZED`.

### UC-A3. Выход

- **Актор:** аутентифицированный пользователь. **С релиза:** v1.
- **Поток:** `POST /api/v1/auth/logout` → сервер удаляет строку из `auth_sessions` → очищает cookie → `204`.
- **Отклонения:** нет активной сессии → `204` (идемпотентно).

### UC-A4. Удаление аккаунта

- **Актор:** аутентифицированный пользователь. **С релиза:** v1.
- **Поток:** кабинет → «Удалить аккаунт» → в диалоге ввести свой логин → «Удалить навсегда» → `DELETE /api/v1/auth/me` → блокировка профиля → удаление `users`; каскадом уходят профиль, контакты, проекты, скриншоты, технологии проектов, витрина, привязки репозиториев, сессии и `github_accounts` → коммит → удаление файлов скриншотов из тома `media` → строка лога `account deleted user_id=<uuid>` → очистка cookie → `204` → переход на `/login`. Общие строки `github_repositories` остаются. Повторный вход через GitHub создаёт новый пустой аккаунт.
- **Отклонения:** нет сессии → `401 UNAUTHORIZED`; чужой Origin → `403 CSRF_ORIGIN_INVALID`. Файл, который не удалось удалить, пишется в лог и убирается `app.media.sweep`.
- **ADR:** [ADR-0028](release/v1/adr/0028-account-deletion-hard-and-immediate.md).

---

## B. Профиль

### UC-B1. Редактирование профиля

- **Актор:** аутентифицированный владелец профиля. **С релиза:** v1.
- **Поток:** `PATCH /api/v1/profile` с JSON-телом → Origin-проверка → валидация полей → обновление только переданных полей → `200` с обновлённым профилем.
- **Отклонения:** недопустимый Origin → `403 CSRF_ORIGIN_INVALID`; невалидные поля → `422 VALIDATION_ERROR`; не аутентифицирован → `401`.
- **ADR:** [ADR-0013](release/v1/adr/0013-profile-patch-origin-check.md).

### UC-B2. Публикация профиля

- **Актор:** аутентифицированный владелец профиля. **С релиза:** v1.
- **Поток:** `POST /api/v1/profile/publish` → проверяет наличие `display_name` и `headline` → устанавливает `status = PUBLISHED` → `200`.
- **Отклонения:** профиль неполный → `422 PROFILE_INCOMPLETE`; уже опубликован → `200` (идемпотентно).
- **ADR:** [ADR-0005](release/v1/adr/0005-project-lifecycle-visibility.md).

### UC-B3. Снятие профиля с публикации

- **Актор:** аутентифицированный владелец профиля. **С релиза:** v1.
- **Поток:** `POST /api/v1/profile/unpublish` → устанавливает `status = PRIVATE` → `200`.
- **Отклонения:** уже `PRIVATE` → `200` (идемпотентно).

### UC-B4. Контакты профиля

- **Актор:** аутентифицированный владелец профиля. **С релиза:** v1 (бэкенд — C.1; кабинет — C.2).
- **Поток:** `PATCH /api/v1/profile` с `contacts: [{type, value, label}]` → Origin-проверка → нормализация каждого значения (`EMAIL`, `TELEGRAM`, `LINKEDIN`, `PHONE`, `OTHER` с названием) → под блокировкой профиля список заменяется целиком (`DELETE`, затем `INSERT`, `position` — по порядку) → `200` с `contacts: [{type, value, label, url}]`, `url` построен сервером. Поле отсутствует — список не меняется; `[]` — очищает. `profiles.updated_at` меняется, только если нормализованный список другой.
- **Отклонения:** `422 VALIDATION_ERROR` — `null` вместо списка; больше 7 контактов (`too_long`), больше 3 `OTHER` (`too_many_other_contacts`), повтор стандартного типа (`duplicate_contact_type`) — `loc` `["body","contacts"]`; неверное значение (`invalid_email`, `invalid_telegram`, `invalid_linkedin`, `invalid_phone`, `invalid_url`, `string_too_short`, `string_too_long`) или название (`missing`, `label_not_allowed`) — `loc` `["body","contacts",i,"value"|"label"]`; присланный `url` — `extra_forbidden`. Введённые значения в ответ не попадают. Недопустимый Origin → `403 CSRF_ORIGIN_INVALID`.
- **Кабинет:** блок «Контакты» в форме профиля, общая «Сохранить». Поля «Email», «Telegram», «LinkedIn», «Телефон» и до трёх строк «+ Другие способы связи» («Название», «Ссылка», «Удалить»). Пустые поля и пустые строки не отправляются; список уходит, только если изменился. После сохранения поля показывают значения из ответа и подпись «Сохранено как: …». Ошибка значения — под своим полем (например, «Укажите номер с плюсом, например +79991234567.»); ошибка списка — общее сообщение с кодом запроса.
- **ADR:** [ADR-0020](release/v1/adr/0020-contacts-separate-table.md).

---

## C. Проекты

### UC-C1. Создание проекта

- **Актор:** аутентифицированный пользователь. **С релиза:** v1.
- **Поток:** `POST /api/v1/projects` с JSON-телом → проверка лимита 50 проектов → создаёт `DRAFT + PRIVATE` → `201` с проектом.
- **Отклонения:** превышен лимит → `422 PROJECTS_LIMIT_REACHED`; невалидные поля → `422`.

### UC-C2. Редактирование проекта

- **Актор:** владелец проекта. **С релиза:** v1.
- **Поток:** `PATCH /api/v1/projects/{id}` → проверка ownership → Origin-проверка → обновление переданных полей → `200`. Ссылка на демо `demo_url` задаётся здесь же, `null` её убирает; бэкенд по ней не ходит (ADR-0023).
- **Отклонения:** проект не найден или чужой → `404`; невалидные поля → `422`; `demo_url` не `http`/`https`, без точки в хосте, с логином или пробелами → `422 invalid_url`.

### UC-C3. Публикация проекта

- **Актор:** владелец проекта. **С релиза:** v1.
- **Поток:** `POST /api/v1/me/projects/{id}/publish` → проверяет наличие `title`, `summary`, `role`, `contribution` → `status = PUBLISHED`; `visibility` остаётся или меняется на `PUBLIC` по запросу → `200`.
- **Отклонения:** проект неполный → `422 PROJECT_INCOMPLETE`; недопустимый статус-переход → `422`.
- **ADR:** [ADR-0005](release/v1/adr/0005-project-lifecycle-visibility.md).

### UC-C4. Добавление проекта в витрину

- **Актор:** владелец профиля. **С релиза:** v1.
- **Поток:** `POST /api/v1/me/profile/featured` с `{project_id, position}` → проверяет, что проект `PUBLISHED + PUBLIC` → проверяет лимит 3 → добавляет строку в `featured_projects` → `200`.
- **Отклонения:** проект не `PUBLISHED + PUBLIC` → `422`; витрина полна → `422 FEATURED_LIMIT_REACHED`.
- **ADR:** [ADR-0015](release/v1/adr/0015-project-entities.md).

### UC-C5. Удаление проекта

- **Актор:** владелец проекта. **С релиза:** v1.
- **Поток:** `DELETE /api/v1/projects/{id}` → CASCADE удаляет связанные `project_technologies`, `featured_projects`, `project_repositories`, `project_screenshots`, счётчики аналитики проекта (`analytics_daily_counts`) → после коммита удаляются файлы скриншотов → `204`.
- **Отклонения:** проект не найден или чужой → `404`.

### UC-C6. Скриншоты проекта

- **Актор:** владелец проекта. **С релиза:** v1.
- **Поток:** `POST /api/v1/projects/{id}/screenshots` (`multipart/form-data`: `file`, необязательная `caption`) → JPEG, PNG или WebP до 5 МБ перекодируется в WebP (длинная сторона до 2560 px, без EXIF) → файл в томе `media`, строка в `project_screenshots` в конце списка → `201` со списком скриншотов. Подпись — `PATCH …/screenshots/{screenshot_id}`, удаление — `DELETE …/screenshots/{screenshot_id}` (файл удаляется после коммита), порядок — `POST …/screenshots/reorder` со всем набором. Скриншоты приходят в `screenshots` ответа проекта; файл открывается по `/media/…`.
- **Отклонения:** проект или скриншот не найден или чужой → `404`; седьмой скриншот → `409 SCREENSHOT_LIMIT_REACHED`; не картинка или другой формат → `422 invalid_image`; больше 5 МБ → `422 image_too_large`; больше 40 Мп → `422 too_many_pixels`; набор в перестановке не совпадает с текущим → `409 SCREENSHOT_ORDER_MISMATCH`.
- **ADR:** [ADR-0022](release/v1/adr/0022-media-on-host-volume.md).

---

## D. GitHub

### UC-D1. Список репозиториев

- **Актор:** аутентифицированный пользователь. **С релиза:** v1.
- **Поток:** `GET /api/v1/integrations/github/repositories?page=1` → запрос к GitHub API с кредами приложения → возвращает список с пагинацией; результат кэшируется в памяти на время сессии API.
- **Отклонения:** GitHub API недоступен → `502`; исчерпан rate limit → `429 GITHUB_RATE_LIMIT`.
- **ADR:** [ADR-0016](release/v1/adr/0016-github-public-only.md).

### UC-D2. Привязка репозитория к проекту

- **Актор:** владелец проекта. **С релиза:** v1.
- **Поток:** `POST /api/v1/me/projects/{id}/repository` с `{full_name}` → проверяет, что репозиторий не привязан к другому проекту пользователя → upsert `github_repositories` → создаёт `project_repositories` → создаёт `github_sync_jobs` → `200`.
- **Отклонения:** репозиторий уже привязан к другому проекту → `409 REPOSITORY_ALREADY_LINKED`; `full_name` не существует на GitHub → `404`.
- **ADR:** [ADR-0017](release/v1/adr/0017-repository-linking.md).

### UC-D3. Импорт репозитория как проекта

- **Актор:** аутентифицированный пользователь. **С релиза:** v1.
- **Поток:** `POST /api/v1/integrations/github/repositories/import` с `{github_repo_id}` → в одной транзакции: создаёт `DRAFT + PRIVATE` проект, upsert `github_repositories`, создаёт `project_repositories`, создаёт `github_sync_jobs` → `201` с проектом.
- **Отклонения:** превышен лимит проектов → `422`; репозиторий уже привязан → `409`.
- **ADR:** [ADR-0017](release/v1/adr/0017-repository-linking.md).

### UC-D4. Ручная синхронизация репозитория

- **Актор:** владелец привязанного проекта. **С релиза:** v1.
- **Поток:** `POST /api/v1/integrations/github/repositories/{id}/sync` → проверяет, что последняя синхронизация была не менее 10 минут назад → создаёт `github_sync_jobs` или отвечает `200` с текущей джобой → воркер забирает джобу через SKIP LOCKED → `metadata` и `languages` обновляются в `github_sync_category_status`.
- **Отклонения:** пауза ещё активна → `429 SYNC_TOO_SOON`; нет привязки → `404`.
- **ADR:** [ADR-0018](release/v1/adr/0018-github-sync-v1.md).

### UC-D5. Отвязка репозитория

- **Актор:** владелец проекта. **С релиза:** v1.
- **Поток:** `DELETE /api/v1/me/projects/{id}/repository` → удаляет строку из `project_repositories` → строка `github_repositories` остаётся → `204`.
- **Отклонения:** нет привязки → `404`.

---

## E. Публичный просмотр

### UC-E1. Просмотр публичного профиля

- **Актор:** любой посетитель. **С релиза:** v1.
- **Поток:** `GET /api/v1/public/profiles/{slug}` → проверяет `status = PUBLISHED` → возвращает публичный DTO: профиль, контакты (`EMAIL` и `PHONE` — без `value` и `url`), список проектов (`PUBLISHED + PUBLIC`), витрина, данные GitHub (если синхронизированы) — батчевыми запросами без вызова GitHub API.
- **Отклонения:** профиль не найден, `PRIVATE` или slug некорректный → `404 NOT_FOUND`, одинаковый для всех случаев.
- **ADR:** [ADR-0019](release/v1/adr/0019-public-github-on-cards.md), [ADR-0013](release/v1/adr/0013-profile-patch-origin-check.md), [ADR-0020](release/v1/adr/0020-contacts-separate-table.md).

### UC-E2. Данные GitHub на карточке проекта

- **Актор:** любой посетитель. **С релиза:** v1.
- **Поток:** объект `github` возвращается в составе `UC-E1`; содержит 10 полей (`full_name`, `html_url`, `description`, `languages`, `pushed_at`, `is_fork`, `parent_full_name`, `is_archived`, `relation`, `synced_at`); равен `null` если нет привязки, синхронизация не завершена, репозиторий недоступен или привязка разорвана.
- **Отклонения:** `github = null` — нормальное состояние, UI обрабатывает молча (одна строка в лог на проект).
- **ADR:** [ADR-0019](release/v1/adr/0019-public-github-on-cards.md).

### UC-E3. Email или телефон по клику

- **Актор:** любой посетитель. **С релиза:** v1 (бэкенд — C.1; кнопки «Показать email» и «Показать телефон» — C.2).
- **Поток:** `GET /api/v1/public/profiles/{slug}/contacts?type=EMAIL|PHONE` без сессии → профиль `PUBLISHED` и контакт этого типа есть → `200 {type, value, url}` с `Cache-Control: no-store`.
- **Отклонения:** профиль не найден, `PRIVATE`, slug некорректный или контакта нет → тот же `404 NOT_FOUND`, что у UC-E1; другой `type` или его нет → `422 VALIDATION_ERROR`. Больше 10 запросов в минуту или 50 в час с одного IP, `404` тоже считаются → `429 RATE_LIMITED` с `Retry-After`; на странице — тот же текст ошибки и «Повторить».
- **Страница:** в секции «Контакты» кнопка «Показать email» или «Показать телефон» → «Загрузка…» → ссылка `mailto:` или `tel:`. Любая ошибка, включая ответ другого типа или с другой ссылкой, — «Не удалось получить email.» / «Не удалось получить телефон.» и «Повторить». Значения нет в HTML страницы и в JSON профиля.
- **ADR:** [ADR-0020](release/v1/adr/0020-contacts-separate-table.md), [ADR-0024](release/v1/adr/0024-rate-limit-in-process.md) — лимит.

### UC-E4. Просмотр публичной страницы проекта

- **Актор:** любой посетитель. **С релиза:** v1 (бэкенд — 4.3; страница `/u/{slug}/projects/{id}` — 4.6).
- **Поток:** `GET /api/v1/public/profiles/{slug}/projects/{id}` без сессии → профиль `PUBLISHED`, проект его владельца в `PUBLISHED + PUBLIC` → `200`: поля проекта (с `description`, `problem`, `results`, `contribution`), технологии, `demo_url`, скриншоты по порядку (`url`, `caption`, `width`, `height` — без id), тот же объект `github`, что на карточке (UC-E2), и `owner` (`slug`, `display_name`, `avatar_url`) — пятью запросами без вызова GitHub API.
- **Отклонения:** профиль не найден или `PRIVATE`, проект другого пользователя, черновик, архивный или скрытый проект, некорректный id → тот же `404 NOT_FOUND`, что у UC-E1.
- **ADR:** [ADR-0019](release/v1/adr/0019-public-github-on-cards.md), [ADR-0022](release/v1/adr/0022-media-on-host-volume.md), [ADR-0023](release/v1/adr/0023-demo-link-without-iframe.md).

### UC-E5. Учёт просмотра или клика на публичной странице

- **Актор:** браузер посетителя. **С релиза:** V1.1 (бэкенд — 7.1; отправка со страниц — 7.3).
- **Когда браузер шлёт событие:** `PROFILE_VIEW` и `PROJECT_VIEW` — после монтирования страницы `/u/{slug}` и `/u/{slug}/projects/{id}` (не при SSR); `DEMO_CLICK` — «Открыть демо ↗»; `GITHUB_CLICK` — кнопка «GitHub» в шапке профиля (без проекта) и ссылка на репозиторий в блоке GitHub карточки, строки или страницы проекта; `CONTACT_CLICK` — ссылки Telegram, LinkedIn и другие и кнопки «Показать email» / «Показать телефон» (раскрытая ссылка `mailto:`/`tel:` второй раз не считается). Считаются левый клик и средняя кнопка. Запрос — `fetch` с `keepalive`, переход его не ждёт, ошибка не показывается. Якоря «Проекты», «Контакты», ссылки на страницу проекта и скриншоты не считаются.
- **Поток:** `POST /api/v1/analytics/events` с `{type, slug, project_id}` → профиль `PUBLISHED`, проект (если есть) его владельца в `PUBLISHED + PUBLIC`, сессия не владельца → `+1` к счётчику типа за сегодняшний день в UTC → `202` без тела. IP, User-Agent, referrer и cookie не сохраняются.
- **Отклонения:** профиль или проект не показан, `project_id` некорректный или не подходит к типу, сессия владельца → тот же `202`, событие не засчитано. Тело другой формы (неизвестный тип, лишнее поле) → `422 VALIDATION_ERROR`; без `Origin` фронтенда → `403 CSRF_ORIGIN_INVALID`; больше 60 событий в минуту с одного IP → `429 RATE_LIMITED` с `Retry-After`.
- **ADR:** [ADR-0029](release/v1/adr/0029-analytics-anonymous-daily-counters.md), [ADR-0024](release/v1/adr/0024-rate-limit-in-process.md) — лимит.

---

## F. Аналитика

### UC-F1. Аналитика профиля

- **Актор:** владелец профиля. **С релиза:** V1.1 (бэкенд — 7.2; экран — 7.4b).
- **Поток:** `GET /api/v1/analytics/profile?days=7|30|90` (по умолчанию 30) → `200`: `period` (`days`, `start`, `end` — дни UTC включительно, сегодня последний), `totals` (`profile_views`, `project_views`, `demo_clicks`, `github_clicks`, `contact_clicks`; `github_clicks` — ссылки на репозитории и на GitHub профиля) и `projects` — все свои проекты в порядке `GET /projects` (`id`, `title` — `null` у черновика без названия, `status`, `visibility`, `counts` с `project_views`, `demo_clicks`, `github_clicks`), без событий — нули. Это суммы событий, не посетители.
- **Экран:** `/me/analytics`, вкладка «Аналитика»: период «7 дней» / «30 дней» / «90 дней» (по умолчанию 30), воронка из четырёх сумм без процентов, проекты в порядке API с бейджем статуса, «По дням» раскрывает один проект (UC-F2) с графиком просмотров и «Таблица по дням». Без событий — «За этот период событий нет.», у скрытого профиля — подсказка опубликовать.
- **Отклонения:** без сессии → `401 UNAUTHORIZED`; другое значение `days` → `422 VALIDATION_ERROR`.
- **ADR:** [ADR-0029](release/v1/adr/0029-analytics-anonymous-daily-counters.md).

### UC-F2. Аналитика проекта по дням

- **Актор:** владелец проекта. **С релиза:** V1.1 (бэкенд — 7.2; экран — 7.4b).
- **Поток:** `GET /api/v1/analytics/projects/{id}?days=7|30|90` (по умолчанию 30) → `200`: `period`, `totals` (`project_views`, `demo_clicks`, `github_clicks`) и `daily` — каждый день периода от старого к новому с теми же `counts`, дни без событий — нули. Проект в любом состоянии: счётчики черновика или скрытого проекта остаются с тех пор, когда он был виден.
- **Отклонения:** без сессии → `401 UNAUTHORIZED`; проект не найден, чужой или id некорректный → `404 NOT_FOUND`, как у `GET /projects/{id}`; другое значение `days` → `422 VALIDATION_ERROR`.
- **ADR:** [ADR-0029](release/v1/adr/0029-analytics-anonymous-daily-counters.md).
