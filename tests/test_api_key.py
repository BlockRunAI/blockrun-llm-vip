import asyncio
import inspect
import json
import httpx
import pytest
import blockrun_llm_vip as vip
from blockrun_llm_vip._common import resolve_chain
from blockrun_llm_vip._api_key import (
    AccountTransport,
    AsyncAccountTransport,
    AccountAPIError,
)

KEY = "brk_live_account_test"
CLASSES = [
    getattr(vip, n)
    for n in (
        "OpenAI",
        "AsyncOpenAI",
        "Anthropic",
        "AsyncAnthropic",
        "Image",
        "AsyncImage",
        "Video",
        "AsyncVideo",
        "Audio",
        "AsyncAudio",
        "Search",
        "AsyncSearch",
        "Exa",
        "AsyncExa",
        "Voice",
        "AsyncVoice",
        "Phone",
        "AsyncPhone",
        "RealFace",
        "AsyncRealFace",
        "VirtualPortrait",
        "AsyncVirtualPortrait",
    )
]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in (
        "BLOCKRUN_API_KEY",
        "BLOCKRUN_API_BASE_URL",
        "BLOCKRUN_CHAIN",
        "BLOCKRUN_WALLET_KEY",
        "BASE_CHAIN_WALLET_KEY",
        "SOLANA_WALLET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("cls", CLASSES)
def test_all_clients_account_without_wallet(cls, monkeypatch):
    monkeypatch.setenv("BLOCKRUN_API_KEY", KEY)
    monkeypatch.setattr(
        "blockrun_llm_vip._common.load_wallet", lambda: pytest.fail("wallet loaded")
    )
    c = cls()
    assert c.auth_mode == "api-key"
    r = (
        c._client.aclose()
        if isinstance(c._client, httpx.AsyncClient)
        else c._client.close()
    )
    if inspect.isawaitable(r):
        asyncio.run(r)


@pytest.mark.parametrize("status", [401, 402, 429])
def test_native_errors_keep_status_no_x402(status, monkeypatch):
    calls = []

    def send(self, request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"error": {"message": KEY, "type": "account_error"}},
            headers={"retry-after": "0"},
            request=request,
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", send)
    for cls in (vip.OpenAI, vip.Anthropic):
        c = cls(api_key=KEY, **({} if status == 402 else {"max_retries": 0}))
        with pytest.raises(Exception) as err:
            if cls is vip.OpenAI:
                c.chat.completions.create(
                    model="openai/gpt-4o-mini",
                    messages=[{"role": "user", "content": "hi"}],
                )
            else:
                c.messages.create(
                    model="anthropic/claude-haiku-4.5",
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=8,
                )
        assert err.value.status_code == status
        assert KEY not in str(err.value)
        c.close()
    assert len(calls) == 2
    assert all(
        r.headers["authorization"] == "Bearer " + KEY
        and not any("payment" in h for h in r.headers)
        for r in calls
    )


def test_service_error_and_retry_after(monkeypatch):
    monkeypatch.setattr(
        httpx.HTTPTransport,
        "handle_request",
        lambda self, r: httpx.Response(
            429, json={"error": KEY}, headers={"retry-after": "12"}, request=r
        ),
    )
    c = vip.Image(api_key=KEY)
    with pytest.raises(AccountAPIError) as err:
        c.models()
    assert err.value.status_code == 429
    assert err.value.retry_after == "12"
    assert KEY not in str(err.value)
    c._client.close()


@pytest.mark.parametrize("async_mode", [False, True])
def test_origin_binding_payment_header_removal_and_poll_normalization(
    async_mode, monkeypatch
):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", lambda self, r: respond(r)
    )

    async def send(self, r):
        return respond(r)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", send)

    async def arun():
        async with httpx.AsyncClient(
            transport=AsyncAccountTransport(KEY, "https://api.blockrun.ai")
        ) as c:
            await c.get(
                "https://api.blockrun.ai/api/v1/jobs/a?sig=abc",
                headers={"x-api-key": "remove", "payment-signature": "remove"},
            )
            with pytest.raises(ValueError):
                await c.get("https://other.example/jobs/a")

    if async_mode:
        asyncio.run(arun())
    else:
        with httpx.Client(
            transport=AccountTransport(KEY, "https://api.blockrun.ai")
        ) as c:
            c.get(
                "https://api.blockrun.ai/api/v1/jobs/a?sig=abc",
                headers={"x-api-key": "remove", "payment-signature": "remove"},
            )
            with pytest.raises(ValueError):
                c.get("https://other.example/jobs/a")
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.blockrun.ai/v1/jobs/a?sig=abc"
    assert seen[0].headers["authorization"] == "Bearer " + KEY
    assert "x-api-key" not in seen[0].headers
    assert "payment-signature" not in seen[0].headers


@pytest.mark.parametrize("cls", [vip.Image, vip.Video])
def test_initial_202_then_poll_once(cls, monkeypatch):
    calls = []

    def send(self, r):
        calls.append(r)
        if r.method == "POST":
            return httpx.Response(
                202,
                json={
                    "id": "job",
                    "status": "queued",
                    "poll_url": "/api/v1/videos/generations/job",
                },
                request=r,
            )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "data": [{"url": "https://cdn.example/result"}],
            },
            request=r,
        )

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", send)
    c = cls(api_key=KEY)
    result = c.generate("cat", poll_interval=0)
    assert result["data"]
    assert [r.method for r in calls] == ["POST", "GET"]
    assert all(r.headers["authorization"] == "Bearer " + KEY for r in calls)
    c._client.close()


def test_key_precedence_and_wallet_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("BLOCKRUN_API_KEY", KEY)
    assert (
        resolve_chain(api_key=KEY, api_url="https://api.blockrun.ai/v1/").api_url
        == "https://api.blockrun.ai"
    )
    assert resolve_chain(private_key="0x" + "1" * 64).chain == "base"
    with pytest.raises(ValueError):
        resolve_chain(api_key="", private_key="0x" + "1" * 64)
    with pytest.raises(ValueError):
        resolve_chain(api_key="bad")
    monkeypatch.delenv("BLOCKRUN_API_KEY")
    # No funded RPC is needed: intercept the final chain-specific loader.
    monkeypatch.setattr(
        "blockrun_llm_vip._solana_wallet.load_solana_wallet", lambda: "test-sol"
    )
    monkeypatch.setattr(
        "blockrun_llm_vip._solana_wallet.get_solana_public_key", lambda k: "address"
    )
    assert resolve_chain().chain == "solana"
    monkeypatch.setenv("BLOCKRUN_WALLET_KEY", "0x" + "1" * 64)
    assert resolve_chain().chain == "base"
    home = tmp_path / ".blockrun"
    home.mkdir()
    (home / "payment-chain").write_text("solana")
    assert resolve_chain().chain == "solana"


def test_wallet_owned_assets_are_explicitly_unavailable():
    from blockrun_llm_vip._realface import _list_url

    with pytest.raises(ValueError, match="requires a wallet"):
        _list_url("https://api.blockrun.ai", "")


@pytest.mark.asyncio
async def test_async_openai_native_sse(monkeypatch):
    async def send(self, r):
        assert r.headers["authorization"] == "Bearer " + KEY
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"id":"chat1","object":"chat.completion.chunk","created":1,"model":"m","choices":[{"index":0,"delta":{"content":"OK"},"finish_reason":null}]}\n\ndata: [DONE]\n\n',
            request=r,
        )

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", send)
    async with vip.AsyncOpenAI(api_key=KEY) as c:
        stream = await c.chat.completions.create(
            model="m", messages=[{"role": "user", "content": "hi"}], stream=True
        )
        chunks = [x async for x in stream]
        assert chunks[0].choices[0].delta.content == "OK"
