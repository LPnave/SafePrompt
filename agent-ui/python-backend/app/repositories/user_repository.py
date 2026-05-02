"""
User repository — data access for the users table.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import User, Role, RolePolicy
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role).selectinload(Role.policy))
            .where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role).selectinload(Role.policy))
            .where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_role(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role).selectinload(Role.policy))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_all_with_roles(self) -> list[User]:
        result = await self.db.execute(
            select(User).options(selectinload(User.role))
        )
        return list(result.scalars().all())

    async def get_by_role_id(self, role_id: int) -> list[User]:
        result = await self.db.execute(
            select(User).where(User.role_id == role_id, User.is_active.is_(True))
        )
        return list(result.scalars().all())
