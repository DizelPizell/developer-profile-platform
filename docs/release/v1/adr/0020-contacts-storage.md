# ADR-0020: Контакты хранятся в отдельной таблице; email и телефон скрыты до явного клика

- **Статус:** принято 2026-11-04
- **Релиз:** v1
- **Связано:** [0012](0012-github-oauth-only.md), [0013](0013-profile-patch-origin-check.md)

## Контекст

Разработчики хотят указывать способы связи на публичном профиле. Набор контактов может меняться в будущем. Нужно решить: хранить контакты в таблице `profiles` или отдельно; как защитить email и телефон от автоматического парсинга.

V1-набор контактов: email, телефон, Telegram, LinkedIn, личный сайт, GitHub (автоматически из OAuth).

## Решение

Отдельная таблица `profile_contacts`:

```
profile_contacts
  id              UUID PK
  profile_id      UUID FK → profiles
  type            ENUM(email, phone, telegram, linkedin, website, github)
  value           TEXT NOT NULL
  is_public       BOOLEAN NOT NULL DEFAULT true
  display_order   SMALLINT
  created_at      TIMESTAMPTZ
  updated_at      TIMESTAMPTZ
```

Уникальное ограничение: `unique(profile_id, type)` — один контакт каждого типа на профиль.

Email и телефон (`type IN ('email', 'phone')`) не включаются в публичный API-ответ как plaintext. Они передаются клиенту только при явном клике пользователя — через отдельный ручку `GET /api/v1/profiles/{slug}/contacts/reveal`.

Остальные типы контактов (telegram, linkedin, website, github) передаются напрямую в публичном ответе при `is_public = true`.

GitHub-контакт создаётся автоматически при первом входе на основе данных OAuth.

## Отвергнуто

- **Поля email/phone/telegram в таблице `profiles`** — негибко при добавлении новых типов; нет `is_public` на уровне контакта.
- **Показывать email plaintext в публичном ответе** — открыт для парсинга ботами.

## Последствия

Новые типы контактов добавляются без миграции схемы (расширение ENUM). Email и телефон защищены от автоматического парсинга. Нужен отдельный эндпоинт reveal с собственными ограничениями (rate limit, логирование).
