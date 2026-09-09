# blockrun-llm-vip

Genuine **native passthrough** for **Anthropic** and **OpenAI** through the BlockRun
gateway — use an **API key** or pay per call in USDC (x402) on **Solana or Base**, with **zero model
substitution and zero response reshaping**.

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

## Account API quick start

Register at [user.blockrun.ai](https://user.blockrun.ai), create an
[API key](https://user.blockrun.ai/dashboard/keys), and add
[account credit](https://user.blockrun.ai/dashboard/credits).

```bash
export BLOCKRUN_API_KEY=brk_live_...
```

```python
from blockrun_llm_vip import OpenAI, Anthropic, Image

client = OpenAI()  # account mode; no wallet or chain selection needed
response = client.chat.completions.create(
    model="openai/gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)
# Explicit credentials also work: Anthropic(api_key="brk_live_...")
# All service clients, including Image/Video/Audio, accept the same api_key.
```

Sync/async clients use the native OpenAI and Anthropic SDK protocols, including
Responses and streaming. Media creation and polling authenticate with the same
account key. The default API root is `https://api.blockrun.ai`; `api_url` or
`BLOCKRUN_API_BASE_URL` can override it (a trailing `/v1` is normalized).
Credentials cannot be forwarded to another origin or through redirects. Account
errors never trigger a wallet payment. Native SDKs retain their error types;
service HTTP failures raise `AccountAPIError` with `status_code` and `retry_after`.
Account balances and charges are authoritative in the portal, separate from VIP
wallet allowlisting. Wallet-owned RealFace/portrait asset lists still require a
wallet; enrollment and generation support account mode.

Explicit `api_key` and `private_key` together are rejected. An explicit private
key selects wallet mode even if the API-key environment variable is set. Without
an API key, explicit/saved chain choices and existing Base-only wallets are
preserved; otherwise the default is Solana. Use `chain="base"` for an explicit
Base wallet. The official SDK dependencies stay on their httpx-compatible majors
(OpenAI <3, Anthropic <1) until a separate httpx2 transport is implemented.

The client supports Responses SSE and video polling; production acceptance of
these two paths currently depends on deployment of Enterprise PR #10 and its
video signing-secret configuration.

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
    model="claude-opus-4.8",              # current flagship (adaptive thinking)
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
    model="gpt-4o",                       # served OpenAI-direct (relay-detector-proof)
    messages=[{"role": "user", "content": "hi"}],
)
print(r.system_fingerprint, r.model)        # genuine OpenAI direct
```

Async: `from blockrun_llm_vip import AsyncAnthropic, AsyncOpenAI`.

### Models

You name the model; the gateway never substitutes it. Pass any current id verbatim:

- **Claude** (native `/v1/messages`): `claude-opus-4.8` · `claude-opus-4.7` ·
  `claude-opus-4.6` · `claude-opus-4.5` · `claude-sonnet-4.6` · `claude-sonnet-4.5` ·
  `claude-haiku-4.5`. Opus 4.7/4.8 use adaptive thinking — the standard
  `thinking={"type": "enabled", "budget_tokens": N}` is honored.
- **GPT** (`/v1/chat/completions`): `gpt-5.5` · `gpt-5.4` · `gpt-5.4-pro` · `gpt-5.3` ·
  `gpt-5.2` · `gpt-4.1` · `gpt-4o` · `gpt-4o-mini`, reasoning `o3` / `o4-mini`, and more.
  GPT‑5.x / o-series are reasoning models — omit `max_tokens` / `temperature` / `top_p`
  (the gateway normalizes them); `gpt-4o` / `gpt-4o-mini` are served OpenAI-direct.

The full live catalog (<!-- br:models.chatVisible -->78<!-- /br:models.chatVisible --> models incl. xAI Grok, DeepSeek, Llama, Mistral, Google
Gemini) is at `https://blockrun.ai/api/v1/models`.

## Solana — pay in USDC on Solana

Pass `chain="solana"` to **any** client to pay USDC on Solana (routed through
`sol.blockrun.ai`) instead of Base. The response is identical native passthrough —
only the payment leg changes (x402 SVM signing instead of EIP-712). Needs the
`[solana]` extra:

```bash
pip install blockrun-llm-vip[solana]
```

```python
from blockrun_llm_vip import Anthropic, OpenAI, Video

claude = Anthropic(chain="solana")   # bs58 key auto-loaded from ~/.blockrun/.solana-session
gpt    = OpenAI(chain="solana")
video  = Video(chain="solana")
# default stays Base:
claude_base = Anthropic()
```

Works on **every** client (`Anthropic`, `OpenAI`, `Video`, `RealFace`,
`VirtualPortrait`, `Image`, `Search`, `Exa`, `Audio`, `Voice`, `Phone` + async).
Signing needs a Solana RPC for the blockhash — it defaults to BlockRun's free proxy
and is overridable via `rpc_url=` or the `SOLANA_RPC_URL` env var.

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

## Image — generate & edit

`Image.generate()` / `Image.edit()` return the gateway's verbatim job (`data[].url` is a
permanent BlockRun-hosted image). They block by default and transparently handle the
gateway's hybrid flow (fast models return inline; slow ones poll). Pass `wait=False` to
get the raw job back and `Image().poll(job)` yourself.

```python
from blockrun_llm_vip import Image

img = Image()
out = img.generate("a red fox in fresh snow, soft studio light", model="openai/gpt-image-1")
print(out["data"][0]["url"])

# edit / fuse — pass a base64 data URI (or a list of up to 4); helper encodes bytes:
from blockrun_llm_vip import encode_data_uri
edited = img.edit("make it night", image=encode_data_uri(open("fox.png", "rb").read()))
```

Models: `openai/gpt-image-1` · `gpt-image-2` · `google/nano-banana` · `nano-banana-pro` ·
`xai/grok-imagine-image` · `zai/cogview-4`. `Image().models()` lists them (free).

## Search — Grok Live Search & Exa

```python
from blockrun_llm_vip import Search, Exa

# xAI Grok live search over X / web / news — grounded summary + citations
r = Search().search("latest on x402 micropayments", sources=["x", "news"], max_results=15)
print(r["summary"], r["citations"])

# Exa neural web search / similar pages / full-text extraction / grounded answer
exa = Exa()
hits = exa.search("x402 protocol", num_results=5, category="github")
text = exa.contents([h["url"] for h in hits["results"]])
ans  = exa.answer("what is the x402 payment header?")
```

## Audio — speech, music, sound effects

```python
from blockrun_llm_vip import Audio

audio = Audio()
speech = audio.speech("Hello there.", voice="sarah")           # ElevenLabs TTS
track  = audio.music("dreamy lo-fi beat", instrumental=True)   # MiniMax music (~2 min)
sfx    = audio.sound_effects("distant thunder over rain")      # ElevenLabs SFX
print(speech["data"][0]["url"], track["data"][0]["url"])

audio.voices()   # FREE: list TTS voices      audio.models()  # FREE: music models
```

## Voice & Phone — AI phone calls

Lease a number, then place an AI-driven outbound call. `Voice.call()` blocks until the
call ends and returns the transcript + recording; `wait=False` + `Voice().poll(call_id)`
for control.

```python
from blockrun_llm_vip import Phone, Voice

num = Phone().buy_number(country="US", area_code="415")   # $5, 30-day lease, wallet-bound
result = Voice().call(
    to="+14155551234",
    task="Ask if they're open Sunday, confirm hours, then thank them and end the call.",
    max_duration=3,
)
print(result["ended_by"], result["transcript"], result.get("recording_url"))
```

`Phone` also does `lookup()` / `lookup_fraud()`, `list_numbers()`, `renew_number()`,
`release_number()`. Async twins: `AsyncImage`, `AsyncSearch`, `AsyncExa`, `AsyncAudio`,
`AsyncVoice`, `AsyncPhone` — and `chain="solana"` works on all of them.

## Wallet

The private key is used **only for local signing** (EIP-712 on Base, SVM on Solana) and
never leaves your machine.

- **Base:** `private_key=` arg → `BLOCKRUN_WALLET_KEY` env → `BASE_CHAIN_WALLET_KEY` env →
  `~/.blockrun/.session`.
- **Solana** (`chain="solana"`): `private_key=` arg (bs58) → `SOLANA_WALLET_KEY` env →
  `~/.*/solana-wallet.json` → `~/.blockrun/.solana-session`.

## Access

Give BlockRun your wallet address to enable VIP, then pay per call from that wallet.

Contact: vicky@blockrun.ai
