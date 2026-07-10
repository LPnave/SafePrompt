"""
Chat service — orchestrates the enterprise prompt pipeline.
"""

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.audit import audit_queue
from app.db.models import AuditEvent, User, RolePolicy
from app.repositories.audit_repository import AuditRepository
from app.repositories.message_repository import MessageRepository
from app.services.policy_service import (
    check_file_uploads,
    enforce_prompt_policy,
    PromptPolicyBlocked,
    block_reason_from_http_detail,
    has_attachments,
)
from app.services.preflight_cache import consume_token
from app.services.response_filter_service import filter_llm_response
from app.services.thread_service import ThreadService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_validator = None


def set_validator(v) -> None:
    global _validator
    _validator = v


def get_validator():
    if _validator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security validator not initialised",
        )
    return _validator


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def _extract_text(content) -> str:
    """Normalise message content to a plain string (text + file attachment bodies)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type")
                if part_type == "text":
                    parts.append(part.get("text", ""))
                elif part_type == "image":
                    parts.append("[image attachment]")
                elif part_type == "file":
                    parts.append("[file attachment]")
                else:
                    parts.append(part.get("text", ""))
            else:
                parts.append(str(part))
        return " ".join(p for p in parts if p).strip()
    return str(content)


def _extract_images(content) -> list[str]:
    """Extract base64 image payloads for Ollama's `images` field."""
    images: list[str] = []
    if not isinstance(content, list):
        return images
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "image":
            continue
        image_ref = part.get("image", "")
        if not isinstance(image_ref, str) or not image_ref:
            continue
        if image_ref.startswith("data:") and "," in image_ref:
            images.append(image_ref.split(",", 1)[1])
        else:
            images.append(image_ref)
    return images


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _build_ollama_messages(
    messages: list, sanitized_content: str, last_message, system_prompt: str | None
) -> list:
    """Convert chat messages to Ollama's message format (text + optional images)."""
    result = []
    if system_prompt:
        result.append({"role": "system", "content": system_prompt})
    for msg in messages:
        is_last = msg is last_message
        content = sanitized_content if is_last else _extract_text(msg.content)
        role = "user" if msg.role == "user" else "assistant"
        ollama_msg: dict = {"role": role, "content": content or " "}
        if is_last and msg.role == "user":
            images = _extract_images(msg.content)
            if images:
                ollama_msg["images"] = images
        result.append(ollama_msg)
    return result


async def _call_ollama(ollama_messages: list) -> str:
    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                url,
                json={
                    "model": settings.OLLAMA_MODEL,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {"temperature": 0.7},
                },
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Ollama timed out — model may be loading, try again in a moment",
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Cannot connect to Ollama at {settings.OLLAMA_BASE_URL}. Is Ollama running?",
            )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ollama error ({response.status_code}): {response.text}",
        )

    try:
        return response.json()["message"]["content"]
    except (KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected response format from Ollama",
        )


def _enqueue_audit(
    user: User,
    policy: RolePolicy,
    original_prompt: str,
    sanitized_prompt: str,
    validation_result,
    action: str,
    block_reason: str | None,
    processing_time_ms: float,
    vetting_time_ms: float,
    llm_time_ms: float,
    tokens_used: int,
    session_id: str | None,
) -> None:
    event = AuditEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        user_id=user.id,
        user_role=user.role.name,
        department=user.department,
        session_id=session_id,
        prompt_hash=_hash_prompt(original_prompt),
        raw_prompt=original_prompt if settings.STORE_RAW_PROMPTS else None,
        sanitized_prompt=sanitized_prompt,
        prompt_length=len(original_prompt),
        threats_detected=validation_result.blocked_patterns if validation_result else [],
        sanitization_applied=original_prompt != sanitized_prompt,
        blocked=action == "blocked",
        block_reason=block_reason,
        security_level_used=policy.security_level,
        confidence_score=validation_result.confidence if validation_result else None,
        processing_time_ms=processing_time_ms,
        vetting_time_ms=vetting_time_ms,
        llm_time_ms=llm_time_ms,
        model_used=settings.OLLAMA_MODEL,
        tokens_used=tokens_used,
        action=action,
    )
    try:
        audit_queue.put_nowait(event)
    except Exception:
        logger.warning("Audit queue is full — event dropped")


def _audit_policy_block(
    user: User,
    policy: RolePolicy,
    original_prompt: str,
    block_reason: str,
    session_id: str | None,
    processing_time_ms: float,
) -> None:
    _enqueue_audit(
        user=user,
        policy=policy,
        original_prompt=original_prompt,
        sanitized_prompt=original_prompt,
        validation_result=None,
        action="blocked",
        block_reason=block_reason,
        processing_time_ms=processing_time_ms,
        vetting_time_ms=0,
        llm_time_ms=0,
        tokens_used=0,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def _audit_policy_http_block(
    user: User,
    policy: RolePolicy,
    original_prompt: str,
    exc: HTTPException,
    session_id: str | None,
    processing_time_ms: float,
) -> None:
    detail = str(exc.detail)
    block_reason = block_reason_from_http_detail(detail)
    if block_reason:
        _audit_policy_block(
            user=user,
            policy=policy,
            original_prompt=original_prompt,
            block_reason=block_reason,
            session_id=session_id,
            processing_time_ms=processing_time_ms,
        )


async def run_chat_pipeline(
    messages: list,
    user: User,
    policy: RolePolicy,
    session_id: str | None,
    audit_repo: AuditRepository,
    message_repo: MessageRepository | None = None,
    db=None,
    preflight_token: str | None = None,
) -> AsyncGenerator[str, None]:
    """Full enterprise chat pipeline. Returns an async generator of data-stream lines."""
    pipeline_start = time.time()

    last_message = next((m for m in reversed(messages) if m.role == "user"), None)
    if not last_message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user message found")

    original_content = _extract_text(last_message.content)

    try:
        check_file_uploads(last_message.content, policy)
    except HTTPException as exc:
        _audit_policy_http_block(
            user=user,
            policy=policy,
            original_prompt=original_content,
            exc=exc,
            session_id=session_id,
            processing_time_ms=(time.time() - pipeline_start) * 1000,
        )
        raise

    lookup_prompt = original_content
    if not lookup_prompt.strip() and has_attachments(last_message.content):
        lookup_prompt = ""
    cached = consume_token(user.id, lookup_prompt, preflight_token)

    try:
        enforcement = await enforce_prompt_policy(
            prompt=original_content,
            user=user,
            policy=policy,
            audit_repo=audit_repo,
            message_repo=message_repo,
            session_id=session_id,
            cached_result=cached,
        )
    except PromptPolicyBlocked as exc:
        logger.warning(
            f"Prompt blocked for user {user.username}: "
            f"{exc.validation_result.blocked_patterns}"
        )
        _enqueue_audit(
            user=user,
            policy=policy,
            original_prompt=original_content,
            sanitized_prompt=original_content,
            validation_result=exc.validation_result,
            action="blocked",
            block_reason=", ".join(exc.validation_result.warnings[:3]),
            processing_time_ms=(time.time() - pipeline_start) * 1000,
            vetting_time_ms=exc.vetting_time_ms,
            llm_time_ms=0,
            tokens_used=0,
            session_id=session_id,
        )
        raise
    except HTTPException as exc:
        processing_time_ms = (time.time() - pipeline_start) * 1000
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            _audit_policy_block(
                user=user,
                policy=policy,
                original_prompt=original_content,
                block_reason="outside_allowed_hours",
                session_id=session_id,
                processing_time_ms=processing_time_ms,
            )
        elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            detail = str(exc.detail)
            block_reason = (
                "conversation_turn_limit"
                if "Conversation turn limit" in detail
                else "daily_request_limit"
            )
            _audit_policy_block(
                user=user,
                policy=policy,
                original_prompt=original_content,
                block_reason=block_reason,
                session_id=session_id,
                processing_time_ms=processing_time_ms,
            )
        elif exc.status_code == status.HTTP_400_BAD_REQUEST:
            _audit_policy_http_block(
                user=user,
                policy=policy,
                original_prompt=original_content,
                exc=exc,
                session_id=session_id,
                processing_time_ms=processing_time_ms,
            )
        raise

    validation_result = enforcement.validation_result
    vetting_time_ms = enforcement.vetting_time_ms
    sanitized_content = validation_result.modified_prompt
    sanitization_applied = original_content != sanitized_content

    ollama_messages = _build_ollama_messages(messages, sanitized_content, last_message, policy.system_prompt)

    llm_start = time.time()
    ai_text = await _call_ollama(ollama_messages)
    llm_time_ms = (time.time() - llm_start) * 1000

    validator = get_validator()
    filter_result = filter_llm_response(ai_text, policy, validator)
    delivered_text = filter_result.delivered
    response_filtered = filter_result.filtered

    processing_time_ms = (time.time() - pipeline_start) * 1000
    tokens_used = len(delivered_text)

    if response_filtered:
        action = "response_filtered"
    else:
        action = "blocked" if not validation_result.is_safe else (
            "sanitized" if sanitization_applied else "passed"
        )
    _enqueue_audit(
        user=user, policy=policy,
        original_prompt=original_content, sanitized_prompt=sanitized_content,
        validation_result=validation_result, action=action,
        block_reason=", ".join(filter_result.warnings[:3]) if response_filtered else None,
        processing_time_ms=processing_time_ms, vetting_time_ms=vetting_time_ms,
        llm_time_ms=llm_time_ms, tokens_used=tokens_used, session_id=session_id,
    )

    if session_id and db is not None:
        try:
            thread_service = ThreadService(db)
            await thread_service.append_turn(
                thread_id=session_id,
                user_id=user.id,
                sanitized_user=sanitized_content,
                assistant_text=delivered_text,
            )
        except Exception as exc:
            logger.error("Failed to persist chat turn for thread %s: %s", session_id, exc)

    logger.info(
        f"Chat pipeline complete — user={user.username} role={user.role.name} "
        f"action={action} time={processing_time_ms:.0f}ms"
    )

    async def _generate():
        if sanitization_applied:
            yield f'8:{json.dumps([{"type": "sanitization", "warnings": validation_result.warnings}])}\n'
        if response_filtered:
            yield f'8:{json.dumps([{"type": "response_filtered", "warnings": filter_result.warnings or []}])}\n'

        chunk_size = 5
        for i in range(0, len(delivered_text), chunk_size):
            yield f'0:{json.dumps(delivered_text[i:i + chunk_size])}\n'

        yield f'd:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": tokens_used}})}\n'

    return _generate()
