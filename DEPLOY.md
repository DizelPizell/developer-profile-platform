# Деплой

Продакшн — один хост с Docker Compose, один origin за Nginx ([ADR-0021](docs/release/v1/adr/0021-single-origin-behind-nginx.md)). Шаг 9.3 дополнит этот файл: секреты, env по сервисам, сервер и обновление.

## Состав

`docker-compose.prod.yml` дополняет `docker-compose.yml`:

| Сервис | Что делает |
|---|---|
| `nginx` | Единственный с портами наружу (80, 443). TLS, `/api/v1/*` → `backend:8000`, остальное → `frontend:3000`, 80 → редирект на https, кроме ACME challenge |
| `frontend` | Next.js (`node server.js` из standalone-сборки). Собирается под один адрес: `NEXT_PUBLIC_API_URL=https://SERVER_NAME` |
| `certbot` | Продлевает сертификат дважды в сутки; Nginx перечитывает его раз в 6 часов |
| `backend` | Доверяет `X-Forwarded-For` и `X-Forwarded-Proto` только от адреса Nginx (`FORWARDED_ALLOW_IPS=NGINX_IP`) |

Команда:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Переменные `.env`

- `SERVER_NAME` — имя сайта (`example.com`). Обязательна для продакшн-файла.
- `FRONTEND_URL=https://SERVER_NAME`, `GITHUB_CALLBACK_URL=https://SERVER_NAME/api/v1/auth/github/callback` — тот же callback в GitHub OAuth App продакшна.
- `APP_ENV=production` — cookie получают `Secure`.
- `INTERNAL_SUBNET`, `NGINX_IP` — внутренняя сеть и фиксированный адрес Nginx в ней (по умолчанию `172.30.10.0/24` и `172.30.10.10`). Менять вместе, если подсеть занята на хосте.

## Первый сертификат

До выпуска Nginx стартует с самоподписанным сертификатом (на 30 дней), иначе он не поднимется на 443. DNS-запись `SERVER_NAME` уже должна указывать на хост, порт 80 — быть открыт.

1. Поднять стек командой выше.
2. Выпустить сертификат (сначала с `--staging`, чтобы не упереться в лимиты Let's Encrypt; потом без него):

   ```sh
   docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --entrypoint certbot certbot \
     certonly --webroot -w /var/www/certbot -d example.com --email admin@example.com --agree-tos --no-eff-email --staging
   ```

   После staging-прогона перед боевым выпуском удалить пробный: `... run --rm --entrypoint certbot certbot delete --cert-name example.com`.
3. Переключить Nginx на выпущенный сертификат: `docker compose -f docker-compose.yml -f docker-compose.prod.yml restart nginx` (в логе — `using the Let's Encrypt certificate`).

Дальше сервис `certbot` продлевает сам.

## Проверка после запуска

- `curl -I http://SERVER_NAME/` → `301` на `https://`.
- `curl -I https://SERVER_NAME/api/v1/health` → `200` и `Strict-Transport-Security`.
- `curl -s -o /dev/null -H "X-Forwarded-For: 1.2.3.4" https://SERVER_NAME/api/v1/health`, затем `docker compose logs backend | tail` — в строке реальный адрес клиента, не `1.2.3.4`.
- `curl -I -H "Host: other.example" http://SERVER_NAME/` — соединение закрыто без ответа.
- `POST /api/v1/auth/logout` с `Origin: https://evil.example` → `403 CSRF_ORIGIN_INVALID`.
- `docker compose ps` — порты наружу только у `nginx`. До шага 9.3 `backend` и `postgres` ещё опубликованы на `127.0.0.1`.

Локально те же проверки проходят с `SERVER_NAME=localhost` и самоподписанным сертификатом (`curl -k`); вход через GitHub — только с отдельным OAuth App, у которого callback `https://localhost/api/v1/auth/github/callback`.
