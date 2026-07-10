"""
Chat thread and message persistence service.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatThread, User
from app.repositories.message_repository import MessageRepository
from app.repositories.thread_repository import ThreadRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _utc_iso(dt: datetime | None) -> str:
    if dt is None:
        return datetime.now(timezone.utc).isoformat()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()


def extract_text_content(content: Any) -> str:
    """Extract plain text from assistant-ui message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts).strip()
    if isinstance(content, dict):
        return str(content.get("text", content))
    return str(content) if content is not None else ""


def message_to_dto(row) -> dict:
    """Map a ChatMessage row to assistant-ui ExportedMessageRepository item."""
    role = row.role
    message: dict[str, Any] = {
        "id": row.id,
        "role": role,
        "content": [{"type": "text", "text": row.content}],
        "createdAt": _utc_iso(row.created_at),
    }
    if role == "assistant":
        message["status"] = {"type": "complete", "reason": "stop"}
        message["metadata"] = {
            "unstable_state": None,
            "unstable_annotations": [],
            "unstable_data": [],
            "steps": [],
            "custom": {},
        }
    elif role == "user":
        message["attachments"] = []
        message["metadata"] = {"custom": {}}
    else:
        message["metadata"] = {"custom": {}}
    return {"message": message, "parentId": row.parent_id}


def messages_to_repository(rows: list) -> dict:
    """Build ExportedMessageRepository payload from DB rows."""
    items = [message_to_dto(row) for row in rows]
    head_id = items[-1]["message"]["id"] if items else None
    return {"headId": head_id, "messages": items}


class ThreadService:
    def __init__(self, db: AsyncSession):
        self.threads = ThreadRepository(db)
        self.messages = MessageRepository(db)

    async def ensure_thread(self, user_id: int, thread_id: str) -> ChatThread:
        existing = await self.threads.get_for_user(thread_id, user_id)
        if existing:
            return existing
        return await self.threads.create(thread_id, user_id)

    async def get_thread_for_user(self, thread_id: str, user_id: int) -> ChatThread:
        thread = await self.threads.get_for_user(thread_id, user_id)
        if not thread:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
        return thread

    async def append_turn(
        self,
        thread_id: str,
        user_id: int,
        sanitized_user: str,
        assistant_text: str,
        user_msg_id: str | None = None,
        assistant_msg_id: str | None = None,
        parent_id: str | None = None,
    ) -> None:
        thread = await self.ensure_thread(user_id, thread_id)
        last_messages = await self.messages.list_by_thread(thread_id)
        prev_parent = last_messages[-1].id if last_messages else None

        user_parent = parent_id if parent_id is not None else prev_parent
        user_msg = await self.messages.append(
            thread_id=thread_id,
            role="user",
            content=sanitized_user,
            message_id=user_msg_id,
            parent_id=user_parent,
        )
        await self.messages.append(
            thread_id=thread_id,
            role="assistant",
            content=assistant_text,
            message_id=assistant_msg_id,
            parent_id=user_msg.id,
        )
        await self.threads.touch_updated_at(thread)

    async def append_message_item(
        self,
        thread_id: str,
        user_id: int,
        *,
        message: dict,
        parent_id: str | None,
    ) -> None:
        await self.ensure_thread(user_id, thread_id)
        role = message.get("role", "user")
        content = extract_text_content(message.get("content"))
        message_id = message.get("id")
        await self.messages.append(
            thread_id=thread_id,
            role=role,
            content=content,
            message_id=message_id,
            parent_id=parent_id,
        )
        thread = await self.threads.get_by_id(thread_id)
        if thread:
            await self.threads.touch_updated_at(thread)
