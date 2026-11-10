# Схема базы данных V1

Документ синхронизируется с кодом в том же PR, что вносит миграцию.
Источник истины по решениям — ADR в `docs/release/v1/adr/`.

## Сущности

```text
-- Аккаунт
users
auth_sessions

-- Профиль
profiles
profile_contacts          (V1, шаг C.1–C.2)

-- Проекты
projects
technologies
project_technologies
featured_projects
project_screenshots       (Phase 4)
project_demos             (Phase 4)

-- GitHub
github_accounts
github_repositories
project_repositories
github_sync_jobs
github_sync_category_status
github_contributors       (отложено, не V1 — ADR-0010, ADR-0018)
github_commits            (отложено, не V1 — ADR-0010, ADR-0018)

-- Аналитика
analytics_events          (V1.1)
```

Нет отдельной сущности `PROJECT_CONTRIBUTION`: поля `role` и `contribution` — обычные текстовые поля `projects` (ADR-0004).
Нет `EXPERIENCE`, `EDUCATION`, `SKILL` — перенесено после V1.

V1 хранит только метаданные и языки репозиториев (ADR-0018). README, дерево файлов, контрибьюторы и коммиты отложены — не отклонены; когда вернутся, добавятся столбцы и таблицы без изменения архитектуры воркера.

## Связи

```text
users 1:1 profiles
users 1:N auth_sessions
users 1:1 github_accounts
users 1:N projects (owner)

profiles 0:N profile_contacts
profiles 1:N featured_projects (0..3)
projects 1:0/1 featured_projects

projects 1:N project_technologies
technologies 1:N project_technologies
projects 1:N project_screenshots      (Phase 4)
projects 0:1 project_demos            (Phase 4)
projects 0:1 project_repositories

github_repositories 1:N project_repositories  (разделяется между пользователями; ADR-0017)
github_repositories 1:N github_sync_jobs
github_repositories 1:N github_sync_category_status
github_repositories 1:N github_contributors    (отложено)
github_repositories 1:N github_commits         (отложено)
```

## Таблицы

### `users`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `github_user_id` | BIGINT UNIQUE NOT NULL | Числовой ID GitHub — основной идентификатор |
| `github_login` | TEXT NOT NULL | Login GitHub |
| `email` | TEXT | Nullable, не уникальный |
| `created_at` | TIMESTAMPTZ NOT NULL | |

Первичный идентификатор — `github_user_id` (стабилен, не меняется при переименовании). Подробнее: ADR-0012.

---

### `auth_sessions`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK → users | ON DELETE CASCADE |
| `token_hash` | TEXT UNIQUE NOT NULL | SHA-256 от сессионного токена |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `expires_at` | TIMESTAMPTZ NOT NULL | Контролируется приложением |

Cookie содержит случайный непрозрачный токен; в БД хранится только хэш. Выход — удаление строки. Подробнее: ADR-0012.

---

### `profiles`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID UNIQUE FK → users | ON DELETE CASCADE |
| `slug` | TEXT UNIQUE NOT NULL | Строчные буквы, цифры, дефисы; 3–39 символов; зарезервированные слова исключены |
| `status` | VARCHAR(20) NOT NULL | `PRIVATE` / `PUBLISHED` |
| `display_name` | TEXT | ≤ 100; nullable; trimmed, никогда пустой |
| `headline` | TEXT | ≤ 160; nullable |
| `bio` | TEXT | ≤ 2000; nullable |
| `location` | TEXT | ≤ 100; nullable |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | Обновляется приложением при каждом изменении |

CHECK `ck_profiles_published_complete`: публикация возможна только при наличии `display_name` и `headline`. Подробнее: ADR-0013, ADR-0005.

---

### `profile_contacts` (V1, шаг C.1)

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `profile_id` | UUID FK → profiles | ON DELETE CASCADE |
| `type` | ENUM | `email`, `phone`, `telegram`, `linkedin`, `website`, `github` |
| `value` | TEXT NOT NULL | |
| `is_public` | BOOLEAN NOT NULL DEFAULT true | |
| `display_order` | SMALLINT | |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

UNIQUE `(profile_id, type)` — один контакт каждого типа на профиль.

`email` и `phone` не включаются в публичный ответ как plaintext — только через `GET /api/v1/profiles/{slug}/contacts/reveal`. Подробнее: ADR-0020.

---

### `github_accounts`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID UNIQUE FK → users | ON DELETE CASCADE |
| `avatar_url` | TEXT | ≤ 2048; обновляется при входе |
| `created_at` | TIMESTAMPTZ NOT NULL | |

Токен пользователя GitHub не хранится. Репозитории не принадлежат github_account. Подробнее: ADR-0016.

---

### `projects`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `owner_id` | UUID FK → users | ON DELETE CASCADE |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'DRAFT' | `DRAFT` / `PUBLISHED` / `ARCHIVED` |
| `visibility` | VARCHAR(20) NOT NULL DEFAULT 'PRIVATE' | `PUBLIC` / `PRIVATE` |
| `title` | TEXT | ≤ 100; nullable; trimmed |
| `summary` | TEXT | ≤ 300; nullable |
| `description` | TEXT | ≤ 5000; nullable |
| `problem` | TEXT | ≤ 2000; nullable |
| `results` | TEXT | ≤ 2000; nullable |
| `role` | TEXT | ≤ 100; nullable |
| `contribution` | TEXT | ≤ 2000; nullable |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Допустимые комбинации `(status, visibility)`: `(DRAFT, PRIVATE)`, `(PUBLISHED, PUBLIC)`, `(PUBLISHED, PRIVATE)`, `(ARCHIVED, PRIVATE)`. Остальные — отклоняются в domain-слое. Подробнее: ADR-0005, ADR-0015.

UNIQUE `(id, owner_id)` (`uq_projects_id_owner`) — служит целью FK из `project_repositories`.

Лимит 50 проектов на пользователя — в domain-слое под блокировкой строки профиля.

---

### `technologies`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `name` | TEXT NOT NULL | ≤ 50; trimmed; схлопывание пробелов |
| `created_at` | TIMESTAMPTZ NOT NULL | |

Shared: не принадлежат пользователю. UNIQUE по `lower(name)`. В V1 не удаляются.

---

### `project_technologies`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `project_id` | UUID FK → projects | ON DELETE CASCADE |
| `technology_id` | UUID FK → technologies | ON DELETE RESTRICT |
| `position` | SMALLINT NOT NULL | 1..20; порядок разработчика |

UNIQUE `(project_id, technology_id)`, UNIQUE `(project_id, position)`.

---

### `featured_projects`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `project_id` | UUID UNIQUE FK → projects | ON DELETE CASCADE |
| `profile_id` | UUID FK → profiles | ON DELETE CASCADE |
| `position` | SMALLINT NOT NULL | 1..3 |
| `created_at` | TIMESTAMPTZ NOT NULL | |

UNIQUE `(profile_id, position)` — DEFERRABLE INITIALLY IMMEDIATE (для атомарной перестановки). Максимум 3 на профиль проверяется в domain-слое. Только `PUBLISHED + PUBLIC` проект может быть в витрине.

---

### `github_repositories`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `github_repo_id` | BIGINT UNIQUE NOT NULL | Числовой ID GitHub |
| `owner_github_id` | BIGINT NOT NULL | |
| `owner_login` | TEXT NOT NULL | |
| `name` | TEXT NOT NULL | |
| `full_name` | TEXT NOT NULL | `owner_login/name` |
| `html_url` | TEXT NOT NULL | Начинается с `https://github.com/` |
| `description` | TEXT | Nullable |
| `is_fork` | BOOLEAN NOT NULL | |
| `parent_full_name` | TEXT | Nullable |
| `is_archived` | BOOLEAN NOT NULL | |
| `pushed_at` | TIMESTAMPTZ | Nullable |
| `languages` | JSONB | `{"язык": байты}`; nullable до первой синхронизации |
| `unavailable_since` | TIMESTAMPTZ | Nullable; дата первого 404; не перезаписывается |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Shared: одна строка на GitHub-репозиторий, независимо от числа пользователей. Текст из GitHub без лимитов длины — платформа устанавливает только инварианты CHECKами. `unavailable_since` — факт о репозитории, не о джобе синхронизации. Подробнее: ADR-0017, ADR-0018.

---

### `project_repositories`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `project_id` | UUID UNIQUE | UNIQUE; часть FK `(project_id, owner_id) → projects(id, owner_id)` ON DELETE CASCADE |
| `owner_id` | UUID FK → users | Владелец проекта |
| `github_repository_id` | UUID FK → github_repositories | ON DELETE RESTRICT |
| `relation` | VARCHAR(20) NOT NULL | `OWNER` / `CONTRIBUTOR` / `NONE` |
| `relation_checked_at` | TIMESTAMPTZ | Nullable |
| `created_at` | TIMESTAMPTZ NOT NULL | |

UNIQUE `(owner_id, github_repository_id)` — один репозиторий в не более чем одном проекте пользователя. Удаление проекта или его владельца удаляет привязку; строка репозитория остаётся.

---

### `github_sync_jobs`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `github_repository_id` | UUID FK → github_repositories | ON DELETE CASCADE |
| `status` | VARCHAR(20) NOT NULL DEFAULT 'QUEUED' | `QUEUED` / `SYNCING` / `SYNCED` / `FAILED` |
| `attempt_count` | INTEGER NOT NULL DEFAULT 0 | ≥ 0 |
| `scheduled_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `last_error` | TEXT | Nullable; метка `^[A-Z_]{1,64}$`; не текст от GitHub |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | Обновляется при каждой смене статуса |

Индексы:
- `uq_github_sync_jobs_active` UNIQUE на `github_repository_id` WHERE status IN ('QUEUED', 'SYNCING') — не более одной активной джобы.
- `ix_github_sync_jobs_claim` на `scheduled_at` WHERE status = 'QUEUED' — захват воркером через SKIP LOCKED.
- `ix_github_sync_jobs_repository_created` на `(github_repository_id, created_at)` — последняя джоба, пауза 10 мин, расписание 24ч.

Подробнее: ADR-0009, ADR-0018.

---

### `github_sync_category_status`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | |
| `github_repository_id` | UUID FK → github_repositories | ON DELETE CASCADE |
| `category` | VARCHAR(20) NOT NULL | `metadata` / `languages` (V1) |
| `last_success_at` | TIMESTAMPTZ | Nullable |
| `last_error` | TEXT | Nullable; та же маска `^[A-Z_]{1,64}$` |
| `last_error_at` | TIMESTAMPTZ | Nullable |

UNIQUE `(github_repository_id, category)`. `last_error` и `last_error_at` устанавливаются вместе. Строка появляется при первой попытке категории.

---

## Решения по схеме

| Решение | ADR |
|---|---|
| Роль и вклад — поля `projects`, нет отдельной сущности | [ADR-0004](../release/v1/adr/0004-contribution-as-fields.md) |
| Жизненный цикл и видимость — разные измерения | [ADR-0005](../release/v1/adr/0005-project-lifecycle-visibility.md) |
| Сессии серверные, `token_hash` без plaintext | [ADR-0012](../release/v1/adr/0012-github-oauth-only.md) |
| CHECK на публикацию профиля (`display_name` + `headline`) | [ADR-0013](../release/v1/adr/0013-profile-patch-origin-check.md) |
| Технологии нормализованы; витрина отдельная | [ADR-0015](../release/v1/adr/0015-project-entities.md) |
| Токен пользователя GitHub не хранится | [ADR-0016](../release/v1/adr/0016-github-public-only.md) |
| Репозиторий — разделяемый ресурс; `unique(owner_id, repo_id)` в привязке | [ADR-0017](../release/v1/adr/0017-repository-linking.md) |
| Одна активная джоба через partial unique index | [ADR-0009](../release/v1/adr/0009-sync-worker-skip-locked.md) |
| `unavailable_since` — факт репозитория, не статус джобы | [ADR-0018](../release/v1/adr/0018-github-sync-v1.md) |
| Контакты в отдельной таблице; email/phone скрыты | [ADR-0020](../release/v1/adr/0020-contacts-storage.md) |

## Статус миграций

| Миграция | Содержание | На проде |
|---|---|---|
| `0001_initial` | `users`, `auth_sessions`, `profiles` | нет |
| `0002_projects` | `projects`, `technologies`, `project_technologies`, `featured_projects` | нет |
| `0003_github` | `github_accounts`, `github_repositories`, `project_repositories` | нет |
| `0004_sync` | `github_sync_jobs`, `github_sync_category_status` | нет |
| `0005_contacts` | `profile_contacts` | нет |

## Аналитика

V1.1: таблица `analytics_events` не существует в V1. Поля при создании: тип события, ссылка на профиль/проект, timestamp, privacy-safe метаданные сессии.

## Приоритеты индексов

- `users.github_user_id` UNIQUE
- `auth_sessions.token_hash` UNIQUE
- `auth_sessions.user_id`
- `profiles.slug` UNIQUE
- `profiles.user_id` UNIQUE
- `projects.owner_id`
- `technologies.lower(name)` UNIQUE
- `project_technologies.(project_id, position)` UNIQUE
- `featured_projects.project_id` UNIQUE
- `featured_projects.(profile_id, position)` UNIQUE DEFERRABLE
- `github_repositories.github_repo_id` UNIQUE
- `project_repositories.project_id` UNIQUE; `github_repository_id`
- `github_sync_jobs` — три индекса выше
- `github_sync_category_status.(repository_id, category)` UNIQUE
