# Production operations runbook

This runbook covers release, backup, recovery, credential rotation, and smoke testing for
PANELPRIMEPASAR. It does not modify PasarGuard or PasarGuard-Node.

## Release prerequisites

Before enabling customer sales:

- GitHub Actions on the exact release commit must be green.
- PostgreSQL and Redis must be reachable from the application.
- `/ready` must return HTTP 200.
- Telegram webhook URL and secret must be configured.
- Web Admin owner/session secrets must be configured.
- PasarGuard credentials must be stored only in deployment environment variables.
- The configured reseller role must be verified against the live PasarGuard instance.
- `PAYMENT_CREDENTIALS_MASTER_KEY` must be at least 32 random characters and backed up
  in the deployment secret store.
- `PAYMENT_CALLBACK_BASE_URL` must point at the public HTTPS application origin.
- Real gateway methods should remain disabled until their credentials have been tested.

## Database migration

The container runs `alembic upgrade head` before Uvicorn starts. For a controlled release,
take a database backup before deploying a migration-bearing commit.

Manual migration check:

```bash
alembic current
alembic upgrade head
alembic current
```

Do not run downgrade operations against production unless recovery has been rehearsed and
a current backup exists.

## Backup

Use the managed PostgreSQL provider's automated backups as the primary backup mechanism.
Before a high-risk release, create an additional on-demand database snapshot.

A logical backup may also be created with the provider's PostgreSQL connection string:

```bash
pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL_SYNC" > panelprimepasar.dump
```

Store backups encrypted and outside the application repository. Never commit database dumps,
API keys, bot tokens, payment credentials, or encryption keys to Git.

Redis contains transient FSM state and is not the system of record. PostgreSQL is the
authoritative store for orders, payments, subscriptions, wallets, discounts, support, and
audit events.

## Restore

For a full database restore:

1. Stop customer writes or put the application into maintenance/offline mode.
2. Provision a clean PostgreSQL database.
3. Restore the selected snapshot or logical dump.
4. Point `DATABASE_URL` at the restored database.
5. Run `alembic upgrade head`.
6. Start the application and verify `/health` and `/ready`.
7. Check recent orders, verified payments, wallet balances, subscriptions, and audit events.
8. Run a low-value end-to-end test before reopening sales.

Example logical restore:

```bash
pg_restore --clean --if-exists --no-owner --no-acl --dbname "$DATABASE_URL_SYNC" panelprimepasar.dump
```

## Secret rotation

### Telegram

Rotate `TELEGRAM_BOT_TOKEN` through BotFather and replace the deployment secret. Rotate
`TELEGRAM_WEBHOOK_SECRET` independently and restart the service so the webhook is
re-registered.

### Web Admin

Rotate `ADMIN_PANEL_API_KEY` and `ADMIN_PANEL_SESSION_SECRET` in the deployment secret
store. Rotating the session secret intentionally invalidates existing Web Admin sessions.

### Payment credential master key

Do not simply replace `PAYMENT_CREDENTIALS_MASTER_KEY` while encrypted gateway credentials
exist. Existing credentials are encrypted with that key.

Safe rotation procedure:

1. Disable online payment methods.
2. Record the gateway credential values from the payment providers' own dashboards.
3. Replace `PAYMENT_CREDENTIALS_MASTER_KEY`.
4. Re-enter each gateway credential from Web Admin so it is encrypted with the new key.
5. Test each gateway.
6. Re-enable successful methods.

### PasarGuard

For each PasarGuard instance, Web Admin stores only the environment-variable name containing
the credential. Rotate the real API key/bearer token in PasarGuard and then replace the value
of that environment variable in the deployment platform.

## Payment incident handling

Never mark an online payment successful from callback query parameters alone. The application
verifies the transaction server-side with the selected provider before changing the order to
`paid`.

If a provider is degraded:

1. Disable that payment method from Web Admin.
2. Keep wallet/card-to-card/other healthy methods enabled.
3. Do not delete pending payment rows.
4. Reconcile disputed transactions against the provider dashboard and the audit log.
5. Retry fulfillment only after payment status is verified.

Duplicate callbacks and fulfillment retries are designed to be idempotent.

## PasarGuard incident handling

If one PasarGuard instance is unhealthy:

1. Run the Web Admin health check.
2. Disable the unhealthy instance for new sales.
3. Existing reseller accounts remain pinned to their original instance for renewal/top-up.
4. Restore that instance before performing lifecycle operations for accounts assigned to it.
5. Never silently migrate an existing reseller account to another PasarGuard instance.

New reseller orders use weighted healthy-instance selection and can fail over to another
enabled healthy instance.

## Smoke test

After every production release, verify:

1. `GET /health` returns `{"status":"ok"}`.
2. `GET /ready` returns `{"status":"ready"}`.
3. Telegram `/start` and customer menu work.
4. Web Admin login works for Owner and one restricted staff role.
5. Create a temporary low-value plan.
6. Create an order and confirm the configured payment methods are shown.
7. Complete one payment path in test/sandbox mode where supported.
8. Confirm server-side verification changes the payment/order state.
9. Confirm reseller provisioning creates an Admin/Reseller, not a normal VPN user.
10. Confirm the customer receives the assigned PasarGuard instance URL and credentials.
11. Test one renewal and one quota top-up.
12. Confirm the audit log contains the actions but no passwords, API keys, tokens, or
    payment secrets.

## Rollback

Application rollback should normally use the previous known-good container/image or Git
revision while keeping the database at the newest compatible migration level.

If a release includes a schema migration that is not backward-compatible:

- stop writes;
- restore the pre-release database snapshot;
- deploy the previous application revision;
- validate `/ready` and run the smoke checks before reopening sales.

Do not attempt an improvised production Alembic downgrade without a backup.
