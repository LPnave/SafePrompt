"""
Chat service — orchestrates the enterprise prompt pipeline:
  1. Rate limit check
  2. Prompt length check
  3. Vetting + sanitization (role security level)
  4. Gemini call with role system prompt
  5. Audit event creation
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
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Injected by main.py after model loading
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
# Pipeline helpers
# ---------------------------------------------------------------------------

def _extract_text(content) -> str:
    """Normalise message content to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part.get("text", str(part)) if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


async def _check_rate_limit(user: User, policy: RolePolicy, audit_repo: AuditRepository) -> None:
    today_count = await audit_repo.count_today_for_user(user.id)
    if today_count >= policy.max_requests_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily request limit of {policy.max_requests_per_day} reached for your role.",
        )


def _check_prompt_length(prompt: str, policy: RolePolicy) -> None:
    if len(prompt) > policy.max_prompt_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt length {len(prompt)} exceeds the {policy.max_prompt_length} character limit for your role.",
        )


def _check_time_restriction(policy: RolePolicy) -> None:
    """Block access outside the configured time window (24-hour HH:MM, UTC)."""
    if not policy.time_restriction_start or not policy.time_restriction_end:
        return
    now = datetime.now(timezone.utc).strftime("%H:%M")
    start = policy.time_restriction_start
    end = policy.time_restriction_end
    # Handle windows that wrap midnight (e.g. 22:00 – 06:00)
    if start <= end:
        allowed = start <= now <= end
    else:
        allowed = now >= start or now <= end
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access not permitted outside allowed hours ({start}–{end} UTC)",
        )


def _check_topic_restrictions(prompt: str, policy: RolePolicy, validator) -> None:
    """
    Two-stage topic enforcement:

    Stage 1 — Blocked keyword matching (always runs when keywords are configured).
    Explicit blocklist: if any blocked keyword/phrase appears in the prompt, reject
    it immediately regardless of whether the topic-restriction toggle is on.

    Stage 2 — Allowed-topic zero-shot classification (only when the toggle is ON).
    Uses the ML classifier to check whether the prompt's topic falls within the
    role's allowed topics list.
    """
    prompt_lower = prompt.lower()

    # Stage 1: blocked keywords — always enforced
    blocked_keywords: list = policy.blocked_topics or []
    for kw in blocked_keywords:
        if kw.lower() in prompt_lower:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prompt contains a blocked topic or keyword: '{kw}'",
            )

    # Stage 2: allowed-topic classification — only when toggle is ON
    if not policy.enforce_topic_restrictions:
        return
    allowed_topics: list = policy.allowed_topics or []
    if not allowed_topics:
        return
    classifier = getattr(validator, "classifier", None)
    if classifier is None:
        logger.warning("Topic restriction toggle is ON but no classifier available — skipping")
        return

    try:
        result = classifier(
            prompt,
            candidate_labels=allowed_topics,
            multi_label=False,
        )
        best_score = result["scores"][0] if result.get("scores") else 0
        if best_score < 0.30:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Prompt topic not permitted for your role. "
                    f"Allowed topics: {', '.join(allowed_topics)}"
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Topic restriction check failed (non-blocking): %s", exc)


def _build_ollama_messages(
    messages: list, sanitized_content: str, last_message, system_prompt: str | None
) -> list:
    """Convert chat messages to Ollama's OpenAI-compatible message format."""
    result = []
    if system_prompt:
        result.append({"role": "system", "content": system_prompt})
    for msg in messages:
        content = sanitized_content if msg is last_message else _extract_text(msg.content)
        role = "user" if msg.role == "user" else "assistant"
        result.append({"role": role, "content": content})
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


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

async def run_chat_pipeline(
    messages: list,
    user: User,
    policy: RolePolicy,
    session_id: str | None,
    audit_repo: AuditRepository,
) -> AsyncGenerator[str, None]:
    """
    Full enterprise chat pipeline. Returns an async generator of data-stream lines.
    """
    pipeline_start = time.time()

    # Find the last user message
    last_message = next((m for m in reversed(messages) if m.role == "user"), None)
    if not last_message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user message found")

    original_content = _extract_text(last_message.content)

    # 1. Time restriction check
    _check_time_restriction(policy)

    # 2. Rate limit
    await _check_rate_limit(user, policy, audit_repo)

    # 3. Prompt length
    _check_prompt_length(original_content, policy)

    # 4. Topic enforcement (zero-shot classification)
    validator = get_validator()
    _check_topic_restrictions(original_content, policy, validator)

    # 5. Vetting + sanitization (thread-safe, uses role's security level)
    vetting_start = time.time()
    validation_result = validator.validate_for_role(original_content, policy.security_level)
    vetting_time_ms = (time.time() - vetting_start) * 1000

    # Block mode check (HIGH security level blocks threats)
    if validator.block_mode and not validation_result.is_safe and validation_result.blocked_patterns:
        logger.warning(f"Prompt blocked for user {user.username}: {validation_result.blocked_patterns}")
        _enqueue_audit(
            user=user, policy=policy,
            original_prompt=original_content, sanitized_prompt=original_content,
            validation_result=validation_result, action="blocked",
            block_reason=", ".join(validation_result.warnings[:3]),
            processing_time_ms=(time.time() - pipeline_start) * 1000,
            vetting_time_ms=vetting_time_ms, llm_time_ms=0,
            tokens_used=0, session_id=session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt blocked: {', '.join(validation_result.warnings)}",
        )

    sanitized_content = validation_result.modified_prompt
    sanitization_applied = original_content != sanitized_content

    # 4. Build Ollama payload and call LLM
    ollama_messages = _build_ollama_messages(messages, sanitized_content, last_message, policy.system_prompt)

    llm_start = time.time()
    ai_text = await _call_ollama(ollama_messages)
    llm_time_ms = (time.time() - llm_start) * 1000

    processing_time_ms = (time.time() - pipeline_start) * 1000
    tokens_used = len(ai_text)

    # 5. Enqueue audit event (non-blocking)
    action = "blocked" if not validation_result.is_safe else ("sanitized" if sanitization_applied else "passed")
    _enqueue_audit(
        user=user, policy=policy,
        original_prompt=original_content, sanitized_prompt=sanitized_content,
        validation_result=validation_result, action=action,
        block_reason=None,
        processing_time_ms=processing_time_ms, vetting_time_ms=vetting_time_ms,
        llm_time_ms=llm_time_ms, tokens_used=tokens_used, session_id=session_id,
    )

    logger.info(
        f"Chat pipeline complete — user={user.username} role={user.role.name} "
        f"action={action} time={processing_time_ms:.0f}ms"
    )

    # 6. Stream response in data-stream protocol format
    async def _generate():
        if sanitization_applied:
            yield f'8:{json.dumps([{"type": "sanitization", "warnings": validation_result.warnings}])}\n'

        chunk_size = 5
        for i in range(0, len(ai_text), chunk_size):
            yield f'0:{json.dumps(ai_text[i:i + chunk_size])}\n'

        yield f'd:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": tokens_used}})}\n'

    return _generate()
