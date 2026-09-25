from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field


class PasarGuardError(RuntimeError):
    """Base error raised by the PasarGuard integration."""


class PasarGuardConfigurationError(PasarGuardError):
    """Raised when required integration configuration is missing or ambiguous."""


class PasarGuardTransportError(PasarGuardError):
    """Raised when the PasarGuard service cannot be reached."""


class PasarGuardAuthError(PasarGuardError):
    """Raised when PasarGuard rejects the supplied credentials."""


class PasarGuardPermissionError(PasarGuardError):
    """Raised when credentials are valid but lack the required permission."""


class PasarGuardNotFoundError(PasarGuardError):
    """Raised when a requested PasarGuard resource does not exist."""


class PasarGuardConflictError(PasarGuardError):
    """Raised when PasarGuard reports a resource conflict."""


class PasarGuardRole(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    is_owner: bool = False


class PasarGuardRolesResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    roles: list[PasarGuardRole]
    total: int


class PasarGuardAdmin(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    username: str
    total_users: int = 0
    used_traffic: int = 0
    data_limit: int | None = None
    status: str = "active"
    role: PasarGuardRole | None = None


class PasarGuardAdminsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    admins: list[PasarGuardAdmin]
    total: int
    active: int = 0
    disabled: int = 0
    limited: int = 0


class PasarGuardAdminCreate(BaseModel):
    username: str
    password: str
    role_id: int = Field(ge=1)
    data_limit: int | None = Field(default=None, ge=0)
    note: str | None = None


class PasarGuardAdminModify(BaseModel):
    password: str | None = None
    role_id: int | None = Field(default=None, ge=1)
    data_limit: int | None = Field(default=None, ge=0)
    status: str | None = None
    note: str | None = None


class PasarGuardClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if api_key and bearer_token:
            raise PasarGuardConfigurationError(
                "Configure exactly one PasarGuard credential: API key or bearer token"
            )

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_seconds,
            follow_redirects=True,
        )

    def _auth_headers(self) -> dict[str, str]:
        if self.api_key:
            return {"X-Api-Key": self.api_key}
        if self.bearer_token:
            return {"Authorization": f"Bearer {self.bearer_token}"}
        raise PasarGuardConfigurationError(
            "PasarGuard credentials are required for protected API calls"
        )

    @staticmethod
    def _response_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.reason_phrase or "PasarGuard request failed"

        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail
        return response.reason_phrase or "PasarGuard request failed"

    @classmethod
    def _raise_for_status(cls, response: httpx.Response) -> None:
        if response.is_success:
            return

        detail = cls._response_detail(response)
        if response.status_code == 401:
            raise PasarGuardAuthError(detail)
        if response.status_code == 403:
            raise PasarGuardPermissionError(detail)
        if response.status_code == 404:
            raise PasarGuardNotFoundError(detail)
        if response.status_code == 409:
            raise PasarGuardConflictError(detail)
        raise PasarGuardError(
            f"PasarGuard returned HTTP {response.status_code}: {detail}"
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        protected: bool = True,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = self._auth_headers() if protected else {}
        try:
            response = await self._client.request(
                method,
                path,
                headers=headers,
                json=json,
                params=params,
            )
        except httpx.HTTPError as exc:
            raise PasarGuardTransportError("Could not reach PasarGuard") from exc

        self._raise_for_status(response)
        return response

    async def health(self) -> bool:
        try:
            response = await self._request("GET", "/health", protected=False)
        except PasarGuardError:
            return False
        return response.is_success

    async def get_current_admin(self) -> PasarGuardAdmin:
        response = await self._request("GET", "/api/admin")
        return PasarGuardAdmin.model_validate(response.json())

    async def list_roles_simple(self) -> list[PasarGuardRole]:
        response = await self._request("GET", "/api/admin-roles/simple")
        payload = PasarGuardRolesResponse.model_validate(response.json())
        return payload.roles

    async def resolve_reseller_role(
        self,
        *,
        role_id: int | None,
        role_name: str | None,
    ) -> PasarGuardRole:
        if role_id is None and not role_name:
            raise PasarGuardConfigurationError(
                "Configure PASARGUARD_RESELLER_ROLE_ID or PASARGUARD_RESELLER_ROLE_NAME"
            )

        normalized_name = role_name.strip().casefold() if role_name else None
        roles = await self.list_roles_simple()

        for role in roles:
            id_matches = role_id is None or role.id == role_id
            name_matches = (
                normalized_name is None
                or role.name.strip().casefold() == normalized_name
            )
            if id_matches and name_matches:
                if role.is_owner:
                    raise PasarGuardConfigurationError(
                        "The owner role cannot be used as the reseller role"
                    )
                return role

        raise PasarGuardConfigurationError(
            "Configured PasarGuard reseller role was not found"
        )

    async def find_admin_by_username(self, username: str) -> PasarGuardAdmin | None:
        response = await self._request(
            "GET",
            "/api/admins",
            params={"usernames": username, "limit": "1"},
        )
        payload = PasarGuardAdminsResponse.model_validate(response.json())
        for admin in payload.admins:
            if admin.username == username:
                return admin
        return None

    async def create_admin(
        self,
        *,
        username: str,
        password: str,
        role_id: int,
        data_limit: int | None,
        note: str | None = None,
    ) -> PasarGuardAdmin:
        payload = PasarGuardAdminCreate(
            username=username,
            password=password,
            role_id=role_id,
            data_limit=data_limit,
            note=note,
        )
        response = await self._request(
            "POST",
            "/api/admin",
            json=payload.model_dump(exclude_none=True),
        )
        return PasarGuardAdmin.model_validate(response.json())

    async def ensure_admin(
        self,
        *,
        username: str,
        password: str,
        role_id: int,
        data_limit: int | None,
        note: str | None = None,
    ) -> PasarGuardAdmin:
        existing = await self.find_admin_by_username(username)
        if existing is not None:
            if existing.id is None:
                raise PasarGuardError("Existing PasarGuard admin is missing its ID")
            return await self.modify_admin_by_id(
                existing.id,
                password=password,
                role_id=role_id,
                data_limit=data_limit,
                status="active",
                note=note,
            )

        try:
            return await self.create_admin(
                username=username,
                password=password,
                role_id=role_id,
                data_limit=data_limit,
                note=note,
            )
        except PasarGuardConflictError:
            existing = await self.find_admin_by_username(username)
            if existing is None or existing.id is None:
                raise
            return await self.modify_admin_by_id(
                existing.id,
                password=password,
                role_id=role_id,
                data_limit=data_limit,
                status="active",
                note=note,
            )

    async def modify_admin_by_id(
        self,
        admin_id: int,
        *,
        password: str | None = None,
        role_id: int | None = None,
        data_limit: int | None = None,
        status: str | None = None,
        note: str | None = None,
    ) -> PasarGuardAdmin:
        payload = PasarGuardAdminModify(
            password=password,
            role_id=role_id,
            data_limit=data_limit,
            status=status,
            note=note,
        )
        response = await self._request(
            "PUT",
            f"/api/admin/by-id/{admin_id}",
            json=payload.model_dump(exclude_none=True),
        )
        return PasarGuardAdmin.model_validate(response.json())

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
