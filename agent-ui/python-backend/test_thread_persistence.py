"""
Unit tests for chat thread/message repositories and turn counting.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.policy_service import check_conversation_turns


class _User:
    id = 1


class _Policy:
    max_conversation_turns = 3


@pytest.mark.asyncio
async def test_check_conversation_turns_uses_message_repo_first():
    audit_repo = AsyncMock()
    audit_repo.count_session_turns_for_user = AsyncMock(return_value=5)
    message_repo = AsyncMock()
    message_repo.count_user_turns = AsyncMock(return_value=3)

    with pytest.raises(Exception) as exc:
        await check_conversation_turns(
            _User(), _Policy(), "thread-1", audit_repo, message_repo
        )
    assert exc.value.status_code == 429
    message_repo.count_user_turns.assert_awaited_once_with("thread-1")
    audit_repo.count_session_turns_for_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_conversation_turns_falls_back_to_audit_when_no_messages():
    audit_repo = AsyncMock()
    audit_repo.count_session_turns_for_user = AsyncMock(return_value=3)
    message_repo = AsyncMock()
    message_repo.count_user_turns = AsyncMock(return_value=0)

    with pytest.raises(Exception) as exc:
        await check_conversation_turns(
            _User(), _Policy(), "thread-1", audit_repo, message_repo
        )
    assert exc.value.status_code == 429
    audit_repo.count_session_turns_for_user.assert_awaited_once_with(1, "thread-1")


def test_message_to_dto_shape():
    from app.services.thread_service import message_to_dto

    row = MagicMock()
    row.id = "msg-1"
    row.role = "user"
    row.content = "hello"
    row.parent_id = None
    row.created_at = None

    dto = message_to_dto(row)
    assert dto["message"]["id"] == "msg-1"
    assert dto["message"]["role"] == "user"
    assert dto["message"]["content"][0]["text"] == "hello"
    assert dto["message"]["metadata"] == {"custom": {}}
    assert dto["message"]["attachments"] == []
    assert dto["parentId"] is None


def test_assistant_message_to_dto_includes_metadata():
    from app.services.thread_service import message_to_dto

    row = MagicMock()
    row.id = "msg-2"
    row.role = "assistant"
    row.content = "hi there"
    row.parent_id = "msg-1"
    row.created_at = None

    dto = message_to_dto(row)
    assert dto["message"]["status"] == {"type": "complete", "reason": "stop"}
    assert dto["message"]["metadata"]["unstable_state"] is None
    assert dto["message"]["metadata"]["custom"] == {}
