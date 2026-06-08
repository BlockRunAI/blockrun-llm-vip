"""Shared submit→poll→settle plumbing for the gateway's async media jobs (video,
image, music, voice).

The gateway's async endpoints all follow the same rhythm: a POST submits a job
(verify-only, no charge) and returns a ``poll_url``; you then GET that url until the
job reports a terminal state (the moment you're charged) or fails (never charged).
Both legs are x402-paid by the SAME wallet — handled transparently by the chain
transport (402 → sign → retry).

Each family differs only in how it reads a poll response (status codes, the field that
signals "done") and which error type it raises. So the URL resolution and the timed
loop live here; the family supplies an ``interpret`` callback and a timeout factory.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

import httpx

# interpret(response) -> dict   → terminal: return this verbatim job JSON
#                      -> None  → not done yet: keep polling
#                      (it may also raise the family's error on a `failed` job)
Interpret = Callable[[httpx.Response], Optional[Dict[str, Any]]]


def resolve_poll_url(
    api_url: str, poll_url: str, *, error_cls: type = RuntimeError
) -> str:
    """Turn the gateway's (usually root-relative) ``poll_url`` into an absolute URL.

    The submit body returns e.g. ``/api/v1/videos/generations/<id>?model=…`` which is
    relative to the gateway ORIGIN (scheme://host), not to the ``…/api`` base. The
    signed query string MUST be preserved verbatim, so we only prepend the origin.
    Already-absolute poll urls pass through unchanged.
    """
    if not poll_url:
        raise error_cls("Gateway did not return a poll_url for the job")
    if poll_url.startswith(("http://", "https://")):
        return poll_url
    parsed = urlparse(api_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if not poll_url.startswith("/"):
        poll_url = "/" + poll_url
    return origin + poll_url


def poll_until(
    get: Callable[[], httpx.Response],
    interpret: Interpret,
    *,
    timeout: float,
    interval: float,
    on_timeout: Callable[[], BaseException],
) -> Dict[str, Any]:
    """Block calling ``get()`` and ``interpret``-ing the response until it returns a
    terminal job dict, or raise ``on_timeout()`` once the budget is spent."""
    deadline = time.monotonic() + timeout
    while True:
        done = interpret(get())
        if done is not None:
            return done
        if time.monotonic() >= deadline:
            raise on_timeout()
        time.sleep(interval)


async def poll_until_async(
    get: Callable[[], "Any"],
    interpret: Interpret,
    *,
    timeout: float,
    interval: float,
    on_timeout: Callable[[], BaseException],
) -> Dict[str, Any]:
    """Async counterpart of :func:`poll_until` (``get()`` returns an awaitable)."""
    deadline = time.monotonic() + timeout
    while True:
        done = interpret(await get())
        if done is not None:
            return done
        if time.monotonic() >= deadline:
            raise on_timeout()
        await asyncio.sleep(interval)
