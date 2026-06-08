"""Grok Live Search through the BlockRun gateway, paid via x402.

A single synchronous POST runs an xAI Grok live search over X (Twitter), the web, and/or
news, and returns a grounded summary plus citations — VERBATIM gateway JSON, no
reshaping. Price scales with ``max_results`` (≈$0.025/source); the SAME wallet pays via
the chain transport (402 → sign → retry).

    from blockrun_llm_vip import Search

    s = Search()  # wallet auto-loaded from ~/.blockrun/.session
    r = s.search("latest on x402 micropayments", sources=["x", "news"], max_results=15)
    print(r["summary"])
    print(r["citations"])

Async: `from blockrun_llm_vip import AsyncSearch`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

import httpx

from ._common import resolve_chain
from ._http import ok_json

_SEARCH_PATH = "/v1/search"
_ALLOWED_SOURCES = frozenset({"x", "web", "news"})


class SearchError(RuntimeError):
    """Raised when the gateway rejects or fails a live-search request."""


def build_search_body(
    query: str,
    *,
    sources: Optional[Sequence[str]] = None,
    max_results: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the POST body for /v1/search. Pure (no I/O), unit-testable."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required and must be a non-empty string")
    if len(query) > 1000:
        raise ValueError("query must be at most 1000 characters")
    body: Dict[str, Any] = {"query": query}
    if sources is not None:
        srcs = list(sources)
        bad = [s for s in srcs if s not in _ALLOWED_SOURCES]
        if bad:
            raise ValueError(
                f"unknown sources {bad}; allowed: {sorted(_ALLOWED_SOURCES)}"
            )
        body["sources"] = srcs
    if max_results is not None:
        if not 1 <= max_results <= 50:
            raise ValueError("max_results must be between 1 and 50")
        body["max_results"] = max_results
    if from_date is not None:
        body["from_date"] = from_date
    if to_date is not None:
        body["to_date"] = to_date
    return body


class Search:
    """xAI Grok Live Search through BlockRun, paid via x402.

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

    def search(
        self,
        query: str,
        *,
        sources: Optional[Sequence[str]] = None,
        max_results: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a live search and return the gateway's verbatim
        ``{query, summary, citations, sources_used, model}``."""
        body = build_search_body(
            query,
            sources=sources,
            max_results=max_results,
            from_date=from_date,
            to_date=to_date,
        )
        return ok_json(
            self._client.post(f"{self._api_url}{_SEARCH_PATH}", json=body),
            "search",
            error_cls=SearchError,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Search":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncSearch:
    """Async counterpart of :class:`Search`."""

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

    async def search(
        self,
        query: str,
        *,
        sources: Optional[Sequence[str]] = None,
        max_results: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        body = build_search_body(
            query,
            sources=sources,
            max_results=max_results,
            from_date=from_date,
            to_date=to_date,
        )
        return ok_json(
            await self._client.post(f"{self._api_url}{_SEARCH_PATH}", json=body),
            "search",
            error_cls=SearchError,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncSearch":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
