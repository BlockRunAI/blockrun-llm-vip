"""Solana wallet key loader for blockrun-llm-vip (bs58 keys).

VIP customers already hold a funded Solana wallet — this module only LOADS the
existing key for local SVM x402 signing; the key never leaves the machine.

Resolution order: explicit arg → SOLANA_WALLET_KEY → scan ~/.*/solana-wallet.json
(most recent, any provider) → ~/.blockrun/.solana-session.

Requires the `[solana]` extra (`x402[svm]`, which pulls solders + base58).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

WALLET_DIR = Path.home() / ".blockrun"
SOLANA_WALLET_FILE = WALLET_DIR / ".solana-session"


def _require_solana_deps() -> None:
    try:
        import solders  # noqa: F401
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "Solana support requires the '[solana]' extra. "
            "Install with: pip install blockrun-llm-vip[solana]"
        ) from e


def get_solana_public_key(private_key: str) -> str:
    """Return the bs58 public key (address) for a bs58 secret key.

    Accepts both 64-byte full keypairs and 32-byte seeds.
    """
    _require_solana_deps()
    from solders.keypair import Keypair  # type: ignore

    try:
        return str(Keypair.from_base58_string(private_key).pubkey())
    except Exception:
        import base58 as b58

        decoded = b58.b58decode(private_key)
        if len(decoded) == 32:
            return str(Keypair.from_seed(decoded).pubkey())
        if len(decoded) == 64:
            return str(Keypair.from_seed(decoded[:32]).pubkey())
        raise ValueError(f"Invalid Solana private key: expected 32 or 64 bytes, got {len(decoded)}")


def _expand_solana_seed(private_key: str) -> str:
    """If private_key is a 32-byte seed, expand to a 64-byte keypair bs58 string."""
    import base58 as b58
    from solders.keypair import Keypair  # type: ignore

    decoded = b58.b58decode(private_key)
    if len(decoded) == 32:
        return b58.b58encode(bytes(Keypair.from_seed(decoded))).decode()
    return private_key


def scan_solana_wallets() -> List[dict]:
    """Scan ~/.*/solana-wallet.json files (agentcash & other providers).

    Each file holds JSON with "privateKey" and "address". Most-recent first.
    32-byte seeds are expanded to 64-byte keypairs.
    """
    home = Path.home()
    results = []  # (mtime, private_key, address)
    try:
        for entry in home.iterdir():
            if not entry.name.startswith(".") or not entry.is_dir():
                continue
            wallet_file = entry / "solana-wallet.json"
            if not wallet_file.is_file():
                continue
            try:
                data = json.loads(wallet_file.read_text())
                pk = data.get("privateKey", "")
                addr = data.get("address", "")
                if pk and addr:
                    try:
                        pk = _expand_solana_seed(pk)
                    except Exception:
                        pass
                    results.append((wallet_file.stat().st_mtime, pk, addr))
            except (json.JSONDecodeError, OSError):
                continue
    except OSError:
        pass
    results.sort(key=lambda x: x[0], reverse=True)
    return [{"private_key": pk, "address": addr} for _, pk, addr in results]


def load_solana_wallet() -> Optional[str]:
    """Load the existing Solana wallet's bs58 private key, or None.

    Order: SOLANA_WALLET_KEY env → scan ~/.*/solana-wallet.json →
    legacy ~/.blockrun/.solana-session.
    """
    env = os.environ.get("SOLANA_WALLET_KEY")
    if env and env.strip():
        return env.strip()

    wallets = scan_solana_wallets()
    if wallets:
        return wallets[0]["private_key"]

    if SOLANA_WALLET_FILE.exists():
        key = SOLANA_WALLET_FILE.read_text().strip()
        if key:
            return key
    return None
