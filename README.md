# PANELPRIMEPASAR

Telegram sales, payment, support, wallet, discount, and PasarGuard reseller/admin provisioning service.

## Production flow

Implemented flow:

1. Owner creates traffic plans in Telegram.
2. Customer selects a plan and creates an idempotent order.
3. Customer chooses one of the enabled payment methods: wallet, card-to-card, ZarinPal,
   IDPay, Zibal, NextPay, or manual receipt flow.
4. Online gateway callbacks are verified server-side before an order is marked paid.
5. Manual receipts are reviewed by authorized staff.
6. The bot resolves the configured reseller role and selects the assigned PasarGuard
   instance. New orders use weighted healthy-instance routing; renewals/top-ups stay
   pinned to the original instance.
7. The bot creates or reconciles the PasarGuard Admin/Reseller account with the purchased
   `data_limit`.
8. Credentials are delivered to the customer. Plaintext reseller passwords are never
   persisted.
9. Subscription renewal, quota top-up, support tickets, discounts,
   wallet accounting, and audit events are handled by the same service.
10. Payment/provisioning transitions are idempotent so duplicate callbacks and retries do
    not create duplicate reseller accounts or double-charge wallet balance.

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

Manual payment instructions remain available as a fallback:

```text
MANUAL_PAYMENT_INSTRUCTIONS=...
```

For configurable online gateways:

```text
PAYMENT_CALLBACK_BASE_URL=https://<public-bot-domain>
PAYMENT_CREDENTIALS_MASTER_KEY=<random-secret-at-least-32-characters>
PAYMENT_HTTP_TIMEOUT_SECONDS=15
```

Gateway credentials are entered from Web Admin and encrypted before storage. The encryption
master key must only exist in the deployment secret store. Do not rotate it without first
re-encrypting stored gateway credentials.

Supported configurable payment methods:

- card-to-card (card number / holder / bank / optional IBAN)
- ZarinPal
- IDPay
- Zibal
- NextPay
- internal wallet

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

Core tables include:

- `customers`
- `plans`
- `orders`
- `payments`
- `payment_method_configs`
- `wallets` / `wallet_transactions`
- `discount_codes` / `discount_redemptions`
- `pasarguard_instances` / `pasarguard_accounts`
- `subscriptions`
- `support_tickets` / `support_messages`
- `staff_admins`
- `provisioning_jobs`
- `audit_events`

Quotas are stored in bytes internally, while every plan input and customer-facing value
uses decimal gigabytes (`GB`). A quota of `0` means unlimited traffic. Plans do not have
a day-based expiry because PasarGuard does not expose one. Prices explicitly distinguish
`IRT` from `IRR`.

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

## Administration

Telegram administration supports database-backed roles and permissions for Owner, Admin,
Sales, Finance, and Support staff. Owner IDs remain the bootstrap authority.

Web Admin supports signed sessions and role-aware access. Owner may bootstrap with
`ADMIN_PANEL_API_KEY`; staff accounts use username/password credentials.

Administration features include:

- plans, customers, orders, subscriptions, payments, wallet credit, discounts, and audit
- payment-method creation, update, enable/disable, and encrypted credentials
- card-to-card destination management
- support ticket operations
- staff/RBAC management
- manual payment approval/rejection and unpaid-order cancellation
- provisioning retry and credential rotation/reissue
- multiple PasarGuard instances with weights, health checks, enable/disable, and
  environment-variable based credentials

For multiple PasarGuard instances, store only the environment-variable name in Web Admin.
The actual API key/bearer token must be provided as a deployment environment variable.

## Documentation

- `docs/architecture.md`
- `docs/roadmap.md`
- `docs/pasarguard-contract.md`
- `docs/operations.md`


## Production release checklist

Before enabling real sales:

1. Run `alembic upgrade head` against the production PostgreSQL database.
2. Configure Telegram webhook secret, Redis, database URL, and owner IDs.
3. Configure PasarGuard credentials and validate the live reseller role.
4. Set `ADMIN_PANEL_API_KEY`, `ADMIN_PANEL_SESSION_SECRET`, and a strong
   `PAYMENT_CREDENTIALS_MASTER_KEY`.
5. Set `PAYMENT_CALLBACK_BASE_URL` to the public HTTPS application origin.
6. Add payment methods from Web Admin and first validate them in sandbox/test mode when the
   provider supports it.
7. Run the full CI suite and verify all jobs are green.
8. Perform one real low-value purchase, one renewal, and one top-up before opening sales.
