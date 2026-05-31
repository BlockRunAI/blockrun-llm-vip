"""Seedance (and other) video generation for the BlockRun gateway — incl. real-person
(RealFace) video.

The gateway's video endpoint is async two-step: POST submits a job (verify-only, no
charge) and returns a `poll_url`; you then GET the poll_url until it reports `completed`
(the moment you're charged) or `failed` (never charged). Both legs are x402-paid by the
SAME wallet — handled transparently by `BlockRunX402Transport` (402 → sign → retry).

`Video.generate()` runs that whole submit+poll loop for you and returns the gateway's
VERBATIM completed-job JSON (`data[].url` is the permanent BlockRun-hosted MP4, plus the
native `payment` / settlement block) — no reshaping, consistent with the rest of this SDK.

    from blockrun_llm_vip import Video

    video = Video()  # wallet auto-loaded from ~/.blockrun/.session

    # Real-person video: enroll a RealFace once (see blockrun_llm_vip.RealFace),
    # then pass its ta_xxxx as real_face_asset_id on Seedance 2.0 / 2.0-fast.
    job = video.generate(
        "she smiles warmly and waves at the camera in soft studio light",
        model="bytedance/seedance-2.0",
        real_face_asset_id="ta_f85b20b9394e47be9502d819bee7929c",
        duration_seconds=5,
        aspect_ratio="9:16",
    )
    print(job["data"][0]["url"])               # permanent MP4 URL
    print(job["payment"]["tx_hash"])           # on-chain USDC settlement

Async: `from blockrun_llm_vip import AsyncVideo`.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from ._common import resolve_account_and_url
from ._transport import AsyncBlockRunX402Transport, BlockRunX402Transport

# Seedance is the only family that accepts a real_face_asset_id (RealFace / Virtual
# Portrait) — and only the 2.0 generation does. Keep this in sync with the gateway docs.
REALFACE_CAPABLE_MODELS = frozenset(
    {"bytedance/seedance-2.0", "bytedance/seedance-2.0-fast"}
)

# Default to the RealFace-capable, faster Seedance so the real-person path is the easy
# path. Override per-call with model=...
DEFAULT_VIDEO_MODEL = "bytedance/seedance-2.0-fast"

# Optional Seedance/video tuning params, mapped from snake_case kwargs to the gateway's
# JSON body. None values are omitted so the gateway applies its own defaults.
_OPTIONAL_BODY_FIELDS = (
    "image_url",
    "real_face_asset_id",
    "duration_seconds",
    "resolution",
    "aspect_ratio",
    "generate_audio",
    "seed",
    "watermark",
    "return_last_frame",
)

_GENERATIONS_PATH = "/v1/videos/generations"


class VideoGenerationError(RuntimeError):
    """Raised when the gateway reports a `failed` job (no charge was taken)."""


class VideoGenerationTimeout(TimeoutError):
    """Raised when a job does not reach `completed`/`failed` within the poll budget."""


def build_video_body(prompt: str, model: str, **opts: Any) -> Dict[str, Any]:
    """Build the POST body, validating model/param compatibility client-side.

    Pure function (no I/O) so it's unit-testable. Mirrors the gateway's request schema.
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required and must be a non-empty string")

    image_url = opts.get("image_url")
    real_face_asset_id = opts.get("real_face_asset_id")
    if image_url is not None and real_face_asset_id is not None:
        raise ValueError(
            "image_url and real_face_asset_id are mutually exclusive — pass only one"
        )
    if real_face_asset_id is not None and model not in REALFACE_CAPABLE_MODELS:
        raise ValueError(
            f"real_face_asset_id (real-person / RealFace) is only supported on "
            f"{sorted(REALFACE_CAPABLE_MODELS)}, not {model!r}"
        )

    body: Dict[str, Any] = {"model": model, "prompt": prompt}
    for field in _OPTIONAL_BODY_FIELDS:
        value = opts.get(field)
        if value is not None:
            body[field] = value
    return body


def resolve_poll_url(api_url: str, poll_url: str) -> str:
    """Turn the gateway's (usually root-relative) `poll_url` into an absolute URL.

    The 202 body returns e.g. `/api/v1/videos/generations/<id>?model=…&duration=…`,
    which is relative to the gateway ORIGIN (scheme://host), not to the `…/api` root.
    Already-absolute poll URLs are passed through unchanged.
    """
    if not poll_url:
        raise VideoGenerationError("Gateway did not return a poll_url for the job")
    if poll_url.startswith(("http://", "https://")):
        return poll_url
    parsed = urlparse(api_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if not poll_url.startswith("/"):
        poll_url = "/" + poll_url
    return origin + poll_url


def _generations_url(api_url: str) -> str:
    return f"{api_url}{_GENERATIONS_PATH}"


def _interpret_poll(response: httpx.Response) -> Optional[Dict[str, Any]]:
    """Inspect a poll response. Return the completed-job dict, raise on failure, or
    return None to keep polling."""
    if response.status_code == 202:
        return None  # queued / in_progress
    if response.status_code == 200:
        body = response.json()
        status = body.get("status")
        if status == "failed":
            raise VideoGenerationError(
                body.get("error") or body.get("note") or "Video generation failed"
            )
        if status in (None, "completed") or body.get("data"):
            return body
        return None  # 200 but still running (defensive)
    # Anything else is a hard error — surface the gateway's message.
    raise VideoGenerationError(
        f"Unexpected poll status {response.status_code}: {response.text[:500]}"
    )


def _interpret_submit(response: httpx.Response) -> Dict[str, Any]:
    """Parse the POST response into a job dict ({id, poll_url, ...} or a completed job)."""
    if response.status_code not in (200, 202):
        raise VideoGenerationError(
            f"Video submit failed ({response.status_code}): {response.text[:500]}"
        )
    return response.json()


class Video:
    """Submit + poll Seedance/video generations through BlockRun, paid via x402.

    Real-person video: pass `real_face_asset_id` (a `ta_xxxx` from RealFace enrollment)
    on a Seedance 2.0 / 2.0-fast model. Enroll via `blockrun_llm_vip.RealFace`.
    """

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        request_timeout: float = 120.0,
    ):
        self._account, self._api_url = resolve_account_and_url(private_key, api_url)
        self._client = httpx.Client(
            transport=BlockRunX402Transport(self._account, self._api_url),
            timeout=request_timeout,
        )

    def generate(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_VIDEO_MODEL,
        timeout: float = 300.0,
        poll_interval: float = 6.0,
        **opts: Any,
    ) -> Dict[str, Any]:
        """Generate a video and block until it's done. Returns the gateway's verbatim
        completed-job JSON (`data[].url`, `payment`, …).

        opts: image_url, real_face_asset_id, duration_seconds, resolution, aspect_ratio,
        generate_audio, seed, watermark, return_last_frame.
        """
        body = build_video_body(prompt, model, **opts)
        submit = _interpret_submit(
            self._client.post(_generations_url(self._api_url), json=body)
        )
        if submit.get("status") == "completed" or submit.get("data"):
            return submit

        poll_url = resolve_poll_url(self._api_url, submit.get("poll_url", ""))
        deadline = time.monotonic() + timeout
        while True:
            done = _interpret_poll(self._client.get(poll_url))
            if done is not None:
                return done
            if time.monotonic() >= deadline:
                raise VideoGenerationTimeout(
                    f"Video job {submit.get('id')} did not complete within {timeout}s"
                )
            time.sleep(poll_interval)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Video":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncVideo:
    """Async counterpart of :class:`Video`."""

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        request_timeout: float = 120.0,
    ):
        self._account, self._api_url = resolve_account_and_url(private_key, api_url)
        self._client = httpx.AsyncClient(
            transport=AsyncBlockRunX402Transport(self._account, self._api_url),
            timeout=request_timeout,
        )

    async def generate(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_VIDEO_MODEL,
        timeout: float = 300.0,
        poll_interval: float = 6.0,
        **opts: Any,
    ) -> Dict[str, Any]:
        body = build_video_body(prompt, model, **opts)
        submit = _interpret_submit(
            await self._client.post(_generations_url(self._api_url), json=body)
        )
        if submit.get("status") == "completed" or submit.get("data"):
            return submit

        poll_url = resolve_poll_url(self._api_url, submit.get("poll_url", ""))
        deadline = time.monotonic() + timeout
        while True:
            done = _interpret_poll(await self._client.get(poll_url))
            if done is not None:
                return done
            if time.monotonic() >= deadline:
                raise VideoGenerationTimeout(
                    f"Video job {submit.get('id')} did not complete within {timeout}s"
                )
            await asyncio.sleep(poll_interval)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncVideo":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
