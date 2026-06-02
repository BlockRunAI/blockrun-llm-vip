# blockrun-llm-vip

Genuine **native passthrough** for **Anthropic** and **OpenAI** through the BlockRun
gateway — pay per call in USDC (x402) on Base, with **zero model substitution and zero
response reshaping**.

Unlike a normal aggregator, these clients **subclass the official `anthropic` and
`openai` Python SDKs** and only swap the transport (to add x402 payment) and the base
URL. The gateway returns the upstream provider's response **verbatim**, so the official
SDK parses the real signals:

- **Claude**: real thinking-block `signature`, native `content[]` (text / thinking /
  tool_use), `usage.cache_creation_input_tokens` / `cache_read_input_tokens`, native
  `signature_delta` streaming — routed to Anthropic's native `/v1/messages`.
- **GPT**: native `id` (`chatcmpl-*`), `system_fingerprint`, `usage.*_tokens_details`,
  honest `response_format` (JSON mode) + `stop` + nested errors. `gpt-4o` /
  `gpt-4o-mini` are served **OpenAI-direct**.

A Claude / OpenAI relay detector (e.g. cctest.ai) sees a direct upstream call.

## Install

```bash
pip install blockrun-llm-vip
```

## Use — it's a drop-in

```python
from blockrun_llm_vip import Anthropic, OpenAI

# Claude — exactly the official anthropic SDK API
claude = Anthropic()                      # wallet auto-loaded from ~/.blockrun/.session
r = claude.messages.create(
    model="claude-sonnet-4.6",
    max_tokens=2048,
    thinking={"type": "enabled", "budget_tokens": 1024},
    messages=[{"role": "user", "content": "What is 23*47?"}],
)
for block in r.content:
    if block.type == "thinking":
        print("signature:", block.signature)   # real Anthropic signature

# GPT — exactly the official openai SDK API
gpt = OpenAI()
r = gpt.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "hi"}],
)
print(r.system_fingerprint, r.model)        # genuine OpenAI direct
```

Async: `from blockrun_llm_vip import AsyncAnthropic, AsyncOpenAI`.

## Video — Seedance, incl. real-person (RealFace)

Generate short videos through the gateway with **ByteDance Seedance**. `Video.generate()`
runs the async submit→poll loop for you (x402-paid both legs by the same wallet) and
returns the gateway's verbatim completed-job JSON — `data[0].url` is a permanent
BlockRun-hosted MP4. Defaults to `bytedance/seedance-2.0-fast`.

```python
from blockrun_llm_vip import Video

video = Video()
job = video.generate(
    "a neon-lit cyberpunk street, slow dolly forward",
    duration_seconds=5,
    aspect_ratio="16:9",
)
print(job["data"][0]["url"])          # permanent MP4 URL
```

**Real people are supported.** A specific, real human can appear consistently across
clips — you don't upload a face per call (raw face uploads to Sora / generic
image-to-video are blocked by design). Instead you **enroll the person once** via
**RealFace** (one-time $0.01, ~1-min on-phone liveness for consent, **no KYC**), get a
`ta_xxxx`, and pass it as `real_face_asset_id` on Seedance 2.0 / 2.0-fast:

| Subject | Use | Liveness | KYC | Enroll |
|---|---|---|---|---|
| A real, specific person | `RealFace` | ~1 min on phone (consent) | No | `init → liveness → enroll` |
| AI character / mascot | `VirtualPortrait` | None | No | single `enroll` call |

Full flow, state machine, and error states: **[docs/real-person-flow.md](docs/real-person-flow.md)**.

```python
from blockrun_llm_vip import Video, RealFace

rf = RealFace()
started = rf.init("Spokesperson — Q3 campaign")
print("Open on the rights-holder's phone:", started["h5_link"])   # QR / mobile link
rf.wait_until_active(started["group_id"])                         # after they nod + blink
asset = rf.enroll(
    name="Spokesperson — Q3 campaign",
    image_url="https://example.com/person.jpg",
    group_id=started["group_id"],
)

video = Video()
job = video.generate(
    "she smiles warmly and waves at the camera in soft studio light",
    model="bytedance/seedance-2.0",
    real_face_asset_id=asset["asset_id"],   # ta_xxxx
)
print(job["data"][0]["url"], job["payment"]["tx_hash"])
```

`real_face_asset_id` is mutually exclusive with `image_url` and only works on Seedance
2.0 / 2.0-fast. Other `generate()` options: `resolution`, `generate_audio`, `seed`,
`watermark`, `return_last_frame`, plus `timeout` / `poll_interval` for the poll loop.

**AI character** (mascot / avatar, no liveness) — enroll a **Virtual Portrait** instead
of a RealFace; same `ta_xxxx` → `real_face_asset_id` flow:

```python
from blockrun_llm_vip import VirtualPortrait

vp = VirtualPortrait()
asset = vp.enroll(name="Mascot", image_url="https://example.com/character.jpg")  # $0.01
# pass asset["asset_id"] as real_face_asset_id on Seedance 2.0 / 2.0-fast
```

List what a wallet has enrolled: `RealFace().list()` / `VirtualPortrait().list()` (free).
Async: `AsyncVideo`, `AsyncRealFace`, `AsyncVirtualPortrait`.

## Wallet

The private key is used **only for local EIP-712 signing** and never leaves your machine.
Resolution: `private_key=` arg → `BLOCKRUN_WALLET_KEY` env → `BASE_CHAIN_WALLET_KEY` env →
`~/.blockrun/.session`.

## Access

Give BlockRun your wallet address to enable VIP, then pay per call from that wallet.

Contact: vicky@blockrun.ai
