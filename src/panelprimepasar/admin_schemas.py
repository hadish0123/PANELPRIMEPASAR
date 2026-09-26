from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from panelprimepasar.security.permissions import AdminRole

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    ),
]
Password = Annotated[str, Field(min_length=12, max_length=128)]
PositiveBigInt = Annotated[int, Field(gt=0, le=2**63 - 1, strict=True)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    username: Username
    password: Annotated[str, Field(min_length=1, max_length=128)]


class PlanInput(Input):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=128)]
    description: str = Field(default="", max_length=2000)
    quota_bytes: PositiveBigInt
    price_amount: PositiveBigInt
    currency: Literal["IRT", "IRR", "USD", "EUR"] = "IRT"
    validity_days: Annotated[int, Field(ge=1, le=36500, strict=True)] | None = None
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0, le=1000000)


class BlockCustomer(Input):
    blocked: bool


class AdminInput(Input):
    username: Username
    password: Password
    role: AdminRole


class AdminUpdate(Input):
    role: AdminRole
    is_active: bool


class PasswordInput(Input):
    password: Password
