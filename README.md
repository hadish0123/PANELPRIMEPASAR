# PANELPRIMEPASAR

Telegram sales, payment-review, and PasarGuard reseller/admin provisioning service.

## Current MVP

Implemented flow:

1. Owner creates traffic plans in Telegram.
2. Customer selects a plan and creates an idempotent order.
3. Customer uploads a payment receipt.
4. The receipt is forwarded to configured Telegram owners.
5. Owner approves the payment from the admin UI.
6. The order becomes `paid`.
7. The bot resolves the configured reseller role from the live PasarGuard role list.
8. The bot creates or reconciles the PasarGuard Admin account with the purchased `data_limit`.
9. Credentials are delivered to the customer.
10. Plaintext passwords are not stored. If delivery fails, the owner can rotate and reissue credentials.

No automatic external payment gateway is selected yet. The payment layer is provider-neutral,
and manual receipt approval is the working MVP provider path.

## Safety boundary

This repository is independent from the `PasarGuard`, `PasarGuard-Node`, and
`PasarguardBot` repositories. It integrates with PasarGuard only through its API.
Those repositories must not be modified by this project.

## Stack

- Python 3.13
- aiogram 3
- FastAPI
- PostgreSQL
- SQLAlchemy 2 + Alembic
- Redis-backed aiogram FSM
- httpx
- Pydantic Settings
- pytest / Ruff / mypy
- Docker
- Railway
- GitHub Actions

## Required production configuration

Copy `.env.example` as the configuration reference. Secrets belong in Railway variables,
not in Git.

Required for the Telegram service:

```text
APP_ENV=production
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_BASE_URL=https://<public-bot-domain>
TELEGRAM_WEBHOOK_SECRET=<random-secret>
TELEGRAM_OWNER_IDS=[123456789]
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
```

Manual payment instructions are plain customer-facing text configured through:

```text
MANUAL_PAYMENT_INSTRUCTIONS=...
```

Required for PasarGuard provisioning:

```text
PASARGUARD_BASE_URL=https://pasarguard-production-558a.up.railway.app
PASARGUARD_API_KEY=pg_key_...
PASARGUARD_RESELLER_ROLE_NAME=<live-role-name>
```

`PASARGUARD_RESELLER_ROLE_ID` may be used instead of the role name, or together with it
for stricter validation.

Do not configure both `PASARGUARD_API_KEY` and `PASARGUARD_BEARER_TOKEN`.

## PasarGuard least-privilege permissions

The dedicated bot API key should only receive the permissions required by this service:

- `admins.create`
- `admins.read`
- `admins.update`
- `admin_roles.read_simple`

The bot rejects a reseller role marked as owner.

## Database

Apply migrations with:

```bash
alembic upgrade head
```

The production Docker image runs migrations before starting Uvicorn.

Core tables:

- `customers`
- `plans`
- `orders`
- `payments`
- `pasarguard_accounts`
- `provisioning_jobs`
- `audit_events`

Quotas are stored in bytes. Plan input explicitly distinguishes decimal `GB/TB` from
binary `GiB/TiB`. Prices explicitly distinguish `IRT` from `IRR`.

## Local quality checks

```bash
pip install -e ".[dev]"
ruff check .
mypy
alembic upgrade head
pytest
docker build -t panelprimepasar:test .
```

CI also validates a PostgreSQL migration downgrade/upgrade round trip.

## Admin commands

Use `/admin` from a Telegram user ID listed in `TELEGRAM_OWNER_IDS`.

The admin UI supports:

- plan creation
- plan enable/disable
- recent orders
- manual payment approval
- provisioning retry
- credential rotation/reissue
- read-only PasarGuard diagnostics

## Documentation

- `docs/architecture.md`
- `docs/roadmap.md`
- `docs/pasarguard-contract.md`
