import threading
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import User
from app.security.deps import get_current_user

router = APIRouter()

LSIO_API_URL = "https://api.linuxserver.io/api/v1/images?include_config=true&include_deprecated=false"
_cache: dict = {"data": None, "fetched_at": 0, "failed_at": 0}
CACHE_TTL = 3600
FAIL_TTL = 60
_lock = threading.Lock()


class _RegistryDown(httpx.HTTPError):
    pass

_URL_FIELDS = ("project_url", "github_url", "project_logo")


def _clean(images: list) -> list[dict]:
    """The registry is third-party data: keep only https URLs in link/image fields."""
    out = []
    for img in images:
        if not isinstance(img, dict):
            continue
        img = dict(img)
        for f in _URL_FIELDS:
            v = img.get(f)
            if v is not None and not (isinstance(v, str) and v.lower().startswith("https://")):
                img[f] = None
        out.append(img)
    return out


def _fetch_images() -> list[dict]:
    with _lock:   # one upstream fetch at a time; waiters reuse its result
        now = time.time()
        fresh = _cache["data"] is not None and (now - _cache["fetched_at"]) < CACHE_TTL
        if fresh:
            return _cache["data"]
        if (now - _cache["failed_at"]) < FAIL_TTL:      # negative cache: serve stale or fail fast
            if _cache["data"] is not None:
                return _cache["data"]
            raise _RegistryDown("registry recently unreachable")
        try:
            resp = httpx.get(LSIO_API_URL, timeout=30)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError:
            _cache["failed_at"] = now
            if _cache["data"] is not None:
                return _cache["data"]
            raise
        # Structure: {"status": "OK", "data": {"repositories": {"linuxserver": [...]}}}
        try:
            raw = body["data"]["repositories"]["linuxserver"]
        except (KeyError, TypeError):
            raw = body if isinstance(body, list) else []
        _cache["data"] = _clean(raw)
        _cache["fetched_at"] = now
        return _cache["data"]


@router.get("")
def list_images(
    category: str | None = Query(None),
    search: str | None = Query(None),
    user: User = Depends(get_current_user),
):
    try:
        images = _fetch_images()
    except httpx.HTTPError:
        raise HTTPException(502, "Failed to fetch LinuxServer registry")

    if category:
        images = [
            img for img in images
            if category.lower() in (img.get("category") or "").lower()
        ]
    if search:
        q = search.lower()
        images = [
            img for img in images
            if q in (img.get("name") or "").lower()
            or q in (img.get("description") or "").lower()
        ]

    return images


@router.get("/{name}")
def get_image(name: str, user: User = Depends(get_current_user)):
    try:
        images = _fetch_images()
    except httpx.HTTPError:
        raise HTTPException(502, "Failed to fetch LinuxServer registry")

    for img in images:
        if img["name"] == name:
            return img
    raise HTTPException(404, f"Image '{name}' not found")
