"""Shared wallet/account + API-URL + chain resolution for the VIP clients."""

from __future__ import annotations

import os
from typing import Optional, Tuple

import httpx
from eth_account import Account

from ._wallet import load_wallet
from ._validation import validate_private_key, validate_api_url

DEFAULT_API_URL = "https://blockrun.ai/api"
DEFAULT_SOLANA_API_URL = "https://sol.blockrun.ai/api"


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


class ChainContext:
    """Resolved per-chain handle: which transport to build, the base URL, and the
    wallet address (eth checksum on Base, bs58 pubkey on Solana — RealFace /
    VirtualPortrait build ``/v1/wallet/{address}/...`` URLs from it)."""

    def __init__(
        self,
        chain: str,
        api_url: str,
        address: str,
        *,
        account: Optional[Account] = None,
        solana_key: Optional[str] = None,
        rpc_url: Optional[str] = None,
    ) -> None:
        self.chain = chain
        self.api_url = api_url
        self.address = address
        self._account = account
        self._solana_key = solana_key
        self._rpc_url = rpc_url

    def make_transport(self, *, async_: bool) -> httpx.BaseTransport:
        if self.chain == "solana":
            from ._solana_transport import (
                AsyncBlockRunSolanaTransport,
                BlockRunSolanaTransport,
                SolanaAsyncSigner,
                SolanaSyncSigner,
            )

            if async_:
                signer = SolanaAsyncSigner(self._solana_key, rpc_url=self._rpc_url)
                return AsyncBlockRunSolanaTransport(signer)
            signer = SolanaSyncSigner(self._solana_key, rpc_url=self._rpc_url)
            return BlockRunSolanaTransport(signer)

        from ._transport import AsyncBlockRunX402Transport, BlockRunX402Transport

        if async_:
            return AsyncBlockRunX402Transport(self._account, self.api_url)
        return BlockRunX402Transport(self._account, self.api_url)


def resolve_chain(
    chain: str = "base",
    private_key: Optional[str] = None,
    api_url: Optional[str] = None,
    *,
    rpc_url: Optional[str] = None,
) -> ChainContext:
    """Resolve wallet + base URL + transport factory for the requested chain.

    ``chain="base"`` (default) pays USDC on Base via EIP-712; ``chain="solana"``
    pays USDC on Solana via the x402 SVM signer, routed through sol.blockrun.ai.
    """
    if chain == "solana":
        from ._solana_wallet import get_solana_public_key, load_solana_wallet

        key = private_key or load_solana_wallet()
        if not key:
            raise ValueError(
                "No Solana wallet configured. Set SOLANA_WALLET_KEY, pass private_key=..., "
                "or create ~/.blockrun/.solana-session."
            )
        url = (
            api_url or os.environ.get("BLOCKRUN_SOLANA_API_URL") or DEFAULT_SOLANA_API_URL
        ).rstrip("/")
        validate_api_url(url)
        return ChainContext(
            "solana",
            url,
            get_solana_public_key(key),
            solana_key=key,
            rpc_url=rpc_url,
        )

    if chain == "base":
        account, url = resolve_account_and_url(private_key, api_url)
        return ChainContext("base", url, account.address, account=account)

    raise ValueError(f"Unknown chain {chain!r}; expected 'base' or 'solana'")
