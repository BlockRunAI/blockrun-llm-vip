"""blockrun-llm-vip — genuine native passthrough for Anthropic & OpenAI via BlockRun.

Drop-in for the official SDKs, paid per call in USDC (x402) on Base. Because the clients
DON'T reshape responses, the official SDK parses the gateway's VERBATIM upstream response:
real Claude thinking signatures, native content/tool_use, OpenAI system_fingerprint,
native streaming — zero model substitution.

    from blockrun_llm_vip import Anthropic, OpenAI

    claude = Anthropic()
    gpt = OpenAI()

Async variants: AsyncAnthropic, AsyncOpenAI.

Access: give BlockRun your wallet address to enable VIP, then pay per call from that
wallet (key stays local — used only for EIP-712 signing).
"""

from ._anthropic_client import Anthropic, AsyncAnthropic
from ._openai_client import OpenAI, AsyncOpenAI

__version__ = "0.1.0"
__all__ = ["Anthropic", "AsyncAnthropic", "OpenAI", "AsyncOpenAI"]
