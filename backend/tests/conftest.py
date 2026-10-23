import os

# Set required env vars before any app module is imported during test collection.
# DATABASE_URL has no default in settings; this satisfies the validator without
# connecting to a real database (the health endpoint does not use the DB).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://test:test@localhost:5432/developer_platform_test",
)
