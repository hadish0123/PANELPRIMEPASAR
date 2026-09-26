FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN pip install . && useradd --system --uid 10001 --create-home app

USER app

EXPOSE 8080

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn panelprimepasar.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
