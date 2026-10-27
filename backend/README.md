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
