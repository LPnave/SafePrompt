"""
SQLAlchemy ORM models for the enterprise pipeline
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer,
    String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON

from app.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    policy: Mapped[Optional["RolePolicy"]] = relationship("RolePolicy", back_populates="role", uselist=False)
    users: Mapped[list["User"]] = relationship("User", back_populates="role")


class RolePolicy(Base):
    __tablename__ = "role_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), unique=True, nullable=False)

    # Security
    security_level: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)

    # Operational limits
    max_prompt_length: Mapped[int] = mapped_column(Integer, default=4000, nullable=False)
    max_requests_per_day: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    # LLM behaviour for this role
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Topic control (stored as JSON arrays of strings)
    allowed_topics: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    blocked_topics: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Topic enforcement — actively block prompts whose topic is not in allowed_topics
    enforce_topic_restrictions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # LLM output filtering — scan Gemini responses for sensitive content
    response_filter_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Session controls
    max_conversation_turns: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    session_timeout_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    # Feature flags
    allow_file_uploads: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Time-of-day restrictions (24-hour "HH:MM" strings, UTC)
    time_restriction_start: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    time_restriction_end: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    role: Mapped["Role"] = relationship("Role", back_populates="policy")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    role: Mapped["Role"] = relationship("Role", back_populates="users")
    audit_events: Mapped[list["AuditEvent"]] = relationship("AuditEvent", back_populates="user")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Identity
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    user_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Prompt data (raw prompt stored only if STORE_RAW_PROMPTS=True)
    prompt_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sanitized_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Security results
    threats_detected: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    sanitization_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    block_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    security_level_used: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Performance
    processing_time_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    vetting_time_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    llm_time_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # LLM metadata
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Action taken
    action: Mapped[str] = mapped_column(String(20), default="passed", nullable=False)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_events")
