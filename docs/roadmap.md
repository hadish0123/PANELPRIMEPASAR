# Roadmap

## Completed product scope

### Foundation

- Application scaffold and typed configuration
- PostgreSQL / Redis integration
- Alembic migrations and migration round-trip CI
- Ruff, mypy, pytest, Docker build quality gates
- Liveness and database readiness probes
- Railway container configuration

### Commerce domain

- Customers and blocking
- Traffic plans
- New, renewal, and top-up orders
- Manual payments and receipt review
- Card-to-card destinations
- Internal wallet and idempotent accounting
- Discount codes with reservation/redeem/release lifecycle
- ZarinPal, IDPay, Zibal, and NextPay adapters
- Server-side payment callback verification
- Configurable payment methods from Web Admin
- Encrypted gateway credentials at rest

### PasarGuard integration

- Configuration-driven reseller/admin roles
- Owner-role rejection
- Admin/reseller creation and reconciliation
- Quota assignment
- Credential rotation/reissue
- Subscription renewal and traffic top-up
- Multiple PasarGuard instances
- Weighted healthy-instance routing for new sales
- Existing-account instance pinning
- Health checks and failover for new provisioning
- Correct assigned panel URL delivery

### Telegram customer experience

- Onboarding and catalog
- Checkout
- Wallet, discount, card-to-card, manual receipt, and online gateway payment choices
- Order history
- Subscription listing
- Renewal and quota increase
- Profile/account view
- Support ticket creation and messaging
- Automatic reseller credential delivery

### Administration

- Telegram administration
- Database-backed multi-admin roles and permissions
- Owner / Admin / Sales / Finance / Support roles
- Customer, plan, order, payment, support, and audit operations
- Manual payment approval/rejection
- Unpaid-order cancellation
- Provisioning retry and credential reissue
- Web Admin authentication with signed sessions
- Role-aware Web Admin permissions
- Wallet credit and discount management
- Payment-method management
- Multi-PasarGuard management and health checks
- Web order actions

### Production hardening

- Idempotent payment and provisioning state transitions
- Duplicate gateway callback coverage
- Structured audit events
- Recursive audit secret redaction
- Payment credential encryption
- Database readiness checks
- Subscription expiry maintenance and notifications
- Stale discount reservation cleanup
- Backup, restore, secret-rotation, incident, and smoke-test runbook
- End-to-end database tests for purchase and renewal flows

## Deployment-time validation

The application code is release-ready when CI is green. The following steps require live
production credentials/infrastructure and therefore are operational validation rather than
unfinished application code:

- verify the exact custom reseller role against the live PasarGuard deployment;
- enter and test real payment-provider credentials;
- perform low-value live gateway transactions;
- run a real purchase, renewal, and top-up smoke test;
- confirm backup retention and restore access in the managed PostgreSQL provider;
- deploy the selected release to Railway when explicitly authorized.

Optional observability such as PostHog can be enabled later without changing the core sales,
payment, provisioning, or administration flows.
