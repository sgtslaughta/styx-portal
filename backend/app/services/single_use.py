from datetime import datetime, timezone

from sqlmodel import update


async def claim(session, model, row_id: str) -> bool:
    """Atomically mark a single-use row (Invite, enrollment token) used.

    True only for the one caller whose UPDATE flipped used_at from NULL; concurrent
    redeemers of the same token get False.
    """
    res = await session.exec(
        update(model).where(model.id == row_id, model.used_at == None)  # noqa: E711
        .values(used_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False))
    return res.rowcount == 1
