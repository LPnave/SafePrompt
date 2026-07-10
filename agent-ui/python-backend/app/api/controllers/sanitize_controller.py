"""
Sanitize controller — /api/sanitize endpoints.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    SanitizeRequest, SanitizeResponse,
    BatchSanitizeRequest, BatchSanitizeResponse,
    HealthResponse, StatsResponse,
    SecurityLevelUpdate, SecurityLevelResponse,
)
from app.core.database import get_db
from app.db.models import User, RolePolicy
from app.repositories.audit_repository import AuditRepository
from app.repositories.message_repository import MessageRepository
from app.services.auth_service import get_current_user, require_admin
from app.services.sanitize_service import sanitize_single_with_policy, sanitize_batch_with_policy
from app.services.chat_service import get_validator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(tags=["sanitize"])

_start_time = time.time()
_request_count = 0
_total_time = 0.0


def _reject_security_level_override(
    security_level: str | None,
    user: User,
) -> None:
    """Non-admins cannot override role policy security level."""
    if security_level and not user.role.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins may override security_level on sanitize requests.",
        )


@router.post("/api/sanitize", response_model=SanitizeResponse)
async def sanitize_endpoint(
    request: SanitizeRequest,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    global _request_count, _total_time
    user, policy = current
    _reject_security_level_override(request.security_level, user)

    audit_repo = AuditRepository(db)
    message_repo = MessageRepository(db)
    result = await sanitize_single_with_policy(
        prompt=request.prompt,
        user=user,
        policy=policy,
        audit_repo=audit_repo,
        session_id=request.session_id,
        has_attachments=request.has_attachments,
        message_repo=message_repo,
    )
    _request_count += 1
    _total_time += result["processing_time_ms"]

    details = None
    if request.return_details:
        details = {"security_level": policy.security_level}

    return SanitizeResponse(**result, sanitization_details=details)


@router.post("/api/sanitize/batch", response_model=BatchSanitizeResponse)
async def sanitize_batch_endpoint(
    request: BatchSanitizeRequest,
    db: AsyncSession = Depends(get_db),
    current=Depends(get_current_user),
):
    user, policy = current
    _reject_security_level_override(request.security_level, user)

    audit_repo = AuditRepository(db)
    message_repo = MessageRepository(db)
    start = time.time()
    results = await sanitize_batch_with_policy(
        prompts=request.prompts,
        user=user,
        policy=policy,
        audit_repo=audit_repo,
        session_id=request.session_id,
        has_attachments=request.has_attachments,
        message_repo=message_repo,
    )
    total_ms = (time.time() - start) * 1000

    return BatchSanitizeResponse(
        results=[SanitizeResponse(**r) for r in results],
        total_processed=len(results),
        total_time_ms=total_ms,
    )


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    validator = None
    try:
        validator = get_validator()
    except Exception:
        pass
    return HealthResponse(
        status="healthy" if validator else "unhealthy",
        model_loaded=validator is not None,
        uptime_seconds=time.time() - _start_time,
        version="2.0.0",
    )


@router.get("/api/stats", response_model=StatsResponse)
async def stats_endpoint(_current=Depends(get_current_user)):
    import torch
    validator = get_validator()
    avg = (_total_time / _request_count) if _request_count > 0 else 0
    return StatsResponse(
        security_level=validator.security_level.value,
        model_info={
            "model_name": "facebook/bart-large-mnli",
            "model_type": "zero-shot-classification",
            "device": "cuda" if torch.cuda.is_available() else "cpu",
            "spacy_model": "en_core_web_sm",
        },
        request_stats={
            "total_requests": _request_count,
            "average_latency_ms": round(avg, 2),
            "total_processing_time_ms": round(_total_time, 2),
            "uptime_seconds": round(time.time() - _start_time, 2),
        },
        capabilities=[
            "Zero-shot classification", "Multi-label threat detection",
            "Contextual understanding", "Automatic sanitization",
            "Confidence scoring", "Pattern matching (spaCy)",
            "Entropy-based detection", "Role-based security levels",
        ],
    )


@router.get("/api/security/level", response_model=SecurityLevelResponse)
async def get_security_level(_current=Depends(get_current_user)):
    validator = get_validator()
    return SecurityLevelResponse(
        level=validator.security_level.value,
        success=True,
        message=f"Global default security level is {validator.security_level.value}",
    )


@router.put("/api/security/level", response_model=SecurityLevelResponse)
async def update_security_level(
    request: SecurityLevelUpdate,
    _current=Depends(require_admin),
):
    """Admin-only — updates the global default security level."""
    from app.core.config import SecurityLevel
    validator = get_validator()
    try:
        new_level = SecurityLevel(request.level.lower())
        validator.security_level = new_level
        validator._configure_security_thresholds()
        return SecurityLevelResponse(
            level=new_level.value, success=True,
            message=f"Global security level updated to {new_level.value}",
        )
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid level: {request.level}")
