"""
Reporting controller — analytics endpoints for the admin dashboard.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    UsageSummaryItem, ThreatBreakdownItem,
    UserActivityItem, BlockedEventResponse,
)
from app.core.database import get_db
from app.repositories.audit_repository import AuditRepository
from app.services.auth_service import require_admin

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@router.get("/usage", response_model=list[UsageSummaryItem])
async def usage_summary(
    start: Optional[str] = Query(None, description="ISO datetime start filter"),
    end: Optional[str] = Query(None, description="ISO datetime end filter"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Prompts per day grouped by role — used for the usage trend chart."""
    repo = AuditRepository(db)
    rows = await repo.get_usage_summary(_parse_date(start), _parse_date(end))
    return [UsageSummaryItem(**r) for r in rows]


@router.get("/threats", response_model=list[ThreatBreakdownItem])
async def threat_breakdown(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Threat type distribution — used for the security incidents chart."""
    repo = AuditRepository(db)
    rows = await repo.get_threat_breakdown(_parse_date(start), _parse_date(end))
    return [ThreatBreakdownItem(**r) for r in rows]


@router.get("/users", response_model=list[UserActivityItem])
async def user_activity(
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Per-user prompt activity — used for the user activity table."""
    repo = AuditRepository(db)
    rows = await repo.get_user_activity(_parse_date(start), _parse_date(end))
    return [UserActivityItem(**r) for r in rows]


@router.get("/blocked", response_model=list[BlockedEventResponse])
async def blocked_events(
    limit: int = Query(100, ge=1, le=500),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Recent blocked prompts — shown in the audit log viewer."""
    repo = AuditRepository(db)
    events = await repo.get_blocked_events(limit, _parse_date(start), _parse_date(end))
    return [
        BlockedEventResponse(
            id=e.id, timestamp=e.timestamp,
            user_id=e.user_id, user_role=e.user_role,
            department=e.department, prompt_length=e.prompt_length,
            block_reason=e.block_reason, threats_detected=e.threats_detected,
            security_level_used=e.security_level_used,
        )
        for e in events
    ]
