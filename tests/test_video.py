"""Unit tests for the Seedance/RealFace video client's pure logic (no network)."""

import httpx
import pytest

from blockrun_llm_vip._video_client import (
    DEFAULT_VIDEO_MODEL,
    VideoGenerationError,
    _interpret_poll,
    _interpret_submit,
    build_video_body,
    resolve_poll_url,
)
from blockrun_llm_vip._realface import _is_active
from blockrun_llm_vip._realface import _list_url as _rf_list_url
from blockrun_llm_vip._portrait import _enroll_url as _vp_enroll_url
from blockrun_llm_vip._portrait import _list_url as _vp_list_url


# ---- build_video_body -------------------------------------------------------

def test_body_minimal_omits_none_options():
    body = build_video_body("a corgi surfing", DEFAULT_VIDEO_MODEL)
    assert body == {"model": DEFAULT_VIDEO_MODEL, "prompt": "a corgi surfing"}


def test_body_includes_only_provided_options():
    body = build_video_body(
        "she waves",
        "bytedance/seedance-2.0",
        real_face_asset_id="ta_abc",
        duration_seconds=5,
        aspect_ratio="9:16",
        generate_audio=False,
    )
    assert body == {
        "model": "bytedance/seedance-2.0",
        "prompt": "she waves",
        "real_face_asset_id": "ta_abc",
        "duration_seconds": 5,
        "aspect_ratio": "9:16",
        "generate_audio": False,
    }


def test_body_empty_prompt_rejected():
    with pytest.raises(ValueError, match="prompt"):
        build_video_body("   ", DEFAULT_VIDEO_MODEL)


def test_body_image_and_realface_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_video_body(
            "x",
            "bytedance/seedance-2.0",
            image_url="https://e/x.jpg",
            real_face_asset_id="ta_abc",
        )


def test_body_realface_requires_seedance_2():
    with pytest.raises(ValueError, match="RealFace"):
        build_video_body(
            "x", "bytedance/seedance-1.5-pro", real_face_asset_id="ta_abc"
        )
    # 2.0 and 2.0-fast are allowed
    build_video_body("x", "bytedance/seedance-2.0", real_face_asset_id="ta_abc")
    build_video_body("x", "bytedance/seedance-2.0-fast", real_face_asset_id="ta_abc")


def test_body_last_frame_requires_image_url():
    with pytest.raises(ValueError, match="requires image_url"):
        build_video_body(
            "x", "bytedance/seedance-2.0", last_frame_url="https://e/last.jpg"
        )
    body = build_video_body(
        "x",
        "bytedance/seedance-2.0",
        image_url="https://e/first.jpg",
        last_frame_url="https://e/last.jpg",
    )
    assert body["image_url"] == "https://e/first.jpg"
    assert body["last_frame_url"] == "https://e/last.jpg"


def test_body_reference_images_count_and_model():
    # only on Seedance 2.0 generation
    with pytest.raises(ValueError, match="omni"):
        build_video_body(
            "x", "bytedance/seedance-1.5-pro", reference_image_urls=["https://e/a.jpg"]
        )
    # 1..9 enforced
    with pytest.raises(ValueError, match="between 1 and 9"):
        build_video_body(
            "x", "bytedance/seedance-2.0", reference_image_urls=[f"u{i}" for i in range(10)]
        )
    body = build_video_body(
        "x", "bytedance/seedance-2.0", reference_image_urls=["https://e/a.jpg"]
    )
    assert body["reference_image_urls"] == ["https://e/a.jpg"]


def test_body_reference_images_exclusive_with_image_url():
    with pytest.raises(ValueError, match="mutually exclusive"):
        build_video_body(
            "x",
            "bytedance/seedance-2.0",
            image_url="https://e/x.jpg",
            reference_image_urls=["https://e/a.jpg"],
        )


# ---- resolve_poll_url -------------------------------------------------------

def test_poll_url_root_relative_joins_origin_not_api_root():
    out = resolve_poll_url(
        "https://blockrun.ai/api",
        "/api/v1/videos/generations/x%3Ay?model=z&duration=8",
    )
    assert out == "https://blockrun.ai/api/v1/videos/generations/x%3Ay?model=z&duration=8"


def test_poll_url_absolute_passthrough():
    abs_url = "https://blockrun.ai/api/v1/videos/generations/abc"
    assert resolve_poll_url("https://blockrun.ai/api", abs_url) == abs_url


def test_poll_url_localhost():
    out = resolve_poll_url("http://localhost:3000/api", "/api/v1/videos/generations/j")
    assert out == "http://localhost:3000/api/v1/videos/generations/j"


def test_poll_url_missing_raises():
    with pytest.raises(VideoGenerationError):
        resolve_poll_url("https://blockrun.ai/api", "")


# ---- poll / submit interpretation -------------------------------------------

def _resp(status, json_body):
    return httpx.Response(status, json=json_body, request=httpx.Request("GET", "http://x"))


def test_poll_202_keeps_polling():
    assert _interpret_poll(_resp(202, {"status": "in_progress"})) is None


def test_poll_200_completed_returns_body():
    body = {"status": "completed", "data": [{"url": "http://m/v.mp4"}]}
    assert _interpret_poll(_resp(200, body)) == body


def test_poll_200_failed_raises():
    with pytest.raises(VideoGenerationError, match="content policy"):
        _interpret_poll(_resp(200, {"status": "failed", "error": "content policy"}))


def test_submit_rejects_non_2xx():
    with pytest.raises(VideoGenerationError):
        _interpret_submit(_resp(400, {"error": "bad"}))


# ---- realface ---------------------------------------------------------------

def test_realface_is_active():
    assert _is_active({"status": "active", "ready_to_finalize": True}) is True
    assert _is_active({"ready_to_finalize": True}) is True
    assert _is_active({"status": "pending_validation", "ready_to_finalize": False}) is False


def test_realface_list_url():
    assert (
        _rf_list_url("https://blockrun.ai/api", "0xABC")
        == "https://blockrun.ai/api/v1/wallet/0xABC/realfaces"
    )


# ---- virtual portrait -------------------------------------------------------

def test_portrait_enroll_url():
    assert _vp_enroll_url("https://blockrun.ai/api") == (
        "https://blockrun.ai/api/v1/portrait/enroll"
    )


def test_portrait_list_url():
    assert (
        _vp_list_url("https://blockrun.ai/api", "0xABC")
        == "https://blockrun.ai/api/v1/wallet/0xABC/portraits"
    )
