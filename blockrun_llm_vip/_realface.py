"""RealFace enrollment for the BlockRun gateway — register a real person's face as a
`ta_xxxx` asset usable as `real_face_asset_id` on Seedance 2.0 / 2.0-fast video.

Three steps (see the gateway's realface docs):

  1. ``init(name)``                      — FREE. Returns ``group_id`` + ``h5_link``.
  2. the rights-holder opens ``h5_link`` on their phone and does a ~1-min liveness
     check (nod + blink). NO KYC, NO login. Poll ``status(group_id)`` until ``active``.
  3. ``enroll(name, image_url, group_id)`` — PAID ($0.01 USDC, x402). Face-matches the
     photo against the live H5 face and returns the ``ta_xxxx`` asset id.

The single x402 transport handles all three: the free init/status calls return 200
directly (no 402, nothing signed), and only ``enroll`` triggers the $0.01 settlement.

    from blockrun_llm_vip import RealFace

    rf = RealFace()
    started = rf.init("Spokesperson — Q3 campaign")
    print("Send to the rights-holder's phone:", started["h5_link"])

    rf.wait_until_active(started["group_id"])        # poll until liveness done
    asset = rf.enroll(
        name="Spokesperson — Q3 campaign",
        image_url="https://example.com/person.jpg",
        group_id=started["group_id"],
    )
    print(asset["asset_id"])   # ta_xxxx — pass as real_face_asset_id on Seedance 2.0

Async: `from blockrun_llm_vip import AsyncRealFace`.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

import httpx

from ._common import resolve_account_and_url
from ._transport import AsyncBlockRunX402Transport, BlockRunX402Transport


class RealFaceError(RuntimeError):
    """Raised on a non-2xx RealFace response (e.g. 425 not-yet-active, 422 no match)."""


class RealFaceTimeout(TimeoutError):
    """Raised when the group does not reach `active` within the wait budget."""


def _init_url(api_url: str) -> str:
    return f"{api_url}/v1/realface/init"


def _status_url(api_url: str, group_id: str) -> str:
    return f"{api_url}/v1/realface/status?groupId={group_id}"


def _enroll_url(api_url: str) -> str:
    return f"{api_url}/v1/realface/enroll"


def _ok(response: httpx.Response, context: str) -> Dict[str, Any]:
    if response.status_code // 100 != 2:
        raise RealFaceError(
            f"RealFace {context} failed ({response.status_code}): {response.text[:500]}"
        )
    return response.json()


def _is_active(status_body: Dict[str, Any]) -> bool:
    return status_body.get("status") == "active" or status_body.get(
        "ready_to_finalize"
    ) is True


class RealFace:
    """Enroll a real person's face (RealFace) for Seedance real-person video."""

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        request_timeout: float = 60.0,
    ):
        self._account, self._api_url = resolve_account_and_url(private_key, api_url)
        self._client = httpx.Client(
            transport=BlockRunX402Transport(self._account, self._api_url),
            timeout=request_timeout,
        )

    def init(self, name: str, *, group_id: Optional[str] = None) -> Dict[str, Any]:
        """Step 1 (FREE): start enrollment. Returns ``group_id`` + ``h5_link`` (the
        link the rights-holder opens on their phone). Pass ``group_id`` to refresh an
        expired (120s) H5 session for an existing group."""
        body: Dict[str, Any] = {"name": name}
        if group_id is not None:
            body["groupId"] = group_id
        return _ok(self._client.post(_init_url(self._api_url), json=body), "init")

    def status(self, group_id: str) -> Dict[str, Any]:
        """Step 3 (FREE): current enrollment status. ``active`` once the rights-holder
        has completed the on-phone liveness check."""
        return _ok(self._client.get(_status_url(self._api_url, group_id)), "status")

    def wait_until_active(
        self, group_id: str, *, timeout: float = 300.0, poll_interval: float = 4.0
    ) -> Dict[str, Any]:
        """Poll ``status`` until the group is ``active`` (the H5 liveness check is done),
        then return the final status body. Raises :class:`RealFaceTimeout` on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            body = self.status(group_id)
            if _is_active(body):
                return body
            if time.monotonic() >= deadline:
                raise RealFaceTimeout(
                    f"RealFace group {group_id} not active within {timeout}s — "
                    "has the rights-holder completed the H5 liveness check?"
                )
            time.sleep(poll_interval)

    def enroll(
        self, *, name: str, image_url: str, group_id: str
    ) -> Dict[str, Any]:
        """Step 4 (PAID, $0.01 USDC): finalize. Face-matches ``image_url`` against the
        live H5 face and returns the ``ta_xxxx`` asset id. The group must be ``active``."""
        body = {"name": name, "image_url": image_url, "group_id": group_id}
        return _ok(self._client.post(_enroll_url(self._api_url), json=body), "enroll")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RealFace":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncRealFace:
    """Async counterpart of :class:`RealFace`."""

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        request_timeout: float = 60.0,
    ):
        self._account, self._api_url = resolve_account_and_url(private_key, api_url)
        self._client = httpx.AsyncClient(
            transport=AsyncBlockRunX402Transport(self._account, self._api_url),
            timeout=request_timeout,
        )

    async def init(
        self, name: str, *, group_id: Optional[str] = None
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"name": name}
        if group_id is not None:
            body["groupId"] = group_id
        return _ok(
            await self._client.post(_init_url(self._api_url), json=body), "init"
        )

    async def status(self, group_id: str) -> Dict[str, Any]:
        return _ok(
            await self._client.get(_status_url(self._api_url, group_id)), "status"
        )

    async def wait_until_active(
        self, group_id: str, *, timeout: float = 300.0, poll_interval: float = 4.0
    ) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            body = await self.status(group_id)
            if _is_active(body):
                return body
            if time.monotonic() >= deadline:
                raise RealFaceTimeout(
                    f"RealFace group {group_id} not active within {timeout}s — "
                    "has the rights-holder completed the H5 liveness check?"
                )
            await asyncio.sleep(poll_interval)

    async def enroll(
        self, *, name: str, image_url: str, group_id: str
    ) -> Dict[str, Any]:
        body = {"name": name, "image_url": image_url, "group_id": group_id}
        return _ok(
            await self._client.post(_enroll_url(self._api_url), json=body), "enroll"
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncRealFace":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
