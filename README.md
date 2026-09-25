# PANELPRIMEPASAR

Production-grade Telegram sales and provisioning bot for PasarGuard reseller/admin panels.

## Status

Initial architecture and application scaffold.

## Safety boundary

This repository is independent from the PasarGuard and PasarGuard-Node repositories. It integrates with PasarGuard only through its public/admin API and must not modify those codebases.

## Core stack

- Python 3.13
- aiogram 3
- FastAPI
- PostgreSQL
- SQLAlchemy 2 + Alembic
- Redis
- httpx
- Pydantic Settings
- pytest / Ruff / mypy
- Railway
- GitHub Actions

See `docs/architecture.md` for the system design.
