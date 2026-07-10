"""
Repository for persisted chat messages.
"""

import uuid
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage


class MessageRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_thread(self, thread_id: str) -> List[ChatMessage]:
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, message_id: str) -> Optional[ChatMessage]:
        result = await self.db.execute(
            select(ChatMessage).where(ChatMessage.id == message_id)
        )
        return result.scalar_one_or_none()

    async def append(
        self,
        thread_id: str,
        role: str,
        content: str,
        message_id: str | None = None,
        parent_id: str | None = None,
    ) -> ChatMessage:
        existing = None
        msg_id = message_id or str(uuid.uuid4())
        if message_id:
            existing = await self.get_by_id(message_id)
        if existing:
            return existing

        message = ChatMessage(
            id=msg_id,
            thread_id=thread_id,
            role=role,
            content=content,
            parent_id=parent_id,
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def count_user_turns(self, thread_id: str) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(
                ChatMessage.thread_id == thread_id,
                ChatMessage.role == "user",
            )
        )
        return int(result.scalar_one())

    async def count_by_thread(self, thread_id: str) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.thread_id == thread_id)
        )
        return int(result.scalar_one())
