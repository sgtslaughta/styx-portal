"""Public enrollment endpoints — token-gated or static; no cookie auth.

CSRF-exempt by path prefix (see main.py): agents have no cookies.
"""
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import Workstation, WorkstationEnrollmentToken
from app.schemas import WorkstationRegisterRequest, WorkstationRegisterResponse
from app.security.crypto import encrypt_secret
from app.services import single_use
from app.services.audit import audit_request
from app.services.workstations import (
    AGENT_UPDATE_FILES, SELKIES_USER, sha256_hex, unique_subdomain,
)

router = APIRouter()
_settings = Settings()

# Allowlist: URL name -> file in the agent dir. Only these keys are served.
_SERVED = {remote: local for remote, local in AGENT_UPDATE_FILES} | {
    "script": "enroll.sh", "uninstall": "uninstall.sh"}


def _agent_dir() -> Path:
    p = Path(_settings.AGENT_DIR)
    if p.is_dir():
        return p
    # Dev fallback: repo layout backend/app/routers/ -> repo root /agent
    return Path(__file__).resolve().parents[3] / "agent"


def _serve(filename: str) -> PlainTextResponse:
    path = _agent_dir() / filename
    if not path.is_file():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"Agent file {filename} missing on server — "
                            f"check the ./agent mount (AGENT_DIR).")
    return PlainTextResponse(path.read_text())


@router.get("/artifacts/{name}")
async def artifact(name: str):
    from app.services.artifacts import ARTIFACTS, ArtifactMissing, ensure_artifact
    if name not in ARTIFACTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such artifact: {name}")
    try:
        path = await ensure_artifact(name)
    except ArtifactMissing as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
    except Exception as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Artifact {name} unavailable ({e.__class__.__name__}). "
            "Check network or pre-place it in the artifact cache.")
    return FileResponse(path, media_type="application/gzip", filename=name)


@router.post("/register", response_model=WorkstationRegisterResponse,
             status_code=201)
async def register(body: WorkstationRegisterRequest, request: Request,
                   session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    result = await session.exec(select(WorkstationEnrollmentToken).where(
        WorkstationEnrollmentToken.token_hash == sha256_hex(body.token)))
    tok = result.first()
    expires = tok.expires_at if tok else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if tok is None or tok.used_at is not None or (expires and expires < now):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Invalid, expired, or already-used enrollment token")
    if not await single_use.claim(session, WorkstationEnrollmentToken, tok.id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Invalid, expired, or already-used enrollment token")

    agent_token = secrets.token_urlsafe(32)
    selkies_password = secrets.token_urlsafe(16)
    subdomain = await unique_subdomain(session, body.hostname)
    ws = Workstation(
        name=body.hostname, subdomain=subdomain, hostname=body.hostname,
        lan_ip=body.lan_ip, port=body.port or _settings.WORKSTATION_DEFAULT_PORT,
        display_server=body.display_server, gpu_info=body.gpu_info,
        os_info=body.os_info, agent_version=body.agent_version,
        agent_token_hash=sha256_hex(agent_token),
        selkies_password_enc=encrypt_secret(selkies_password),
        created_by=tok.created_by,
    )
    session.add(ws)
    await audit_request(session, request, "workstation.register",
                        resource=ws.id,
                        detail={"hostname": body.hostname, "lan_ip": body.lan_ip,
                                "display_server": body.display_server})
    await session.commit()
    return WorkstationRegisterResponse(
        workstation_id=ws.id, agent_token=agent_token, subdomain=subdomain,
        selkies_user=SELKIES_USER, selkies_password=selkies_password,
        port=ws.port, stream_settings=ws.stream_settings,
        heartbeat_interval_s=_settings.WORKSTATION_HEARTBEAT_S)


# Must stay LAST: catch-all would shadow any route registered after it.
@router.get("/{name}")
async def agent_file(name: str):
    if name not in _SERVED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such file: {name}")
    return _serve(_SERVED[name])
