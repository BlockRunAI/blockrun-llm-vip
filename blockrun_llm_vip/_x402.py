"""x402 Payment Protocol v2 — signed payload creation (ported from blockrun-llm).

The private key is used ONLY for local EIP-712 signing and NEVER leaves the client.
"""

from __future__ import annotations

import json
import time
import base64
import secrets
from typing import Dict, Any, Optional

from eth_account import Account
from eth_account.messages import encode_typed_data

BASE_CHAIN_ID = 8453
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_SEPOLIA_CHAIN_ID = 84532
USDC_BASE_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


def get_chain_config(network: str) -> tuple[int, str]:
    if network in ("eip155:84532", "base-sepolia"):
        return BASE_SEPOLIA_CHAIN_ID, USDC_BASE_SEPOLIA
    return BASE_CHAIN_ID, USDC_BASE


def get_usdc_domain_name(network: str) -> str:
    if network in ("eip155:84532", "base-sepolia"):
        return "USDC"
    return "USD Coin"


def create_nonce() -> str:
    return "0x" + secrets.token_hex(32)


def create_payment_payload(
    account: Account,
    recipient: str,
    amount: str,
    network: str = "eip155:8453",
    resource_url: str = "https://blockrun.ai/api/v1/chat/completions",
    resource_description: str = "BlockRun AI API call",
    max_timeout_seconds: int = 300,
    extra: Optional[Dict[str, str]] = None,
    extensions: Optional[Dict[str, Any]] = None,
    asset: Optional[str] = None,
) -> str:
    now = int(time.time())
    valid_after = now - 600
    valid_before = now + max_timeout_seconds
    nonce = create_nonce()

    chain_id, default_usdc = get_chain_config(network)
    usdc_address = asset or default_usdc
    default_domain_name = get_usdc_domain_name(network)

    domain = {
        "name": extra.get("name", default_domain_name) if extra else default_domain_name,
        "version": extra.get("version", "2") if extra else "2",
        "chainId": chain_id,
        "verifyingContract": usdc_address,
    }
    types = {
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ],
    }
    message = {
        "from": account.address,
        "to": recipient,
        "value": int(amount),
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": bytes.fromhex(nonce[2:]),
    }

    signable = encode_typed_data(domain, types, message)
    signed = account.sign_message(signable)
    sig_hex = signed.signature.hex()
    signature = sig_hex if sig_hex.startswith("0x") else "0x" + sig_hex

    payment_data = {
        "x402Version": 2,
        "resource": {
            "url": resource_url,
            "description": resource_description,
            "mimeType": "application/json",
        },
        "accepted": {
            "scheme": "exact",
            "network": network,
            "amount": amount,
            "asset": usdc_address,
            "payTo": recipient,
            "maxTimeoutSeconds": max_timeout_seconds,
            "extra": extra or {"name": default_domain_name, "version": "2"},
        },
        "payload": {
            "signature": signature,
            "authorization": {
                "from": account.address,
                "to": recipient,
                "value": amount,
                "validAfter": str(valid_after),
                "validBefore": str(valid_before),
                "nonce": nonce,
            },
        },
        "extensions": extensions or {},
    }
    return base64.b64encode(json.dumps(payment_data).encode()).decode()


def parse_payment_required(header_value: str) -> Dict[str, Any]:
    try:
        return json.loads(base64.b64decode(header_value))
    except Exception:
        raise ValueError("Failed to parse payment-required header: invalid format")


def extract_payment_details(payment_required: Dict[str, Any]) -> Dict[str, Any]:
    accepts = payment_required.get("accepts", [])
    if not accepts:
        raise ValueError("No payment options in payment required response")
    option = accepts[0]
    amount = option.get("amount") or option.get("maxAmountRequired")
    if not amount:
        raise ValueError("No amount found in payment requirements")
    return {
        "amount": amount,
        "recipient": option.get("payTo"),
        "network": option.get("network"),
        "asset": option.get("asset"),
        "scheme": option.get("scheme"),
        "maxTimeoutSeconds": option.get("maxTimeoutSeconds", 300),
        "extra": option.get("extra"),
        "resource": payment_required.get("resource"),
    }
