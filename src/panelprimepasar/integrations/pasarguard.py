from dataclasses import dataclass

import httpx


class PasarGuardError(RuntimeError):
    """Raised when the PasarGuard API cannot satisfy a request."""


@dataclass(slots=True)
class PasarGuardClient:
    base_url: str
    api_token: str
    timeout_seconds: float = 15.0

    async def health(self) -> bool:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.get("/health")
            return response.is_success

    async def close(self) -> None:
        return None
