FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn panelprimepasar.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
