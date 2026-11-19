# Деплой

Продакшн — один хост с Docker Compose, один origin за Nginx ([ADR-0021](docs/release/v1/adr/0021-single-origin-behind-nginx.md)). Бэкапы — шаг 9.5, мониторинг — 9.6, CI/CD — 9.4.

## Состав

`docker-compose.prod.yml` дополняет `docker-compose.yml`:

| Сервис | Что делает |
|---|---|
| `nginx` | Единственный с портами наружу (80, 443). TLS, `/api/v1/*` → `backend:8000`, `/media/*` — файлы скриншотов из тома `media` (только чтение), остальное → `frontend:3000`, 80 → редирект на https, кроме ACME challenge. Тело запроса — до 1 МБ, на загрузке скриншота — до 6 МБ |
| `frontend` | Next.js (`node server.js` из standalone-сборки). Собирается под один адрес: `NEXT_PUBLIC_API_URL=https://SERVER_NAME`. Секретов не получает |
| `backend` | Без портов наружу. Доверяет `X-Forwarded-For` и `X-Forwarded-Proto` только от адреса Nginx (`FORWARDED_ALLOW_IPS=NGINX_IP`). Один процесс uvicorn: бюджет запросов к GitHub и кеш списка репозиториев живут в памяти процесса. Пишет скриншоты в том `media` (`/srv/media`) |
| `migrate` | Применяет миграции при каждом `up` и завершается; бэкенд и воркер ждут его |
| `github-worker` | Синхронизация GitHub, один процесс |
| `postgres` | Без портов наружу: `docker compose exec postgres psql -U <POSTGRES_USER> <POSTGRES_DB>` |
| `certbot` | Продлевает сертификат дважды в сутки; Nginx перечитывает его раз в 6 часов |
| `backup` | Бэкап базы и тома `media` в restic-репозиторий вне хоста при старте и раз в сутки ([ADR-0026](docs/release/v1/adr/0026-backups-with-restic.md)); после него — проверка свободного места и пинги мониторинга ([ADR-0027](docs/release/v1/adr/0027-monitoring-external-heartbeats.md)) |
| `restore` | Только вручную (`docker compose run --rm restore`), в `up` не входит: восстановление из бэкапа |

У всех сервисов логи `json-file` с ротацией: 5 файлов по 10 МБ. Опубликованные Docker порты обходят ufw, поэтому наружу их нет ни у кого, кроме Nginx; CI это проверяет (`check_compose.py --production`).

## Сервер

- Linux с Docker Engine и плагином Compose v2.24 или новее (`!reset` в `docker-compose.prod.yml`).
- Firewall: открыты только 22, 80, 443.
- DNS: A-запись `SERVER_NAME` указывает на сервер.
- Пользователь деплоя в группе `docker`. Доступ к Docker равен root: давать его только тем, кому можно видеть секреты.
- GitHub OAuth App для продакшна: Homepage `https://SERVER_NAME`, callback `https://SERVER_NAME/api/v1/auth/github/callback`.

## Секреты и `.env`

Все настройки — в `.env` в корне репозитория на сервере. Файл не в git, права `600`, владелец — пользователь деплоя:

```sh
cp .env.example .env
chmod 600 .env
```

Его читают `backend`, `migrate` и `github-worker` (`env_file`); `postgres` получает только `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`; `backup` и `restore` — данные Postgres, `RESTIC_*`, `AWS_*`, `BACKUP_HEARTBEAT_URL` и `DISK_HEARTBEAT_URL`; `frontend`, `nginx` и `certbot` секретов не получают. Секретов нет в образах.

Что поменять относительно примера:

| Переменная | Значение |
|---|---|
| `COMPOSE_FILE` | `docker-compose.yml:docker-compose.prod.yml` — обычные `docker compose up`, `logs`, `exec` используют оба файла |
| `APP_ENV` | `production` — cookie получают `Secure` |
| `SERVER_NAME` | имя сайта, например `example.com` |
| `FRONTEND_URL` | `https://SERVER_NAME` |
| `GITHUB_CALLBACK_URL` | `https://SERVER_NAME/api/v1/auth/github/callback` |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | из OAuth App продакшна (не из dev-приложения) |
| `POSTGRES_PASSWORD` | `openssl rand -hex 32`; тот же пароль — в `DATABASE_URL` |
| `INTERNAL_SUBNET`, `NGINX_IP` | оставить, если подсеть `172.30.10.0/24` не занята на хосте; менять вместе |
| `RESTIC_REPOSITORY` | хранилище бэкапов вне хоста, для S3-совместимого — `s3:https://<endpoint>/<bucket>/<path>` |
| `RESTIC_PASSWORD` | `openssl rand -hex 32`; без него бэкапы не прочитать |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` | ключ хранилища с доступом только к этому бакету |
| `WORKER_HEARTBEAT_URL`, `BACKUP_HEARTBEAT_URL`, `DISK_HEARTBEAT_URL` | URL трёх проверок у сервиса мониторинга («Мониторинг» ниже), без `/` на конце |

При `APP_ENV=production` бэкенд, `migrate` и воркер не стартуют, если `FRONTEND_URL` не https, `GITHUB_CALLBACK_URL` не на том же origin с путём `/api/v1/auth/github/callback` или пуст `WORKER_HEARTBEAT_URL`: ошибка видна сразу, а не при входе или при первом сбое.

`.env` — единственное место секретов: его копия, вместе с `RESTIC_PASSWORD`, хранится в менеджере паролей владельца, отдельно от сервера и репозитория. В бэкап он не входит: в нём пароль от самого бэкапа.

### Ротация

- `GITHUB_CLIENT_SECRET`: создать новый секрет в OAuth App, заменить в `.env`, `docker compose up -d` (пересоздаст `backend`, `migrate`, `github-worker`), удалить старый секрет в GitHub.
- `POSTGRES_PASSWORD`: переменная задаёт пароль только при первой инициализации тома, поэтому сначала меняется пароль в базе, потом `.env`:

  ```sh
  docker compose exec postgres psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "ALTER USER <POSTGRES_USER> PASSWORD '<новый>'"
  ```

  Затем новый пароль — в `POSTGRES_PASSWORD` и `DATABASE_URL`, и `docker compose up -d`.
- Сессии пользователей (`auth_sessions`) от секретов не зависят и при ротации не сбрасываются.

## Первый запуск

1. Клонировать репозиторий, заполнить `.env` (раздел выше).
2. `docker compose up -d --build`. Проверить: `docker compose ps` — `migrate` завершился с кодом 0, остальные `Up`; порты только у `nginx`.
3. Создать репозиторий бэкапов (один раз): `docker compose run --rm backup restic init`, затем `docker compose restart backup` и в `docker compose logs backup` — `backup: done`.
4. Выпустить сертификат (раздел ниже).
5. Пройти «Проверку после запуска».

## Первый сертификат

До выпуска Nginx стартует с самоподписанным сертификатом (на 30 дней), иначе он не поднимется на 443. DNS уже должен указывать на хост, порт 80 — быть открыт.

1. Выпустить сертификат (сначала с `--staging`, чтобы не упереться в лимиты Let's Encrypt; потом без него):

   ```sh
   docker compose run --rm --entrypoint certbot certbot \
     certonly --webroot -w /var/www/certbot -d example.com --email admin@example.com --agree-tos --no-eff-email --staging
   ```

   После staging-прогона перед боевым выпуском удалить пробный: `docker compose run --rm --entrypoint certbot certbot delete --cert-name example.com`.
2. Переключить Nginx на выпущенный сертификат: `docker compose restart nginx` (в логе — `using the Let's Encrypt certificate`).

Дальше сервис `certbot` продлевает сам.

## Обновление

Выкладывается только `main`, прошедшая CI: ветка защищена (ниже). На сервере, в каталоге репозитория ([ADR-0025](docs/release/v1/adr/0025-manual-deploy-script.md)):

```sh
./deploy.sh
```

Скрипт переходит на `origin/main` (или на коммит: `./deploy.sh <commit>`), запоминает прошлый коммит в `.deploy/previous`, запускает `docker compose up -d --build` и ждёт до 60 секунд ответа `/api/v1/health` и `/` через Nginx. Не дождался — ошибка: смотреть `docker compose logs`. Checkout остаётся в detached HEAD, `git pull` не нужен.

`migrate` применяет новые миграции до старта бэкенда и воркера; упал — `up` завершается ошибкой, бэкенд и воркер не перезапускаются. Миграции не откатываются автоматически, поэтому если в обновлении есть миграция, скрипт сначала делает бэкап (`docker compose run --rm backup backup.sh`); бэкап не прошёл — ничего не обновляется.

Откат на коммит до последней выкладки:

```sh
./deploy.sh --rollback
```

Если между ними миграция, скрипт откажет: откат с миграцией — восстановление из бэкапа, сделанного перед выкладкой (ниже).

### Защита `main`

В GitHub: Settings → Branches → правило для `main` — «Require a pull request before merging» и «Require status checks to pass» с проверками `Lint and test`, `Build the backend image`, `Lint, typecheck, test and build`, `Build the frontend image`, `Check the Compose file`. Скрипт не проверяет CI сам и опирается на это правило.

## Файлы скриншотов

Скриншоты лежат в именованном томе `media` ([ADR-0022](docs/release/v1/adr/0022-media-on-host-volume.md)); в базе — только путь к файлу. Том и база бэкапятся вместе (ниже): без тома ссылки в базе ведут в `404`, без базы файлы ничьи. Свободное место на диске проверяет мониторинг («Мониторинг» ниже).

Файл удаляется вместе со скриншотом или проектом. Если процесс упал между записью файла и строки, файл остаётся без строки. Такие файлы старше суток убирает ручная команда — раз в месяц или после сбоя бэкенда:

```sh
docker compose exec backend python -m app.media.sweep --dry-run
docker compose exec backend python -m app.media.sweep
```

Первая только печатает, что будет удалено; вторая удаляет и печатает удалённое. Если `MEDIA_ROOT` не каталог, команда завершается с кодом 1 и ничего не трогает.

## Бэкапы

Сервис `backup` при старте и раз в сутки ([ADR-0026](docs/release/v1/adr/0026-backups-with-restic.md)):

1. `pg_dump` базы в формате `custom`;
2. `restic backup` дампа и тома `media` — зашифровано, неизменённые файлы не передаются заново;
3. `restic forget --prune`: остаются 7 ежедневных, 4 еженедельных и 6 ежемесячных снимков;
4. по понедельникам `restic check` — целостность репозитория.

Ошибка пишется в `docker compose logs backup` (`backup failed`) и уходит пингом `/fail` в мониторинг; следующая попытка — через сутки. Бэкап вручную:

```sh
docker compose run --rm backup backup.sh
docker compose run --rm backup restic snapshots
```

Хранилище — у другого провайдера или в другом дата-центре, чем сервер: бэкап на том же диске не переживает потери хоста. В бэкапе персональные данные; юрисдикция хранилища — та же, что у хоста ([ADR-0020](docs/release/v1/adr/0020-contacts-separate-table.md), «Видимость и персональные данные»).

## Восстановление

Базу и том `media` восстанавливают вместе, из одного снимка. Сервис `restore` удаляет базу и создаёт её заново из дампа, а содержимое тома заменяет файлами снимка.

1. Если откатывается выкладка с миграцией — сначала вернуть код: `git checkout --detach <коммит до выкладки>` (он в `.deploy/previous`). Иначе код остаётся текущим: `migrate` при старте доведёт восстановленную базу до него.
2. Остановить тех, кто пишет в базу и том:

   ```sh
   docker compose stop backend github-worker
   ```

3. Восстановить последний снимок или выбранный (`restic snapshots` — список):

   ```sh
   docker compose run --rm restore
   docker compose run --rm restore <snapshot>
   ```

4. `docker compose up -d --build` и «Проверка после запуска».

На новом хосте: «Первый запуск» с копией `.env` из менеджера паролей (без `restic init` — репозиторий уже есть), затем шаги 2–4.

До запуска (9.8) восстановление проверяется один раз по-настоящему: из продакшн-хранилища на отдельной машине. CI проверяет его на каждом PR, но на временной базе и локальном репозитории (`check_backup.sh`).

## Мониторинг

Сервис мониторинга — внешний, не на этом хосте: иначе он молчит, когда хост лежит ([ADR-0027](docs/release/v1/adr/0027-monitoring-external-heartbeats.md)). Подходит любой с HTTP-пробером и dead-man's switch, у которого GET на URL — «жив», `<URL>/fail` — «сбой» (Healthchecks.io, Better Stack). Что завести:

| Проверка | Что делает | Срок / запас |
|---|---|---|
| Пробер `https://SERVER_NAME/api/v1/health` | ждёт `200`; заодно срок сертификата | раз в 5 минут |
| Пробер `https://SERVER_NAME/` | ждёт `200` | раз в 5 минут |
| Воркер → `WORKER_HEARTBEAT_URL` | пинг после итерации без ошибки, не чаще раза в 5 минут | 5 минут / 10 минут |
| Бэкап → `BACKUP_HEARTBEAT_URL` | пинг после бэкапа, `/fail` при ошибке | сутки / 2 часа |
| Диск → `DISK_HEARTBEAT_URL` | пинг раз в сутки, `/fail` при 80% занятого диска | сутки / 2 часа |

Алерты — на почту или в Telegram владельца. URL проверок — секреты: они в `.env` и в логи не пишутся. Ошибка самого пинга не останавливает ни воркер, ни бэкап: в логах `heartbeat failed` и `monitoring: a ping failed`.

Что делать по алерту:

- **Пробер:** `docker compose ps`, `docker compose logs --tail 100 nginx backend frontend`.
- **Воркер:** `docker compose logs --tail 100 github-worker`. `rejected the app credentials` — сменились `GITHUB_CLIENT_ID` или `GITHUB_CLIENT_SECRET` («Ротация»); `an iteration failed` — смотреть базу.
- **Бэкап:** `docker compose logs backup` («Бэкапы»).
- **Диск:** `df -h`, `docker system df`; лишние образы — `docker image prune`.

До запуска (9.8) один раз проверить, что алерт доходит: `docker compose stop github-worker`, дождаться письма, `docker compose start github-worker`.

## Проверка после запуска

- `curl -I http://SERVER_NAME/` → `301` на `https://`.
- `curl -I https://SERVER_NAME/api/v1/health` → `200` и `Strict-Transport-Security`.
- `curl -I https://SERVER_NAME/` → `X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.
- `curl -s -o /dev/null -H "X-Forwarded-For: 1.2.3.4" https://SERVER_NAME/api/v1/health`, затем `docker compose logs backend | tail` — в строке реальный адрес клиента, не `1.2.3.4`.
- `curl -I -H "Host: other.example" http://SERVER_NAME/` — соединение закрыто без ответа.
- `POST /api/v1/auth/logout` с `Origin: https://evil.example` → `403 CSRF_ORIGIN_INVALID`.
- `docker compose ps` — порты наружу только у `nginx`; снаружи `nc -z SERVER_NAME 5432` и `8000` не соединяются.
- Вход через GitHub и публикация профиля проходят в браузере.
- Скриншот загружается в форме проекта; `curl -I https://SERVER_NAME/media/projects/<id>/<id>.webp` (адрес — из `url` в ответе) → `200`, `Content-Type: image/webp`, `Cache-Control: public, max-age=31536000, immutable`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security` и те же заголовки против встраивания. `curl -I https://SERVER_NAME/media/` → `404`.

Локально те же проверки проходят с `SERVER_NAME=localhost` и самоподписанным сертификатом (`curl -k`); вход через GitHub — только с отдельным OAuth App, у которого callback `https://localhost/api/v1/auth/github/callback`.
