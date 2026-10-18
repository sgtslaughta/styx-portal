from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.models import RefreshToken

PW = "correct horse battery staple"


async def test_refresh_losing_the_rotation_race_is_treated_as_reuse(admin_client, session, monkeypatch):
    from sqlmodel import update
    real_get = session.get
    state = {"done": False}

    async def racing_get(model, ident, *a, **k):
        row = await real_get(model, ident, *a, **k)
        if model is RefreshToken and not state["done"]:
            state["done"] = True
            # a concurrent request rotates the same token right after we read it
            await session.exec(update(RefreshToken).where(
                RefreshToken.jti == ident).values(revoked=True))
        return row

    monkeypatch.setattr(session, "get", racing_get)
    h = {"X-CSRF-Token": admin_client.cookies.get("csrf_token")}
    assert (await admin_client.post("/api/auth/refresh", headers=h)).status_code == 401
    rows = (await session.exec(select(RefreshToken))).all()
    assert all(r.revoked for r in rows)


async def test_logout_revokes_whole_family(admin_client, session):
    h = {"X-CSRF-Token": admin_client.cookies.get("csrf_token")}
    assert (await admin_client.post("/api/auth/refresh", headers=h)).status_code == 200
    h = {"X-CSRF-Token": admin_client.cookies.get("csrf_token")}
    live = (await session.exec(select(RefreshToken).where(RefreshToken.revoked == False))).all()  # noqa: E712
    assert len(live) == 1
    assert (await admin_client.post("/api/auth/logout", headers=h)).status_code == 200
    rows = (await session.exec(select(RefreshToken))).all()
    assert rows and all(r.revoked for r in rows)


async def test_family_has_absolute_lifetime(admin_client, session):
    rows = (await session.exec(select(RefreshToken))).all()
    for r in rows:
        r.created_at = datetime.now(timezone.utc) - timedelta(days=400)
        session.add(r)
    await session.commit()
    h = {"X-CSRF-Token": admin_client.cookies.get("csrf_token")}
    assert (await admin_client.post("/api/auth/refresh", headers=h)).status_code == 401
