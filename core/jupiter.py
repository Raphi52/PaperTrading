"""
Jupiter DEX Integration for Solana
===================================

Real swap execution via Jupiter aggregator (v6 API).

Features:
- Best price routing across all Solana DEXs
- Slippage protection
- Transaction building and signing
- Confirmation tracking
"""

import json
import base64
import time
import requests
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime

# Solana constants
LAMPORTS_PER_SOL = 1_000_000_000
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

# Jupiter API
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"
JUPITER_PRICE_API = "https://price.jup.ag/v6/price"

# Solana RPC endpoints
SOLANA_RPC_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",
    "https://solana-mainnet.g.alchemy.com/v2/demo",
    "https://rpc.ankr.com/solana",
]


@dataclass
class SwapQuote:
    """Jupiter swap quote"""
    input_mint: str
    output_mint: str
    input_amount: int  # In smallest unit (lamports/token decimals)
    output_amount: int
    output_amount_ui: float  # Human readable
    price_impact_pct: float
    slippage_bps: int
    route_plan: List[Dict]
    quote_response: Dict  # Raw response for swap


@dataclass
class SwapResult:
    """Result of a swap execution"""
    success: bool
    signature: Optional[str] = None
    input_amount: float = 0
    output_amount: float = 0
    price: float = 0
    fees_sol: float = 0
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class JupiterClient:
    """Jupiter DEX client for Solana swaps"""

    def __init__(self, rpc_url: str = None):
        self.rpc_url = rpc_url or SOLANA_RPC_ENDPOINTS[0]
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })

    # ==================== PRICE & QUOTES ====================

    def get_token_price(self, mint: str) -> Optional[float]:
        """Get token price in USDC"""
        try:
            response = self.session.get(
                JUPITER_PRICE_API,
                params={"ids": mint},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if mint in data.get('data', {}):
                    return data['data'][mint].get('price', 0)
            return None
        except Exception as e:
            print(f"[Jupiter] Price error: {e}")
            return None

    def get_quote(self, input_mint: str, output_mint: str,
                  amount: int, slippage_bps: int = 50) -> Optional[SwapQuote]:
        """
        Get a swap quote from Jupiter.

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest unit (lamports for SOL)
            slippage_bps: Slippage tolerance in basis points (50 = 0.5%)

        Returns:
            SwapQuote or None if failed
        """
        try:
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount),
                "slippageBps": slippage_bps,
                "onlyDirectRoutes": False,
                "asLegacyTransaction": False,
            }

            response = self.session.get(JUPITER_QUOTE_API, params=params, timeout=15)

            if response.status_code != 200:
                print(f"[Jupiter] Quote error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # Parse route info
            route_plan = []
            for route in data.get('routePlan', []):
                swap_info = route.get('swapInfo', {})
                route_plan.append({
                    'dex': swap_info.get('label', 'Unknown'),
                    'input_mint': swap_info.get('inputMint', ''),
                    'output_mint': swap_info.get('outputMint', ''),
                    'in_amount': swap_info.get('inAmount', '0'),
                    'out_amount': swap_info.get('outAmount', '0'),
                    'fee_amount': swap_info.get('feeAmount', '0'),
                })

            return SwapQuote(
                input_mint=input_mint,
                output_mint=output_mint,
                input_amount=int(data.get('inAmount', 0)),
                output_amount=int(data.get('outAmount', 0)),
                output_amount_ui=float(data.get('outAmount', 0)),  # Will be adjusted by decimals
                price_impact_pct=float(data.get('priceImpactPct', 0)),
                slippage_bps=slippage_bps,
                route_plan=route_plan,
                quote_response=data
            )

        except Exception as e:
            print(f"[Jupiter] Quote exception: {e}")
            return None

    # ==================== SWAP EXECUTION ====================

    def execute_swap(self, quote: SwapQuote, wallet_keypair,
                     priority_fee_lamports: int = 10000) -> SwapResult:
        """
        Execute a swap using a quote.

        Args:
            quote: SwapQuote from get_quote()
            wallet_keypair: Solana Keypair object (from solders)
            priority_fee_lamports: Priority fee for faster confirmation

        Returns:
            SwapResult with transaction details
        """
        try:
            from solders.keypair import Keypair
            from solders.transaction import VersionedTransaction
            from solana.rpc.api import Client
            from solana.rpc.types import TxOpts
            from solana.rpc.commitment import Confirmed

            wallet_pubkey = str(wallet_keypair.pubkey())

            # 1. Get swap transaction from Jupiter
            swap_payload = {
                "quoteResponse": quote.quote_response,
                "userPublicKey": wallet_pubkey,
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": priority_fee_lamports,
            }

            response = self.session.post(
                JUPITER_SWAP_API,
                json=swap_payload,
                timeout=30
            )

            if response.status_code != 200:
                return SwapResult(
                    success=False,
                    error=f"Swap API error: {response.status_code} - {response.text}"
                )

            swap_data = response.json()
            swap_transaction = swap_data.get('swapTransaction')

            if not swap_transaction:
                return SwapResult(
                    success=False,
                    error="No swap transaction returned"
                )

            # 2. Decode and sign transaction
            tx_bytes = base64.b64decode(swap_transaction)
            transaction = VersionedTransaction.from_bytes(tx_bytes)

            # Sign the transaction
            transaction.sign([wallet_keypair])

            # 3. Send transaction
            client = Client(self.rpc_url)

            # Serialize signed transaction
            signed_tx_bytes = bytes(transaction)

            # Send with confirmation
            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)

            result = client.send_raw_transaction(signed_tx_bytes, opts)

            if hasattr(result, 'value') and result.value:
                signature = str(result.value)

                # 4. Wait for confirmation
                confirmed = self._wait_for_confirmation(client, signature, max_attempts=30)

                if confirmed:
                    # Calculate actual amounts (need token decimals)
                    input_decimals = self._get_token_decimals(quote.input_mint)
                    output_decimals = self._get_token_decimals(quote.output_mint)

                    input_amount = quote.input_amount / (10 ** input_decimals)
                    output_amount = quote.output_amount / (10 ** output_decimals)

                    return SwapResult(
                        success=True,
                        signature=signature,
                        input_amount=input_amount,
                        output_amount=output_amount,
                        price=output_amount / input_amount if input_amount > 0 else 0,
                        fees_sol=priority_fee_lamports / LAMPORTS_PER_SOL
                    )
                else:
                    return SwapResult(
                        success=False,
                        signature=signature,
                        error="Transaction not confirmed within timeout"
                    )
            else:
                return SwapResult(
                    success=False,
                    error=f"Send failed: {result}"
                )

        except ImportError as e:
            return SwapResult(
                success=False,
                error=f"Missing dependency: {e}. Install with: pip install solana solders"
            )
        except Exception as e:
            return SwapResult(
                success=False,
                error=f"Swap execution error: {str(e)}"
            )

    def _wait_for_confirmation(self, client, signature: str,
                                max_attempts: int = 30, delay: float = 1.0) -> bool:
        """Wait for transaction confirmation"""
        from solana.rpc.commitment import Confirmed

        for _ in range(max_attempts):
            try:
                response = client.get_signature_statuses([signature])
                if response.value and response.value[0]:
                    status = response.value[0]
                    if status.confirmation_status in [Confirmed, "confirmed", "finalized"]:
                        return True
                    if status.err:
                        print(f"[Jupiter] Transaction error: {status.err}")
                        return False
            except:
                pass
            time.sleep(delay)

        return False

    def _get_token_decimals(self, mint: str) -> int:
        """Get token decimals (simplified - common tokens)"""
        # Common token decimals
        decimals_map = {
            SOL_MINT: 9,
            USDC_MINT: 6,
            USDT_MINT: 6,
        }
        return decimals_map.get(mint, 9)  # Default to 9 (SOL-like)

    # ==================== HELPERS ====================

    def get_sol_balance(self, pubkey: str) -> float:
        """Get SOL balance for a wallet"""
        try:
            from solana.rpc.api import Client
            client = Client(self.rpc_url)
            response = client.get_balance(pubkey)
            if response.value is not None:
                return response.value / LAMPORTS_PER_SOL
            return 0
        except:
            return 0

    def get_token_balance(self, wallet_pubkey: str, mint: str) -> float:
        """Get SPL token balance"""
        try:
            from solana.rpc.api import Client
            from solders.pubkey import Pubkey

            client = Client(self.rpc_url)

            # Get token accounts
            response = client.get_token_accounts_by_owner_json_parsed(
                Pubkey.from_string(wallet_pubkey),
                {"mint": Pubkey.from_string(mint)}
            )

            if response.value:
                for account in response.value:
                    info = account.account.data.parsed.get('info', {})
                    token_amount = info.get('tokenAmount', {})
                    return float(token_amount.get('uiAmount', 0))
            return 0
        except:
            return 0


class JupiterSwapper:
    """High-level Jupiter swap interface"""

    def __init__(self, private_key: str, rpc_url: str = None):
        """
        Initialize swapper with wallet.

        Args:
            private_key: Base58 encoded private key
            rpc_url: Solana RPC URL (optional)
        """
        self.client = JupiterClient(rpc_url)
        self.keypair = self._load_keypair(private_key)
        self.wallet_address = str(self.keypair.pubkey()) if self.keypair else None

    def _load_keypair(self, private_key: str):
        """Load keypair from private key"""
        try:
            from solders.keypair import Keypair

            # Try different formats
            if len(private_key) == 88:  # Base58
                return Keypair.from_base58_string(private_key)
            elif len(private_key) == 128:  # Hex (64 bytes)
                return Keypair.from_bytes(bytes.fromhex(private_key))
            elif private_key.startswith('['):  # JSON array
                key_bytes = bytes(json.loads(private_key))
                return Keypair.from_bytes(key_bytes)
            else:
                # Try base58 anyway
                return Keypair.from_base58_string(private_key)
        except Exception as e:
            print(f"[Jupiter] Keypair error: {e}")
            return None

    def buy_token(self, token_mint: str, amount_sol: float,
                  slippage_pct: float = 1.0) -> SwapResult:
        """
        Buy a token with SOL.

        Args:
            token_mint: Token mint address to buy
            amount_sol: Amount of SOL to spend
            slippage_pct: Slippage tolerance (1.0 = 1%)

        Returns:
            SwapResult
        """
        if not self.keypair:
            return SwapResult(success=False, error="Wallet not loaded")

        # Convert to lamports
        amount_lamports = int(amount_sol * LAMPORTS_PER_SOL)
        slippage_bps = int(slippage_pct * 100)

        # Get quote
        quote = self.client.get_quote(
            input_mint=SOL_MINT,
            output_mint=token_mint,
            amount=amount_lamports,
            slippage_bps=slippage_bps
        )

        if not quote:
            return SwapResult(success=False, error="Failed to get quote")

        # Check price impact
        if quote.price_impact_pct > 5.0:
            return SwapResult(
                success=False,
                error=f"Price impact too high: {quote.price_impact_pct:.2f}%"
            )

        # Execute swap
        return self.client.execute_swap(quote, self.keypair)

    def sell_token(self, token_mint: str, amount: float = None,
                   sell_all: bool = False, slippage_pct: float = 1.0) -> SwapResult:
        """
        Sell a token for SOL.

        Args:
            token_mint: Token mint address to sell
            amount: Amount of tokens to sell (in token units)
            sell_all: If True, sell entire balance
            slippage_pct: Slippage tolerance

        Returns:
            SwapResult
        """
        if not self.keypair:
            return SwapResult(success=False, error="Wallet not loaded")

        # Get token balance if selling all
        if sell_all or amount is None:
            balance = self.client.get_token_balance(self.wallet_address, token_mint)
            if balance <= 0:
                return SwapResult(success=False, error="No token balance to sell")
            amount = balance

        # Get token decimals and convert to smallest unit
        decimals = self.client._get_token_decimals(token_mint)
        amount_raw = int(amount * (10 ** decimals))
        slippage_bps = int(slippage_pct * 100)

        # Get quote
        quote = self.client.get_quote(
            input_mint=token_mint,
            output_mint=SOL_MINT,
            amount=amount_raw,
            slippage_bps=slippage_bps
        )

        if not quote:
            return SwapResult(success=False, error="Failed to get quote")

        # Execute swap
        return self.client.execute_swap(quote, self.keypair)

    def get_balances(self) -> Dict:
        """Get wallet balances"""
        if not self.wallet_address:
            return {}

        return {
            'sol': self.client.get_sol_balance(self.wallet_address),
            'usdc': self.client.get_token_balance(self.wallet_address, USDC_MINT),
            'usdt': self.client.get_token_balance(self.wallet_address, USDT_MINT),
        }


# ==================== INTEGRATION FUNCTIONS ====================

def execute_jupiter_swap(private_key: str, token_address: str,
                         amount_sol: float, action: str = "BUY",
                         slippage_pct: float = 1.0) -> Dict:
    """
    Execute a Jupiter swap - main entry point.

    Args:
        private_key: Wallet private key (base58)
        token_address: Token mint address
        amount_sol: Amount in SOL (for BUY) or tokens (for SELL)
        action: "BUY" or "SELL"
        slippage_pct: Slippage tolerance

    Returns:
        Dict with success, signature, amounts, etc.
    """
    try:
        swapper = JupiterSwapper(private_key)

        if not swapper.keypair:
            return {
                'success': False,
                'error': 'Invalid private key format'
            }

        if action.upper() == "BUY":
            result = swapper.buy_token(token_address, amount_sol, slippage_pct)
        else:
            result = swapper.sell_token(token_address, amount_sol, slippage_pct=slippage_pct)

        return {
            'success': result.success,
            'signature': result.signature,
            'input_amount': result.input_amount,
            'output_amount': result.output_amount,
            'price': result.price,
            'fees_sol': result.fees_sol,
            'error': result.error,
            'timestamp': result.timestamp,
            'explorer_url': f"https://solscan.io/tx/{result.signature}" if result.signature else None
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def get_jupiter_quote(input_mint: str, output_mint: str,
                      amount: float, is_sol_input: bool = True) -> Dict:
    """
    Get a Jupiter quote without executing.

    Args:
        input_mint: Input token mint
        output_mint: Output token mint
        amount: Amount (in SOL if is_sol_input, else in token units)
        is_sol_input: Whether input is SOL

    Returns:
        Quote details
    """
    client = JupiterClient()

    if is_sol_input:
        amount_raw = int(amount * LAMPORTS_PER_SOL)
    else:
        amount_raw = int(amount * 1_000_000)  # Assume 6 decimals

    quote = client.get_quote(input_mint, output_mint, amount_raw)

    if not quote:
        return {'success': False, 'error': 'Failed to get quote'}

    return {
        'success': True,
        'input_amount': quote.input_amount,
        'output_amount': quote.output_amount,
        'price_impact_pct': quote.price_impact_pct,
        'route': [r['dex'] for r in quote.route_plan],
    }
