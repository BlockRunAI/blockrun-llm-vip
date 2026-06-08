"""Outbound AI voice calls (Bland.ai) through the BlockRun gateway, paid via x402.

``Voice.call()`` places an AI-driven phone call: a POST submits it (flat $0.54, charged
on accept) and returns a ``call_id`` + ``poll_url``; the call then runs until the human
hangs up or ``max_duration`` is hit. By default ``call()`` blocks, polling the free
status endpoint until the call completes, and returns the gateway's VERBATIM final job
(``transcript``, ``recording_url``, ``ended_by``…). Pass ``wait=False`` to get the
submit response immediately and poll yourself with ``Voice.poll(call_id)``.

You must own an active BlockRun phone number to place a call (buy one via
``blockrun_llm_vip.Phone``). If your wallet owns exactly one, ``from_`` is auto-picked.

    from blockrun_llm_vip import Voice

    v = Voice()  # wallet auto-loaded from ~/.blockrun/.session
    result = v.call(
        to="+14155551234",
        task="Ask if they're open Sunday, confirm hours, then thank them and end.",
        max_duration=3,
    )
    print(result["ended_by"], result["transcript"])

Async: `from blockrun_llm_vip import AsyncVoice`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

import httpx

from ._common import resolve_chain
from ._polling import poll_until, poll_until_async

_CALL_PATH = "/v1/voice/call"

# Optional call params mapped straight to the gateway body (snake_case kept as-is).
_OPTIONAL_CALL_FIELDS = (
    "voice",
    "max_duration",
    "language",
    "first_sentence",
    "wait_for_greeting",
    "interruption_threshold",
    "model",
    "voicemail_action",
    "voicemail_message",
)


class VoiceError(RuntimeError):
    """Raised when the gateway rejects a call or the call ends in a provider error."""


class VoiceCallTimeout(TimeoutError):
    """Raised when a call does not complete within the poll budget."""


def build_call_body(
    to: str,
    task: str,
    *,
    from_: Optional[str] = None,
    **opts: Any,
) -> Dict[str, Any]:
    """Build the POST body for /v1/voice/call. ``from_`` maps to the gateway's reserved
    ``from`` field. Pure (no I/O), unit-testable."""
    if not isinstance(to, str) or not to.strip():
        raise ValueError("to is required (E.164 phone number, e.g. +14155551234)")
    if not isinstance(task, str) or len(task.strip()) < 10:
        raise ValueError("task is required and must be at least 10 characters")
    if opts.get("voicemail_action") == "leave_message" and not opts.get("voicemail_message"):
        raise ValueError(
            "voicemail_message is required when voicemail_action='leave_message'"
        )
    body: Dict[str, Any] = {"to": to, "task": task}
    if from_ is not None:
        body["from"] = from_
    for field in _OPTIONAL_CALL_FIELDS:
        value = opts.get(field)
        if value is not None:
            body[field] = value
    return body


def _interpret_call_poll(response: httpx.Response) -> Optional[Dict[str, Any]]:
    """Inspect a status poll. Return the completed call, raise on a provider error, or
    return None to keep polling."""
    if response.status_code == 404:
        raise VoiceError("Call not found (it may have expired)")
    if response.status_code // 100 != 2:
        raise VoiceError(
            f"Unexpected poll status {response.status_code}: {response.text[:500]}"
        )
    body = response.json()
    if body.get("completed") is True:
        return body
    if body.get("status") == "error":
        raise VoiceError(body.get("error_message") or "Voice call failed")
    return None


def _submit_call_id(submit: Dict[str, Any]) -> Optional[str]:
    return submit.get("call_id")


def _default_timeout(max_duration: Optional[int]) -> float:
    # Poll a little past the call's hard cap (minutes → seconds, + buffer).
    return float((max_duration or 5) * 60 + 120)


class _VoiceBase:
    def _poll_url(self, job: Union[Dict[str, Any], str]) -> str:
        if isinstance(job, str):
            return f"{self._api_url}{_CALL_PATH}/{job}"
        poll_url = job.get("poll_url")
        if poll_url:
            if poll_url.startswith(("http://", "https://")):
                return poll_url
            return f"{self._api_url}{_CALL_PATH}/{job.get('call_id', '')}"
        call_id = job.get("call_id")
        if not call_id:
            raise VoiceError("job has neither poll_url nor call_id to poll")
        return f"{self._api_url}{_CALL_PATH}/{call_id}"


class Voice(_VoiceBase):
    """Outbound AI voice calls through BlockRun, paid via x402.

    ``chain="solana"`` pays USDC on Solana via sol.blockrun.ai instead of Base.
    """

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        chain: str = "base",
        rpc_url: Optional[str] = None,
        request_timeout: float = 60.0,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        self._api_url = ctx.api_url
        self._client = httpx.Client(
            transport=ctx.make_transport(async_=False),
            timeout=request_timeout,
        )

    def call(
        self,
        *,
        to: str,
        task: str,
        from_: Optional[str] = None,
        wait: bool = True,
        timeout: Optional[float] = None,
        poll_interval: float = 10.0,
        **opts: Any,
    ) -> Dict[str, Any]:
        """Place an outbound call. Blocks until it completes and returns the verbatim
        final call (transcript, recording_url, ended_by). ``wait=False`` returns the
        submit response (``call_id`` + ``poll_url``) for you to :meth:`poll`.

        opts: voice, max_duration, language, first_sentence, wait_for_greeting,
        interruption_threshold, model, voicemail_action, voicemail_message.
        """
        body = build_call_body(to, task, from_=from_, **opts)
        r = self._client.post(f"{self._api_url}{_CALL_PATH}", json=body)
        if r.status_code // 100 != 2:
            raise VoiceError(f"Call submit failed ({r.status_code}): {r.text[:500]}")
        submit = r.json()
        if not wait:
            return submit
        if timeout is None:
            timeout = _default_timeout(opts.get("max_duration"))
        return self.poll(submit, timeout=timeout, poll_interval=poll_interval)

    def poll(
        self,
        job: Union[Dict[str, Any], str],
        *,
        timeout: float = 420.0,
        poll_interval: float = 10.0,
    ) -> Dict[str, Any]:
        """Block on a call (submit dict or call_id) until it completes."""
        poll_url = self._poll_url(job)
        call_id = job if isinstance(job, str) else _submit_call_id(job)
        return poll_until(
            lambda: self._client.get(poll_url),
            _interpret_call_poll,
            timeout=timeout,
            interval=poll_interval,
            on_timeout=lambda: VoiceCallTimeout(
                f"Voice call {call_id} did not complete within {timeout}s"
            ),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Voice":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncVoice(_VoiceBase):
    """Async counterpart of :class:`Voice`."""

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        chain: str = "base",
        rpc_url: Optional[str] = None,
        request_timeout: float = 60.0,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        self._api_url = ctx.api_url
        self._client = httpx.AsyncClient(
            transport=ctx.make_transport(async_=True),
            timeout=request_timeout,
        )

    async def call(
        self,
        *,
        to: str,
        task: str,
        from_: Optional[str] = None,
        wait: bool = True,
        timeout: Optional[float] = None,
        poll_interval: float = 10.0,
        **opts: Any,
    ) -> Dict[str, Any]:
        body = build_call_body(to, task, from_=from_, **opts)
        r = await self._client.post(f"{self._api_url}{_CALL_PATH}", json=body)
        if r.status_code // 100 != 2:
            raise VoiceError(f"Call submit failed ({r.status_code}): {r.text[:500]}")
        submit = r.json()
        if not wait:
            return submit
        if timeout is None:
            timeout = _default_timeout(opts.get("max_duration"))
        return await self.poll(submit, timeout=timeout, poll_interval=poll_interval)

    async def poll(
        self,
        job: Union[Dict[str, Any], str],
        *,
        timeout: float = 420.0,
        poll_interval: float = 10.0,
    ) -> Dict[str, Any]:
        poll_url = self._poll_url(job)
        call_id = job if isinstance(job, str) else _submit_call_id(job)
        return await poll_until_async(
            lambda: self._client.get(poll_url),
            _interpret_call_poll,
            timeout=timeout,
            interval=poll_interval,
            on_timeout=lambda: VoiceCallTimeout(
                f"Voice call {call_id} did not complete within {timeout}s"
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncVoice":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
