"""Unit tests for Voice + Phone pure logic (no network)."""

import httpx
import pytest

from blockrun_llm_vip._voice_client import (
    VoiceError,
    _default_timeout,
    _interpret_call_poll,
    build_call_body,
)


def _resp(status, json_body):
    return httpx.Response(status, json=json_body, request=httpx.Request("GET", "http://x"))


# ---- build_call_body --------------------------------------------------------

def test_call_body_minimal():
    body = build_call_body("+14155551234", "Please confirm the reservation for tonight.")
    assert body == {
        "to": "+14155551234",
        "task": "Please confirm the reservation for tonight.",
    }


def test_call_body_maps_from_keyword():
    body = build_call_body(
        "+1415", "Confirm hours please today.", from_="+1888", max_duration=3, voice="nat"
    )
    assert body["from"] == "+1888"
    assert body["max_duration"] == 3
    assert body["voice"] == "nat"


def test_call_body_requires_to():
    with pytest.raises(ValueError, match="to is required"):
        build_call_body("  ", "a task that is long enough")


def test_call_body_task_min_length():
    with pytest.raises(ValueError, match="at least 10"):
        build_call_body("+1415", "short")


def test_call_body_voicemail_message_required():
    with pytest.raises(ValueError, match="voicemail_message"):
        build_call_body(
            "+1415", "Leave a detailed message please.", voicemail_action="leave_message"
        )


# ---- poll interpretation ----------------------------------------------------

def test_call_poll_in_progress_keeps_polling():
    assert _interpret_call_poll(_resp(200, {"completed": False, "status": "in-progress"})) is None


def test_call_poll_completed_returns():
    body = {"completed": True, "ended_by": "USER", "transcript": "..."}
    assert _interpret_call_poll(_resp(200, body)) == body


def test_call_poll_error_raises():
    with pytest.raises(VoiceError, match="boom"):
        _interpret_call_poll(_resp(200, {"completed": False, "status": "error", "error_message": "boom"}))


def test_call_poll_404_raises():
    with pytest.raises(VoiceError, match="not found"):
        _interpret_call_poll(_resp(404, {"error": "Call not found"}))


def test_default_timeout_scales_with_max_duration():
    assert _default_timeout(None) == 5 * 60 + 120
    assert _default_timeout(10) == 10 * 60 + 120
