from enum import StrEnum


class AdminRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SALES = "sales"
    FINANCE = "finance"
    SUPPORT = "support"


class Permission(StrEnum):
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_USERS = "view_users"
    MANAGE_USERS = "manage_users"
    MANAGE_PLANS = "manage_plans"
    VIEW_ORDERS = "view_orders"
    MANAGE_ORDERS = "manage_orders"
    VIEW_PAYMENTS = "view_payments"
    APPROVE_PAYMENTS = "approve_payments"
    MANAGE_WALLETS = "manage_wallets"
    MANAGE_DISCOUNTS = "manage_discounts"
    MANAGE_PASARGUARD = "manage_pasarguard"
    MANAGE_SUPPORT = "manage_support"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_ADMINS = "manage_admins"


ROLE_PERMISSIONS: dict[AdminRole, frozenset[Permission]] = {
    AdminRole.OWNER: frozenset(Permission),
    AdminRole.ADMIN: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_USERS,
            Permission.MANAGE_USERS,
            Permission.MANAGE_PLANS,
            Permission.VIEW_ORDERS,
            Permission.MANAGE_ORDERS,
            Permission.VIEW_PAYMENTS,
            Permission.APPROVE_PAYMENTS,
            Permission.MANAGE_WALLETS,
            Permission.MANAGE_DISCOUNTS,
            Permission.MANAGE_PASARGUARD,
            Permission.MANAGE_SUPPORT,
            Permission.VIEW_AUDIT_LOGS,
        }
    ),
    AdminRole.SALES: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_USERS,
            Permission.MANAGE_USERS,
            Permission.VIEW_ORDERS,
            Permission.MANAGE_ORDERS,
        }
    ),
    AdminRole.FINANCE: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_ORDERS,
            Permission.VIEW_PAYMENTS,
            Permission.APPROVE_PAYMENTS,
            Permission.MANAGE_WALLETS,
            Permission.VIEW_AUDIT_LOGS,
        }
    ),
    AdminRole.SUPPORT: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_USERS,
            Permission.VIEW_ORDERS,
            Permission.MANAGE_SUPPORT,
        }
    ),
}


def has_permission(role: AdminRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
