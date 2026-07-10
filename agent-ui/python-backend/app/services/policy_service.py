"""
Shared role-policy enforcement helpers used by chat and sanitize pipelines.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.db.models import RolePolicy, User
from app.repositories.audit_repository import AuditRepository
from app.repositories.message_repository import MessageRepository
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_session_turn_warning_logged = False


@dataclass
class PolicyEnforcementResult:
    validation_result: object
    vetting_time_ms: float


class PromptPolicyBlocked(HTTPException):
    """Raised when validator block_mode rejects a prompt."""

    def __init__(self, detail: str, validation_result: object, vetting_time_ms: float):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
        self.validation_result = validation_result
        self.vetting_time_ms = vetting_time_ms


def is_within_time_window(
    start: str | None,
    end: str | None,
    now_hhmm: str | None = None,
) -> bool:
    """Return True when now falls inside the UTC HH:MM window (inclusive)."""
    if not start or not end:
        return True
    now = now_hhmm or datetime.now(timezone.utc).strftime("%H:%M")
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def time_restriction_message(policy: RolePolicy) -> str:
    start = policy.time_restriction_start or ""
    end = policy.time_restriction_end or ""
    return f"Access not permitted outside allowed hours ({start}–{end} UTC)"


def check_time_restriction(policy: RolePolicy) -> None:
    """Block access outside the configured time window (24-hour HH:MM, UTC)."""
    if not policy.time_restriction_start or not policy.time_restriction_end:
        return
    if not is_within_time_window(
        policy.time_restriction_start,
        policy.time_restriction_end,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=time_restriction_message(policy),
        )


def has_attachments(content) -> bool:
    """Return True when the message includes image or file parts."""
    if not isinstance(content, list):
        return False
    for part in content:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type in ("image", "file"):
            return True
        if part_type == "text" and str(part.get("text", "")).strip().startswith("<attachment name="):
            return True
    return False


def check_file_uploads(content, policy: RolePolicy) -> None:
    if has_attachments(content) and not policy.allow_file_uploads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File uploads are not permitted for your role.",
        )


def check_prompt_length(prompt: str, policy: RolePolicy) -> None:
    if len(prompt) > policy.max_prompt_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Prompt length {len(prompt)} exceeds the "
                f"{policy.max_prompt_length} character limit for your role."
            ),
        )


def check_topic_restrictions(prompt: str, policy: RolePolicy, validator) -> None:
    """
    Two-stage topic enforcement:
    Stage 1 — blocked keyword matching (always when configured).
    Stage 2 — allowed-topic zero-shot classification (when toggle is ON).
    """
    prompt_lower = prompt.lower()

    blocked_keywords: list = policy.blocked_topics or []
    for kw in blocked_keywords:
        if kw.lower() in prompt_lower:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prompt contains a blocked topic or keyword: '{kw}'",
            )

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


def validate_time_restriction_fields(
    start: str | None,
    end: str | None,
) -> None:
    """Validate time restriction fields on admin policy save."""
    if (start is None) != (end is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both time_restriction_start and time_restriction_end must be set together.",
        )
    if start and end and start == end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="time_restriction_start and time_restriction_end cannot be equal.",
        )


async def check_rate_limit(
    user: User,
    policy: RolePolicy,
    audit_repo: AuditRepository,
) -> None:
    today_count = await audit_repo.count_today_requests_for_user(user.id)
    if today_count >= policy.max_requests_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily request limit of {policy.max_requests_per_day} reached for your role.",
        )


async def check_conversation_turns(
    user: User,
    policy: RolePolicy,
    session_id: str | None,
    audit_repo: AuditRepository,
    message_repo: MessageRepository | None = None,
) -> None:
    global _session_turn_warning_logged
    if not session_id:
        if not _session_turn_warning_logged:
            logger.warning("session_id missing — max_conversation_turns check skipped")
            _session_turn_warning_logged = True
        return

    turn_count = 0
    if message_repo is not None:
        turn_count = await message_repo.count_user_turns(session_id)
    if turn_count == 0:
        turn_count = await audit_repo.count_session_turns_for_user(user.id, session_id)
    if turn_count >= policy.max_conversation_turns:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Conversation turn limit of {policy.max_conversation_turns} "
                f"reached for this session."
            ),
        )


def block_reason_from_http_detail(detail: str) -> str | None:
    """Map policy HTTPException detail to an audit block_reason."""
    if "character limit" in detail:
        return "prompt_length_exceeded"
    if "blocked topic" in detail or "topic not permitted" in detail:
        return "topic_restriction"
    if "File uploads are not permitted" in detail:
        return "file_upload_denied"
    return None


async def enforce_prompt_policy(
    *,
    prompt: str,
    user: User,
    policy: RolePolicy,
    audit_repo: AuditRepository | None = None,
    message_repo: MessageRepository | None = None,
    session_id: str | None = None,
    check_rate: bool = True,
    check_turns: bool = True,
    cached_result: PolicyEnforcementResult | None = None,
) -> PolicyEnforcementResult:
    """
    Shared preflight for chat and sanitize pipelines.
    Always validates using policy.security_level (role policy).
    """
    check_time_restriction(policy)

    if audit_repo is not None:
        if check_rate:
            await check_rate_limit(user, policy, audit_repo)
        if check_turns:
            await check_conversation_turns(
                user, policy, session_id, audit_repo, message_repo
            )

    if cached_result is not None:
        return cached_result

    check_prompt_length(prompt, policy)

    from app.services.chat_service import get_validator

    validator = get_validator()
    check_topic_restrictions(prompt, policy, validator)

    vetting_start = time.time()
    validation_result = validator.validate_for_role(prompt, policy.security_level)
    vetting_time_ms = (time.time() - vetting_start) * 1000

    if validator.block_mode and not validation_result.is_safe and validation_result.blocked_patterns:
        raise PromptPolicyBlocked(
            detail=f"Prompt blocked: {', '.join(validation_result.warnings)}",
            validation_result=validation_result,
            vetting_time_ms=vetting_time_ms,
        )

    return PolicyEnforcementResult(
        validation_result=validation_result,
        vetting_time_ms=vetting_time_ms,
    )
