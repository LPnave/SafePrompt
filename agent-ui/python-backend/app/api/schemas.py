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
    allow_file_uploads: bool = False
    time_restriction_start: Optional[str] = None
    time_restriction_end: Optional[str] = None
    session_timeout_minutes: int = 60
    max_conversation_turns: int = 50
    security_level: str = "medium"
    max_prompt_length: int = 4000
    max_requests_per_day: int = 100
    requests_today: int = 0


# ---------------------------------------------------------------------------
# Sanitize
# ---------------------------------------------------------------------------

class SanitizeRequest(BaseModel):
    prompt: str = ""
    session_id: Optional[str] = Field(None, description="Conversation session id for turn-limit checks")
    has_attachments: bool = False
    security_level: Optional[str] = Field(None, description="Admin override: low, medium, high")
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
    preflight_token: Optional[str] = None


class BatchSanitizeRequest(BaseModel):
    prompts: List[str]
    session_id: Optional[str] = None
    has_attachments: bool = False
    security_level: Optional[str] = Field(None, description="Admin override: low, medium, high")
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
    preflight_token: Optional[str] = None
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


# ---------------------------------------------------------------------------
# Chat threads & messages
# ---------------------------------------------------------------------------

class CreateThreadRequest(BaseModel):
    id: Optional[str] = Field(None, description="Client-generated thread UUID")
    title: Optional[str] = Field(None, max_length=255)


class ThreadInitializeResponse(BaseModel):
    remoteId: str
    externalId: Optional[str] = None
    title: str


class ThreadSummary(BaseModel):
    remoteId: str
    title: Optional[str]
    status: str
    updated_at: datetime
    message_count: int = 0


class ThreadDetail(BaseModel):
    id: str
    title: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class UpdateThreadRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    status: Optional[str] = Field(None, pattern=r"^(active|archived)$")


class MessageRecord(BaseModel):
    id: str
    role: str
    content: str
    parent_id: Optional[str]
    created_at: datetime


class AppendMessageRequest(BaseModel):
    message: Dict[str, Any]
    parentId: Optional[str] = None


class MessageRepositoryResponse(BaseModel):
    headId: Optional[str] = None
    messages: List[Dict[str, Any]]


class AdminThreadSummary(BaseModel):
    id: str
    title: Optional[str]
    status: str
    user_id: int
    username: str
    message_count: int
    updated_at: datetime


class AdminThreadListResponse(BaseModel):
    threads: List[AdminThreadSummary]
    total: int
