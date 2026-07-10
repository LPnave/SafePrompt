"""
Unit tests for LLM response filtering.
"""

from unittest.mock import MagicMock

from app.services.response_filter_service import filter_llm_response


class _Policy:
    response_filter_enabled = True
    security_level = "medium"


class _ValidationResult:
    def __init__(self, is_safe, modified_prompt, warnings=None):
        self.is_safe = is_safe
        self.modified_prompt = modified_prompt
        self.warnings = warnings or []


def test_filter_passthrough_when_disabled():
    policy = _Policy()
    policy.response_filter_enabled = False
    validator = MagicMock()
    result = filter_llm_response("hello world", policy, validator)
    assert result.delivered == "hello world"
    assert result.filtered is False
    validator.validate_for_role.assert_not_called()


def test_filter_redacts_unsafe_output():
    policy = _Policy()
    validator = MagicMock()
    validator.validate_for_role.return_value = _ValidationResult(
        is_safe=False,
        modified_prompt="[REDACTED]",
        warnings=["Credential exposure detected"],
    )
    result = filter_llm_response("secret password is abc", policy, validator)
    assert result.filtered is True
    assert result.delivered == "[REDACTED]"
    assert result.warnings == ["Credential exposure detected"]


def test_filter_passthrough_when_safe():
    policy = _Policy()
    validator = MagicMock()
    validator.validate_for_role.return_value = _ValidationResult(
        is_safe=True,
        modified_prompt="safe answer",
    )
    result = filter_llm_response("safe answer", policy, validator)
    assert result.filtered is False
    assert result.delivered == "safe answer"
