# Design: Solana chain support for blockrun-llm-vip

**Date:** 2026-06-02
**Status:** Approved (design forks chosen by owner)

## Goal

Add Solana payment support to the VIP SDK, matching what `blockrun-llm`
already does with its `SolanaLLMClient` — but in the VIP idiom (subclass the
official SDK, swap only the transport + base URL). Users pay per call in USDC
on Solana via x402, routed through `sol.blockrun.ai`.

## Decisions (owner-chosen)

1. **API shape:** a `chain="base" | "solana"` keyword on every existing
   client (default `"base"`). No new classes.
2. **Scope:** all 6 clients + async variants — `Anthropic`, `OpenAI`,
   `Video`, `RealFace`, `VirtualPortrait`.
3. **Dependencies:** optional `[solana]` extra — `x402[svm]>=2.0.0` (pulls
   `solders` / `base58` / `solana-py`). Base-only users stay slim.

## Background — how VIP differs from blockrun-llm

`blockrun-llm` ships a large standalone `SolanaLLMClient` with its own request
methods. VIP instead **subclasses the official `anthropic`/`openai` SDKs** and
swaps only the httpx transport: on a gateway `402`, the transport signs an x402
payment locally and retries with a `PAYMENT-SIGNATURE` header. The response is
never reshaped, so the official SDK parses the upstream signals verbatim.

Today VIP is **Base-only**: `BlockRunX402Transport` signs EIP-712 via
`eth_account`. Solana signing is a *different* path — the `x402` SDK's SVM
`KeypairSigner` + `x402Client(Sync).create_payment_payload`, bs58 keys, and a
Solana RPC for blockhash. So "add the sol side" = a parallel wallet loader +
a parallel transport, selected by `chain=`.

## Architecture

### New file: `_solana_wallet.py`

bs58 Solana key loader (ported, trimmed, from `blockrun-llm/solana_wallet.py`):

- `load_solana_wallet() -> Optional[str]` — resolution order:
  `SOLANA_WALLET_KEY` env → scan `~/.*/solana-wallet.json` (most recent) →
  `~/.blockrun/.solana-session`.
- `get_solana_public_key(key) -> str` — bs58 pubkey via `solders`.
- `solana_key_to_bytes(key)` — accept 32-byte seed or 64-byte keypair.
- `_require_solana_deps()` — raise a clear `ImportError` pointing at
  `pip install blockrun-llm-vip[solana]` when `x402[svm]` is missing.

QR / balance helpers from blockrun-llm are **omitted** (YAGNI — VIP clients
don't expose them).

### New file: `_solana_transport.py`

`BlockRunSolanaTransport(httpx.BaseTransport)` + async twin
`AsyncBlockRunSolanaTransport(httpx.AsyncBaseTransport)`:

- On construction: build the SVM signer from the bs58 key, build an
  `x402ClientSync` (sync) / `x402Client` (async), register the exact-SVM
  scheme with the resolved RPC, and create a signing lock
  (`threading.Lock` / `asyncio.Lock`).
- On `402`: read body, extract payment-required (header **or** JSON body,
  base64), `decode_payment_required_header` → `create_payment_payload`
  (under the lock — the x402 client is not concurrency-safe) →
  `encode_payment_signature_header`, set `PAYMENT-SIGNATURE` (and `X-Payment`
  for parity with the Base transport), retry once.
- RPC config via `_resolve_rpc_config(rpc_url, rpc_headers)`:
  `rpc_url` arg → `SOLANA_RPC_URL` env → default
  `https://sol.blockrun.ai/api/v1/solana/rpc` (BlockRun's free proxy).
  Header-auth (Tatum/QuickNode) supported via `SOLANA_RPC_HEADERS` /
  `SOLANA_RPC_API_KEY`, mirroring blockrun-llm's `_register_svm_with_headers`.

The signing lock + single-retry mirror blockrun-llm's concurrency fix; we do
**not** port the whole-request payment-retry loop (VIP's transport is a thin
402→sign→retry, and the official SDKs already retry transient failures).

### Modified: `_common.py`

Add chain dispatch without disturbing the existing Base path:

```python
DEFAULT_SOLANA_API_URL = "https://sol.blockrun.ai/api"

class ChainContext:
    chain: str
    api_url: str
    address: str          # eth checksum addr OR solana bs58 pubkey
    def make_transport(self, *, async_: bool) -> httpx.BaseTransport: ...

def resolve_chain(chain="base", private_key=None, api_url=None,
                  *, rpc_url=None, rpc_headers=None) -> ChainContext: ...
```

- `chain="base"` → reuses `resolve_account_and_url`, address = eth address,
  transport = `BlockRunX402Transport`.
- `chain="solana"` → `load_solana_wallet`, address = bs58 pubkey,
  transport = `BlockRunSolanaTransport`, default URL = solana.
- anything else → `ValueError`.

`resolve_account_and_url` stays for back-compat.

### Modified: the 6 client `__init__`s

Each gains `chain: str = "base"` (+ `rpc_url`, `rpc_headers` for the solana
path). Body becomes:

```python
ctx = resolve_chain(chain, private_key, api_url, rpc_url=rpc_url, rpc_headers=rpc_headers)
http_client = httpx.Client(transport=ctx.make_transport(async_=False), timeout=timeout)
super().__init__(base_url=ctx.api_url, ...)   # OpenAI: _openai_base_url(ctx.api_url)
```

`RealFace`/`VirtualPortrait` reference `self._account.address` when building
`/v1/wallet/{address}/...` URLs — replace with `self._address = ctx.address`
so the bs58 pubkey is used on Solana.

### Modified: `pyproject.toml`

```toml
[project.optional-dependencies]
solana = ["x402[svm]>=2.0.0"]
```

### Modified: `__init__.py` / README / VERSION

- Bump `0.2.1 → 0.3.0` (additive feature).
- Document `chain="solana"` + the `[solana]` extra.

## Testing

`tests/test_solana.py`, network-free:

- `resolve_chain("solana", private_key=<bs58>)` → solana transport type,
  bs58 address, `sol.blockrun.ai` URL.
- `resolve_chain("base", ...)` unchanged (eth transport + address).
- bad `chain` raises `ValueError`.
- `get_solana_public_key` round-trips a freshly generated keypair.
- 402 payment-required extraction (header + JSON-body forms).

`tests/test_video.py` must keep passing (Base default unchanged).

## Out of scope (YAGNI)

- QR funding / balance helpers.
- Whole-request payment-retry loop (official SDK retries suffice).
- A standalone `SolanaLLMClient`-style aggregator class.
