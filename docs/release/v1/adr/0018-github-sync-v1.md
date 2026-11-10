# ADR-0018: V1 синхронизирует только метаданные и языки; контрибьюторы/коммиты/README/дерево файлов отложены

- **Статус:** принято 2026-10-30
- **Релиз:** v1
- **Связано:** [0010](0010-github-evidence-model.md) — полная модель; [0009](0009-sync-worker-skip-locked.md) — воркер; [0016](0016-github-public-only.md) — credentials

## Контекст

[0010](0010-github-evidence-model.md) описал полную модель данных GitHub Evidence. Для V1 нужно сузить объём до реально нужного: лишние запросы к GitHub тратят rate limit и усложняют воркер.

## Решение

V1 синхронизирует только:
- **Метаданные** — `GET /repos/{owner}/{repo}`: name, description, html_url, stargazers_count, forks_count, open_issues_count, default_branch, topics, archived, fork.
- **Языки** — `GET /repos/{owner}/{repo}/languages`.

Не синхронизируются в V1: README, дерево файлов, контрибьюторы, коммиты.

Расписание периодической синхронизации: репозитории PUBLISHED-проектов без активной джобы и без синхронизации за 24 часа — до 30 джобов за итерацию воркера (не чаще одного раза в минуту).

Правило «два 404 → недоступен»: репозиторий помечается `unavailable_since` при втором последовательном 404 от GitHub. `unavailable_since` фиксирует первую дату недоступности — не перезаписывается при следующих 404.

Ручная синхронизация: `POST /api/v1/integrations/github/repositories/{id}/sync` — пауза 10 минут. Возвращает `sync` в ответе `ProjectResponse`.

## Последствия

Существенно снижен расход rate limit в V1. Дерево файлов и README могут быть добавлены позже без изменения архитектуры воркера — только новые категории в `github_sync_category_status`.
