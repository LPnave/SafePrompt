"""
Sanitization service — wraps role-policy enforcement for standalone sanitize endpoints.
"""

import time

from fastapi import HTTPException, status

from app.db.models import RolePolicy, User
from app.repositories.audit_repository import AuditRepository
from app.repositories.message_repository import MessageRepository
from app.services.policy_service import check_file_uploads, enforce_prompt_policy
from app.services.preflight_cache import issue_token
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_ATTACHMENT_PLACEHOLDER = [{"type": "file"}]


async def sanitize_single_with_policy(
    prompt: str,
    user: User,
    policy: RolePolicy,
    audit_repo: AuditRepository,
    session_id: str | None = None,
    has_attachments: bool = False,
    message_repo: MessageRepository | None = None,
) -> dict:
    """Run full role-policy preflight and return structured sanitize results."""
    if not prompt.strip() and not has_attachments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt or attachment required",
        )

    if has_attachments:
        check_file_uploads(_ATTACHMENT_PLACEHOLDER, policy)

    pipeline_start = time.time()
    enforcement = await enforce_prompt_policy(
        prompt=prompt,
        user=user,
        policy=policy,
        audit_repo=audit_repo,
        message_repo=message_repo,
        session_id=session_id,
    )
    result = enforcement.validation_result
    processing_time = (time.time() - pipeline_start) * 1000
    preflight_token = issue_token(user.id, prompt, enforcement)

    return {
        "is_safe": result.is_safe,
        "sanitized_prompt": result.modified_prompt,
        "original_prompt": prompt,
        "warnings": result.warnings,
        "blocked_patterns": result.blocked_patterns,
        "confidence": result.confidence,
        "modifications_made": prompt != result.modified_prompt,
        "processing_time_ms": result.processing_time_ms or processing_time,
        "preflight_token": preflight_token,
    }


async def sanitize_batch_with_policy(
    prompts: list[str],
    user: User,
    policy: RolePolicy,
    audit_repo: AuditRepository,
    session_id: str | None = None,
    has_attachments: bool = False,
    message_repo: MessageRepository | None = None,
) -> list[dict]:
    """Run policy enforcement on multiple prompts; fail fast on first block."""
    results = []
    for prompt in prompts:
        results.append(
            await sanitize_single_with_policy(
                prompt=prompt,
                user=user,
                policy=policy,
                audit_repo=audit_repo,
                session_id=session_id,
                has_attachments=has_attachments,
                message_repo=message_repo,
            )
        )
    return results
