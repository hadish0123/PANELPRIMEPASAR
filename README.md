# PANELPRIMEPASAR

Telegram sales, payment-review, and PasarGuard reseller/admin provisioning service.

## Current capabilities

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

Web administration is available at `/admin/ui` with a Persian RTL interface, individual
administrator accounts, JWT authentication, Argon2 password hashing, role checks,
Redis login limits and an audit trail. It supports plan CRUD, customer lookup/blocking,
order review/cancellation, manual payment approval/rejection, receipt download,
provisioning/reissue, administrator management and currency-aware sales metrics.

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

See [Installation and operations](docs/installation.md) for deployment, administrator
bootstrap, environment variables, backup and restore, and current product limitations.

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

The admin API accepts a JWT bearer token or the legacy owner `X-Admin-Key`. `GET /admin/customers` supports
`search` (Telegram username or exact numeric Telegram ID), `blocked`, `offset`,
and `limit`. `GET /admin/orders` supports `status`, `offset`, and `limit`.
Both endpoints keep their existing list response format; pagination defaults to
100 records and caps each request at 100. Invalid filters return HTTP 422.

## Documentation

- `docs/architecture.md`
- `docs/roadmap.md`
- `docs/pasarguard-contract.md`
- `docs/installation.md`
- `docs/repository-audit.md`

## Verification

GitHub Actions runs Python 3.13, Ruff, mypy, PostgreSQL/Redis integration tests,
Alembic upgrade/downgrade/upgrade, browser E2E and the production Docker build.
The broader SaaS roadmap is still in progress; see the explicit gaps in the installation guide.
