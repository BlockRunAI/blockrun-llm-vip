"""Shared response handling for the gateway's synchronous (non-polling) clients.

The chain transport already does the x402 dance (402 → sign → retry), so by the time a
response reaches here it has either succeeded or hard-failed. We return the gateway's
VERBATIM JSON on 2xx and raise the family's error type otherwise — keeping the
zero-reshaping contract the rest of this SDK holds.
"""

from __future__ import annotations

from typing import Any, Dict

import httpx


def ok_json(
    response: httpx.Response, context: str, *, error_cls: type = RuntimeError
) -> Dict[str, Any]:
    """Return the response JSON on 2xx, else raise ``error_cls`` with the gateway's
    message. ``context`` names the operation for the error string."""
    if response.status_code // 100 != 2:
        raise error_cls(f"{context} failed ({response.status_code}): {response.text[:500]}")
    return response.json()
