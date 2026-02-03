"""
API Request and Response models
"""

from typing import List, Optional, Dict, Union, Any
from pydantic import BaseModel, Field


class SanitizeRequest(BaseModel):
    """Request model for sanitization endpoint"""
    prompt: str = Field(..., description="The prompt to sanitize", min_length=1)
    security_level: Optional[str] = Field(None, description="Security level: low, medium, or high (None = use global setting)")
    return_details: bool = Field(False, description="Whether to return detailed classification info")


class SanitizeResponse(BaseModel):
    """Response model for sanitization endpoint"""
    is_safe: bool = Field(..., description="Whether the prompt is safe")
    sanitized_prompt: str = Field(..., description="The sanitized prompt")
    original_prompt: str = Field(..., description="The original prompt")
    warnings: List[str] = Field(default_factory=list, description="List of security warnings")
    blocked_patterns: List[str] = Field(default_factory=list, description="List of blocked patterns")
    confidence: float = Field(..., description="Confidence score of the assessment")
    modifications_made: bool = Field(..., description="Whether the prompt was modified")
    sanitization_details: Optional[Dict] = Field(None, description="Detailed sanitization info")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")


class BatchSanitizeRequest(BaseModel):
    """Request model for batch sanitization"""
    prompts: List[str] = Field(..., description="List of prompts to sanitize")
    security_level: Optional[str] = Field(None, description="Security level for all prompts (None = use global setting)")
    return_details: bool = Field(False, description="Whether to return detailed info")


class BatchSanitizeResponse(BaseModel):
    """Response model for batch sanitization"""
    results: List[SanitizeResponse] = Field(..., description="List of sanitization results")
    total_processed: int = Field(..., description="Total number of prompts processed")
    total_time_ms: float = Field(..., description="Total processing time in milliseconds")


class SecurityLevelUpdate(BaseModel):
    """Request model for updating security level"""
    level: str = Field(..., description="Security level: low, medium, or high")


class SecurityLevelResponse(BaseModel):
    """Response model for security level"""
    level: str = Field(..., description="Current security level")
    success: bool = Field(..., description="Whether the operation was successful")
    message: Optional[str] = Field(None, description="Additional message")


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str = Field(..., description="Health status")
    model_loaded: bool = Field(..., description="Whether ML models are loaded")
    uptime_seconds: float = Field(..., description="Server uptime in seconds")
    version: str = Field(..., description="API version")


class StatsResponse(BaseModel):
    """Response model for statistics"""
    security_level: str = Field(..., description="Current security level")
    model_info: Dict = Field(..., description="ML model information")
    request_stats: Dict = Field(..., description="Request statistics")
    capabilities: List[str] = Field(..., description="System capabilities")


class ChatMessage(BaseModel):
    """Chat message model"""
    model_config = {"extra": "allow"}  # Allow extra fields from frontend
    
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: Union[str, List[Any], Dict[str, Any]] = Field(..., description="Message content (string, array, or object)")


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    model_config = {"extra": "allow"}  # Allow extra fields from frontend
    
    messages: List[ChatMessage] = Field(..., description="List of chat messages")
    security_level: Optional[str] = Field(default=None, description="Security level for sanitization (None = use global setting)")
    stream: Optional[bool] = Field(default=False, description="Whether to stream the response")


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    message: ChatMessage = Field(..., description="AI response message")
    sanitization_applied: bool = Field(..., description="Whether sanitization was applied")
    warnings: List[str] = Field(default_factory=list, description="Security warnings")
    original_prompt: Optional[str] = Field(None, description="Original user prompt before sanitization")