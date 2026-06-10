import pytest

import app.main as main
from app.config import Settings


@pytest.mark.asyncio
async def test_lifespan_fails_fast_with_short_jwt_secret(monkeypatch):
    """App must refuse to start with a clear RuntimeError when JWT_SECRET is
    too short, instead of 500ing on the first token mint."""
    bad = Settings(JWT_SECRET="short", COOKIE_SECURE=True)
    monkeypatch.setattr(main, "_settings", bad)
    with pytest.raises(RuntimeError, match="32"):
        async with main.lifespan(main.app):
            pass
