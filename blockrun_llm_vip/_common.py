"""Shared wallet/account + API-URL resolution for the VIP clients."""

from __future__ import annotations

import os
from typing import Optional, Tuple

from eth_account import Account

from ._wallet import load_wallet
from ._validation import validate_private_key, validate_api_url

DEFAULT_API_URL = "https://blockrun.ai/api"


def resolve_account_and_url(
    private_key: Optional[str], api_url: Optional[str]
) -> Tuple[Account, str]:
    key = private_key or load_wallet()
    if not key:
        raise ValueError(
            "No wallet configured. Set BLOCKRUN_WALLET_KEY, pass private_key=..., "
            "or create ~/.blockrun/.session. Give BlockRun your wallet address to enable VIP."
        )
    if not key.startswith("0x"):
        key = "0x" + key
    validate_private_key(key)
    account = Account.from_key(key)

    url = (api_url or os.environ.get("BLOCKRUN_API_URL") or DEFAULT_API_URL).rstrip("/")
    validate_api_url(url)
    return account, url
