"""httpx transports that intercept a 402 from the BlockRun gateway, sign an x402
payment locally (EIP-712), and retry — for both sync and async official SDKs.

These wrap the official anthropic/openai SDK HTTP clients, so the SDK's OWN parsing
sees the gateway's VERBATIM upstream response (genuine thinking signatures,
system_fingerprint, native SSE). We never touch the response body — only inject the
PAYMENT-SIGNATURE header on the paid retry.
"""

from __future__ import annotations

from typing import Optional

import httpx
from eth_account import Account

from ._x402 import (
    create_payment_payload,
    parse_payment_required,
    extract_payment_details,
)


def _payment_header_from_402(account: Account, api_url: str, response: httpx.Response) -> Optional[str]:
    """Build the PAYMENT-SIGNATURE header value from a 402 response, or None."""
    payment_header = response.headers.get("payment-required") or response.headers.get(
        "x-payment-required"
    )
    if not payment_header:
        try:
            body = response.json()
            if isinstance(body, dict) and ("x402" in body or "accepts" in body):
                payment_header = body
        except Exception:
            return None
    if not payment_header:
        return None

    payment_required = (
        parse_payment_required(payment_header)
        if isinstance(payment_header, str)
        else payment_header
    )
    details = extract_payment_details(payment_required)
    resource = details.get("resource") or {}
    return create_payment_payload(
        account=account,
        recipient=details["recipient"],
        amount=details["amount"],
        network=details.get("network", "eip155:8453"),
        resource_url=resource.get("url", f"{api_url}/v1/chat/completions"),
        resource_description=resource.get("description", "BlockRun AI API call"),
        max_timeout_seconds=details.get("maxTimeoutSeconds", 300),
        extra=details.get("extra"),
        extensions=payment_required.get("extensions", {}),
        asset=details.get("asset"),
    )


class BlockRunX402Transport(httpx.BaseTransport):
    """Sync transport: 402 → sign → retry."""

    def __init__(self, account: Account, api_url: str, base_transport: Optional[httpx.BaseTransport] = None):
        self._account = account
        self._api_url = api_url
        self._base = base_transport or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._base.handle_request(request)
        if response.status_code != 402:
            return response
        response.read()
        header = _payment_header_from_402(self._account, self._api_url, response)
        if not header:
            return response
        request.headers["PAYMENT-SIGNATURE"] = header
        return self._base.handle_request(request)

    def close(self) -> None:
        self._base.close()


class AsyncBlockRunX402Transport(httpx.AsyncBaseTransport):
    """Async transport: 402 → sign → retry."""

    def __init__(self, account: Account, api_url: str, base_transport: Optional[httpx.AsyncBaseTransport] = None):
        self._account = account
        self._api_url = api_url
        self._base = base_transport or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._base.handle_async_request(request)
        if response.status_code != 402:
            return response
        await response.aread()
        header = _payment_header_from_402(self._account, self._api_url, response)
        if not header:
            return response
        request.headers["PAYMENT-SIGNATURE"] = header
        return await self._base.handle_async_request(request)

    async def aclose(self) -> None:
        await self._base.aclose()
