# Сценарии использования

Живой документ: описывает текущий `main`. Обновляется в том же PR, что меняет поведение.

Группы: **A** — Аккаунт, **B** — Профиль, **C** — Проекты, **D** — GitHub, **E** — Публичный просмотр.

---

## A. Аккаунт и сессии

### UC-A1. Вход через GitHub OAuth

- **Актор:** неаутентифицированный пользователь. **С релиза:** v1.
- **Поток:** открывает `GET /api/v1/auth/github/login` → редирект на GitHub OAuth → GitHub редиректит на `GET /api/v1/auth/github/callback?code=…` → сервер обменивает code на access token → получает `github_user_id`, `github_login`, email → upsert `users` и `github_accounts` → создаёт `auth_sessions`, пишет `token_hash` → устанавливает HttpOnly cookie → редирект на `/me`.
- **Отклонения:** GitHub вернул ошибку → редирект на `/auth/error`; недопустимый `state` → `400`.
- **ADR:** [ADR-0012](release/v1/adr/0012-github-oauth-only.md).

### UC-A2. Получение текущего пользователя

- **Актор:** аутентифицированный пользователь. **С релиза:** v1.
- **Поток:** `GET /api/v1/auth/me` → сервер читает cookie → проверяет `token_hash` в `auth_sessions` → возвращает `{id, github_login, email}`.
- **Отклонения:** нет cookie или сессия не найдена → `401 UNAUTHORIZED`.

### UC-A3. Выход

- **Актор:** аутентифицированный пользователь. **С релиза:** v1.
- **Поток:** `POST /api/v1/auth/logout` → сервер удаляет строку из `auth_sessions` → очищает cookie → `200`.
- **Отклонения:** нет активной сессии → `200` (идемпотентно).

---

## B. Профиль

### UC-B1. Редактирование профиля

- **Актор:** аутентифицированный владелец профиля. **С релиза:** v1.
- **Поток:** `PATCH /api/v1/me/profile` с JSON-телом → Origin-проверка → валидация полей → обновление только переданных полей → `200` с обновлённым профилем.
- **Отклонения:** недопустимый Origin → `403 CSRF_VALIDATION_FAILED`; невалидные поля → `422 VALIDATION_ERROR`; не аутентифицирован → `401`.
- **ADR:** [ADR-0013](release/v1/adr/0013-profile-patch-origin-check.md).

### UC-B2. Публикация профиля

- **Актор:** аутентифицированный владелец профиля. **С релиза:** v1.
- **Поток:** `POST /api/v1/me/profile/publish` → проверяет наличие `display_name` и `headline` → устанавливает `status = PUBLISHED` → `200`.
- **Отклонения:** профиль неполный → `422 PROFILE_INCOMPLETE`; уже опубликован → `200` (идемпотентно).
- **ADR:** [ADR-0005](release/v1/adr/0005-project-lifecycle-visibility.md).

### UC-B3. Снятие профиля с публикации

- **Актор:** аутентифицированный владелец профиля. **С релиза:** v1.
- **Поток:** `POST /api/v1/me/profile/unpublish` → устанавливает `status = PRIVATE` → `200`.
- **Отклонения:** уже `PRIVATE` → `200` (идемпотентно).

---

## C. Проекты

### UC-C1. Создание проекта

- **Актор:** аутентифицированный пользователь. **С релиза:** v1.
- **Поток:** `POST /api/v1/me/projects` с JSON-телом → проверка лимита 50 проектов → создаёт `DRAFT + PRIVATE` → `201` с проектом.
- **Отклонения:** превышен лимит → `422 PROJECTS_LIMIT_REACHED`; невалидные поля → `422`.

### UC-C2. Редактирование проекта

- **Актор:** владелец проекта. **С релиза:** v1.
- **Поток:** `PATCH /api/v1/me/projects/{id}` → проверка ownership → Origin-проверка → обновление переданных полей → `200`.
- **Отклонения:** проект не найден или чужой → `404`; невалидные поля → `422`.

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
- **Поток:** `DELETE /api/v1/me/projects/{id}` → CASCADE удаляет связанные `project_technologies`, `featured_projects`, `project_repositories` → `204`.
- **Отклонения:** проект не найден или чужой → `404`.

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
- **Поток:** `GET /api/v1/profiles/{slug}` → проверяет `status = PUBLISHED` → возвращает публичный DTO: профиль, список проектов (`PUBLISHED + PUBLIC`), витрина, данные GitHub (если синхронизированы) — батчевым запросом без вызова GitHub API.
- **Отклонения:** профиль не найден или `PRIVATE` → `404 PROFILE_NOT_FOUND`.
- **ADR:** [ADR-0019](release/v1/adr/0019-public-github-on-cards.md), [ADR-0013](release/v1/adr/0013-profile-patch-origin-check.md).

### UC-E2. Данные GitHub на карточке проекта

- **Актор:** любой посетитель. **С релиза:** v1.
- **Поток:** объект `github` возвращается в составе `UC-E1`; содержит 10 полей (full_name, html_url, description, stars, forks, open_issues, is_fork, is_archived, languages, synced_at); равен `null` если нет привязки, синхронизация не завершена, репозиторий недоступен или привязка разорвана.
- **Отклонения:** `github = null` — нормальное состояние, UI обрабатывает молча (одна строка в лог на проект).
- **ADR:** [ADR-0019](release/v1/adr/0019-public-github-on-cards.md).
