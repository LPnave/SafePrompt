"""
Audit repository — read-side queries on audit_events for reporting.
"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.db.models import AuditEvent
from app.repositories.base_repository import BaseRepository


class AuditRepository(BaseRepository[AuditEvent]):
    def __init__(self, db: AsyncSession):
        super().__init__(AuditEvent, db)

    async def count_today_for_user(self, user_id: int) -> int:
        """Count all audit events today (reporting)."""
        today = date.today()
        today_str = today.isoformat()
        result = await self.db.execute(
            select(func.count(AuditEvent.id)).where(
                and_(
                    AuditEvent.user_id == user_id,
                    func.date(AuditEvent.timestamp) == today_str,
                )
            )
        )
        return result.scalar_one() or 0

    async def count_today_requests_for_user(self, user_id: int) -> int:
        """Count billable requests today (passed or sanitized only)."""
        today = date.today()
        today_str = today.isoformat()
        result = await self.db.execute(
            select(func.count(AuditEvent.id)).where(
                and_(
                    AuditEvent.user_id == user_id,
                    func.date(AuditEvent.timestamp) == today_str,
                    AuditEvent.action.in_(("passed", "sanitized")),
                )
            )
        )
        return result.scalar_one() or 0

    async def count_session_turns_for_user(self, user_id: int, session_id: str) -> int:
        """Count completed user turns (passed or sanitized) in a conversation session."""
        result = await self.db.execute(
            select(func.count(AuditEvent.id)).where(
                and_(
                    AuditEvent.user_id == user_id,
                    AuditEvent.session_id == session_id,
                    AuditEvent.action.in_(("passed", "sanitized")),
                )
            )
        )
        return result.scalar_one() or 0

    async def get_usage_summary(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[dict]:
        """Prompts per day grouped by role."""
        day_col = func.date(AuditEvent.timestamp)
        query = select(
            day_col.label("day"),
            AuditEvent.user_role,
            func.count(AuditEvent.id).label("total"),
            func.count(AuditEvent.id).filter(AuditEvent.blocked.is_(True)).label("blocked"),
            func.count(AuditEvent.id).filter(AuditEvent.sanitization_applied.is_(True)).label("sanitized"),
        ).group_by(day_col, AuditEvent.user_role)

        if start:
            query = query.where(AuditEvent.timestamp >= start)
        if end:
            query = query.where(AuditEvent.timestamp <= end)

        result = await self.db.execute(query.order_by(day_col.desc()))
        rows = result.all()
        return [
            {
                "day": str(r.day),
                "role": r.user_role,
                "total": r.total,
                "blocked": r.blocked or 0,
                "sanitized": r.sanitized or 0,
            }
            for r in rows
        ]

    async def get_threat_breakdown(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[dict]:
        """Count of events that had at least one threat detected, by role."""
        query = (
            select(
                AuditEvent.user_role,
                AuditEvent.action,
                func.count(AuditEvent.id).label("count"),
            )
            .where(AuditEvent.threats_detected.is_not(None))
            .group_by(AuditEvent.user_role, AuditEvent.action)
        )
        if start:
            query = query.where(AuditEvent.timestamp >= start)
        if end:
            query = query.where(AuditEvent.timestamp <= end)

        result = await self.db.execute(query)
        rows = result.all()
        return [{"role": r.user_role, "action": r.action, "count": r.count} for r in rows]

    async def get_user_activity(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[dict]:
        """Per-user prompt count summary."""
        query = select(
            AuditEvent.user_id,
            AuditEvent.user_role,
            AuditEvent.department,
            func.count(AuditEvent.id).label("total_prompts"),
            func.count(AuditEvent.id).filter(AuditEvent.blocked.is_(True)).label("blocked"),
            func.avg(AuditEvent.processing_time_ms).label("avg_latency_ms"),
        ).group_by(AuditEvent.user_id, AuditEvent.user_role, AuditEvent.department)

        if start:
            query = query.where(AuditEvent.timestamp >= start)
        if end:
            query = query.where(AuditEvent.timestamp <= end)

        result = await self.db.execute(query)
        rows = result.all()
        return [
            {
                "user_id": r.user_id,
                "role": r.user_role,
                "department": r.department,
                "total_prompts": r.total_prompts,
                "blocked": r.blocked or 0,
                "avg_latency_ms": round(r.avg_latency_ms or 0, 2),
            }
            for r in rows
        ]

    async def get_blocked_events(
        self,
        limit: int = 100,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[AuditEvent]:
        query = (
            select(AuditEvent)
            .where(AuditEvent.blocked.is_(True))
            .order_by(AuditEvent.timestamp.desc())
            .limit(limit)
        )
        if start:
            query = query.where(AuditEvent.timestamp >= start)
        if end:
            query = query.where(AuditEvent.timestamp <= end)

        result = await self.db.execute(query)
        return list(result.scalars().all())
