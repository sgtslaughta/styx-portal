import pytest
from sqlmodel import select

from app.models import WorkstationEnrollmentToken


@pytest.mark.asyncio
async def test_mint_enroll_token_admin_only(client):
    r = await client.post("/api/workstations/enroll-tokens")
    assert r.status_code == 403  # CSRF check before auth


@pytest.mark.asyncio
async def test_mint_enroll_token(admin_client, session):
    r = await admin_client.post("/api/workstations/enroll-tokens")
    assert r.status_code == 201
    body = r.json()
    assert len(body["token"]) > 30
    assert "curl -fsSL" in body["command"]
    assert "--token " + body["token"] in body["command"]
    assert "/api/enroll/script" in body["command"]
    rows = (await session.exec(select(WorkstationEnrollmentToken))).all()
    assert len(rows) == 1
    assert rows[0].token_hash != body["token"]  # stored hashed
