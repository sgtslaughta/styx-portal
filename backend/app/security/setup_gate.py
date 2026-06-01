from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import User


async def users_exist(session: AsyncSession) -> bool:
    result = await session.exec(select(func.count()).select_from(User))
    return (result.one() or 0) > 0
