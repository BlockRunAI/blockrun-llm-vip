"""httpx transports that pay the BlockRun gateway in Solana USDC via x402.

Same shape as the Base ``_transport`` module — intercept a 402, sign the payment
locally, retry — but the signing leg uses the x402 SDK's SVM ``KeypairSigner``
instead of EIP-712. The response body is never touched, so the official
anthropic/openai SDK still parses the gateway's VERBATIM upstream response.

The bs58 private key is used ONLY for local SVM signing and never leaves the
machine. Signing needs a Solana RPC (for the blockhash); it defaults to
BlockRun's free proxy and is overridable via ``rpc_url`` / ``SOLANA_RPC_URL``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
from typing import Any, Dict, Optional

import httpx

DEFAULT_SOLANA_RPC_URL = "https://sol.blockrun.ai/api/v1/solana/rpc"


def _require_x402():
    try:
        from x402 import x402Client, x402ClientSync
        from x402.http.utils import (
            decode_payment_required_header,
            encode_payment_signature_header,
        )
        from x402.mechanisms.svm import KeypairSigner
        from x402.mechanisms.svm.exact.register import register_exact_svm_client
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "Solana payment requires the '[solana]' extra. "
            "Install with: pip install blockrun-llm-vip[solana]"
        ) from e
    return (
        x402Client,
        x402ClientSync,
        decode_payment_required_header,
        encode_payment_signature_header,
        KeypairSigner,
        register_exact_svm_client,
    )


def _resolve_rpc_url(rpc_url: Optional[str]) -> str:
    """Explicit arg → SOLANA_RPC_URL env → BlockRun's free proxy."""
    return rpc_url or os.environ.get("SOLANA_RPC_URL") or DEFAULT_SOLANA_RPC_URL


def _create_keypair_signer(private_key: str):
    """Build an SVM KeypairSigner, accepting a 64-byte keypair or a 32-byte seed."""
    (_, _, _, _, KeypairSigner, _) = _require_x402()
    try:
        return KeypairSigner.from_base58(private_key)
    except Exception:
        import base58 as b58
        from solders.keypair import Keypair  # type: ignore

        decoded = b58.b58decode(private_key)
        if len(decoded) == 32:
            full = b58.b58encode(bytes(Keypair.from_seed(decoded))).decode()
            return KeypairSigner.from_base58(full)
        raise


def _extract_payment_required_header(response: httpx.Response) -> Optional[str]:
    """Pull the base64 x402 payment-required blob from a 402 response.

    Either a ``payment-required`` header (returned verbatim), or the JSON body
    carrying ``accepts`` / ``x402Version`` (re-encoded to base64). ``None`` when
    the 402 carries no payment requirements.
    """
    header = response.headers.get("payment-required") or response.headers.get(
        "x-payment-required"
    )
    if header:
        return header
    try:
        body = response.json()
    except Exception:
        return None
    if isinstance(body, dict) and (body.get("accepts") or body.get("x402Version")):
        return base64.b64encode(json.dumps(body).encode()).decode()
    return None


class SolanaSyncSigner:
    """Signs an x402 payment-required header with the SVM keypair (sync).

    The x402 client is not concurrency-safe, so the (fast) signing step is
    serialized with a lock — one signer can be shared across threads.
    """

    def __init__(self, private_key: str, rpc_url: Optional[str] = None):
        (_, x402ClientSync, _, _, _, register_exact_svm_client) = _require_x402()
        self._decode, self._encode = self._utils()
        rpc = _resolve_rpc_url(rpc_url)
        self._client = x402ClientSync()
        signer = _create_keypair_signer(private_key)
        register_exact_svm_client(self._client, signer, rpc_url=rpc)
        self._lock = threading.Lock()

    @staticmethod
    def _utils():
        from x402.http.utils import (
            decode_payment_required_header,
            encode_payment_signature_header,
        )

        return decode_payment_required_header, encode_payment_signature_header

    def sign(self, payment_header: str) -> str:
        payment_required = self._decode(payment_header)
        with self._lock:
            payload = self._client.create_payment_payload(payment_required)
        return self._encode(payload)


class SolanaAsyncSigner:
    """Async counterpart of :class:`SolanaSyncSigner`."""

    def __init__(self, private_key: str, rpc_url: Optional[str] = None):
        (x402Client, _, _, _, _, register_exact_svm_client) = _require_x402()
        self._decode, self._encode = SolanaSyncSigner._utils()
        rpc = _resolve_rpc_url(rpc_url)
        self._client = x402Client()
        signer = _create_keypair_signer(private_key)
        register_exact_svm_client(self._client, signer, rpc_url=rpc)
        self._lock = asyncio.Lock()

    async def asign(self, payment_header: str) -> str:
        payment_required = self._decode(payment_header)
        async with self._lock:
            payload = await self._client.create_payment_payload(payment_required)
        return self._encode(payload)


def _apply_signature(request: httpx.Request, encoded: str) -> None:
    # PAYMENT-SIGNATURE is what BlockRun's gateway expects; X-Payment is the
    # generic x402 header the video/realface endpoints document. Send both so one
    # transport serves every endpoint (mirrors the Base transport).
    request.headers["PAYMENT-SIGNATURE"] = encoded
    request.headers["X-Payment"] = encoded


class BlockRunSolanaTransport(httpx.BaseTransport):
    """Sync transport: 402 → sign (SVM) → retry."""

    def __init__(self, signer: Any, base_transport: Optional[httpx.BaseTransport] = None):
        self._signer = signer
        self._base = base_transport or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._base.handle_request(request)
        if response.status_code != 402:
            return response
        response.read()
        header = _extract_payment_required_header(response)
        if not header:
            return response
        _apply_signature(request, self._signer.sign(header))
        return self._base.handle_request(request)

    def close(self) -> None:
        self._base.close()


class AsyncBlockRunSolanaTransport(httpx.AsyncBaseTransport):
    """Async transport: 402 → sign (SVM) → retry."""

    def __init__(self, signer: Any, base_transport: Optional[httpx.AsyncBaseTransport] = None):
        self._signer = signer
        self._base = base_transport or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._base.handle_async_request(request)
        if response.status_code != 402:
            return response
        await response.aread()
        header = _extract_payment_required_header(response)
        if not header:
            return response
        _apply_signature(request, await self._signer.asign(header))
        return await self._base.handle_async_request(request)

    async def aclose(self) -> None:
        await self._base.aclose()
