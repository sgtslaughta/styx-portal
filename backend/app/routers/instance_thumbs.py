"""Browser-uploaded instance thumbnails (the streaming tab PUTs a small frame).

Stored where GET /api/instances/{id}/screenshot already reads ({id}.png in the
screenshot cache dir; the bytes may be webp/jpeg, GET sniffs the type)."""
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import Instance, User
from app.security.deps import get_current_user, require_owner_or_admin

router = APIRouter()

MAX_BYTES = 200 * 1024
MIN_INTERVAL_S = 20
# ponytail: per-process dict is enough (single backend); resets on restart, bounded by instance count.
_last_upload: dict[str, float] = {}


def thumb_dir() -> Path:
    return Path(Settings().SCREENSHOT_CACHE_DIR)


def sniff_image_type(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return None


@router.put("/{instance_id}/screenshot")
async def upload_thumbnail(
    instance_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)

    if int(request.headers.get("content-length") or 0) > MAX_BYTES:
        raise HTTPException(413, "Thumbnail too large")
    now = time.monotonic()
    if now - _last_upload.get(instance_id, -MIN_INTERVAL_S) < MIN_INTERVAL_S:
        return Response(status_code=204)
    # request.body(): BaseHTTPMiddleware (CSRF) already buffered the stream.
    data = await request.body()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Thumbnail too large")
    if sniff_image_type(data) is None:
        raise HTTPException(415, "Only webp or jpeg images are accepted")

    d = thumb_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{instance_id}.png.tmp"
    tmp.write_bytes(data)
    tmp.replace(d / f"{instance_id}.png")
    _last_upload[instance_id] = now
    return {"ok": True}


def head(path: Path) -> bytes:
    with path.open("rb") as f:
        return f.read(12)
