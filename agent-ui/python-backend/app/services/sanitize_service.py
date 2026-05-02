"""
Sanitization service — wraps the security validator for standalone sanitize endpoints.
"""

import time
from fastapi import HTTPException, status

from app.services.chat_service import get_validator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def sanitize_single(prompt: str, security_level: str | None = None) -> dict:
    """Run validation on a single prompt and return structured results."""
    validator = get_validator()
    start = time.time()

    if security_level:
        result = validator.validate_for_role(prompt, security_level)
    else:
        result = validator.validate_prompt(prompt)

    processing_time = (time.time() - start) * 1000

    return {
        "is_safe": result.is_safe,
        "sanitized_prompt": result.modified_prompt,
        "original_prompt": prompt,
        "warnings": result.warnings,
        "blocked_patterns": result.blocked_patterns,
        "confidence": result.confidence,
        "modifications_made": prompt != result.modified_prompt,
        "processing_time_ms": result.processing_time_ms or processing_time,
    }


def sanitize_batch(prompts: list[str], security_level: str | None = None) -> list[dict]:
    """Run validation on multiple prompts."""
    return [sanitize_single(p, security_level) for p in prompts]
