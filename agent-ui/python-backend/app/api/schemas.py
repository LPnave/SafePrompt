"""
Pydantic request/response schemas for all API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, EmailStr


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(..., description="Role name: admin, engineering, hr, finance")
    department: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[Dict] = None


class UserProfileResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    department: Optional[str]
    is_admin: bool
    is_active: bool


# ---------------------------------------------------------------------------
# Sanitize
# ---------------------------------------------------------------------------

class SanitizeRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    security_level: Optional[str] = Field(None, description="Override: low, medium, high")
    return_details: bool = False


class SanitizeResponse(BaseModel):
    is_safe: bool
    sanitized_prompt: str
    original_prompt: str
    warnings: List[str] = []
    blocked_patterns: List[str] = []
    confidence: float
    modifications_made: bool
    sanitization_details: Optional[Dict] = None
    processing_time_ms: float


class BatchSanitizeRequest(BaseModel):
    prompts: List[str]
    security_level: Optional[str] = None
    return_details: bool = False


class BatchSanitizeResponse(BaseModel):
    results: List[SanitizeResponse]
    total_processed: int
    total_time_ms: float


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    model_config = {"extra": "allow"}
    role: str
    content: Union[str, List[Any], Dict[str, Any]]


class ChatRequest(BaseModel):
    model_config = {"extra": "allow"}
    messages: List[ChatMessage]
    session_id: Optional[str] = None
    stream: Optional[bool] = False


# ---------------------------------------------------------------------------
# Security level (admin-only)
# ---------------------------------------------------------------------------

class SecurityLevelUpdate(BaseModel):
    level: str


class SecurityLevelResponse(BaseModel):
    level: str
    success: bool
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Health & Stats
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    uptime_seconds: float
    version: str


class StatsResponse(BaseModel):
    security_level: str
    model_info: Dict
    request_stats: Dict
    capabilities: List[str]


# ---------------------------------------------------------------------------
# Admin — users
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str
    department: Optional[str] = None


class UpdateUserRequest(BaseModel):
    role_name: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    department: Optional[str]
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Admin — roles & policies
# ---------------------------------------------------------------------------

class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9_-]+$")
    description: Optional[str] = Field(None, max_length=255)
    is_admin: bool = False


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=50, pattern=r"^[a-z0-9_-]+$")
    description: Optional[str] = Field(None, max_length=255)
    is_admin: Optional[bool] = None


class RolePolicyResponse(BaseModel):
    id: int
    role_id: int
    security_level: str
    max_prompt_length: int
    max_requests_per_day: int
    system_prompt: Optional[str]
    allowed_topics: Optional[List[str]]
    blocked_topics: Optional[List[str]]
    enforce_topic_restrictions: bool
    response_filter_enabled: bool
    max_conversation_turns: int
    session_timeout_minutes: int
    allow_file_uploads: bool
    time_restriction_start: Optional[str]
    time_restriction_end: Optional[str]
    updated_at: datetime


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_admin: bool
    policy: Optional[RolePolicyResponse] = None


class UpdatePolicyRequest(BaseModel):
    security_level: Optional[str] = None
    max_prompt_length: Optional[int] = None
    max_requests_per_day: Optional[int] = None
    system_prompt: Optional[str] = None
    allowed_topics: Optional[List[str]] = None
    blocked_topics: Optional[List[str]] = None
    enforce_topic_restrictions: Optional[bool] = None
    response_filter_enabled: Optional[bool] = None
    max_conversation_turns: Optional[int] = Field(None, ge=1, le=500)
    session_timeout_minutes: Optional[int] = Field(None, ge=1, le=1440)
    allow_file_uploads: Optional[bool] = None
    time_restriction_start: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    time_restriction_end: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

class UsageSummaryItem(BaseModel):
    day: str
    role: str
    total: int
    blocked: int
    sanitized: int


class ThreatBreakdownItem(BaseModel):
    role: str
    action: str
    count: int


class UserActivityItem(BaseModel):
    user_id: Optional[int]
    role: Optional[str]
    department: Optional[str]
    total_prompts: int
    blocked: int
    avg_latency_ms: float


class BlockedEventResponse(BaseModel):
    id: str
    timestamp: datetime
    user_id: Optional[int]
    user_role: Optional[str]
    department: Optional[str]
    prompt_length: int
    block_reason: Optional[str]
    threats_detected: Optional[List[str]]
    security_level_used: Optional[str]
