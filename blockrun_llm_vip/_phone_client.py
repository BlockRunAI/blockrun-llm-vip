"""Phone number provisioning + carrier lookup (Twilio) through the BlockRun gateway,
paid via x402.

Buy a dedicated number (30-day lease, $5) to use as caller ID for
``blockrun_llm_vip.Voice`` calls, renew or release it, and run carrier / fraud lookups.
Numbers are bound to your wallet. Every method returns the gateway's VERBATIM JSON; the
SAME wallet pays via the chain transport (402 → sign → retry).

    from blockrun_llm_vip import Phone

    p = Phone()  # wallet auto-loaded from ~/.blockrun/.session
    bought = p.buy_number(country="US", area_code="415")   # $5, 30-day lease
    print(bought["phone_number"], bought["expires_at"])
    p.list_numbers()                                       # your active numbers
    p.lookup("+14155551234")                               # carrier + line type

Async: `from blockrun_llm_vip import AsyncPhone`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ._common import resolve_chain
from ._http import ok_json

_PHONE_BASE = "/v1/phone"


class PhoneError(RuntimeError):
    """Raised when the gateway rejects a phone request."""


class Phone:
    """Twilio phone numbers + lookup through BlockRun, paid via x402.

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

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return ok_json(
            self._client.post(f"{self._api_url}{_PHONE_BASE}/{path}", json=body),
            f"phone/{path}",
            error_cls=PhoneError,
        )

    def lookup(self, phone_number: str) -> Dict[str, Any]:
        """PAID ($0.01): carrier name + line type for a number."""
        return self._post("lookup", {"phoneNumber": phone_number})

    def lookup_fraud(self, phone_number: str) -> Dict[str, Any]:
        """PAID ($0.05): carrier + fraud signals (SIM swap, call forwarding)."""
        return self._post("lookup/fraud", {"phoneNumber": phone_number})

    def buy_number(
        self, *, country: str = "US", area_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """PAID ($5): lease a dedicated number for 30 days, bound to your wallet."""
        body: Dict[str, Any] = {"country": country}
        if area_code is not None:
            body["areaCode"] = area_code
        return self._post("numbers/buy", body)

    def renew_number(self, phone_number: str) -> Dict[str, Any]:
        """PAID ($5): extend a number's lease by 30 days."""
        return self._post("numbers/renew", {"phoneNumber": phone_number})

    def list_numbers(self) -> Dict[str, Any]:
        """PAID ($0.001): list the active numbers your wallet owns."""
        return self._post("numbers/list", {})

    def release_number(self, phone_number: str) -> Dict[str, Any]:
        """FREE: release a number you own."""
        return self._post("numbers/release", {"phoneNumber": phone_number})

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Phone":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncPhone:
    """Async counterpart of :class:`Phone`."""

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

    async def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return ok_json(
            await self._client.post(f"{self._api_url}{_PHONE_BASE}/{path}", json=body),
            f"phone/{path}",
            error_cls=PhoneError,
        )

    async def lookup(self, phone_number: str) -> Dict[str, Any]:
        return await self._post("lookup", {"phoneNumber": phone_number})

    async def lookup_fraud(self, phone_number: str) -> Dict[str, Any]:
        return await self._post("lookup/fraud", {"phoneNumber": phone_number})

    async def buy_number(
        self, *, country: str = "US", area_code: Optional[str] = None
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"country": country}
        if area_code is not None:
            body["areaCode"] = area_code
        return await self._post("numbers/buy", body)

    async def renew_number(self, phone_number: str) -> Dict[str, Any]:
        return await self._post("numbers/renew", {"phoneNumber": phone_number})

    async def list_numbers(self) -> Dict[str, Any]:
        return await self._post("numbers/list", {})

    async def release_number(self, phone_number: str) -> Dict[str, Any]:
        return await self._post("numbers/release", {"phoneNumber": phone_number})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncPhone":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
