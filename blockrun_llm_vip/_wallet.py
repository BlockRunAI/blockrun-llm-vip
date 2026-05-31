"""Minimal wallet key loader for blockrun-llm-vip.

The private key is used ONLY for local EIP-712 signing and NEVER leaves the machine.
Resolution order: explicit arg → BLOCKRUN_WALLET_KEY → BASE_CHAIN_WALLET_KEY →
~/.blockrun/.session (same file the blockrun-llm SDK and MCP wallet use).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

WALLET_FILE = Path.home() / ".blockrun" / ".session"


def load_wallet() -> Optional[str]:
    for env in ("BLOCKRUN_WALLET_KEY", "BASE_CHAIN_WALLET_KEY"):
        v = os.environ.get(env)
        if v and v.strip():
            return v.strip()
    if WALLET_FILE.exists():
        k = WALLET_FILE.read_text().strip()
        if k:
            return k
    return None
