FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app/ ./app/
COPY alembic.ini ./
COPY alembic/ ./alembic/

COPY requirements.lock ./
RUN pip install --no-cache-dir -c requirements.lock .

# The media volume's mount point (ADR-0022): an empty named volume takes the
# owner of this directory on its first mount, so the app user can write to it.
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home app \
    && chown -R app:app /app \
    && mkdir -p /srv/media \
    && chown app:app /srv/media

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
