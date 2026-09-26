from panelprimepasar.security import AdminRole, Permission, has_permission


def test_owner_has_every_permission() -> None:
    for permission in Permission:
        assert has_permission(AdminRole.OWNER, permission)


def test_finance_permissions_are_scoped() -> None:
    assert has_permission(AdminRole.FINANCE, Permission.VIEW_PAYMENTS)
    assert has_permission(AdminRole.FINANCE, Permission.APPROVE_PAYMENTS)
    assert not has_permission(AdminRole.FINANCE, Permission.MANAGE_PASARGUARD)
    assert not has_permission(AdminRole.FINANCE, Permission.MANAGE_ADMINS)


def test_support_cannot_approve_payments() -> None:
    assert has_permission(AdminRole.SUPPORT, Permission.MANAGE_SUPPORT)
    assert not has_permission(AdminRole.SUPPORT, Permission.APPROVE_PAYMENTS)
