"""
Unit tests for time-of-day restriction policy checks.
"""

import pytest
from fastapi import HTTPException

from app.services.policy_service import (
    check_time_restriction,
    is_within_time_window,
    validate_time_restriction_fields,
)


class _Policy:
    time_restriction_start = None
    time_restriction_end = None


def test_no_restriction_when_fields_unset():
    policy = _Policy()
    check_time_restriction(policy)  # should not raise


def test_normal_window_inside():
    assert is_within_time_window("09:00", "18:00", "13:45") is True


def test_normal_window_outside():
    assert is_within_time_window("09:00", "18:00", "08:30") is False
    assert is_within_time_window("09:00", "18:00", "18:01") is False


def test_normal_window_boundaries_inclusive():
    assert is_within_time_window("09:00", "18:00", "09:00") is True
    assert is_within_time_window("09:00", "18:00", "18:00") is True


def test_midnight_wrap_inside_late():
    assert is_within_time_window("22:00", "06:00", "23:30") is True


def test_midnight_wrap_inside_early():
    assert is_within_time_window("22:00", "06:00", "05:00") is True


def test_midnight_wrap_outside():
    assert is_within_time_window("22:00", "06:00", "12:00") is False


def test_check_time_restriction_raises_when_outside_window():
    from unittest.mock import patch
    from app.services import policy_service

    policy = _Policy()
    policy.time_restriction_start = "09:00"
    policy.time_restriction_end = "12:00"
    with patch.object(policy_service, "is_within_time_window", return_value=False):
        with pytest.raises(HTTPException) as exc:
            check_time_restriction(policy)
        assert exc.value.status_code == 403
        assert "UTC" in exc.value.detail


def test_validate_requires_both_fields():
    with pytest.raises(HTTPException) as exc:
        validate_time_restriction_fields("09:00", None)
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        validate_time_restriction_fields(None, "18:00")
    assert exc.value.status_code == 400


def test_validate_rejects_equal_times():
    with pytest.raises(HTTPException) as exc:
        validate_time_restriction_fields("09:00", "09:00")
    assert exc.value.status_code == 400


def test_validate_accepts_valid_pair():
    validate_time_restriction_fields("09:00", "18:00")
    validate_time_restriction_fields(None, None)
