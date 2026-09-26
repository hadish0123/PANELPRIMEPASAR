# Repository audit — 2026-09-26

Baseline: `d13bcd01c2601ab597bd51a68ed83d01c9da414a`.

This repository is an independent FastAPI/aiogram commerce service. It provisions
PasarGuard **admin/reseller accounts**, not end-user VPN configurations. The existing
adapter and database are retained. Changes to PasarGuard or its node repositories
are outside this repository's scope.

## Baseline findings

- Seven domain tables and one migration; no persisted web administrator identities.
- Five read-only admin endpoints use one shared API key. The role permission table
  is not enforced by any route. No browser admin application exists.
- Telegram implements checkout, receipt upload, owner approval, provisioning retry
  and password reissue. Customer blocking is stored but not enforced.
- Payment verification can revive canceled orders; payment/order lock acquisition
  is inconsistent, so concurrent approval and verification can deadlock.
- Manual approval overwrites the original receipt reference.
- Credential reissue can change quota, role and active state unexpectedly.
- Unexpected upstream JSON can bypass provisioning error persistence.
- Liveness always reports OK; dependency readiness is absent.
- No production compose, backup procedure, worker or installation guide.
- No automatic gateways, reseller wallet hierarchy, service expiration/renewal,
  multiple PasarGuard targets, email delivery or client subscription engine.
- The configured plan validity is displayed and stored but is not enforced upstream.

## Baseline checks

Python 3.13.15 installed locally. The 17 tests not requiring PostgreSQL pass.
Ruff reports 10 findings and mypy one type error in the admin API.
Database tests require an isolated PostgreSQL instance, which is being prepared;
production data and production payment/provisioning credentials are not used.

## Implementation sequence

1. Recover the complete test environment and fix payment/order/security defects.
2. Persist administrator identities, authenticate with short-lived JWTs, enforce
   permissions, and retain the legacy key for existing integrations.
3. Add usable admin management flows with atomic audit records and an RTL UI.
4. Test real PostgreSQL transactions, HTTP authorization and failure scenarios;
   document deployment and remaining product gaps explicitly.
