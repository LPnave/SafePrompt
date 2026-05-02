"""Initial schema — roles, role_policies, users, audit_events

Revision ID: 0001
Revises:
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── roles ─────────────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    # ── role_policies ─────────────────────────────────────────────────────────
    op.create_table(
        "role_policies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("security_level", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("max_prompt_length", sa.Integer(), nullable=False, server_default="4000"),
        sa.Column("max_requests_per_day", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("allowed_topics", sa.JSON(), nullable=True),
        sa.Column("blocked_topics", sa.JSON(), nullable=True),
        sa.Column("enforce_topic_restrictions", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("response_filter_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_conversation_turns", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("session_timeout_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("allow_file_uploads", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("time_restriction_start", sa.String(length=5), nullable=True),
        sa.Column("time_restriction_end", sa.String(length=5), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("role_id", name="uq_role_policies_role_id"),
    )

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # ── audit_events ──────────────────────────────────────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("user_role", sa.String(length=50), nullable=True),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("prompt_hash", sa.String(length=64), nullable=True),
        sa.Column("raw_prompt", sa.Text(), nullable=True),
        sa.Column("sanitized_prompt", sa.Text(), nullable=True),
        sa.Column("prompt_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("threats_detected", sa.JSON(), nullable=True),
        sa.Column("sanitization_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("block_reason", sa.String(length=255), nullable=True),
        sa.Column("security_level_used", sa.String(length=10), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("processing_time_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("vetting_time_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("llm_time_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action", sa.String(length=20), nullable=False, server_default="passed"),
    )

    # ── indexes for common query patterns ─────────────────────────────────────
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])
    op.create_index("ix_audit_events_blocked", "audit_events", ["blocked"])
    op.create_index("ix_audit_events_user_role", "audit_events", ["user_role"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_user_role", table_name="audit_events")
    op.drop_index("ix_audit_events_blocked", table_name="audit_events")
    op.drop_index("ix_audit_events_timestamp", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("users")
    op.drop_table("role_policies")
    op.drop_table("roles")
