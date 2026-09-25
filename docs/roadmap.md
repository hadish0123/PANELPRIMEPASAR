# Roadmap

## Phase 1 - Foundation

- Application scaffold
- Typed configuration
- PostgreSQL/Redis integration
- CI quality gates
- Health checks
- Internal documentation

## Phase 2 - Domain model

- Customers
- Plans
- Orders
- Payments
- PasarGuard accounts
- Provisioning jobs
- Audit events

## Phase 3 - PasarGuard integration

- Verify live authentication mechanism
- Read live admin roles
- Resolve "نماینده کل" / "نمایندگان"
- Create reseller/admin account
- Apply quota
- Disable/enable/update reseller account
- Idempotent retries

## Phase 4 - Telegram UX

- Customer onboarding
- Catalog
- Checkout
- Payment status
- Account delivery
- Renewal / traffic increase
- Support

## Phase 5 - Admin UX

- Plan management
- Order management
- Payment approval/reconciliation
- Customer lookup
- Provisioning retry
- Audit log
- Operator permissions

## Phase 6 - Production hardening

- Redis-backed FSM / locks
- PostHog events and error capture
- Rate limiting
- Security review
- Backup/recovery runbook
- Railway deployment
- End-to-end QA
