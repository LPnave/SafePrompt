"""
Role repository — data access for roles and role_policies tables.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Role, RolePolicy
from app.repositories.base_repository import BaseRepository


class RoleRepository(BaseRepository[Role]):
    def __init__(self, db: AsyncSession):
        super().__init__(Role, db)

    async def get_by_name(self, name: str) -> Optional[Role]:
        result = await self.db.execute(
            select(Role)
            .options(selectinload(Role.policy))
            .where(Role.name == name)
        )
        return result.scalar_one_or_none()

    async def get_all_with_policies(self) -> list[Role]:
        result = await self.db.execute(
            select(Role).options(selectinload(Role.policy))
        )
        return list(result.scalars().all())

    async def get_policy_by_role_id(self, role_id: int) -> Optional[RolePolicy]:
        result = await self.db.execute(
            select(RolePolicy).where(RolePolicy.role_id == role_id)
        )
        return result.scalar_one_or_none()


class RolePolicyRepository(BaseRepository[RolePolicy]):
    def __init__(self, db: AsyncSession):
        super().__init__(RolePolicy, db)

    async def get_by_role_id(self, role_id: int) -> Optional[RolePolicy]:
        result = await self.db.execute(
            select(RolePolicy).where(RolePolicy.role_id == role_id)
        )
        return result.scalar_one_or_none()
