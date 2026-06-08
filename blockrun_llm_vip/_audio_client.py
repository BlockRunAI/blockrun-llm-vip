"""Audio generation through the BlockRun gateway, paid via x402 — text-to-speech,
music, and sound effects.

Every audio call is a single (server-blocking) request — no client polling. The gateway
holds the connection until the audio is ready and returns the VERBATIM job JSON
(``data[].url`` is a permanent BlockRun-hosted file). Music can take 1-3 minutes, so the
client's default timeout is generous; speech and sound effects return in ~1s. The SAME
wallet pays via the chain transport (402 → sign → retry).

    from blockrun_llm_vip import Audio

    audio = Audio()  # wallet auto-loaded from ~/.blockrun/.session

    speech = audio.speech("Hello there.", voice="sarah")          # ElevenLabs TTS
    track  = audio.music("dreamy lo-fi beat", instrumental=True)  # MiniMax music
    sfx    = audio.sound_effects("distant thunder over rain")     # ElevenLabs SFX
    print(speech["data"][0]["url"], track["data"][0]["url"])

    audio.voices()  # FREE: list TTS voices    audio.models()  # FREE: music models

Async: `from blockrun_llm_vip import AsyncAudio`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ._common import resolve_chain
from ._http import ok_json

_SPEECH_PATH = "/v1/audio/speech"
_MUSIC_PATH = "/v1/audio/generations"
_SFX_PATH = "/v1/audio/sound-effects"
_VOICES_PATH = "/v1/audio/voices"
_MODELS_PATH = "/v1/audio/models"

DEFAULT_SPEECH_MODEL = "elevenlabs/flash-v2.5"
DEFAULT_MUSIC_MODEL = "minimax/music-2.5+"
DEFAULT_SFX_MODEL = "elevenlabs/sound-effects"

_AUDIO_FORMATS = frozenset({"mp3", "opus", "pcm", "wav"})


class AudioGenerationError(RuntimeError):
    """Raised when the gateway rejects or fails an audio request (no charge on failure)."""


def _check_format(response_format: Optional[str]) -> None:
    if response_format is not None and response_format not in _AUDIO_FORMATS:
        raise ValueError(
            f"response_format must be one of {sorted(_AUDIO_FORMATS)}, got {response_format!r}"
        )


def build_speech_body(
    text: str,
    *,
    model: str = DEFAULT_SPEECH_MODEL,
    voice: Optional[str] = None,
    response_format: Optional[str] = None,
    speed: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the POST body for /v1/audio/speech. ``text`` maps to the gateway's
    ``input`` field. Pure (no I/O), unit-testable."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text is required and must be a non-empty string")
    _check_format(response_format)
    if speed is not None and not 0.7 <= speed <= 1.2:
        raise ValueError("speed must be between 0.7 and 1.2")
    body: Dict[str, Any] = {"model": model, "input": text}
    if voice is not None:
        body["voice"] = voice
    if response_format is not None:
        body["response_format"] = response_format
    if speed is not None:
        body["speed"] = speed
    return body


def build_music_body(
    prompt: str,
    *,
    model: str = DEFAULT_MUSIC_MODEL,
    lyrics: Optional[str] = None,
    instrumental: Optional[bool] = None,
    duration_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the POST body for /v1/audio/generations (music)."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required and must be a non-empty string")
    if instrumental and lyrics is not None:
        raise ValueError("lyrics cannot be set when instrumental=True")
    if duration_seconds is not None and not 5 <= duration_seconds <= 240:
        raise ValueError("duration_seconds must be between 5 and 240")
    body: Dict[str, Any] = {"model": model, "prompt": prompt}
    if lyrics is not None:
        body["lyrics"] = lyrics
    if instrumental is not None:
        body["instrumental"] = instrumental
    if duration_seconds is not None:
        body["duration_seconds"] = duration_seconds
    return body


def build_sound_effects_body(
    text: str,
    *,
    model: str = DEFAULT_SFX_MODEL,
    duration_seconds: Optional[float] = None,
    prompt_influence: Optional[float] = None,
    response_format: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the POST body for /v1/audio/sound-effects."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text is required and must be a non-empty string")
    if len(text) > 1000:
        raise ValueError("text must be at most 1000 characters")
    _check_format(response_format)
    if duration_seconds is not None and not 0.5 <= duration_seconds <= 22:
        raise ValueError("duration_seconds must be between 0.5 and 22")
    if prompt_influence is not None and not 0 <= prompt_influence <= 1:
        raise ValueError("prompt_influence must be between 0 and 1")
    body: Dict[str, Any] = {"model": model, "text": text}
    if duration_seconds is not None:
        body["duration_seconds"] = duration_seconds
    if prompt_influence is not None:
        body["prompt_influence"] = prompt_influence
    if response_format is not None:
        body["response_format"] = response_format
    return body


class Audio:
    """Text-to-speech, music, and sound effects through BlockRun, paid via x402.

    ``chain="solana"`` pays USDC on Solana via sol.blockrun.ai instead of Base. The
    default ``request_timeout`` is generous so music (1-3 min) completes; override it if
    you only use speech.
    """

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        chain: str = "base",
        rpc_url: Optional[str] = None,
        request_timeout: float = 240.0,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        self._api_url = ctx.api_url
        self._client = httpx.Client(
            transport=ctx.make_transport(async_=False),
            timeout=request_timeout,
        )

    def speech(
        self,
        text: str,
        *,
        model: str = DEFAULT_SPEECH_MODEL,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Synthesize speech (ElevenLabs). Returns verbatim ``{created, model, data}``."""
        body = build_speech_body(
            text, model=model, voice=voice, response_format=response_format, speed=speed
        )
        return ok_json(
            self._client.post(f"{self._api_url}{_SPEECH_PATH}", json=body),
            "speech",
            error_cls=AudioGenerationError,
        )

    def music(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_MUSIC_MODEL,
        lyrics: Optional[str] = None,
        instrumental: Optional[bool] = None,
        duration_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generate a music track (MiniMax). Blocks until the track is ready (1-3 min)."""
        body = build_music_body(
            prompt,
            model=model,
            lyrics=lyrics,
            instrumental=instrumental,
            duration_seconds=duration_seconds,
        )
        return ok_json(
            self._client.post(f"{self._api_url}{_MUSIC_PATH}", json=body),
            "music",
            error_cls=AudioGenerationError,
        )

    def sound_effects(
        self,
        text: str,
        *,
        model: str = DEFAULT_SFX_MODEL,
        duration_seconds: Optional[float] = None,
        prompt_influence: Optional[float] = None,
        response_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a cinematic sound effect (ElevenLabs)."""
        body = build_sound_effects_body(
            text,
            model=model,
            duration_seconds=duration_seconds,
            prompt_influence=prompt_influence,
            response_format=response_format,
        )
        return ok_json(
            self._client.post(f"{self._api_url}{_SFX_PATH}", json=body),
            "sound_effects",
            error_cls=AudioGenerationError,
        )

    def voices(self) -> Dict[str, Any]:
        """FREE: list available TTS voices (alias + voice_id)."""
        return ok_json(
            self._client.get(f"{self._api_url}{_VOICES_PATH}"),
            "voices",
            error_cls=AudioGenerationError,
        )

    def models(self) -> Dict[str, Any]:
        """FREE: list available music models."""
        return ok_json(
            self._client.get(f"{self._api_url}{_MODELS_PATH}"),
            "models",
            error_cls=AudioGenerationError,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Audio":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncAudio:
    """Async counterpart of :class:`Audio`."""

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        chain: str = "base",
        rpc_url: Optional[str] = None,
        request_timeout: float = 240.0,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        self._api_url = ctx.api_url
        self._client = httpx.AsyncClient(
            transport=ctx.make_transport(async_=True),
            timeout=request_timeout,
        )

    async def speech(
        self,
        text: str,
        *,
        model: str = DEFAULT_SPEECH_MODEL,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        speed: Optional[float] = None,
    ) -> Dict[str, Any]:
        body = build_speech_body(
            text, model=model, voice=voice, response_format=response_format, speed=speed
        )
        return ok_json(
            await self._client.post(f"{self._api_url}{_SPEECH_PATH}", json=body),
            "speech",
            error_cls=AudioGenerationError,
        )

    async def music(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_MUSIC_MODEL,
        lyrics: Optional[str] = None,
        instrumental: Optional[bool] = None,
        duration_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        body = build_music_body(
            prompt,
            model=model,
            lyrics=lyrics,
            instrumental=instrumental,
            duration_seconds=duration_seconds,
        )
        return ok_json(
            await self._client.post(f"{self._api_url}{_MUSIC_PATH}", json=body),
            "music",
            error_cls=AudioGenerationError,
        )

    async def sound_effects(
        self,
        text: str,
        *,
        model: str = DEFAULT_SFX_MODEL,
        duration_seconds: Optional[float] = None,
        prompt_influence: Optional[float] = None,
        response_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        body = build_sound_effects_body(
            text,
            model=model,
            duration_seconds=duration_seconds,
            prompt_influence=prompt_influence,
            response_format=response_format,
        )
        return ok_json(
            await self._client.post(f"{self._api_url}{_SFX_PATH}", json=body),
            "sound_effects",
            error_cls=AudioGenerationError,
        )

    async def voices(self) -> Dict[str, Any]:
        return ok_json(
            await self._client.get(f"{self._api_url}{_VOICES_PATH}"),
            "voices",
            error_cls=AudioGenerationError,
        )

    async def models(self) -> Dict[str, Any]:
        return ok_json(
            await self._client.get(f"{self._api_url}{_MODELS_PATH}"),
            "models",
            error_cls=AudioGenerationError,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncAudio":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
