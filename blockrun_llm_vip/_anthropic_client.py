"""Drop-in replacements for anthropic.Anthropic / anthropic.AsyncAnthropic.

Subclass the official SDK so `client.messages.create(...)`, `.stream(...)`, `.beta`,
etc. all work exactly as upstream — but route through BlockRun's native
`/v1/messages` with automatic x402 USDC payment. Because we DON'T touch the response,
the official SDK parses the gateway's VERBATIM Anthropic response: real thinking-block
`signature`, native `content[]`, `usage.cache_*`, native `signature_delta` streaming.

    from blockrun_llm_vip import Anthropic

    client = Anthropic()  # wallet auto-loaded from ~/.blockrun/.session
    r = client.messages.create(
        model="claude-opus-4.8",   # or claude-sonnet-4.6 / claude-haiku-4.5 — never substituted
        max_tokens=2048,
        thinking={"type": "enabled", "budget_tokens": 1024},  # adaptive on Opus 4.7/4.8
        messages=[{"role": "user", "content": "hi"}],
    )
    print(r.content)               # includes a thinking block with a real .signature

Current Claude ids: claude-opus-4.8 / 4.7 / 4.6 / 4.5, claude-sonnet-4.6 / 4.5,
claude-haiku-4.5. The id you pass is forwarded verbatim — the gateway never upgrades or
downgrades it (live catalog: https://blockrun.ai/api/v1/models).
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

try:
    import anthropic
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "The 'anthropic' package is required. Install: pip install blockrun-llm-vip"
    ) from e

from ._common import resolve_chain

# Default chat HTTP timeout (seconds). Reasoning models (opus-4.8) think 200-300s+;
# the old 120s default cut them off. Override via BLOCKRUN_CHAT_TIMEOUT env.
# Mirrors blockrun-llm 1.4.7 (client.py / anthropic_client.py).
DEFAULT_CHAT_TIMEOUT = float(os.environ.get("BLOCKRUN_CHAT_TIMEOUT", "600"))


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
        timeout: float = DEFAULT_CHAT_TIMEOUT,
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
        timeout: float = DEFAULT_CHAT_TIMEOUT,
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
