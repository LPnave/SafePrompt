"""
Chat controller — /api/chat endpoint.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ChatRequest
from app.core.database import get_db
from app.db.models import User, RolePolicy
from app.repositories.audit_repository import AuditRepository
from app.services.auth_service import get_current_user
from app.services.chat_service import run_chat_pipeline
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/api/chat")
async def chat_endpoint(
    raw_request: Request,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, RolePolicy] = Depends(get_current_user),
):
    """
    Enterprise chat endpoint.
    Authenticated users only — security level and limits come from role policy.
    """
    user, policy = current

    try:
        body = await raw_request.json()

        # Normalise 'parts' array format from assistant-ui
        for msg in body.get("messages", []):
            if "parts" in msg and "content" not in msg:
                parts = msg.pop("parts")
                msg["content"] = " ".join(
                    p.get("text", str(p)) if isinstance(p, dict) else str(p)
                    for p in parts
                )

        request = ChatRequest(**body)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid request: {e}")

    audit_repo = AuditRepository(db)
    stream = await run_chat_pipeline(
        messages=request.messages,
        user=user,
        policy=policy,
        session_id=request.session_id,
        audit_repo=audit_repo,
    )

    return StreamingResponse(
        stream,
        media_type="text/plain; charset=utf-8",
        headers={"X-Vercel-AI-Data-Stream": "v1"},
    )
