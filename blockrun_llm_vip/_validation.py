"""Lightweight input validation (ported from blockrun-llm)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_LOCALHOST = {"localhost", "127.0.0.1"}


def validate_private_key(key: str) -> None:
    if not isinstance(key, str):
        raise ValueError("Private key must be a string")
    if not key.startswith("0x"):
        raise ValueError("Private key must start with 0x")
    if len(key) != 66 or not re.match(r"^0x[0-9a-fA-F]{64}$", key):
        raise ValueError("Private key must be 0x + 64 hexadecimal characters")


def validate_api_url(url: str) -> None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("API URL must include scheme and domain")
    is_localhost = parsed.netloc.split(":")[0] in _LOCALHOST
    if parsed.scheme != "https" and not is_localhost:
        raise ValueError("API URL must use HTTPS for non-localhost endpoints")
