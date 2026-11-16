# ADR-0021: В продакшне фронтенд и API работают на одном origin за Nginx на одном хосте

- **Статус:** принято 2026-11-17
- **Релиз:** v1
- **Связано:** [0012](0012-github-oauth-only.md) — cookie сессии и OAuth callback; [0013](0013-profile-patch-origin-check.md) — Origin-проверка и CORS; [0014](0014-nextjs-ssr-public.md) — SSR ходит в API из Server Components; [0018](0018-github-sync-v1.md) — сервис `github-worker`; [0020](0020-contacts-separate-table.md) — ручка раскрытия контактов и rate limit в 8.3

## Контекст

V1 должен работать в продакшне по HTTPS (PRD, «V1 scope»; скоуп, «Деплой»). До шагов 9.2–9.3 (образы, Nginx, продакшн Compose) нужно решить, по какому адресу браузер ходит в API: от этого зависят cookie, CORS, Origin-проверка, OAuth callback и переменные фронтенда.

Что есть в коде на момент решения:

- Origin-проверка и CORS (`backend/app/main.py`) разрешают ровно один origin — вычисленный из `FRONTEND_URL`. Настройки `ALLOWED_ORIGINS`, которую называет [0013](0013-profile-patch-origin-check.md), в `Settings` нет.
- Cookie сессии и `state` (`backend/app/identity/router.py`): `HttpOnly`, `SameSite=Lax`, без `Domain` (только хост, который её поставил). `Secure` — по `APP_ENV != development` (`Settings.secure_cookies`), не по схеме запроса.
- Обе переадресации OAuth callback (успех и ошибка) строятся только из `FRONTEND_URL`. Заголовок `Host` и `request.url` бэкенд не использует.
- Фронтенд (`frontend/src/lib/api/config.ts`): `NEXT_PUBLIC_API_URL` — для кода в браузере, вшивается при сборке; `API_INTERNAL_URL` — для серверного кода. Оба — абсолютные URL без `/api/v1`; относительный путь не проходит проверку.
- SSR публичных страниц ходит в API анонимно, только за публичными данными, без cookie пользователя. Кабинет вызывает API из браузера.
- Uvicorn запущен без `--forwarded-allow-ips`: за Nginx в соседнем контейнере `X-Forwarded-*` игнорируются, `request.client.host` — адрес Nginx.
- В `docker-compose.yml` нет сервиса фронтенда; `backend` опубликован на `127.0.0.1:8000`.
- Локально фронтенд и API — разные origin (`localhost:3000` и `localhost:8000`), но один site: CORS работает только здесь.

Варианты: один origin (`example.com`, API по пути `/api/v1/*`) или отдельный API-хост (`api.example.com`).

## Решение

1. **Один origin.** Nginx принимает весь трафик `https://example.com`: `/api/v1/*` → FastAPI (`backend:8000`), остальное → Next.js. Код и API-контракт не меняются; меняются только значения окружения:
   - `FRONTEND_URL=https://example.com`;
   - `GITHUB_CALLBACK_URL=https://example.com/api/v1/auth/github/callback` — тот же адрес прописывается в GitHub OAuth App продакшна;
   - `NEXT_PUBLIC_API_URL=https://example.com` — абсолютный URL того же origin: проверка в `config.ts` остаётся как есть;
   - `API_INTERNAL_URL=http://backend:8000` — SSR ходит в API внутри сети Compose, мимо Nginx и TLS.
2. **Cookie** остаются привязанными к хосту `example.com`, `Domain` не задаётся: cookie не уходит на поддомены. `SameSite=Lax` достаточно: переход с GitHub на callback — top-level GET, cookie `state` приходит, `Set-Cookie` сессии в ответе-редиректе принимается. `Secure` даёт `APP_ENV=production`.
3. **CORS в продакшне не участвует**: запросы браузера same-origin, preflight нет. `CORSMiddleware` остаётся для локальной разработки и в продакшне ничего не разрешает сверх того же origin. **Origin-проверка не меняется**: браузер шлёт `Origin` и на same-origin POST/PATCH/DELETE, сравнивается с `https://example.com`.
4. **TLS заканчивается на Nginx.** Сертификат — Let's Encrypt, проверка HTTP-01: порт 80 отдаёт только ACME challenge и редирект на `https`. HSTS включён. За Nginx — обычный HTTP во внутренней сети. Как запускается certbot и как продлевается сертификат — шаг 9.2.
5. **Доверие к прокси.** Бэкенд принимает `X-Forwarded-For` и `X-Forwarded-Proto` только от Nginx (в 9.2 — `--forwarded-allow-ips` с адресом Nginx, не `*`), потому что иначе любой контейнер сети подставит чужой IP и обойдёт rate limit 8.3. Nginx — край сети, поэтому он **заменяет** `X-Forwarded-For` на `$remote_addr`, а не дописывает к пришедшему: заголовок от клиента не доходит до бэкенда. `X-Forwarded-Host` не передаётся: бэкенд не строит адреса из `Host`.
6. **Наружу открыт только Nginx** на 80 и 443. `postgres`, `backend`, `frontend`, `github-worker` — только во внутренней сети Compose; в продакшне `backend` не публикуется даже на `127.0.0.1`.
7. **Окружение V1 — один хост с Docker Compose.** Без Kubernetes, CDN, внешнего балансировщика и второго прокси.
8. **Медиа фазы 4 — направление:** публичные файлы отдаются с того же origin по пути (например `/media/*`) через Nginx, объектное хранилище наружу не торчит. Загрузка, URL и политика бакета решаются в фазе 4.

_Правка 2026-11-17 (шаг 9.2, механика пунктов 4 и 5): certbot — сервис в Compose (`certbot/certbot`), а не пакет на хосте, потому что тогда хост пересоздаётся из git и `.env` без ручного состояния. Первый сертификат выпускается вручную (`certonly --webroot`), до него Nginx стартует с самоподписанным; сервис продлевает дважды в сутки, Nginx перечитывает раз в 6 часов. Доверие к прокси — без кода: у внутренней сети фиксированная подсеть (`INTERNAL_SUBNET`, `172.30.10.0/24`), у Nginx фиксированный адрес (`NGINX_IP`, `172.30.10.10`), uvicorn читает его из `FORWARDED_ALLOW_IPS`. Nginx находит `backend` и `frontend` через DNS Docker на каждый запрос: пересозданный контейнер получает новый адрес. Запросы с чужим `Host` закрываются без ответа. Порядок запуска — [DEPLOY.md](../../../../DEPLOY.md)._

## Отвергнуто

- **Отдельный API-хост (`api.example.com`).** Работает — запросы same-site, `Lax` проходит, — но добавляет CORS с `credentials` в продакшне, второе имя в DNS и сертификате и соблазн поставить `Domain=.example.com`, который отдаёт cookie сессии всем поддоменам. Выгоды в V1 нет: у API один клиент — свой фронтенд.
- **Проксирование API через Next.js (rewrites).** Лишний хоп и второй прокси, который должен правильно передавать `X-Forwarded-*`; Nginx и так стоит на краю.
- **Относительный `NEXT_PUBLIC_API_URL` (`/`).** Потребовал бы правки `config.ts` и его проверки при сборке; абсолютный URL того же origin даёт то же без кода.

## Последствия

- Скелет деплоя не требует правок кода: шаги 9.2–9.3 — Nginx, образы, Compose и значения окружения.
- Локально и в продакшне топология разная: CORS проверяется только при разработке. Origin-проверка работает одинаково.
- Rate limit 8.3 по IP имеет смысл только на ручках, которые вызывает браузер (раскрытие контактов, вход): SSR-запросы идут мимо Nginx с адресом контейнера фронтенда и IP посетителя не несут.
- При переезде на свой домен меняется callback в GitHub OAuth App.
- Решение пересматривается, если у API появится внешний клиент на другом домене (V2+), фронтенд уедет на отдельный хостинг или API понадобится масштабировать отдельно.

## Риски

- `--forwarded-allow-ips="*"` или Nginx, дописывающий `X-Forwarded-For`, сделают IP поддельным, и rate limit 8.3 обходится сменой заголовка. Проверяем в 9.2: запрос с поддельным `X-Forwarded-For` снаружи логируется бэкендом с реальным адресом.
- Если в продакшн-Compose останется публикация `backend` на хосте, Nginx и TLS можно обойти с самого хоста. Проверяем в 9.3: `docker compose ps` показывает порты только у Nginx.
