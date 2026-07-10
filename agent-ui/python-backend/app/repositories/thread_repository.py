"""
Repository for chat thread metadata.
"""

from typing import List, Optional

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ChatThread, User


class ThreadRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_user(
        self,
        user_id: int,
        status: str | None = "active",
    ) -> List[ChatThread]:
        query = select(ChatThread).where(ChatThread.user_id == user_id)
        if status:
            query = query.where(ChatThread.status == status)
        query = query.order_by(ChatThread.updated_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, thread_id: str) -> Optional[ChatThread]:
        result = await self.db.execute(
            select(ChatThread).where(ChatThread.id == thread_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, thread_id: str, user_id: int) -> Optional[ChatThread]:
        result = await self.db.execute(
            select(ChatThread).where(
                ChatThread.id == thread_id,
                ChatThread.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        thread_id: str,
        user_id: int,
        title: str | None = "New Chat",
    ) -> ChatThread:
        thread = ChatThread(id=thread_id, user_id=user_id, title=title)
        self.db.add(thread)
        await self.db.commit()
        await self.db.refresh(thread)
        return thread

    async def update_title(self, thread: ChatThread, title: str) -> ChatThread:
        thread.title = title
        await self.db.commit()
        await self.db.refresh(thread)
        return thread

    async def set_status(self, thread: ChatThread, status: str) -> ChatThread:
        thread.status = status
        await self.db.commit()
        await self.db.refresh(thread)
        return thread

    async def touch_updated_at(self, thread: ChatThread) -> None:
        thread.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()

    async def delete(self, thread: ChatThread) -> None:
        await self.db.delete(thread)
        await self.db.commit()

    async def list_admin(
        self,
        *,
        user_id: int | None = None,
        username: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ChatThread]:
        query = (
            select(ChatThread)
            .join(User, ChatThread.user_id == User.id)
            .options(selectinload(ChatThread.user))
            .order_by(ChatThread.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if user_id is not None:
            query = query.where(ChatThread.user_id == user_id)
        if username:
            query = query.where(User.username == username)
        result = await self.db.execute(query)
        return list(result.scalars().all())
