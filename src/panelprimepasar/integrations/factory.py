from panelprimepasar.config import Settings
from panelprimepasar.integrations.pasarguard import (
    PasarGuardClient,
    PasarGuardConfigurationError,
)


def build_pasarguard_client(settings: Settings) -> PasarGuardClient:
    api_key = (
        settings.pasarguard_api_key.get_secret_value()
        if settings.pasarguard_api_key is not None
        else None
    )
    bearer_token = (
        settings.pasarguard_bearer_token.get_secret_value()
        if settings.pasarguard_bearer_token is not None
        else None
    )

    if api_key is None and bearer_token is None:
        raise PasarGuardConfigurationError(
            "Configure PASARGUARD_API_KEY or PASARGUARD_BEARER_TOKEN"
        )

    return PasarGuardClient(
        base_url=str(settings.pasarguard_base_url),
        api_key=api_key,
        bearer_token=bearer_token,
        timeout_seconds=settings.pasarguard_timeout_seconds,
    )
