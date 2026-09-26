from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    app_env: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8080

    telegram_bot_token: SecretStr | None = None
    telegram_webhook_base_url: AnyHttpUrl | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_owner_ids: list[int] = []
    manual_payment_instructions: str | None = None

    admin_panel_api_key: SecretStr | None = None
    admin_jwt_secret: SecretStr | None = None
    admin_token_minutes: int = Field(default=30, ge=5, le=120)
    admin_login_attempts: int = Field(default=10, ge=1, le=100)
    admin_login_window_seconds: int = Field(default=300, ge=30, le=3600)

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/panelprimepasar"
    redis_url: str = "redis://localhost:6379/0"

    pasarguard_base_url: AnyHttpUrl = AnyHttpUrl(
        "https://pasarguard-production-558a.up.railway.app"
    )
    pasarguard_api_key: SecretStr | None = None
    pasarguard_bearer_token: SecretStr | None = None
    pasarguard_timeout_seconds: float = 15.0
    pasarguard_reseller_role_name: str | None = None
    pasarguard_reseller_role_id: int | None = None

    posthog_api_key: SecretStr | None = None
    posthog_host: AnyHttpUrl | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
