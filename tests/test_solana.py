"""Unit tests for Solana chain support — pure logic, no network.

The Solana payment leg signs via the x402 SVM SDK, but every test here uses a
fake signer + a canned base transport, so nothing touches the network or an RPC.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from eth_account import Account

from blockrun_llm_vip._solana_wallet import get_solana_public_key, load_solana_wallet
from blockrun_llm_vip._solana_transport import (
    AsyncBlockRunSolanaTransport,
    BlockRunSolanaTransport,
    _extract_payment_required_header,
)
from blockrun_llm_vip._common import resolve_chain
from blockrun_llm_vip._transport import BlockRunX402Transport
from blockrun_llm_vip import Anthropic, OpenAI, RealFace, Video, VirtualPortrait


# ---- helpers ----------------------------------------------------------------

def _new_solana_key() -> str:
    """A valid bs58 64-byte Solana secret key."""
    from solders.keypair import Keypair

    return str(Keypair())


_BASE_KEY = "0x" + "1" * 64

_PAYMENT_REQUIRED_BODY = {
    "x402Version": 2,
    "accepts": [
        {
            "scheme": "exact",
            "network": "solana",
            "amount": "2000",
            "asset": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "payTo": "SoMeReCiPiEnT1111111111111111111111111111111",
            "maxTimeoutSeconds": 300,
        }
    ],
}


class _SeqTransport(httpx.BaseTransport):
    """Returns queued responses in order; records each request's headers."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.sent_headers = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.sent_headers.append(dict(request.headers))
        return self._responses.pop(0)


class _AsyncSeqTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses):
        self._responses = list(responses)
        self.sent_headers = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.sent_headers.append(dict(request.headers))
        return self._responses.pop(0)


class _FakeSigner:
    """Stand-in for the SVM signer; records the header it was asked to sign."""

    def __init__(self):
        self.seen = None

    def sign(self, payment_header: str) -> str:
        self.seen = payment_header
        return "ENCODED-SIG"

    async def asign(self, payment_header: str) -> str:
        self.seen = payment_header
        return "ENCODED-SIG"


def _resp(status, json_body, headers=None):
    return httpx.Response(
        status,
        json=json_body,
        headers=headers or {},
        request=httpx.Request("POST", "https://sol.blockrun.ai/api/v1/chat/completions"),
    )


# ---- wallet -----------------------------------------------------------------

def test_get_solana_public_key_roundtrip():
    from solders.keypair import Keypair

    kp = Keypair()
    assert get_solana_public_key(str(kp)) == str(kp.pubkey())


def test_load_solana_wallet_env_takes_precedence(monkeypatch):
    monkeypatch.setenv("SOLANA_WALLET_KEY", "  envkey123  ")
    assert load_solana_wallet() == "envkey123"


# ---- payment-required extraction --------------------------------------------

def test_extract_payment_required_from_header():
    resp = _resp(402, {"error": "pay"}, headers={"payment-required": "ALREADY-B64"})
    assert _extract_payment_required_header(resp) == "ALREADY-B64"


def test_extract_payment_required_from_body_reencodes():
    import base64
    import json

    resp = _resp(402, _PAYMENT_REQUIRED_BODY)
    out = _extract_payment_required_header(resp)
    assert json.loads(base64.b64decode(out)) == _PAYMENT_REQUIRED_BODY


def test_extract_payment_required_absent_returns_none():
    resp = _resp(402, {"error": "nope"})
    assert _extract_payment_required_header(resp) is None


# ---- sync transport ---------------------------------------------------------

def test_solana_transport_passthrough_non_402():
    base = _SeqTransport([_resp(200, {"ok": 1})])
    signer = _FakeSigner()
    t = BlockRunSolanaTransport(signer, base_transport=base)

    resp = t.handle_request(httpx.Request("POST", "https://sol.blockrun.ai/api/x"))

    assert resp.status_code == 200
    assert signer.seen is None
    assert len(base.sent_headers) == 1


def test_solana_transport_signs_and_retries():
    base = _SeqTransport([_resp(402, _PAYMENT_REQUIRED_BODY), _resp(200, {"ok": 1})])
    signer = _FakeSigner()
    t = BlockRunSolanaTransport(signer, base_transport=base)

    resp = t.handle_request(httpx.Request("POST", "https://sol.blockrun.ai/api/x"))

    assert resp.status_code == 200
    assert signer.seen is not None  # was handed the payment-required header
    # the paid retry carried the signature
    assert base.sent_headers[1]["payment-signature"] == "ENCODED-SIG"
    assert base.sent_headers[1]["x-payment"] == "ENCODED-SIG"


def test_solana_transport_402_without_payment_info_not_signed():
    base = _SeqTransport([_resp(402, {"error": "nope"})])
    signer = _FakeSigner()
    t = BlockRunSolanaTransport(signer, base_transport=base)

    resp = t.handle_request(httpx.Request("POST", "https://sol.blockrun.ai/api/x"))

    assert resp.status_code == 402
    assert signer.seen is None
    assert len(base.sent_headers) == 1


# ---- async transport --------------------------------------------------------

def test_async_solana_transport_signs_and_retries():
    base = _AsyncSeqTransport([_resp(402, _PAYMENT_REQUIRED_BODY), _resp(200, {"ok": 1})])
    signer = _FakeSigner()
    t = AsyncBlockRunSolanaTransport(signer, base_transport=base)

    async def go():
        return await t.handle_async_request(
            httpx.Request("POST", "https://sol.blockrun.ai/api/x")
        )

    resp = asyncio.run(go())

    assert resp.status_code == 200
    assert signer.seen is not None
    assert base.sent_headers[1]["payment-signature"] == "ENCODED-SIG"


# ---- resolve_chain ----------------------------------------------------------

def test_resolve_chain_solana():
    key = _new_solana_key()
    ctx = resolve_chain("solana", private_key=key)

    assert ctx.api_url == "https://sol.blockrun.ai/api"
    assert ctx.address == get_solana_public_key(key)
    assert isinstance(ctx.make_transport(async_=False), BlockRunSolanaTransport)
    assert isinstance(ctx.make_transport(async_=True), AsyncBlockRunSolanaTransport)


def test_resolve_chain_base_unchanged():
    ctx = resolve_chain("base", private_key=_BASE_KEY)

    assert ctx.api_url == "https://blockrun.ai/api"
    assert ctx.address == Account.from_key(_BASE_KEY).address
    assert isinstance(ctx.make_transport(async_=False), BlockRunX402Transport)


def test_resolve_chain_default_is_base():
    ctx = resolve_chain(private_key=_BASE_KEY)
    assert ctx.api_url == "https://blockrun.ai/api"


def test_resolve_chain_rejects_unknown():
    with pytest.raises(ValueError, match="chain"):
        resolve_chain("dogecoin", private_key=_BASE_KEY)


# ---- client wiring (construction only, no network) --------------------------

def test_anthropic_solana_wires_solana_transport():
    c = Anthropic(chain="solana", private_key=_new_solana_key())
    assert isinstance(c._client._transport, BlockRunSolanaTransport)
    assert "sol.blockrun.ai" in str(c.base_url)


def test_anthropic_base_default_unchanged():
    c = Anthropic(private_key=_BASE_KEY)
    assert isinstance(c._client._transport, BlockRunX402Transport)
    assert "sol.blockrun.ai" not in str(c.base_url)


def test_openai_solana_base_url_keeps_v1_suffix():
    c = OpenAI(chain="solana", private_key=_new_solana_key())
    assert isinstance(c._client._transport, BlockRunSolanaTransport)
    assert str(c.base_url).rstrip("/") == "https://sol.blockrun.ai/api/v1"


def test_video_solana_wires_solana_transport():
    v = Video(chain="solana", private_key=_new_solana_key())
    assert isinstance(v._client._transport, BlockRunSolanaTransport)
    assert v._api_url == "https://sol.blockrun.ai/api"


def test_realface_solana_lists_against_bs58_address():
    from blockrun_llm_vip._realface import _list_url

    key = _new_solana_key()
    rf = RealFace(chain="solana", private_key=key)
    assert rf._address == get_solana_public_key(key)
    assert "sol.blockrun.ai/api/v1/wallet/" in _list_url(rf._api_url, rf._address)


def test_portrait_solana_uses_bs58_address():
    key = _new_solana_key()
    vp = VirtualPortrait(chain="solana", private_key=key)
    assert vp._address == get_solana_public_key(key)
    assert isinstance(vp._client._transport, BlockRunSolanaTransport)
