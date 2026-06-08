"""Unit tests for the Image client's pure logic (no network)."""

import httpx
import pytest

from blockrun_llm_vip._image_client import (
    DEFAULT_EDIT_MODEL,
    DEFAULT_IMAGE_MODEL,
    ImageGenerationError,
    _interpret_poll,
    _interpret_submit,
    _is_inline_done,
    build_edit_body,
    build_image_body,
    encode_data_uri,
)


def _resp(status, json_body):
    return httpx.Response(status, json=json_body, request=httpx.Request("GET", "http://x"))


# ---- build_image_body -------------------------------------------------------

def test_image_body_minimal():
    assert build_image_body("a fox", DEFAULT_IMAGE_MODEL) == {
        "model": DEFAULT_IMAGE_MODEL,
        "prompt": "a fox",
    }


def test_image_body_with_size_and_n():
    body = build_image_body("a fox", "google/nano-banana", size="1024x1024", n=3)
    assert body == {
        "model": "google/nano-banana",
        "prompt": "a fox",
        "size": "1024x1024",
        "n": 3,
    }


def test_image_body_empty_prompt_rejected():
    with pytest.raises(ValueError, match="prompt"):
        build_image_body("  ", DEFAULT_IMAGE_MODEL)


# ---- build_edit_body --------------------------------------------------------

def test_edit_body_single_image_stays_scalar():
    body = build_edit_body("night", "data:image/png;base64,AAA", model=DEFAULT_EDIT_MODEL)
    assert body["image"] == "data:image/png;base64,AAA"
    assert body["model"] == DEFAULT_EDIT_MODEL


def test_edit_body_multi_image_becomes_list():
    body = build_edit_body("fuse", ["data:a", "data:b"], model=DEFAULT_EDIT_MODEL)
    assert body["image"] == ["data:a", "data:b"]


def test_edit_body_mask_with_multiple_images_rejected():
    with pytest.raises(ValueError, match="mask"):
        build_edit_body(
            "x", ["data:a", "data:b"], model=DEFAULT_EDIT_MODEL, mask="data:m"
        )


def test_edit_body_empty_image_rejected():
    with pytest.raises(ValueError, match="image is required"):
        build_edit_body("x", [], model=DEFAULT_EDIT_MODEL)


# ---- submit / poll interpretation -------------------------------------------

def test_image_submit_inline_200():
    body = {"created": 1, "data": [{"url": "http://m/i.png"}]}
    assert _interpret_submit(_resp(200, body)) == body
    assert _is_inline_done(body) is True


def test_image_submit_async_202():
    body = {"id": "job_1", "status": "queued", "poll_url": "/api/v1/images/generations/job_1"}
    assert _interpret_submit(_resp(202, body)) == body
    assert _is_inline_done(body) is False


def test_image_submit_rejects_400():
    with pytest.raises(ImageGenerationError):
        _interpret_submit(_resp(400, {"error": "bad"}))


def test_image_poll_202_keeps_polling():
    assert _interpret_poll(_resp(202, {"status": "in_progress"})) is None


def test_image_poll_200_completed_returns():
    body = {"status": "completed", "data": [{"url": "http://m/i.png"}], "payment": {}}
    assert _interpret_poll(_resp(200, body)) == body


def test_image_poll_200_failed_raises():
    with pytest.raises(ImageGenerationError, match="content policy"):
        _interpret_poll(_resp(200, {"status": "failed", "error": "content policy"}))


# ---- helpers ----------------------------------------------------------------

def test_encode_data_uri():
    assert encode_data_uri(b"\x00\x01", "image/png") == "data:image/png;base64,AAE="
