# Installation and operations

## Runtime and dependencies

Use **Python 3.13**, PostgreSQL 17 and Redis 7. Production code remains the existing
FastAPI/aiogram application. No Node build step is needed for the bundled admin UI.
PasarGuard is a separate service; configure an API credential and a non-owner reseller
role. Existing migrations and Telegram owner commands remain supported.

## Docker Compose on a server

1. Copy `.env.example` to `.env` and fill the configuration below. Never commit `.env`.
   For each password/JWT secret, generate a separate value with
   `python -c 'import secrets; print(secrets.token_urlsafe(48))'`.
   Compose database/Redis passwords must be URL-safe because they are used in URLs.
2. Configure HTTPS termination with your existing reverse proxy. The application
   binds to `127.0.0.1:8080`; PostgreSQL and Redis have no host-exposed ports.
3. Start the containers:

   ```bash
   docker compose -f docker-compose.production.yml up -d --build
   docker compose -f docker-compose.production.yml logs --tail=100 migrate web
   ```

4. Create the initial owner; the password is requested securely in the terminal:

   ```bash
   docker compose -f docker-compose.production.yml exec web \
     python -m panelprimepasar.manage create-admin --username owner --role owner
   ```

5. Open `https://YOUR-DOMAIN/admin/ui`. Log in and create other administrators from
   the **مدیران** section. Supported roles: owner, admin, sales, finance and support.
6. Check `/health/ready`. Both dependencies must report `ok`. `/health` remains a
   process liveness endpoint for backward compatibility.

Only trust forwarding headers from the actual reverse proxy. Configure Uvicorn's
`--forwarded-allow-ips` with that proxy's address if needed. Do not trust arbitrary
client `X-Forwarded-For` headers; login rate limits use the trusted connection IP.
All sessions use Authorization headers. The UI keeps its JWT in memory, sends no
cookies, and requires login after refresh. Changing a password, changing a role,
disabling an administrator or logging out revokes that administrator's existing tokens.
The last active owner cannot be disabled or demoted through the API.

## Railway / existing installation

Keep the existing database, Redis and PasarGuard variables. The image still runs
`alembic upgrade head` before Uvicorn. Migration `0002` only adds `web_admins` and
an empty plan description; it does not rewrite orders, payments or customers.
Add `ADMIN_JWT_SECRET` and bootstrap an administrator using a trusted shell connected
to the same database. Alternatively an existing `ADMIN_PANEL_API_KEY` owner integration
can call `POST /admin/admins` to create the first account.

Existing `X-Admin-Key` calls remain supported as owner access. Remove this variable
when all integrations have migrated to individual administrator authentication.
Do not put the key in a URL, frontend configuration or browser storage.

## Local development and checks

```bash
uv python install 3.13
uv venv --python 3.13
uv pip install -e '.[dev]'
# Activate .venv using your shell, then configure a disposable DATABASE_URL and REDIS_URL.
alembic upgrade head
ruff check .
mypy
pytest
playwright install chromium
python tests/browser/admin_flow.py
uvicorn panelprimepasar.api:app --reload
```

Run tests only against a disposable database. API tests isolate writes in database
transactions. The browser test creates a real test administrator and plan, then removes
them; CI recreates its database before the browser check. Unit integration adapters use
controlled upstream responses and do not contact a live PasarGuard or payment gateway.

## Configuration reference

Blank optional values in `.env` are ignored.

| Variable | Purpose / default |
| --- | --- |
| `APP_ENV` | `development`; use `production` for deployed Telegram validation |
| `LOG_LEVEL` | `INFO`; retained application setting |
| `HOST`, `PORT` | Bind configuration; container command uses port 8080 or Railway `PORT` |
| `DATABASE_URL` | SQLAlchemy `postgresql+asyncpg://…`; required in deployed environments |
| `REDIS_URL` | Redis URL for Telegram FSM and shared login limits |
| `ADMIN_JWT_SECRET` | At least 32 random characters; required for username/password login |
| `ADMIN_TOKEN_MINUTES` | JWT lifetime, default 30, range 5–120 |
| `ADMIN_LOGIN_ATTEMPTS` | Shared per-IP and per-username login limit, default 10 |
| `ADMIN_LOGIN_WINDOW_SECONDS` | Limit window, default 300 seconds |
| `ADMIN_PANEL_API_KEY` | Optional legacy owner credential; keep secret |
| `TELEGRAM_BOT_TOKEN` | Bot token; optional for admin-only use |
| `TELEGRAM_WEBHOOK_BASE_URL` | Public HTTPS origin; bot webhook path is `/telegram/webhook` |
| `TELEGRAM_WEBHOOK_SECRET` | Random webhook authentication secret |
| `TELEGRAM_OWNER_IDS` | JSON list of Telegram owners, such as `[123456789]` |
| `MANUAL_PAYMENT_INSTRUCTIONS` | Customer-facing bank transfer instructions |
| `PASARGUARD_BASE_URL` | Existing deployment default; override for your panel |
| `PASARGUARD_API_KEY` | Dedicated integration credential, exclusive with bearer token |
| `PASARGUARD_BEARER_TOKEN` | Alternative integration credential |
| `PASARGUARD_TIMEOUT_SECONDS` | Upstream request timeout, default 15 |
| `PASARGUARD_RESELLER_ROLE_ID` | Optional configured role ID; ID or name required for provisioning |
| `PASARGUARD_RESELLER_ROLE_NAME` | Optional exact role name; owner roles are rejected |
| `POSTGRES_PASSWORD` | Compose only; URL-safe random value |
| `REDIS_PASSWORD` | Compose only; URL-safe random value |
| `POSTHOG_API_KEY`, `POSTHOG_HOST` | Reserved existing settings; no analytics exporter is implemented |

## Payments and provisioning

Approval verifies a manual payment and commits the payment state. The web admin then
runs **ساخت حساب / تلاش مجدد** from the order details; finance users cannot provision.
The Telegram owner's existing approve-and-provision flow is preserved. Unpaid orders
can be canceled; paid orders require a separate refund policy and are not silently
canceled. Rejected manual receipts can be resubmitted by the customer.

Credentials are generated per provisioning attempt and delivered through Telegram.
No plaintext password is persisted or returned by the admin API. If delivery fails,
use **تغییر رمز و ارسال مجدد**. Rotation changes only the upstream password and leaves
quota, role and account status intact. Provisioning failures and delivery outcomes
are audited. An already provisioned order does not create another account on retry.

Daily/monthly sales are grouped by currency and use the Tehran timezone. IRR and IRT
are never summed together. In this version the month is a **Gregorian calendar month**
measured in Tehran time. Financial reporting is based on verified payments.

## Backup and restore

Create a PostgreSQL backup before applying production migrations:

```bash
docker compose -f docker-compose.production.yml exec -T postgres \
  pg_dump -U panelprimepasar -d panelprimepasar -Fc > panelprimepasar.backup
```

Store encrypted backup copies outside the server, restrict file access and regularly
restore into an isolated database to verify them. A restore **replaces data**; stop
application writes first and inspect the target database before executing:

```bash
docker compose -f docker-compose.production.yml stop web
docker compose -f docker-compose.production.yml exec -T postgres \
  pg_restore -U panelprimepasar -d panelprimepasar --clean --if-exists < panelprimepasar.backup
docker compose -f docker-compose.production.yml up -d web
```

Redis AOF is persisted in a volume. PostgreSQL is the source of truth for orders,
payments, administrators and provisioning; Redis contains short-lived conversation
state and login limits. Never execute Alembic downgrade against production merely
to roll back code: it deletes administrator identities/columns. Restore a verified
backup or apply a forward corrective migration.

## Remaining product work

This release adds an operational web administration layer to the existing reseller
sales system. It is not the entire proposed SaaS. Automatic service expiration and
renewal, reseller wallet/commission trees, external payment gateways, multi-panel
selection, email delivery and a durable background provisioning worker are not
implemented. Plan validity is recorded/displayed but automatic expiry is not enforced;
do not sell automatic time-based cutoff until that service engine is implemented.
