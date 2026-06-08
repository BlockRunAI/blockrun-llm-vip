"""Image generation + editing through the BlockRun gateway, paid via x402.

The gateway's image endpoint is *hybrid*: a POST that finishes within ~30s returns the
images inline (HTTP 200, ``data[].url``); a slower model returns HTTP 202 with a
``poll_url`` you GET until ``status == "completed"``. Either way you're charged only on
completion, and the SAME wallet pays both legs (the chain transport signs the 402
challenge transparently).

``Image.generate()`` / ``Image.edit()`` hide that: by default they block and return the
gateway's VERBATIM completed-job JSON (``data[].url`` is a permanent BlockRun-hosted
image). Pass ``wait=False`` to get the raw submit response (``id`` + ``poll_url``) and
drive the poll yourself with ``Image.poll(job)``.

    from blockrun_llm_vip import Image

    img = Image()  # wallet auto-loaded from ~/.blockrun/.session
    out = img.generate("a red fox in snow, studio light", model="openai/gpt-image-1")
    print(out["data"][0]["url"])               # permanent image URL

    # edit / fuse: pass a base64 data URI (or a list of up to 4)
    edited = img.edit("make it night", image="data:image/png;base64,iVBOR…")

Async: `from blockrun_llm_vip import AsyncImage`.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Sequence, Union

import httpx

from ._common import resolve_chain
from ._polling import poll_until, poll_until_async
from ._polling import resolve_poll_url as _resolve_poll_url

# Generations require an explicit model server-side; default to the cheap, fast flagship
# so the easy path just works. Override per-call with model=...
DEFAULT_IMAGE_MODEL = "openai/gpt-image-1"
# Editing (image2image) defaults to the edit-capable flagship.
DEFAULT_EDIT_MODEL = "openai/gpt-image-2"

_GENERATIONS_PATH = "/v1/images/generations"
_EDIT_PATH = "/v1/images/image2image"
_MODELS_PATH = "/v1/images/models"

ImageInput = Union[str, Sequence[str]]


class ImageGenerationError(RuntimeError):
    """Raised when the gateway reports a `failed` image job (no charge was taken)."""


class ImageGenerationTimeout(TimeoutError):
    """Raised when an image job does not complete within the poll budget."""


def encode_data_uri(data: bytes, mime: str = "image/png") -> str:
    """Helper: turn raw image bytes into a ``data:`` URI accepted by :meth:`Image.edit`."""
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def build_image_body(
    prompt: str,
    model: str,
    *,
    size: Optional[str] = None,
    n: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the POST body for /v1/images/generations. Pure (no I/O), unit-testable."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required and must be a non-empty string")
    body: Dict[str, Any] = {"model": model, "prompt": prompt}
    if size is not None:
        body["size"] = size
    if n is not None:
        body["n"] = n
    return body


def build_edit_body(
    prompt: str,
    image: ImageInput,
    *,
    model: str,
    mask: Optional[str] = None,
    size: Optional[str] = None,
    n: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the POST body for /v1/images/image2image. ``image`` is a base64 data URI
    or a list of 1-4 of them (multi-image fusion). ``mask`` (inpainting) is OpenAI-only
    and can't be combined with multiple source images."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required and must be a non-empty string")
    images: List[str] = [image] if isinstance(image, str) else list(image)
    if not images:
        raise ValueError("image is required (a base64 data URI or a list of them)")
    if mask is not None and len(images) > 1:
        raise ValueError("mask cannot be combined with multiple source images")
    body: Dict[str, Any] = {"model": model, "prompt": prompt}
    body["image"] = images[0] if len(images) == 1 else images
    if mask is not None:
        body["mask"] = mask
    if size is not None:
        body["size"] = size
    if n is not None:
        body["n"] = n
    return body


def _interpret_submit(response: httpx.Response) -> Dict[str, Any]:
    """Parse a POST response: 200 = inline-complete (has ``data``), 202 = async job
    (``id`` + ``poll_url``)."""
    if response.status_code not in (200, 202):
        raise ImageGenerationError(
            f"Image submit failed ({response.status_code}): {response.text[:500]}"
        )
    return response.json()


def _interpret_poll(response: httpx.Response) -> Optional[Dict[str, Any]]:
    """Inspect a poll response. Return the completed job, raise on failure, or return
    None to keep polling."""
    if response.status_code == 202:
        return None  # queued / in_progress
    if response.status_code == 200:
        body = response.json()
        status = body.get("status")
        if status == "failed":
            raise ImageGenerationError(
                body.get("error") or body.get("note") or "Image generation failed"
            )
        if status == "completed" or body.get("data"):
            return body
        return None  # 200 but still running (defensive)
    raise ImageGenerationError(
        f"Unexpected poll status {response.status_code}: {response.text[:500]}"
    )


def _is_inline_done(submit: Dict[str, Any]) -> bool:
    return submit.get("status") == "completed" or bool(submit.get("data"))


def _job_poll_url(api_url: str, submit: Dict[str, Any]) -> str:
    return _resolve_poll_url(
        api_url, submit.get("poll_url", ""), error_cls=ImageGenerationError
    )


class Image:
    """Generate and edit images through BlockRun, paid via x402.

    ``chain="solana"`` pays USDC on Solana via sol.blockrun.ai instead of Base.
    """

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        chain: str = "base",
        rpc_url: Optional[str] = None,
        request_timeout: float = 120.0,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        self._api_url = ctx.api_url
        self._address = ctx.address
        self._client = httpx.Client(
            transport=ctx.make_transport(async_=False),
            timeout=request_timeout,
        )

    def generate(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_IMAGE_MODEL,
        size: Optional[str] = None,
        n: Optional[int] = None,
        wait: bool = True,
        timeout: float = 180.0,
        poll_interval: float = 3.0,
    ) -> Dict[str, Any]:
        """Generate image(s). Blocks until done and returns the verbatim completed job
        (``data[].url``, ``payment``). Pass ``wait=False`` to get the raw submit
        response and poll yourself via :meth:`poll`."""
        body = build_image_body(prompt, model, size=size, n=n)
        submit = _interpret_submit(self._client.post(self._url(_GENERATIONS_PATH), json=body))
        return self._maybe_wait(submit, wait, timeout, poll_interval)

    def edit(
        self,
        prompt: str,
        image: ImageInput,
        *,
        model: str = DEFAULT_EDIT_MODEL,
        mask: Optional[str] = None,
        size: Optional[str] = None,
        n: Optional[int] = None,
        wait: bool = True,
        timeout: float = 180.0,
        poll_interval: float = 3.0,
    ) -> Dict[str, Any]:
        """Edit / fuse image(s) from a prompt + base64 data URI(s). Same block/poll
        semantics as :meth:`generate`."""
        body = build_edit_body(prompt, image, model=model, mask=mask, size=size, n=n)
        submit = _interpret_submit(self._client.post(self._url(_EDIT_PATH), json=body))
        return self._maybe_wait(submit, wait, timeout, poll_interval)

    def poll(
        self,
        job: Dict[str, Any],
        *,
        timeout: float = 180.0,
        poll_interval: float = 3.0,
    ) -> Dict[str, Any]:
        """Block on a ``wait=False`` job (the submit dict) until it completes."""
        if _is_inline_done(job):
            return job
        poll_url = _job_poll_url(self._api_url, job)
        return poll_until(
            lambda: self._client.get(poll_url),
            _interpret_poll,
            timeout=timeout,
            interval=poll_interval,
            on_timeout=lambda: ImageGenerationTimeout(
                f"Image job {job.get('id')} did not complete within {timeout}s"
            ),
        )

    def models(self) -> Dict[str, Any]:
        """FREE: list available image models + per-size pricing."""
        r = self._client.get(self._url(_MODELS_PATH))
        if r.status_code // 100 != 2:
            raise ImageGenerationError(
                f"Image models list failed ({r.status_code}): {r.text[:500]}"
            )
        return r.json()

    def _maybe_wait(
        self, submit: Dict[str, Any], wait: bool, timeout: float, poll_interval: float
    ) -> Dict[str, Any]:
        if _is_inline_done(submit) or not wait:
            return submit
        return self.poll(submit, timeout=timeout, poll_interval=poll_interval)

    def _url(self, path: str) -> str:
        return f"{self._api_url}{path}"

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Image":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncImage:
    """Async counterpart of :class:`Image`."""

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        chain: str = "base",
        rpc_url: Optional[str] = None,
        request_timeout: float = 120.0,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        self._api_url = ctx.api_url
        self._address = ctx.address
        self._client = httpx.AsyncClient(
            transport=ctx.make_transport(async_=True),
            timeout=request_timeout,
        )

    async def generate(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_IMAGE_MODEL,
        size: Optional[str] = None,
        n: Optional[int] = None,
        wait: bool = True,
        timeout: float = 180.0,
        poll_interval: float = 3.0,
    ) -> Dict[str, Any]:
        body = build_image_body(prompt, model, size=size, n=n)
        submit = _interpret_submit(
            await self._client.post(self._url(_GENERATIONS_PATH), json=body)
        )
        return await self._maybe_wait(submit, wait, timeout, poll_interval)

    async def edit(
        self,
        prompt: str,
        image: ImageInput,
        *,
        model: str = DEFAULT_EDIT_MODEL,
        mask: Optional[str] = None,
        size: Optional[str] = None,
        n: Optional[int] = None,
        wait: bool = True,
        timeout: float = 180.0,
        poll_interval: float = 3.0,
    ) -> Dict[str, Any]:
        body = build_edit_body(prompt, image, model=model, mask=mask, size=size, n=n)
        submit = _interpret_submit(
            await self._client.post(self._url(_EDIT_PATH), json=body)
        )
        return await self._maybe_wait(submit, wait, timeout, poll_interval)

    async def poll(
        self,
        job: Dict[str, Any],
        *,
        timeout: float = 180.0,
        poll_interval: float = 3.0,
    ) -> Dict[str, Any]:
        if _is_inline_done(job):
            return job
        poll_url = _job_poll_url(self._api_url, job)
        return await poll_until_async(
            lambda: self._client.get(poll_url),
            _interpret_poll,
            timeout=timeout,
            interval=poll_interval,
            on_timeout=lambda: ImageGenerationTimeout(
                f"Image job {job.get('id')} did not complete within {timeout}s"
            ),
        )

    async def models(self) -> Dict[str, Any]:
        r = await self._client.get(self._url(_MODELS_PATH))
        if r.status_code // 100 != 2:
            raise ImageGenerationError(
                f"Image models list failed ({r.status_code}): {r.text[:500]}"
            )
        return r.json()

    async def _maybe_wait(
        self, submit: Dict[str, Any], wait: bool, timeout: float, poll_interval: float
    ) -> Dict[str, Any]:
        if _is_inline_done(submit) or not wait:
            return submit
        return await self.poll(submit, timeout=timeout, poll_interval=poll_interval)

    def _url(self, path: str) -> str:
        return f"{self._api_url}{path}"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncImage":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
