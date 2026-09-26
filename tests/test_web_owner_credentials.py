from panelprimepasar.admin_panel import _owner_credentials_valid
from panelprimepasar.config import Settings
from panelprimepasar.security import hash_password


def test_owner_username_password_authentication() -> None:
    password = "ExamplePassphrase123!"
    settings = Settings(
        admin_panel_owner_username="OwnerExample",
        admin_panel_owner_password_hash=hash_password(password),
    )

    assert _owner_credentials_valid(
        settings,
        username="OwnerExample",
        password=password,
    )
    assert not _owner_credentials_valid(
        settings,
        username="ownerexample",
        password=password,
    )
    assert not _owner_credentials_valid(
        settings,
        username="OwnerExample",
        password="DifferentPassphrase456!",
    )


def test_owner_credentials_disabled_without_hash() -> None:
    settings = Settings(admin_panel_owner_username="OwnerExample")

    assert not _owner_credentials_valid(
        settings,
        username="OwnerExample",
        password="ExamplePassphrase123!",
    )
