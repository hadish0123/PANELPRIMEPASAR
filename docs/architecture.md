# Architecture

## Goal

PANELPRIMEPASAR sells PasarGuard reseller/admin access through Telegram.

## Production boundary

The bot is an independent service. It must **not** modify the PasarGuard or PasarGuard-Node repositories.

Target PasarGuard deployment:

- Railway project: `zealous-friendship`
- Panel: `https://pasarguard-production-558a.up.railway.app`

## High-level flow

```text
Telegram customer
      |
      v
PANELPRIMEPASAR
  |- customer bot flows
  |- admin flows
  |- plans/products
  |- orders
  |- payments
  |- provisioning
  |- audit log
      |
      +--> PostgreSQL
      +--> Redis
      +--> PostHog
      |
      v
PasarGuard Admin API
      |
      v
Customer reseller/admin account
```

## Design rules

1. Provisioning is idempotent.
2. Payment confirmation and provisioning are separate state transitions.
3. PasarGuard credentials and payment secrets are never logged.
4. PasarGuard integration lives behind an adapter.
5. The reseller role is configuration-driven and must be validated against the live panel before production provisioning.
6. Quotas are stored internally in bytes.
7. All externally-triggered writes must have an audit trail.
