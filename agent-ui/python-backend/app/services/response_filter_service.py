"""
LLM output filtering — redact sensitive content before delivery.
"""

from dataclasses import dataclass

from app.db.models import RolePolicy


@dataclass
class FilterResult:
    delivered: str
    filtered: bool
    warnings: list[str] | None = None


def filter_llm_response(text: str, policy: RolePolicy, validator) -> FilterResult:
    if not policy.response_filter_enabled:
        return FilterResult(delivered=text, filtered=False)

    result = validator.validate_for_role(text, policy.security_level)
    if result.is_safe and text == result.modified_prompt:
        return FilterResult(delivered=text, filtered=False)

    delivered = result.modified_prompt or "[Response redacted due to policy]"
    return FilterResult(
        delivered=delivered,
        filtered=True,
        warnings=result.warnings,
    )
