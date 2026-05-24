import time

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

LSIO_API_URL = "https://api.linuxserver.io/api/v1/images?include_config=true&include_deprecated=false"
_cache: dict = {"data": None, "fetched_at": 0}
CACHE_TTL = 3600


def _fetch_images() -> list[dict]:
    now = time.time()
    if _cache["data"] and (now - _cache["fetched_at"]) < CACHE_TTL:
        return _cache["data"]

    resp = httpx.get(LSIO_API_URL, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    # Structure: {"status": "OK", "data": {"repositories": {"linuxserver": [...]}}}
    try:
        _cache["data"] = body["data"]["repositories"]["linuxserver"]
    except (KeyError, TypeError):
        _cache["data"] = body if isinstance(body, list) else []
    _cache["fetched_at"] = now
    return _cache["data"]


@router.get("")
def list_images(
    category: str | None = Query(None),
    search: str | None = Query(None),
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
def get_image(name: str):
    try:
        images = _fetch_images()
    except httpx.HTTPError:
        raise HTTPException(502, "Failed to fetch LinuxServer registry")

    for img in images:
        if img["name"] == name:
            return img
    raise HTTPException(404, f"Image '{name}' not found")
