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
exits; the backend starts only after it succeeds.

### Run the GitHub sync worker

The worker (ADR-018) takes sync jobs from the database, reads the repositories'
metadata and languages from GitHub with the app credentials, and recomputes
the relation of every link. It has no Compose service yet (step 6.6); with the
stack running, start it by hand on the backend image:

```bash
docker compose run --rm --no-deps backend python -m app.github.worker
```

Ctrl+C stops it after the current job. It exits with code 1 when GitHub
rejects the credentials or cannot be reached at startup. Jobs queued before
the first run (every link and import since step 6.2) run back to back, up to
7 GitHub requests each; the worker claims no job while GitHub's remaining
budget is at or below `GITHUB_WORKER_RESERVE`. To count them first:

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

Not run yet. Real GitHub, a repository of your own, the stack running after
`docker compose build backend`. Each step that changes the root `.env` ends by
putting the value back. The worker reads `.env` when it starts, so restart it
after a change.

1. Link the repository to a published project, and to a draft of another
   repository. Set `GITHUB_PERIODIC_SYNC_SECONDS=120` and start the worker: both
   links' jobs run once.
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
