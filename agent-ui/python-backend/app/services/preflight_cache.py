"""
Short-lived cache for sanitize preflight results to avoid duplicate validator runs.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass

from app.services.policy_service import PolicyEnforcementResult

_TTL_SECONDS = 120
_cache: dict[str, dict] = {}


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


@dataclass
class CachedPreflight:
    validation_result: object
    vetting_time_ms: float


def issue_token(
    user_id: int,
    prompt: str,
    enforcement: PolicyEnforcementResult,
) -> str:
    _purge_expired()
    token = secrets.token_urlsafe(32)
    _cache[token] = {
        "user_id": user_id,
        "prompt_hash": _prompt_hash(prompt),
        "validation_result": enforcement.validation_result,
        "vetting_time_ms": enforcement.vetting_time_ms,
        "expires_at": time.time() + _TTL_SECONDS,
    }
    return token


def consume_token(user_id: int, prompt: str, token: str | None) -> PolicyEnforcementResult | None:
    if not token:
        return None
    _purge_expired()
    entry = _cache.pop(token, None)
    if entry is None:
        return None
    if entry["user_id"] != user_id:
        return None
    if entry["prompt_hash"] != _prompt_hash(prompt):
        return None
    return PolicyEnforcementResult(
        validation_result=entry["validation_result"],
        vetting_time_ms=entry["vetting_time_ms"],
    )


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, v in _cache.items() if v["expires_at"] <= now]
    for key in expired:
        del _cache[key]
