import pytest

import app.main as main
from app.config import Settings


@pytest.mark.asyncio
async def test_lifespan_fails_fast_without_jwt_secret(monkeypatch):
    """App must refuse to start (clear RuntimeError) when JWT_SECRET is unset
    and COOKIE_SECURE=true, instead of 500ing on the first token mint."""
    bad = Settings(JWT_SECRET="", COOKIE_SECURE=True)
    monkeypatch.setattr(main, "_settings", bad)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        async with main.lifespan(main.app):
            pass
