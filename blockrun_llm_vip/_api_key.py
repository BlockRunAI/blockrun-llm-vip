"""Account authentication bound to one origin; never signs or retries x402."""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlsplit
import httpx


class AccountAPIError(RuntimeError):
    def __init__(self, response: httpx.Response):
        self.status_code = response.status_code
        self.retry_after = response.headers.get("retry-after")
        self.response = response
        super().__init__(
            f"BlockRun account API error ({self.status_code}): {response.text[:500]}"
        )


def resolve_api_key(
    api_key: Optional[str], private_key: Optional[str]
) -> Optional[str]:
    if api_key is not None and private_key is not None:
        raise ValueError("Pass either api_key or private_key, not both")
    key = (
        api_key
        if api_key is not None
        else (None if private_key is not None else os.getenv("BLOCKRUN_API_KEY"))
    )
    if key is not None and (
        not key.startswith("brk_live_")
        or len(key) <= 9
        or any(c.isspace() for c in key)
    ):
        raise ValueError(
            "Invalid BlockRun API key; create one at https://user.blockrun.ai/dashboard/keys"
        )
    return key


def account_url(api_url: Optional[str]) -> str:
    value = (
        api_url or os.getenv("BLOCKRUN_API_BASE_URL") or "https://api.blockrun.ai"
    ).rstrip("/")
    if value.endswith("/v1"):
        value = value[:-3]
    u = urlsplit(value)
    if (
        (
            u.scheme != "https"
            and not (
                u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1")
            )
        )
        or not u.hostname
        or u.username
        or u.password
        or u.query
        or u.fragment
    ):
        raise ValueError("API URL must be HTTPS (HTTP is allowed only for localhost)")
    return value


class AccountTransport(httpx.BaseTransport):
    def __init__(self, key: str, api_url: str, *, native_sdk: bool = False):
        self._key = key
        self._url = httpx.URL(api_url)
        self._native_sdk = native_sdk
        self._inner = httpx.HTTPTransport()

    def prepare(self, request: httpx.Request) -> None:
        u = request.url
        if (
            (u.scheme, u.host, u.port)
            != (self._url.scheme, self._url.host, self._url.port)
            or u.username
            or u.password
        ):
            raise ValueError(
                "Refusing to send account credentials outside the configured API origin"
            )
        if u.path.startswith("/api/v1/") and self._url.path in ("", "/"):
            request.url = u.copy_with(path=u.path[4:])
        for name in list(request.headers):
            if "payment" in name.lower() or name.lower() in (
                "authorization",
                "x-api-key",
            ):
                del request.headers[name]
        request.headers["authorization"] = "Bearer " + self._key

    def checked(self, response: httpx.Response, content: bytes) -> httpx.Response:
        headers = dict(response.headers)
        headers.pop("content-length", None)
        headers.pop("content-encoding", None)
        response = httpx.Response(
            response.status_code,
            headers=headers,
            content=content.replace(self._key.encode(), b"[REDACTED]"),
            request=response.request,
            extensions=response.extensions,
        )
        if response.status_code >= 400 and not self._native_sdk:
            raise AccountAPIError(response)
        return response

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.prepare(request)
        response = self._inner.handle_request(request)
        response.request = request
        if response.status_code >= 300:
            try:
                return self.checked(response, response.read())
            finally:
                response.close()
        return response

    def close(self) -> None:
        self._inner.close()


class AsyncAccountTransport(httpx.AsyncBaseTransport):
    def __init__(self, key: str, api_url: str, *, native_sdk: bool = False):
        # Reuse credential policy without creating an unused synchronous pool.
        self._policy = object.__new__(AccountTransport)
        self._policy._key = key
        self._policy._url = httpx.URL(api_url)
        self._policy._native_sdk = native_sdk
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._policy.prepare(request)
        response = await self._inner.handle_async_request(request)
        response.request = request
        if response.status_code >= 300:
            try:
                return self._policy.checked(response, await response.aread())
            finally:
                await response.aclose()
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()
