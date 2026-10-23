FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app/ ./app/
COPY alembic.ini ./
COPY alembic/ ./alembic/

RUN pip install --no-cache-dir .

RUN groupadd --system app \
    && useradd --system --gid app --no-create-home app \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
