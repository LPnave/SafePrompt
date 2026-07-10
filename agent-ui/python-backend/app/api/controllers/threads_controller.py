"""
Threads controller — user chat history CRUD.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AppendMessageRequest,
    CreateThreadRequest,
    MessageRepositoryResponse,
    ThreadDetail,
    ThreadInitializeResponse,
    ThreadSummary,
    UpdateThreadRequest,
)
from app.core.database import get_db
from app.db.models import RolePolicy, User
from app.repositories.message_repository import MessageRepository
from app.services.auth_service import get_current_user
from app.services.thread_service import ThreadService, messages_to_repository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/threads", tags=["threads"])


def _status_to_ui(status_value: str) -> str:
    return "archived" if status_value == "archived" else "regular"


def _status_from_ui(status_value: str | None) -> str | None:
    if status_value is None:
        return None
    if status_value == "archived":
        return "archived"
    return "active"


@router.get("", response_model=list[ThreadSummary])
async def list_threads(
    status: str | None = "active",
    db: AsyncSession = Depends(get_db),
    current: tuple[User, RolePolicy] = Depends(get_current_user),
):
    user, _policy = current
    service = ThreadService(db)
    db_status = _status_from_ui(status) if status in ("active", "archived", "regular") else "active"
    if status == "regular":
        db_status = "active"
    threads = await service.threads.list_for_user(user.id, db_status)
    summaries: list[ThreadSummary] = []
    for thread in threads:
        count = await service.messages.count_by_thread(thread.id)
        summaries.append(
            ThreadSummary(
                remoteId=thread.id,
                title=thread.title,
                status=_status_to_ui(thread.status),
                updated_at=thread.updated_at,
                message_count=count,
            )
        )
    return summaries


@router.post("", response_model=ThreadInitializeResponse, status_code=201)
async def create_thread(
    request: CreateThreadRequest,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, RolePolicy] = Depends(get_current_user),
):
    user, _policy = current
    service = ThreadService(db)
    thread_id = request.id or str(uuid.uuid4())
    existing = await service.threads.get_for_user(thread_id, user.id)
    if existing:
        return ThreadInitializeResponse(
            remoteId=existing.id,
            externalId=None,
            title=existing.title or "New Chat",
        )
    thread = await service.threads.create(
        thread_id,
        user.id,
        title=request.title or "New Chat",
    )
    return ThreadInitializeResponse(
        remoteId=thread.id,
        externalId=None,
        title=thread.title or "New Chat",
    )


@router.get("/{thread_id}", response_model=ThreadDetail)
async def get_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, RolePolicy] = Depends(get_current_user),
):
    user, _policy = current
    service = ThreadService(db)
    thread = await service.get_thread_for_user(thread_id, user.id)
    return ThreadDetail(
        id=thread.id,
        title=thread.title,
        status=thread.status,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.patch("/{thread_id}", response_model=ThreadDetail)
async def update_thread(
    thread_id: str,
    request: UpdateThreadRequest,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, RolePolicy] = Depends(get_current_user),
):
    user, _policy = current
    service = ThreadService(db)
    thread = await service.get_thread_for_user(thread_id, user.id)
    if request.title is not None:
        thread = await service.threads.update_title(thread, request.title)
    if request.status is not None:
        thread = await service.threads.set_status(thread, request.status)
    return ThreadDetail(
        id=thread.id,
        title=thread.title,
        status=thread.status,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, RolePolicy] = Depends(get_current_user),
):
    user, _policy = current
    service = ThreadService(db)
    thread = await service.get_thread_for_user(thread_id, user.id)
    await service.threads.delete(thread)


@router.get("/{thread_id}/messages", response_model=MessageRepositoryResponse)
async def list_messages(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, RolePolicy] = Depends(get_current_user),
):
    user, _policy = current
    service = ThreadService(db)
    await service.get_thread_for_user(thread_id, user.id)
    rows = await service.messages.list_by_thread(thread_id)
    return MessageRepositoryResponse(**messages_to_repository(rows))


@router.post("/{thread_id}/messages", status_code=201)
async def append_message(
    thread_id: str,
    request: AppendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, RolePolicy] = Depends(get_current_user),
):
    user, _policy = current
    service = ThreadService(db)
    await service.append_message_item(
        thread_id,
        user.id,
        message=request.message,
        parent_id=request.parentId,
    )
    return {"ok": True}
