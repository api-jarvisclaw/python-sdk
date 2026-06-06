"""x402 Solana payment signing — SPL Token TransferChecked with partial sign."""
from __future__ import annotations

import base64
import json
import struct

import requests

# Solana mainnet USDC
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOLANA_NETWORK = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
USDC_DECIMALS = 6

# Program IDs
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"

FALLBACK_RPC = "https://api.mainnet-beta.solana.com"


class SolanaX402Signer:
    """Signs x402 Solana payment payloads (SPL Transfer transaction)."""

    def __init__(self, private_key_bs58: str):
        try:
            from solders.keypair import Keypair  # noqa: F401
        except ImportError:
            raise ImportError(
                "Solana x402 requires solders. "
                "Install with: pip install jarvisclaw[solana]"
            )

        decoded = self._decode_key(private_key_bs58)
        from solders.keypair import Keypair
        self._keypair = Keypair.from_bytes(decoded)

    @staticmethod
    def _decode_key(key: str) -> bytes:
        """Decode bs58 private key (64 bytes full keypair or 32 bytes seed)."""
        import base58

        decoded = base58.b58decode(key)
        if len(decoded) == 64:
            return decoded
        elif len(decoded) == 32:
            from solders.keypair import Keypair
            kp = Keypair.from_seed(decoded)
            return bytes(kp)
        else:
            raise ValueError(
                f"Invalid Solana key length: {len(decoded)} bytes (expected 32 or 64)"
            )

    @property
    def address(self) -> str:
        return str(self._keypair.pubkey())

    def sign_from_402(self, resp, resource_url: str, base_url: str) -> str:
        """Parse 402 response, find Solana option, build tx, return base64 signature."""
        body = resp.json()
        payments = body.get("payments", [])
        resource = body.get("resource", {})

        # Find Solana payment option
        payment = None
        for p in payments:
            if p.get("network", "").startswith("solana:"):
                payment = p
                break
        if payment is None:
            raise ValueError("x402: no Solana payment option in 402 response")

        pay_to = payment.get("payTo", "")
        amount = int(payment.get("amount", "0"))
        if amount <= 0:
            raise ValueError("x402: invalid Solana payment amount (must be positive)")
        if amount > 100_000_000:  # 100 USDC safety cap
            raise ValueError(f"x402: Solana amount {amount} exceeds safety cap (100 USDC)")
        asset = payment.get("asset", USDC_MINT)
        if asset != USDC_MINT:
            raise ValueError(f"x402: unexpected Solana asset {asset}, expected USDC")
        network = payment.get("network", SOLANA_NETWORK)
        max_timeout = payment.get("maxTimeoutSeconds", 300)
        extra = payment.get("extra", {})
        description = resource.get("description", "API request")

        fee_payer_str = extra.get("feePayer", "")
        if not fee_payer_str:
            raise ValueError("x402: server did not provide feePayer for Solana")
        if not pay_to:
            raise ValueError("x402: server returned empty payTo for Solana")

        # Get blockhash from server proxy
        blockhash = self._get_blockhash(base_url)

        # Build and sign transaction
        tx_base64 = self._build_partial_tx(
            amount=amount,
            mint=asset,
            recipient=pay_to,
            fee_payer=fee_payer_str,
            blockhash=blockhash,
        )

        # x402 v2 payload
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
                "amount": str(amount),
                "asset": asset,
                "payTo": pay_to,
                "maxTimeoutSeconds": max_timeout,
                "extra": extra,
            },
            "payload": {
                "transaction": tx_base64,
            },
            "extensions": {},
        }

        return base64.b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).decode()

    def _get_blockhash(self, base_url: str) -> str:
        """Fetch latest blockhash from server proxy, fallback to public RPC."""
        # Try server proxy first
        if base_url:
            try:
                resp = requests.get(
                    f"{base_url}/api/solana/blockhash", timeout=5
                )
                if resp.status_code == 200:
                    return resp.json()["blockhash"]
            except Exception:
                pass

        # Fallback to public RPC
        rpc_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getLatestBlockhash",
            "params": [{"commitment": "finalized"}],
        }
        resp = requests.post(FALLBACK_RPC, json=rpc_payload, timeout=10)
        result = resp.json().get("result", {}).get("value", {})
        bh = result.get("blockhash", "")
        if not bh:
            raise RuntimeError(
                "Failed to get Solana blockhash from all sources"
            )
        return bh

    def _build_partial_tx(
        self, *, amount: int, mint: str, recipient: str,
        fee_payer: str, blockhash: str
    ) -> str:
        """Build a partially-signed SPL TransferChecked transaction."""
        from solders.pubkey import Pubkey
        from solders.hash import Hash as SolHash
        from solders.message import MessageV0
        from solders.transaction import VersionedTransaction
        from solders.instruction import Instruction, AccountMeta

        fee_payer_pk = Pubkey.from_string(fee_payer)
        mint_pk = Pubkey.from_string(mint)
        recipient_pk = Pubkey.from_string(recipient)
        payer_pk = self._keypair.pubkey()
        token_program = Pubkey.from_string(TOKEN_PROGRAM_ID)
        ata_program = Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)
        compute_budget = Pubkey.from_string(COMPUTE_BUDGET_PROGRAM_ID)

        # Derive Associated Token Accounts
        source_ata = self._find_ata(payer_pk, mint_pk, token_program, ata_program)
        dest_ata = self._find_ata(recipient_pk, mint_pk, token_program, ata_program)

        # Instruction 0: SetComputeUnitLimit (200000)
        cu_limit_data = struct.pack("<BI", 2, 200_000)
        ix_cu_limit = Instruction(compute_budget, cu_limit_data, [])

        # Instruction 1: SetComputeUnitPrice (10000 microlamports)
        cu_price_data = struct.pack("<BQ", 3, 10_000)
        ix_cu_price = Instruction(compute_budget, cu_price_data, [])

        # Instruction 2: TransferChecked
        # Data: [12 (discriminator)] + [amount u64] + [decimals u8]
        transfer_data = struct.pack("<BQB", 12, amount, USDC_DECIMALS)
        ix_transfer = Instruction(
            token_program,
            transfer_data,
            [
                AccountMeta(source_ata, is_signer=False, is_writable=True),
                AccountMeta(mint_pk, is_signer=False, is_writable=False),
                AccountMeta(dest_ata, is_signer=False, is_writable=True),
                AccountMeta(payer_pk, is_signer=True, is_writable=False),
            ],
        )

        instructions = [ix_cu_limit, ix_cu_price, ix_transfer]

        # Build MessageV0
        recent_blockhash = SolHash.from_string(blockhash)
        msg = MessageV0.try_compile(
            fee_payer_pk, instructions, [], recent_blockhash
        )

        # Create partially-signed transaction
        tx = VersionedTransaction(msg, [self._keypair])

        # Serialize to base64
        tx_bytes = bytes(tx)
        return base64.b64encode(tx_bytes).decode()

    @staticmethod
    def _find_ata(
        owner: "Pubkey", mint: "Pubkey",
        token_program: "Pubkey", ata_program: "Pubkey"
    ) -> "Pubkey":
        """Derive Associated Token Account address."""
        from solders.pubkey import Pubkey

        ata, _bump = Pubkey.find_program_address(
            [bytes(owner), bytes(token_program), bytes(mint)],
            ata_program,
        )
        return ata
