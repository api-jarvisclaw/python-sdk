"""
JarvisClaw SDK — x402 Machine Payment Client

Handles the full x402 payment flow:
1. Send request → receive 402 + payment requirements
2. Sign payment with wallet private key (EIP-712)
3. Retry request with PAYMENT-SIGNATURE header
"""
import base64
import json
import time
from typing import Any, Optional

import requests
from eth_account import Account
from eth_account.messages import encode_typed_data

DEFAULT_BASE_URL = "https://api.jarvisclaw.ai"
DEFAULT_NETWORK = "eip155:8453"


class JarvisClawClient:
    """x402-enabled HTTP client for JarvisClaw APIs.

    Usage:
        client = JarvisClawClient(private_key="0x...")

        # AI model call
        resp = client.post("/v1/chat/completions", json={
            "model": "openai/gpt-5.4-nano",
            "messages": [{"role": "user", "content": "Hello"}]
        })

        # Prediction market data
        markets = client.get("/v1/prediction/polymarket/markets")
    """

    def __init__(
        self,
        private_key: str,
        base_url: str = DEFAULT_BASE_URL,
        network: str = DEFAULT_NETWORK,
        timeout: int = 60,
        max_retries: int = 1,
    ):
        self.account = Account.from_key(private_key)
        self.base_url = base_url.rstrip("/")
        self.network = network
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()

    @property
    def address(self) -> str:
        return self.account.address

    def get(self, path: str, **kwargs) -> Any:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> Any:
        return self._request("POST", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = self.base_url + path
        kwargs.setdefault("timeout", self.timeout)

        resp = self.session.request(method, url, **kwargs)

        if resp.status_code != 402:
            resp.raise_for_status()
            return resp.json()

        # Handle x402 payment
        payment_req = self._parse_payment_required(resp)
        signature = self._sign_payment(payment_req, url)

        headers = kwargs.pop("headers", {}) or {}
        headers["PAYMENT-SIGNATURE"] = signature

        retry_resp = self.session.request(method, url, headers=headers, **kwargs)
        retry_resp.raise_for_status()
        return retry_resp.json()

    def _parse_payment_required(self, resp: requests.Response) -> dict:
        """Parse x402 payment requirements from 402 response."""
        body = resp.json()
        # Standard x402 format: {"payments": [...], "resource": {...}}
        if "payments" in body and len(body["payments"]) > 0:
            payment = body["payments"][0]
            payment["resource"] = body.get("resource", {}).get("url", "")
            payment["description"] = body.get("resource", {}).get("description", "")
            return payment
        # Legacy format
        return body

    def _sign_payment(self, payment_req: dict, resource_url: str) -> str:
        pay_to = payment_req.get("payTo", "")
        amount = payment_req.get("amount", payment_req.get("maxAmountRequired", "0"))
        network = payment_req.get("network", self.network)
        max_timeout = payment_req.get("maxTimeoutSeconds", 300)
        asset = payment_req.get("asset", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
        description = payment_req.get("description", "API request")

        nonce = self._generate_nonce()
        valid_after = int(time.time()) - 600  # 10 min before (clock skew)
        valid_before = int(time.time()) + max_timeout

        # EIP-3009 TransferWithAuthorization signature (USDC on Base)
        chain_id_map = {"base": 8453, "base-sepolia": 84532, "eip155:8453": 8453, "eip155:84532": 84532}
        chain_id = chain_id_map.get(network, int(network.split(":")[1]) if ":" in network else 8453)

        usdc_name = "USD Coin"
        usdc_version = "2"

        # Sign EIP-712 typed data
        from eth_account.messages import encode_typed_data
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
                "name": usdc_name,
                "version": usdc_version,
                "chainId": chain_id,
                "verifyingContract": asset,
            },
            "message": {
                "from": self.account.address,
                "to": pay_to,
                "value": int(amount),
                "validAfter": valid_after,
                "validBefore": valid_before,
                "nonce": bytes.fromhex(nonce[2:]),
            },
        }

        signable = encode_typed_data(full_message=full_message)
        signed = self.account.sign_message(signable)

        # Build x402 v2 payment payload (matching BlockRun SDK format)
        payload = {
            "x402Version": 2,
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
                "extra": {
                    "name": usdc_name,
                    "version": usdc_version,
                },
            },
            "payload": {
                "signature": "0x" + signed.signature.hex(),
                "authorization": {
                    "from": self.account.address,
                    "to": pay_to,
                    "value": amount,
                    "validAfter": str(valid_after),
                    "validBefore": str(valid_before),
                    "nonce": nonce,
                },
            },
        }

        payload_json = json.dumps(payload, separators=(",", ":"))
        return base64.b64encode(payload_json.encode()).decode()

    def _generate_nonce(self) -> str:
        import os
        return "0x" + os.urandom(32).hex()
