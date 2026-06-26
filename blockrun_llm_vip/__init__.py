"""blockrun-llm-vip — genuine native passthrough for Anthropic & OpenAI via BlockRun.

Drop-in for the official SDKs, paid per call in USDC (x402) on Base. Because the clients
DON'T reshape responses, the official SDK parses the gateway's VERBATIM upstream response:
real Claude thinking signatures, native content/tool_use, OpenAI system_fingerprint,
native streaming — zero model substitution.

    from blockrun_llm_vip import Anthropic, OpenAI

    claude = Anthropic()
    gpt = OpenAI()

Video (Seedance, incl. real-person / RealFace):

    from blockrun_llm_vip import Video, RealFace

    video = Video()
    job = video.generate(
        "she waves at the camera in soft studio light",
        model="bytedance/seedance-2.0",
        real_face_asset_id="ta_...",   # from RealFace enrollment
    )

More AI generation, same idiom (thin client, verbatim gateway JSON, x402-paid):

    from blockrun_llm_vip import Image, Search, Exa, Audio, Voice, Phone

    Image().generate("a red fox in snow", model="openai/gpt-image-1")
    Search().search("latest on x402", sources=["x", "news"])   # Grok live search
    Exa().search("neural search", category="research paper")    # Exa web search
    Audio().speech("hello there", voice="sarah")                # TTS / music / SFX
    Voice().call(to="+1...", task="confirm hours, then end")    # AI phone call
    Phone().buy_number(area_code="415")                         # lease caller-ID number

Async variants: AsyncAnthropic, AsyncOpenAI, AsyncVideo, AsyncRealFace, AsyncImage,
AsyncSearch, AsyncExa, AsyncAudio, AsyncVoice, AsyncPhone.

Solana: pass `chain="solana"` to any client to pay USDC on Solana via
sol.blockrun.ai instead of Base (needs the `[solana]` extra):

    pip install blockrun-llm-vip[solana]

    from blockrun_llm_vip import Anthropic, OpenAI
    claude = Anthropic(chain="solana")   # bs58 key from ~/.blockrun/.solana-session
    gpt = OpenAI(chain="solana")

Access: give BlockRun your wallet address to enable VIP, then pay per call from that
wallet (key stays local — used only for EIP-712 / Solana SVM signing).
"""

from ._anthropic_client import Anthropic, AsyncAnthropic
from ._openai_client import OpenAI, AsyncOpenAI
from ._realface import (
    AsyncRealFace,
    RealFace,
    RealFaceError,
    RealFaceTimeout,
)
from ._portrait import AsyncVirtualPortrait, VirtualPortrait
from ._video_client import (
    AsyncVideo,
    Video,
    VideoGenerationError,
    VideoGenerationTimeout,
)
from ._image_client import (
    AsyncImage,
    Image,
    ImageGenerationError,
    ImageGenerationTimeout,
    encode_data_uri,
)
from ._search_client import AsyncSearch, Search, SearchError
from ._exa_client import AsyncExa, Exa, ExaError
from ._audio_client import AsyncAudio, Audio, AudioGenerationError
from ._voice_client import AsyncVoice, Voice, VoiceCallTimeout, VoiceError
from ._phone_client import AsyncPhone, Phone, PhoneError

__version__ = "0.5.0"
__all__ = [
    # LLM passthrough
    "Anthropic",
    "AsyncAnthropic",
    "OpenAI",
    "AsyncOpenAI",
    # Video + real-person
    "Video",
    "AsyncVideo",
    "VideoGenerationError",
    "VideoGenerationTimeout",
    "RealFace",
    "AsyncRealFace",
    "RealFaceError",
    "RealFaceTimeout",
    "VirtualPortrait",
    "AsyncVirtualPortrait",
    # Image
    "Image",
    "AsyncImage",
    "ImageGenerationError",
    "ImageGenerationTimeout",
    "encode_data_uri",
    # Search
    "Search",
    "AsyncSearch",
    "SearchError",
    "Exa",
    "AsyncExa",
    "ExaError",
    # Audio
    "Audio",
    "AsyncAudio",
    "AudioGenerationError",
    # Voice + Phone
    "Voice",
    "AsyncVoice",
    "VoiceError",
    "VoiceCallTimeout",
    "Phone",
    "AsyncPhone",
    "PhoneError",
]
