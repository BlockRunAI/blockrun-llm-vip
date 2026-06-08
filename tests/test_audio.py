"""Unit tests for the Audio client's pure body builders (no network)."""

import pytest

from blockrun_llm_vip._audio_client import (
    DEFAULT_MUSIC_MODEL,
    DEFAULT_SFX_MODEL,
    DEFAULT_SPEECH_MODEL,
    build_music_body,
    build_sound_effects_body,
    build_speech_body,
)


# ---- speech -----------------------------------------------------------------

def test_speech_body_minimal_uses_input_field():
    assert build_speech_body("hello") == {"model": DEFAULT_SPEECH_MODEL, "input": "hello"}


def test_speech_body_full():
    body = build_speech_body("hi", voice="sarah", response_format="wav", speed=1.1)
    assert body == {
        "model": DEFAULT_SPEECH_MODEL,
        "input": "hi",
        "voice": "sarah",
        "response_format": "wav",
        "speed": 1.1,
    }


def test_speech_body_bad_format_rejected():
    with pytest.raises(ValueError, match="response_format"):
        build_speech_body("hi", response_format="flac")


def test_speech_body_speed_bounds():
    with pytest.raises(ValueError, match="speed"):
        build_speech_body("hi", speed=2.0)


def test_speech_body_empty_rejected():
    with pytest.raises(ValueError, match="text"):
        build_speech_body("   ")


# ---- music ------------------------------------------------------------------

def test_music_body_minimal():
    assert build_music_body("lofi beat") == {"model": DEFAULT_MUSIC_MODEL, "prompt": "lofi beat"}


def test_music_body_instrumental_with_lyrics_rejected():
    with pytest.raises(ValueError, match="lyrics"):
        build_music_body("beat", instrumental=True, lyrics="la la")


def test_music_body_duration_bounds():
    with pytest.raises(ValueError, match="duration_seconds"):
        build_music_body("beat", duration_seconds=999)


def test_music_body_lyrics_ok_without_instrumental():
    body = build_music_body("ballad", lyrics="hello world", duration_seconds=120)
    assert body["lyrics"] == "hello world"
    assert body["duration_seconds"] == 120


# ---- sound effects ----------------------------------------------------------

def test_sfx_body_minimal_uses_text_field():
    assert build_sound_effects_body("thunder") == {
        "model": DEFAULT_SFX_MODEL,
        "text": "thunder",
    }


def test_sfx_body_duration_bounds():
    with pytest.raises(ValueError, match="duration_seconds"):
        build_sound_effects_body("thunder", duration_seconds=30)


def test_sfx_body_prompt_influence_bounds():
    with pytest.raises(ValueError, match="prompt_influence"):
        build_sound_effects_body("thunder", prompt_influence=2)


def test_sfx_body_too_long_rejected():
    with pytest.raises(ValueError, match="at most 1000"):
        build_sound_effects_body("x" * 1001)
