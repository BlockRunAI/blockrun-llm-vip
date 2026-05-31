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

## Wallet

The private key is used **only for local EIP-712 signing** and never leaves your machine.
Resolution: `private_key=` arg → `BLOCKRUN_WALLET_KEY` env → `BASE_CHAIN_WALLET_KEY` env →
`~/.blockrun/.session`.

## Access

Give BlockRun your wallet address to enable VIP, then pay per call from that wallet.

Contact: vicky@blockrun.ai
