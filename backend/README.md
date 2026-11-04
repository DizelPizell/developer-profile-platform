# Backend

FastAPI backend for the Developer Profile Platform.

## Local development

### Start PostgreSQL

```bash
docker compose up -d postgres
```

### Run the backend

```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

### Run the whole stack in Docker

```bash
docker compose up -d --build
```

The one-shot `migrate` service runs `alembic upgrade head` on every `up` and
exits; the backend and the worker start only after it succeeds.

### GitHub sync worker (service)

The worker (ADR-018) takes sync jobs from the database, reads the repositories'
metadata and languages from GitHub with the app credentials, and recomputes
the relation of every link. It is the `github-worker` service on the backend's
image, always on. The one command to start or update it is the whole stack:

```bash
docker compose up -d --build
```

Compose copies the code into the image when it builds, so other commands can
leave the worker on old code:

| Command | Result |
| --- | --- |
| `docker compose up -d --build` | API and worker on the new image |
| `docker compose up -d --build github-worker` | The same: the worker's link to `backend` builds the image |
| `docker compose up -d --build backend` | API on the new image, **worker on the old one** |
| `docker compose up -d` | Nothing is built: both stay on the old image |
| A container started earlier by `docker compose run` | Keeps its image until it is stopped |

Two identical builds get different image ids here, so every `up --build`
recreates the containers, and the worker restarts after its current job.

To check that the API and the worker run one image, compare the two lines:

```bash
docker inspect --format "{{.Image}}" developer-platform-backend developer-platform-github-worker
```

The log's start line, `started, periodic sync every 86400 s, batch 30`, shows
the settings the running code reads:

```bash
docker compose logs -f github-worker
```

To stop it after the current job (Compose waits up to 90 seconds):

```bash
docker compose stop github-worker
```

It stays stopped until the next `docker compose up -d`. That also applies after
`docker kill developer-platform-github-worker`, which the restart policy ignores;
a job killed halfway stays `SYNCING` until the watchdog takes it back
(`GITHUB_WORKER_STALE_SECONDS`). `docker compose up -d` also recreates the backend
and the worker after a change of `.env`.

The worker exits with code 1 when GitHub rejects the credentials or cannot be
reached at startup, and Docker restarts it with pauses that grow: a loop in the
log, which spends no GitHub budget, until the keys are fixed or the worker is
stopped with the command above. Without GitHub keys in development it is the same
loop. `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` must still not be empty, or
the backend does not start either.

For debugging by hand, this is a second worker, which ADR-018 considers safe; stop
it when done, as it keeps its image:

```bash
docker compose run --build --rm --no-deps backend python -m app.github.worker
```

Jobs queued while no worker ran go back to back, up to 7 GitHub requests each; the
worker claims no job while GitHub's remaining budget is at or below
`GITHUB_WORKER_RESERVE`. To count them first:

```bash
docker exec developer-platform-postgres psql -U <user> -d <database> \
  -c "SELECT status, count(*) FROM github_sync_jobs GROUP BY status"
```

Use `POSTGRES_USER` and `POSTGRES_DB` from your `.env` file.

Once a minute the worker also queues up to `GITHUB_PERIODIC_SYNC_BATCH` jobs for
repositories linked to a published project with no job in the last
`GITHUB_PERIODIC_SYNC_SECONDS`, so they sync only while it runs. It queues
nothing while it claims nothing (a rate limit, the reserve).

### Manual periodic sync check

Not run yet. Real GitHub and a repository of your own. Each step that changes
the root `.env` ends by putting the value back, and `docker compose up -d` after
a change recreates the worker with it.

0. Check that the worker has the current code. Run `docker compose up -d --build`
   for the whole stack: `docker compose up -d --build backend` does not update the
   worker. A variable the image's `Settings` does not know is dropped silently, so
   `printenv` proves nothing. Ask the settings themselves, which fails with an
   `AttributeError` on an old image:

   ```bash
   docker compose exec github-worker python -c "from app.settings import settings; print(settings.github_periodic_sync_seconds)"
   ```

   The worker's line after the limit names both values, such as `started, periodic
   sync every 120 s, batch 30`.
1. Link the repository to a published project, and to a draft of another
   repository. Set `GITHUB_PERIODIC_SYNC_SECONDS=120` and run `docker compose up
   -d`: both links' jobs run once. The first periodic look comes with the first
   iteration, so a published repository with no recent job is queued at once.
2. Wait 3 minutes: the log shows `periodic syncs queued`, and only the published
   project's repository gets new jobs (the query above, or the job lines of the
   log).
3. Rename the repository on GitHub and wait for the next job: the project form
   shows the new name, with no error.
4. Make the repository private and wait for the next job: `NOT_FOUND at attempt
   1`, about 30 seconds later `FAILED at attempt 2`, and the form shows
   «Репозиторий недоступен: удалён или стал приватным.»
5. Wait for another job: `FAILED at attempt 1` after one request, and
   `unavailable_since` keeps its date.
6. Make the repository public again and wait for the next job: `SYNCED`, and the
   warning is gone after the form is reloaded.
7. Press «Обновить данные» right after a periodic job: the button shows its
   pause, as after a manual sync.

Checked by tests only: the batch limit, the reserve, a link during a 404, and a
rate limit between two 404s.

### Run tests

Tests require a PostgreSQL instance. Use the Docker Compose database or create a
separate test database:

```bash
# Create the test database (once):
docker exec -it developer-platform-postgres \
  psql -U developer -c "CREATE DATABASE developer_platform_test;"
```

Set `DATABASE_URL` to the test database and run pytest:

```bash
export DATABASE_URL="postgresql+psycopg://developer:<password>@localhost:5432/developer_platform_test"
cd backend
pytest
```

Replace `<password>` with the value of `POSTGRES_PASSWORD` from your `.env` file.
The test database is isolated from the dev database — each test runs in a
transaction that is rolled back at teardown.

If `DATABASE_URL` is not reachable, database tests are skipped automatically
with a clear message. The health endpoint test runs regardless.
