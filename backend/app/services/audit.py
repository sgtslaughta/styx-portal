"""Append-only audit trail. Call sites must commit (or be committed by caller)."""
from fastapi import Request

from app.middleware.rate_limit import client_ip_from_headers
from app.models import AuditLog

_REDACT_KEYS = {"client_secret", "password", "token", "secret", "authorization"}


def _redact(detail: dict | None) -> dict | None:
    if not detail:
        return detail
    return {k: ("[redacted]" if k.lower() in _REDACT_KEYS else v)
            for k, v in detail.items()}


async def audit(session, action: str, *, user_id: str | None = None,
                actor_ip: str | None = None, resource: str | None = None,
                detail: dict | None = None) -> None:
    session.add(AuditLog(action=action, user_id=user_id, actor_ip=actor_ip,
                         resource=resource, detail=_redact(detail)))


async def audit_request(session, request: Request, action: str, *,
                        user_id: str | None = None, resource: str | None = None,
                        detail: dict | None = None) -> None:
    await audit(session, action, user_id=user_id, resource=resource,
                detail=detail, actor_ip=client_ip_from_headers(request))
