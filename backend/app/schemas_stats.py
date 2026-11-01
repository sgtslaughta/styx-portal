"""Schemas added with the Glance stats/overview work (split out of schemas.py)."""
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator

RELAY_REASONS = ("strict_nat", "firewall", "mobile", "unknown")


def _coerce_reason(v: Any) -> str:
    return v if isinstance(v, str) and v in RELAY_REASONS else "unknown"


# Any value is accepted; unknown/non-string values coerce to "unknown" (never a 422).
RelayReason = Annotated[str, BeforeValidator(_coerce_reason)]


class PendingInviteOut(BaseModel):
    id: str
    email: str | None
    role: str
    created_at: str
    expires_at: str | None


class InviteOut(BaseModel):
    token: str
    expires_at: str | None


class TempPasswordOut(BaseModel):
    temp_password: str
