import secrets

from fastapi import APIRouter, Header, HTTPException, status

from panelprimepasar.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])


def _check_admin_key(api_key: str | None) -> None:
    settings = get_settings()
    configured = settings.admin_panel_api_key
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin panel key is not configured",
        )

    if api_key is None or not secrets.compare_digest(
        api_key,
        configured.get_secret_value(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )


@router.get("/dashboard")
async def dashboard(
    x_admin_key: str | None = Header(default=None),
) -> dict[str, str]:
    _check_admin_key(x_admin_key)
    return {
        "panel": "PANELPRIMEPASAR",
        "status": "ready",
        "version": "full-development",
    }
