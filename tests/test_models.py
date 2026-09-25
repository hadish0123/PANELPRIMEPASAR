from panelprimepasar.models import Base


def test_core_tables_registered() -> None:
    expected = {
        "audit_events",
        "customers",
        "orders",
        "pasarguard_accounts",
        "payments",
        "plans",
        "provisioning_jobs",
    }

    assert expected.issubset(Base.metadata.tables)
