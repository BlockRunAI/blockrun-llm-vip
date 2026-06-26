"""Drop-in replacements for openai.OpenAI / openai.AsyncOpenAI.

Subclass the official SDK so `client.chat.completions.create(...)` works exactly as
upstream — but route through BlockRun's `/v1/chat/completions` with automatic x402 USDC
payment. We DON'T touch the response, so the official SDK parses the gateway's VERBATIM
OpenAI response: native `id` (chatcmpl-*), `system_fingerprint`, `usage.*_tokens_details`,
native streaming chunks. gpt-4o / gpt-4o-mini are served OpenAI-direct.

    from blockrun_llm_vip import OpenAI

    client = OpenAI()  # wallet auto-loaded from ~/.blockrun/.session
    r = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi"}],
        response_format={"type": "json_object"},
        stop=["END"],
    )
    print(r.system_fingerprint)
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

try:
    import openai
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "The 'openai' package is required. Install: pip install blockrun-llm-vip"
    ) from e

from ._common import resolve_chain

# Default chat HTTP timeout (seconds). Was 120; reasoning models (opus-4.8,
# deepseek-v4-pro) routinely take 200–300s, so 120 timed out non-streaming
# calls. Override via the BLOCKRUN_CHAT_TIMEOUT env var. Mirrors blockrun-llm.
DEFAULT_CHAT_TIMEOUT = float(os.environ.get("BLOCKRUN_CHAT_TIMEOUT", "600"))


def _openai_base_url(api_root: str) -> str:
    # The OpenAI SDK appends "/chat/completions" to base_url, so base_url must end at
    # the "/v1" root. BlockRun's gateway lives under {api_root}/v1.
    return f"{api_root}/v1"


class OpenAI(openai.OpenAI):
    """Drop-in for openai.OpenAI, paid via x402, native passthrough.

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
            base_url=_openai_base_url(ctx.api_url),
            api_key=kwargs.pop("api_key", "blockrun"),
            http_client=http_client,
            **kwargs,
        )


class AsyncOpenAI(openai.AsyncOpenAI):
    """Async drop-in for openai.AsyncOpenAI."""

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
            base_url=_openai_base_url(ctx.api_url),
            api_key=kwargs.pop("api_key", "blockrun"),
            http_client=http_client,
            **kwargs,
        )
