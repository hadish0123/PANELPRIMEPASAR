from enum import StrEnum


class AdminRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SALES = "sales"
    FINANCE = "finance"
    SUPPORT = "support"


class Permission(StrEnum):
    VIEW_DASHBOARD = "view_dashboard"
    MANAGE_USERS = "manage_users"
    MANAGE_PLANS = "manage_plans"
    VIEW_ORDERS = "view_orders"
    MANAGE_ORDERS = "manage_orders"
    APPROVE_PAYMENTS = "approve_payments"
    MANAGE_PASARGUARD = "manage_pasarguard"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_ADMINS = "manage_admins"


ROLE_PERMISSIONS: dict[AdminRole, frozenset[Permission]] = {
    AdminRole.OWNER: frozenset(Permission),
    AdminRole.ADMIN: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.MANAGE_USERS,
            Permission.MANAGE_PLANS,
            Permission.VIEW_ORDERS,
            Permission.MANAGE_ORDERS,
            Permission.APPROVE_PAYMENTS,
            Permission.MANAGE_PASARGUARD,
            Permission.VIEW_AUDIT_LOGS,
        }
    ),
    AdminRole.SALES: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_ORDERS,
            Permission.MANAGE_ORDERS,
            Permission.MANAGE_USERS,
        }
    ),
    AdminRole.FINANCE: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.VIEW_ORDERS,
            Permission.APPROVE_PAYMENTS,
            Permission.VIEW_AUDIT_LOGS,
        }
    ),
    AdminRole.SUPPORT: frozenset(
        {
            Permission.VIEW_DASHBOARD,
            Permission.MANAGE_USERS,
            Permission.VIEW_ORDERS,
        }
    ),
}


def has_permission(role: AdminRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
