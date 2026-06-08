"""Exa web search through the BlockRun gateway, paid via x402.

Thin x402-paid proxy over Exa's neural search API — four synchronous endpoints, each
returning Exa's response VERBATIM:

- ``search(query)``        — neural/keyword web search        ($0.01)
- ``find_similar(url)``    — pages similar to a reference URL ($0.01)
- ``contents(urls)``       — full text extraction             ($0.002 / URL)
- ``answer(query)``        — grounded answer + sources         ($0.01)

The SAME wallet pays via the chain transport (402 → sign → retry).

    from blockrun_llm_vip import Exa

    exa = Exa()  # wallet auto-loaded from ~/.blockrun/.session
    hits = exa.search("x402 micropayment protocol", num_results=5, category="github")
    text = exa.contents([h["url"] for h in hits["results"]])

Async: `from blockrun_llm_vip import AsyncExa`.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

import httpx

from ._common import resolve_chain
from ._http import ok_json

_EXA_BASE = "/v1/exa"


class ExaError(RuntimeError):
    """Raised when the gateway or Exa rejects a request (payment is not taken on a
    4xx/5xx from Exa)."""


def build_exa_search_body(
    query: str,
    *,
    num_results: Optional[int] = None,
    category: Optional[str] = None,
    include_domains: Optional[Sequence[str]] = None,
    exclude_domains: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required and must be a non-empty string")
    body: Dict[str, Any] = {"query": query}
    if num_results is not None:
        body["numResults"] = num_results
    if category is not None:
        body["category"] = category
    if include_domains is not None:
        body["includeDomains"] = list(include_domains)
    if exclude_domains is not None:
        body["excludeDomains"] = list(exclude_domains)
    return body


def build_exa_find_similar_body(
    url: str, *, num_results: Optional[int] = None
) -> Dict[str, Any]:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url is required and must be a non-empty string")
    body: Dict[str, Any] = {"url": url}
    if num_results is not None:
        body["numResults"] = num_results
    return body


def build_exa_contents_body(urls: Sequence[str]) -> Dict[str, Any]:
    items = list(urls)
    if not items:
        raise ValueError("urls is required (1-100 URLs)")
    if len(items) > 100:
        raise ValueError("urls must contain at most 100 URLs")
    return {"urls": items}


def build_exa_answer_body(query: str) -> Dict[str, Any]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required and must be a non-empty string")
    return {"query": query}


class Exa:
    """Exa web search through BlockRun, paid via x402.

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

    def _post(self, endpoint: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return ok_json(
            self._client.post(f"{self._api_url}{_EXA_BASE}/{endpoint}", json=body),
            f"exa/{endpoint}",
            error_cls=ExaError,
        )

    def search(
        self,
        query: str,
        *,
        num_results: Optional[int] = None,
        category: Optional[str] = None,
        include_domains: Optional[Sequence[str]] = None,
        exclude_domains: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        return self._post(
            "search",
            build_exa_search_body(
                query,
                num_results=num_results,
                category=category,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            ),
        )

    def find_similar(self, url: str, *, num_results: Optional[int] = None) -> Dict[str, Any]:
        return self._post("find-similar", build_exa_find_similar_body(url, num_results=num_results))

    def contents(self, urls: Sequence[str]) -> Dict[str, Any]:
        return self._post("contents", build_exa_contents_body(urls))

    def answer(self, query: str) -> Dict[str, Any]:
        return self._post("answer", build_exa_answer_body(query))

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Exa":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncExa:
    """Async counterpart of :class:`Exa`."""

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

    async def _post(self, endpoint: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return ok_json(
            await self._client.post(f"{self._api_url}{_EXA_BASE}/{endpoint}", json=body),
            f"exa/{endpoint}",
            error_cls=ExaError,
        )

    async def search(
        self,
        query: str,
        *,
        num_results: Optional[int] = None,
        category: Optional[str] = None,
        include_domains: Optional[Sequence[str]] = None,
        exclude_domains: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        return await self._post(
            "search",
            build_exa_search_body(
                query,
                num_results=num_results,
                category=category,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            ),
        )

    async def find_similar(
        self, url: str, *, num_results: Optional[int] = None
    ) -> Dict[str, Any]:
        return await self._post(
            "find-similar", build_exa_find_similar_body(url, num_results=num_results)
        )

    async def contents(self, urls: Sequence[str]) -> Dict[str, Any]:
        return await self._post("contents", build_exa_contents_body(urls))

    async def answer(self, query: str) -> Dict[str, Any]:
        return await self._post("answer", build_exa_answer_body(query))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncExa":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
