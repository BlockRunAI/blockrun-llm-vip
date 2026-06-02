"""Drop-in replacements for anthropic.Anthropic / anthropic.AsyncAnthropic.

Subclass the official SDK so `client.messages.create(...)`, `.stream(...)`, `.beta`,
etc. all work exactly as upstream — but route through BlockRun's native
`/v1/messages` with automatic x402 USDC payment. Because we DON'T touch the response,
the official SDK parses the gateway's VERBATIM Anthropic response: real thinking-block
`signature`, native `content[]`, `usage.cache_*`, native `signature_delta` streaming.

    from blockrun_llm_vip import Anthropic

    client = Anthropic()  # wallet auto-loaded from ~/.blockrun/.session
    r = client.messages.create(
        model="claude-sonnet-4.6",
        max_tokens=2048,
        thinking={"type": "enabled", "budget_tokens": 1024},
        messages=[{"role": "user", "content": "hi"}],
    )
    print(r.content)               # includes a thinking block with a real .signature
"""

from __future__ import annotations

from typing import Optional

import httpx

try:
    import anthropic
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "The 'anthropic' package is required. Install: pip install blockrun-llm-vip"
    ) from e

from ._common import resolve_chain


class Anthropic(anthropic.Anthropic):
    """Drop-in for anthropic.Anthropic, paid via x402, native passthrough.

    ``chain="solana"`` pays USDC on Solana via sol.blockrun.ai instead of Base.
    """

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        chain: str = "base",
        rpc_url: Optional[str] = None,
        timeout: float = 120.0,
        **kwargs,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        http_client = httpx.Client(
            transport=ctx.make_transport(async_=False), timeout=timeout
        )
        super().__init__(
            base_url=ctx.api_url,
            api_key=kwargs.pop("api_key", "blockrun"),
            http_client=http_client,
            **kwargs,
        )


class AsyncAnthropic(anthropic.AsyncAnthropic):
    """Async drop-in for anthropic.AsyncAnthropic."""

    def __init__(
        self,
        *,
        private_key: Optional[str] = None,
        api_url: Optional[str] = None,
        chain: str = "base",
        rpc_url: Optional[str] = None,
        timeout: float = 120.0,
        **kwargs,
    ):
        ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url)
        http_client = httpx.AsyncClient(
            transport=ctx.make_transport(async_=True), timeout=timeout
        )
        super().__init__(
            base_url=ctx.api_url,
            api_key=kwargs.pop("api_key", "blockrun"),
            http_client=http_client,
            **kwargs,
        )
