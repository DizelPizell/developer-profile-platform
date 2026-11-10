# Документация

## Принцип

Документы живут рядом с кодом и обновляются в том же PR.
Вся документация — на русском.

Правило выбора документа:

| Вопрос | Документ |
|---|---|
| *Что* входит в релиз | `release/vN/scope/scope-vN.md` |
| *Почему* решили так | `release/vN/adr/NNNN-slug.md` |
| *Как* система ведёт себя сейчас | `usecases.md` |
| *Какая* схема сейчас | `database/DATABASE_SCHEMA.md` |

Подробнее о структуре и шаблонах — `.claude/skills/arch-docs/skill.md`.

---

## Скоуп и ADR

- [Scope v1](release/v1/scope/scope-v1.md) — что входит в V1 и текущий статус

**ADR V1** (20 решений):

| № | Решение | Файл |
|---|---|---|
| 0001 | Серверная часть — модульный монолит | [ADR-0001](release/v1/adr/0001-modular-monolith.md) |
| 0002 | Kafka и Outbox — исторический ADR (отменён 0008) | [ADR-0002](release/v1/adr/0002-kafka-outbox-superseded.md) |
| 0003 | GitHub-токен шифруется; в V1 не хранится (см. 0016) | [ADR-0003](release/v1/adr/0003-github-token-encryption.md) |
| 0004 | Роль и вклад — поля `projects` | [ADR-0004](release/v1/adr/0004-contribution-as-fields.md) |
| 0005 | Жизненный цикл и видимость проекта — разные измерения | [ADR-0005](release/v1/adr/0005-project-lifecycle-visibility.md) |
| 0006 | Рабочее пространство — только чтение, после V1 | [ADR-0006](release/v1/adr/0006-workspace-readonly.md) |
| 0007 | GitHub — источник технических данных | [ADR-0007](release/v1/adr/0007-github-evidence-source.md) |
| 0008 | Kafka и Outbox не используются в V1 | [ADR-0008](release/v1/adr/0008-no-kafka-v1.md) |
| 0009 | Воркер синхронизации — SKIP LOCKED | [ADR-0009](release/v1/adr/0009-sync-worker-skip-locked.md) |
| 0010 | Модель данных GitHub Evidence | [ADR-0010](release/v1/adr/0010-github-evidence-model.md) |
| 0011 | Частичный успех синхронизации | [ADR-0011](release/v1/adr/0011-sync-partial-success.md) |
| 0012 | Единственный вход — GitHub OAuth | [ADR-0012](release/v1/adr/0012-github-oauth-only.md) |
| 0013 | PATCH-профиль + Origin-проверка | [ADR-0013](release/v1/adr/0013-profile-patch-origin-check.md) |
| 0014 | Next.js App Router + SSR для публичных страниц | [ADR-0014](release/v1/adr/0014-nextjs-ssr-public.md) |
| 0015 | Технологии и витрина — самостоятельные сущности | [ADR-0015](release/v1/adr/0015-project-entities.md) |
| 0016 | V1 читает только публичный GitHub | [ADR-0016](release/v1/adr/0016-github-public-only.md) |
| 0017 | Репозиторий — разделяемый ресурс | [ADR-0017](release/v1/adr/0017-repository-linking.md) |
| 0018 | V1 синхронизирует только метаданные и языки | [ADR-0018](release/v1/adr/0018-github-sync-v1.md) |
| 0019 | GitHub на карточках проектов, без агрегатов | [ADR-0019](release/v1/adr/0019-public-github-on-cards.md) |
| 0020 | Контакты — отдельная таблица, email и телефон по клику | [ADR-0020](release/v1/adr/0020-contacts-separate-table.md) |

---

## Сценарии и схема

- [Сценарии использования](usecases.md) — текущее поведение системы
- [Схема базы данных](database/DATABASE_SCHEMA.md) — актуальная схема и решения

---

## API и продукт

- [API Contract](api/API_CONTRACT.md)
- [OpenAPI](api/openapi.yaml)
- [PRD](product/PRD.md)

---

## Архитектура и фронтенд

- [Architecture](architecture/ARCHITECTURE.md)
- [Domain Model](architecture/DOMAIN_MODEL.md)
- [Design Guide](frontend/DESIGN.md)
- [Frontend Plan](frontend/FRONTEND_PLAN.md)
- [Definition of Done](development/DEFINITION_OF_DONE.md)
