"""x402 payment signing logic (EIP-712 / EIP-3009)."""
from __future__ import annotations

import base64
import json
import os
import time

DEFAULT_NETWORK = "eip155:8453"
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_NAME = "USD Coin"
USDC_VERSION = "2"

CHAIN_ID_MAP = {
    "base": 8453,
    "base-sepolia": 84532,
    "eip155:8453": 8453,
    "eip155:84532": 84532,
}


class X402Signer:
    """Signs x402 payment payloads using EIP-712 typed data."""

    def __init__(self, private_key: str, network: str = DEFAULT_NETWORK):
        try:
            from eth_account import Account
        except ImportError:
            raise ImportError(
                "x402 Agent mode requires eth-account. "
                "Install with: pip install jarvisclaw[agent]"
            )
        self._account = Account.from_key(private_key)
        self.network = network

    @property
    def address(self) -> str:
        return self._account.address

    def sign_from_402(self, resp, resource_url: str) -> str:
        """Parse 402 response and return base64 payment signature."""
        body = resp.json()
        if "payments" in body and len(body["payments"]) > 0:
            payment = body["payments"][0]
            resource = body.get("resource", {})
        else:
            payment = body
            resource = {}

        pay_to = payment.get("payTo", "")
        amount = payment.get("amount", payment.get("maxAmountRequired", "0"))
        network = payment.get("network", self.network)
        max_timeout = payment.get("maxTimeoutSeconds", 300)
        asset = payment.get("asset", USDC_CONTRACT)
        description = resource.get("description", "API request")

        return self._sign_payment(
            pay_to=pay_to, amount=amount, network=network,
            max_timeout=max_timeout, asset=asset,
            resource_url=resource_url, description=description,
        )

    def _sign_payment(
        self, *, pay_to, amount, network, max_timeout, asset, resource_url, description
    ) -> str:
        from eth_account.messages import encode_typed_data

        nonce = "0x" + os.urandom(32).hex()
        valid_after = int(time.time()) - 600
        valid_before = int(time.time()) + max_timeout

        chain_id = CHAIN_ID_MAP.get(network, 8453)
        if ":" in network and network not in CHAIN_ID_MAP:
            chain_id = int(network.split(":")[1])

        full_message = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "TransferWithAuthorization": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"},
                    {"name": "validAfter", "type": "uint256"},
                    {"name": "validBefore", "type": "uint256"},
                    {"name": "nonce", "type": "bytes32"},
                ],
            },
            "primaryType": "TransferWithAuthorization",
            "domain": {
                "name": USDC_NAME,
                "version": USDC_VERSION,
                "chainId": chain_id,
                "verifyingContract": asset,
            },
            "message": {
                "from": self._account.address,
                "to": pay_to,
                "value": int(amount),
                "validAfter": valid_after,
                "validBefore": valid_before,
                "nonce": bytes.fromhex(nonce[2:]),
            },
        }

        signable = encode_typed_data(full_message=full_message)
        signed = self._account.sign_message(signable)

        payload = {
            "x402Version": 2,
            "scheme": "exact",
            "network": network,
            "resource": {
                "url": resource_url,
                "description": description,
                "mimeType": "application/json",
            },
            "accepted": {
                "scheme": "exact",
                "network": network,
                "amount": amount,
                "asset": asset,
                "payTo": pay_to,
                "maxTimeoutSeconds": max_timeout,
                "extra": {"name": USDC_NAME, "version": USDC_VERSION},
            },
            "payload": {
                "signature": "0x" + signed.signature.hex(),
                "authorization": {
                    "from": self._account.address,
                    "to": pay_to,
                    "value": amount,
                    "validAfter": str(valid_after),
                    "validBefore": str(valid_before),
                    "nonce": nonce,
                },
            },
        }

        return base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()
