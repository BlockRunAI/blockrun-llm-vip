"""Virtual Portrait enrollment for the BlockRun gateway — register an AI-generated
CHARACTER image (mascot, avatar, virtual spokesperson) as a `ta_xxxx` asset usable as
`real_face_asset_id` on Seedance 2.0 / 2.0-fast.

This is the no-liveness sibling of RealFace: no KYC, no phone step — the asset is
understood to be a synthetic character, so a single $0.01 x402 call enrolls it. For a
REAL person's likeness use ``blockrun_llm_vip.RealFace`` instead (consent liveness).

    from blockrun_llm_vip import VirtualPortrait, Video

    vp = VirtualPortrait()
    asset = vp.enroll(name="Mascot", image_url="https://example.com/character.jpg")
    print(asset["asset_id"])                 # ta_xxxx

    video = Video()
    job = video.generate(
        "the character smiles warmly and waves at the camera",
        model="bytedance/seedance-2.0-fast",
        real_face_asset_id=asset["asset_id"],
    )

Async: `from blockrun_llm_vip import AsyncVirtualPortrait`.
"""

from __future__ import annotations

from typing import Any, Dict

import httpx

from ._common import resolve_chain
from ._realface import RealFaceError  # shared error type for enrollment/list calls


def _enroll_url(api_url: str) -> str:
    return f"{api_url}/v1/portrait/enroll"


def _list_url(api_url: str, address: str) -> str:
    return f"{api_url}/v1/wallet/{address}/portraits"


def _ok(response: httpx.Response, context: str) -> Dict[str, Any]:
    if response.status_code // 100 != 2:
        raise RealFaceError(
            f"VirtualPortrait {context} failed ({response.status_code}): "
            f"{response.text[:500]}"
        )
    return response.json()


class VirtualPortrait:
    """Enroll an AI character as a Virtual Portrait (`ta_xxxx`) for Seedance video."""

    def __init__(
        self,
        *,
        private_key: "str | None" = None,
        api_url: "str | None" = None,
        chain: str = "base",
        rpc_url: "str | None" = None,
        request_timeout: float = 60.0,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        self._api_url = ctx.api_url
        self._address = ctx.address
        self._client = httpx.Client(
            transport=ctx.make_transport(async_=False),
            timeout=request_timeout,
        )

    def enroll(self, *, name: str, image_url: str) -> Dict[str, Any]:
        """PAID ($0.01 USDC): register ``image_url`` as a Virtual Portrait and return
        the ``ta_xxxx`` asset id (in ``asset_id``)."""
        body = {"name": name, "image_url": image_url}
        return _ok(self._client.post(_enroll_url(self._api_url), json=body), "enroll")

    def list(self) -> Dict[str, Any]:
        """FREE: list the Virtual Portraits this wallet has enrolled."""
        return _ok(
            self._client.get(_list_url(self._api_url, self._address)), "list"
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "VirtualPortrait":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncVirtualPortrait:
    """Async counterpart of :class:`VirtualPortrait`."""

    def __init__(
        self,
        *,
        private_key: "str | None" = None,
        api_url: "str | None" = None,
        chain: str = "base",
        rpc_url: "str | None" = None,
        request_timeout: float = 60.0,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        self._api_url = ctx.api_url
        self._address = ctx.address
        self._client = httpx.AsyncClient(
            transport=ctx.make_transport(async_=True),
            timeout=request_timeout,
        )

    async def enroll(self, *, name: str, image_url: str) -> Dict[str, Any]:
        body = {"name": name, "image_url": image_url}
        return _ok(
            await self._client.post(_enroll_url(self._api_url), json=body), "enroll"
        )

    async def list(self) -> Dict[str, Any]:
        return _ok(
            await self._client.get(_list_url(self._api_url, self._address)),
            "list",
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncVirtualPortrait":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
