"""
PancakeSwap DEX Integration for BSC
====================================

Real swap execution via PancakeSwap V3 (with V2 fallback).

Features:
- Best price routing via PancakeSwap Smart Router
- Slippage protection
- Transaction building and signing
- Gas estimation and optimization
- Multi-hop routing support
"""

import json
import time
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime

# Common token addresses (BSC Mainnet)
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
BUSD = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"
USDT_BSC = "0x55d398326f99059fF775485246999027B3197955"
USDC_BSC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
CAKE = "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"
ETH_BSC = "0x2170Ed0880ac9A755fd29B2688956BD959F933F8"
BTCB = "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c"

# PancakeSwap V3 Contract Addresses (BSC Mainnet)
PANCAKE_V3_ROUTER = "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4"  # SmartRouter
PANCAKE_V3_QUOTER = "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997"  # QuoterV2
PANCAKE_V3_FACTORY = "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"

# PancakeSwap V2 Contract Addresses (BSC Mainnet)
PANCAKE_V2_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
PANCAKE_V2_FACTORY = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"

# Fee tiers for PancakeSwap V3 (in basis points * 100)
FEE_TIERS = [100, 500, 2500, 10000]  # 0.01%, 0.05%, 0.25%, 1%

# BSC RPC endpoints
BSC_RPC_ENDPOINTS = [
    "https://bsc-dataseed.binance.org",
    "https://bsc-dataseed1.binance.org",
    "https://bsc-dataseed2.binance.org",
    "https://bsc.publicnode.com",
    "https://rpc.ankr.com/bsc",
]

# ABIs (minimal for swaps)
SMART_ROUTER_ABI = json.loads('''[
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "recipient", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMinimum", "type": "uint256"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "components": [
                    {"name": "path", "type": "bytes"},
                    {"name": "recipient", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMinimum", "type": "uint256"}
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "exactInput",
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"name": "amountMinimum", "type": "uint256"}, {"name": "recipient", "type": "address"}],
        "name": "unwrapWETH9",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    }
]''')

QUOTER_V2_ABI = json.loads('''[
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "name": "params",
                "type": "tuple"
            }
        ],
        "name": "quoteExactInputSingle",
        "outputs": [
            {"name": "amountOut", "type": "uint256"},
            {"name": "sqrtPriceX96After", "type": "uint160"},
            {"name": "initializedTicksCrossed", "type": "uint32"},
            {"name": "gasEstimate", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]''')

# PancakeSwap V2 Router ABI (for fallback)
ROUTER_V2_ABI = json.loads('''[
    {
        "inputs": [
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETH",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function"
    }
]''')

ERC20_ABI = json.loads('''[
    {"constant": true, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": true, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": true, "inputs": [{"name": "owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": false, "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": true, "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
]''')


@dataclass
class SwapQuote:
    """PancakeSwap swap quote"""
    token_in: str
    token_out: str
    amount_in: int  # In wei/smallest unit
    amount_out: int
    amount_out_min: int  # After slippage
    fee_tier: int  # 0 for V2
    price_impact_pct: float
    gas_estimate: int
    use_v2: bool = False  # True if using V2 router


@dataclass
class SwapResult:
    """Result of a swap execution"""
    success: bool
    tx_hash: Optional[str] = None
    input_amount: float = 0
    output_amount: float = 0
    price: float = 0
    gas_used: int = 0
    gas_price_gwei: float = 0
    total_fee_bnb: float = 0
    error: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class PancakeSwapClient:
    """PancakeSwap client for BSC swaps"""

    def __init__(self, rpc_url: str = None):
        """
        Initialize PancakeSwap client.

        Args:
            rpc_url: BSC RPC URL
        """
        self.rpc_url = rpc_url or BSC_RPC_ENDPOINTS[0]
        self.w3 = None
        self._init_web3()

    def _init_web3(self):
        """Initialize Web3 connection"""
        try:
            from web3 import Web3
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        except ImportError:
            self.w3 = None

    def is_connected(self) -> bool:
        """Check if connected to RPC"""
        if not self.w3:
            return False
        try:
            return self.w3.is_connected()
        except:
            return False

    # ==================== TOKEN INFO ====================

    def get_token_decimals(self, token_address: str) -> int:
        """Get token decimals"""
        if not self.w3:
            return 18

        try:
            # Common tokens
            common_decimals = {
                BUSD.lower(): 18,
                USDT_BSC.lower(): 18,
                USDC_BSC.lower(): 18,
                BTCB.lower(): 18,
            }
            if token_address.lower() in common_decimals:
                return common_decimals[token_address.lower()]

            contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            return contract.functions.decimals().call()
        except:
            return 18

    def get_token_balance(self, token_address: str, wallet_address: str) -> Tuple[int, float]:
        """
        Get token balance.

        Returns:
            (raw_balance, human_readable_balance)
        """
        if not self.w3:
            return 0, 0.0

        try:
            wallet = self.w3.to_checksum_address(wallet_address)

            # BNB balance
            if token_address.lower() == WBNB.lower() or token_address.lower() == "bnb":
                balance = self.w3.eth.get_balance(wallet)
                return balance, float(self.w3.from_wei(balance, 'ether'))

            # BEP20 balance
            contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            balance = contract.functions.balanceOf(wallet).call()
            decimals = self.get_token_decimals(token_address)
            human_balance = balance / (10 ** decimals)

            return balance, human_balance
        except Exception as e:
            print(f"[PancakeSwap] Balance error: {e}")
            return 0, 0.0

    def get_bnb_balance(self, wallet_address: str) -> float:
        """Get BNB balance"""
        if not self.w3:
            return 0.0
        try:
            balance = self.w3.eth.get_balance(self.w3.to_checksum_address(wallet_address))
            return float(self.w3.from_wei(balance, 'ether'))
        except:
            return 0.0

    # ==================== QUOTES ====================

    def get_quote_v3(self, token_in: str, token_out: str, amount_in: int,
                     slippage_pct: float = 0.5) -> Optional[SwapQuote]:
        """Get quote from PancakeSwap V3"""
        if not self.w3 or not self.is_connected():
            return None

        try:
            quoter = self.w3.eth.contract(
                address=self.w3.to_checksum_address(PANCAKE_V3_QUOTER),
                abi=QUOTER_V2_ABI
            )

            best_quote = None
            best_amount_out = 0

            # Try all fee tiers
            for fee in FEE_TIERS:
                try:
                    params = {
                        'tokenIn': self.w3.to_checksum_address(token_in),
                        'tokenOut': self.w3.to_checksum_address(token_out),
                        'amountIn': amount_in,
                        'fee': fee,
                        'sqrtPriceLimitX96': 0
                    }

                    result = quoter.functions.quoteExactInputSingle(params).call()
                    amount_out = result[0]
                    gas_estimate = result[3] if len(result) > 3 else 200000

                    if amount_out > best_amount_out:
                        best_amount_out = amount_out
                        amount_out_min = int(amount_out * (1 - slippage_pct / 100))

                        best_quote = SwapQuote(
                            token_in=token_in,
                            token_out=token_out,
                            amount_in=amount_in,
                            amount_out=amount_out,
                            amount_out_min=amount_out_min,
                            fee_tier=fee,
                            price_impact_pct=0.0,
                            gas_estimate=gas_estimate,
                            use_v2=False
                        )
                except:
                    continue

            return best_quote

        except Exception as e:
            print(f"[PancakeSwap] V3 Quote error: {e}")
            return None

    def get_quote_v2(self, token_in: str, token_out: str, amount_in: int,
                     slippage_pct: float = 0.5) -> Optional[SwapQuote]:
        """Get quote from PancakeSwap V2 (fallback)"""
        if not self.w3 or not self.is_connected():
            return None

        try:
            router = self.w3.eth.contract(
                address=self.w3.to_checksum_address(PANCAKE_V2_ROUTER),
                abi=ROUTER_V2_ABI
            )

            path = [
                self.w3.to_checksum_address(token_in),
                self.w3.to_checksum_address(token_out)
            ]

            amounts = router.functions.getAmountsOut(amount_in, path).call()
            amount_out = amounts[-1]
            amount_out_min = int(amount_out * (1 - slippage_pct / 100))

            return SwapQuote(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
                amount_out=amount_out,
                amount_out_min=amount_out_min,
                fee_tier=0,  # V2 uses 0.25% flat fee
                price_impact_pct=0.0,
                gas_estimate=250000,
                use_v2=True
            )

        except Exception as e:
            print(f"[PancakeSwap] V2 Quote error: {e}")
            return None

    def get_quote(self, token_in: str, token_out: str, amount_in: int,
                  slippage_pct: float = 0.5) -> Optional[SwapQuote]:
        """
        Get best quote from V3 or V2.

        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount in smallest unit (wei)
            slippage_pct: Slippage tolerance

        Returns:
            SwapQuote or None
        """
        # Try V3 first
        v3_quote = self.get_quote_v3(token_in, token_out, amount_in, slippage_pct)

        # Try V2 as fallback or comparison
        v2_quote = self.get_quote_v2(token_in, token_out, amount_in, slippage_pct)

        # Return best quote
        if v3_quote and v2_quote:
            return v3_quote if v3_quote.amount_out >= v2_quote.amount_out else v2_quote
        return v3_quote or v2_quote

    # ==================== APPROVALS ====================

    def check_allowance(self, token_address: str, wallet_address: str,
                        spender: str = None) -> int:
        """Check token allowance for router"""
        if not self.w3:
            return 0

        try:
            spender = spender or PANCAKE_V3_ROUTER
            contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            return contract.functions.allowance(
                self.w3.to_checksum_address(wallet_address),
                self.w3.to_checksum_address(spender)
            ).call()
        except:
            return 0

    def approve_token(self, token_address: str, wallet_keypair,
                      amount: int = None, spender: str = None) -> Optional[str]:
        """
        Approve token spending for router.

        Returns:
            Transaction hash or None
        """
        if not self.w3:
            return None

        try:
            spender = spender or PANCAKE_V3_ROUTER
            amount = amount or 2**256 - 1  # Max uint256

            contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )

            # Build transaction
            tx = contract.functions.approve(
                self.w3.to_checksum_address(spender),
                amount
            ).build_transaction({
                'from': wallet_keypair.address,
                'nonce': self.w3.eth.get_transaction_count(wallet_keypair.address),
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': 56  # BSC mainnet
            })

            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, wallet_keypair.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status == 1:
                return tx_hash.hex()
            return None

        except Exception as e:
            print(f"[PancakeSwap] Approval error: {e}")
            return None

    # ==================== SWAP EXECUTION ====================

    def execute_swap_v3(self, quote: SwapQuote, wallet_keypair,
                        deadline_minutes: int = 20) -> SwapResult:
        """Execute swap using PancakeSwap V3"""
        if not self.w3:
            return SwapResult(success=False, error="Web3 not initialized")

        try:
            router = self.w3.eth.contract(
                address=self.w3.to_checksum_address(PANCAKE_V3_ROUTER),
                abi=SMART_ROUTER_ABI
            )

            deadline = int(time.time()) + (deadline_minutes * 60)
            is_bnb_input = quote.token_in.lower() == WBNB.lower()

            # For token inputs, check and set allowance
            if not is_bnb_input:
                allowance = self.check_allowance(quote.token_in, wallet_keypair.address)
                if allowance < quote.amount_in:
                    print("[PancakeSwap] Approving token...")
                    approve_hash = self.approve_token(quote.token_in, wallet_keypair)
                    if not approve_hash:
                        return SwapResult(success=False, error="Token approval failed")
                    print(f"[PancakeSwap] Approved: {approve_hash}")
                    time.sleep(3)  # Wait for approval to be confirmed

            # Build swap parameters
            params = {
                'tokenIn': self.w3.to_checksum_address(quote.token_in),
                'tokenOut': self.w3.to_checksum_address(quote.token_out),
                'fee': quote.fee_tier,
                'recipient': wallet_keypair.address,
                'amountIn': quote.amount_in,
                'amountOutMinimum': quote.amount_out_min,
                'sqrtPriceLimitX96': 0
            }

            gas_price = self.w3.eth.gas_price

            tx_params = {
                'from': wallet_keypair.address,
                'nonce': self.w3.eth.get_transaction_count(wallet_keypair.address),
                'gas': quote.gas_estimate + 50000,
                'gasPrice': gas_price,
                'chainId': 56
            }

            if is_bnb_input:
                tx_params['value'] = quote.amount_in

            tx = router.functions.exactInputSingle(params).build_transaction(tx_params)

            signed_tx = self.w3.eth.account.sign_transaction(tx, wallet_keypair.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"[PancakeSwap] Tx sent: {tx_hash.hex()}")

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

            if receipt.status == 1:
                in_decimals = self.get_token_decimals(quote.token_in)
                out_decimals = self.get_token_decimals(quote.token_out)

                input_amount = quote.amount_in / (10 ** in_decimals)
                output_amount = quote.amount_out / (10 ** out_decimals)

                gas_used = receipt.gasUsed
                gas_price_gwei = gas_price / 1e9
                total_fee_bnb = (gas_used * gas_price) / 1e18

                return SwapResult(
                    success=True,
                    tx_hash=tx_hash.hex(),
                    input_amount=input_amount,
                    output_amount=output_amount,
                    price=output_amount / input_amount if input_amount > 0 else 0,
                    gas_used=gas_used,
                    gas_price_gwei=gas_price_gwei,
                    total_fee_bnb=total_fee_bnb
                )
            else:
                return SwapResult(
                    success=False,
                    tx_hash=tx_hash.hex(),
                    error="Transaction reverted"
                )

        except Exception as e:
            return SwapResult(success=False, error=str(e))

    def execute_swap_v2(self, quote: SwapQuote, wallet_keypair,
                        deadline_minutes: int = 20) -> SwapResult:
        """Execute swap using PancakeSwap V2"""
        if not self.w3:
            return SwapResult(success=False, error="Web3 not initialized")

        try:
            router = self.w3.eth.contract(
                address=self.w3.to_checksum_address(PANCAKE_V2_ROUTER),
                abi=ROUTER_V2_ABI
            )

            deadline = int(time.time()) + (deadline_minutes * 60)
            is_bnb_input = quote.token_in.lower() == WBNB.lower()
            is_bnb_output = quote.token_out.lower() == WBNB.lower()

            path = [
                self.w3.to_checksum_address(quote.token_in),
                self.w3.to_checksum_address(quote.token_out)
            ]

            gas_price = self.w3.eth.gas_price

            if is_bnb_input:
                # BNB -> Token
                tx = router.functions.swapExactETHForTokens(
                    quote.amount_out_min,
                    path,
                    wallet_keypair.address,
                    deadline
                ).build_transaction({
                    'from': wallet_keypair.address,
                    'nonce': self.w3.eth.get_transaction_count(wallet_keypair.address),
                    'gas': quote.gas_estimate,
                    'gasPrice': gas_price,
                    'value': quote.amount_in,
                    'chainId': 56
                })
            elif is_bnb_output:
                # Token -> BNB
                # First approve
                allowance = self.check_allowance(quote.token_in, wallet_keypair.address, PANCAKE_V2_ROUTER)
                if allowance < quote.amount_in:
                    print("[PancakeSwap] Approving token for V2...")
                    approve_hash = self.approve_token(quote.token_in, wallet_keypair, spender=PANCAKE_V2_ROUTER)
                    if not approve_hash:
                        return SwapResult(success=False, error="Token approval failed")
                    time.sleep(3)

                tx = router.functions.swapExactTokensForETH(
                    quote.amount_in,
                    quote.amount_out_min,
                    path,
                    wallet_keypair.address,
                    deadline
                ).build_transaction({
                    'from': wallet_keypair.address,
                    'nonce': self.w3.eth.get_transaction_count(wallet_keypair.address),
                    'gas': quote.gas_estimate,
                    'gasPrice': gas_price,
                    'chainId': 56
                })
            else:
                return SwapResult(success=False, error="Token-to-token swaps require WBNB path")

            signed_tx = self.w3.eth.account.sign_transaction(tx, wallet_keypair.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"[PancakeSwap V2] Tx sent: {tx_hash.hex()}")

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

            if receipt.status == 1:
                in_decimals = self.get_token_decimals(quote.token_in)
                out_decimals = self.get_token_decimals(quote.token_out)

                input_amount = quote.amount_in / (10 ** in_decimals)
                output_amount = quote.amount_out / (10 ** out_decimals)

                gas_used = receipt.gasUsed
                gas_price_gwei = gas_price / 1e9
                total_fee_bnb = (gas_used * gas_price) / 1e18

                return SwapResult(
                    success=True,
                    tx_hash=tx_hash.hex(),
                    input_amount=input_amount,
                    output_amount=output_amount,
                    price=output_amount / input_amount if input_amount > 0 else 0,
                    gas_used=gas_used,
                    gas_price_gwei=gas_price_gwei,
                    total_fee_bnb=total_fee_bnb
                )
            else:
                return SwapResult(
                    success=False,
                    tx_hash=tx_hash.hex(),
                    error="Transaction reverted"
                )

        except Exception as e:
            return SwapResult(success=False, error=str(e))

    def execute_swap(self, quote: SwapQuote, wallet_keypair,
                     deadline_minutes: int = 20) -> SwapResult:
        """Execute swap using best router (V3 or V2)"""
        if quote.use_v2:
            return self.execute_swap_v2(quote, wallet_keypair, deadline_minutes)
        else:
            return self.execute_swap_v3(quote, wallet_keypair, deadline_minutes)


class PancakeSwapper:
    """High-level PancakeSwap interface"""

    def __init__(self, private_key: str, rpc_url: str = None):
        """
        Initialize swapper with wallet.

        Args:
            private_key: Hex private key (with or without 0x prefix)
            rpc_url: RPC URL (optional)
        """
        self.client = PancakeSwapClient(rpc_url)
        self.account = self._load_account(private_key)
        self.wallet_address = self.account.address if self.account else None

    def _load_account(self, private_key: str):
        """Load account from private key"""
        if not self.client.w3:
            return None

        try:
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            return self.client.w3.eth.account.from_key(private_key)
        except Exception as e:
            print(f"[PancakeSwap] Account error: {e}")
            return None

    def buy_token(self, token_address: str, amount_bnb: float,
                  slippage_pct: float = 0.5) -> SwapResult:
        """
        Buy a token with BNB.

        Args:
            token_address: Token to buy
            amount_bnb: Amount of BNB to spend
            slippage_pct: Slippage tolerance

        Returns:
            SwapResult
        """
        if not self.account:
            return SwapResult(success=False, error="Wallet not loaded")

        if not self.client.is_connected():
            return SwapResult(success=False, error="Not connected to BSC RPC")

        # Check BNB balance
        bnb_balance = self.client.get_bnb_balance(self.wallet_address)
        if bnb_balance < amount_bnb + 0.005:  # Reserve for gas
            return SwapResult(
                success=False,
                error=f"Insufficient BNB (have {bnb_balance:.4f}, need {amount_bnb + 0.005:.4f})"
            )

        # Convert BNB to wei
        amount_wei = int(amount_bnb * 1e18)

        # Get quote
        quote = self.client.get_quote(
            token_in=WBNB,
            token_out=token_address,
            amount_in=amount_wei,
            slippage_pct=slippage_pct
        )

        if not quote:
            return SwapResult(success=False, error="Failed to get quote")

        # Execute swap
        return self.client.execute_swap(quote, self.account)

    def sell_token(self, token_address: str, amount: float = None,
                   sell_all: bool = False, slippage_pct: float = 1.0) -> SwapResult:
        """
        Sell a token for BNB.

        Args:
            token_address: Token to sell
            amount: Amount of tokens to sell
            sell_all: If True, sell entire balance
            slippage_pct: Slippage tolerance

        Returns:
            SwapResult
        """
        if not self.account:
            return SwapResult(success=False, error="Wallet not loaded")

        if not self.client.is_connected():
            return SwapResult(success=False, error="Not connected to BSC RPC")

        # Get token balance
        raw_balance, human_balance = self.client.get_token_balance(
            token_address, self.wallet_address
        )

        if human_balance <= 0:
            return SwapResult(success=False, error="No token balance to sell")

        if sell_all:
            amount = human_balance
        elif amount is None or amount > human_balance:
            amount = human_balance

        # Convert to raw amount
        decimals = self.client.get_token_decimals(token_address)
        amount_raw = int(amount * (10 ** decimals))

        # Get quote
        quote = self.client.get_quote(
            token_in=token_address,
            token_out=WBNB,
            amount_in=amount_raw,
            slippage_pct=slippage_pct
        )

        if not quote:
            return SwapResult(success=False, error="Failed to get quote")

        # Execute swap
        return self.client.execute_swap(quote, self.account)

    def get_balances(self) -> Dict:
        """Get wallet balances"""
        if not self.wallet_address:
            return {}

        bnb_balance = self.client.get_bnb_balance(self.wallet_address)
        _, busd_balance = self.client.get_token_balance(BUSD, self.wallet_address)
        _, usdt_balance = self.client.get_token_balance(USDT_BSC, self.wallet_address)
        _, cake_balance = self.client.get_token_balance(CAKE, self.wallet_address)

        return {
            'bnb': bnb_balance,
            'busd': busd_balance,
            'usdt': usdt_balance,
            'cake': cake_balance,
        }


# ==================== INTEGRATION FUNCTIONS ====================

def execute_pancakeswap_swap(private_key: str, token_address: str,
                              amount_bnb: float, action: str = "BUY",
                              slippage_pct: float = 0.5,
                              rpc_url: str = None) -> Dict:
    """
    Execute a PancakeSwap swap - main entry point.

    Args:
        private_key: Wallet private key (hex)
        token_address: Token contract address
        amount_bnb: Amount in BNB (for BUY) or tokens (for SELL)
        action: "BUY" or "SELL"
        slippage_pct: Slippage tolerance
        rpc_url: Custom RPC URL

    Returns:
        Dict with success, tx_hash, amounts, etc.
    """
    try:
        swapper = PancakeSwapper(private_key, rpc_url)

        if not swapper.account:
            return {'success': False, 'error': 'Invalid private key format'}

        if not swapper.client.is_connected():
            return {'success': False, 'error': 'Failed to connect to BSC RPC'}

        if action.upper() == "BUY":
            result = swapper.buy_token(token_address, amount_bnb, slippage_pct)
        else:
            result = swapper.sell_token(token_address, amount_bnb, slippage_pct=slippage_pct)

        return {
            'success': result.success,
            'tx_hash': result.tx_hash,
            'input_amount': result.input_amount,
            'output_amount': result.output_amount,
            'price': result.price,
            'gas_used': result.gas_used,
            'gas_price_gwei': result.gas_price_gwei,
            'total_fee_bnb': result.total_fee_bnb,
            'error': result.error,
            'timestamp': result.timestamp,
            'explorer_url': f"https://bscscan.com/tx/{result.tx_hash}" if result.tx_hash else None
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_pancakeswap_quote(token_in: str, token_out: str, amount: float,
                          is_bnb_input: bool = True) -> Dict:
    """
    Get a PancakeSwap quote without executing.

    Args:
        token_in: Input token address
        token_out: Output token address
        amount: Amount (in BNB if is_bnb_input)
        is_bnb_input: Whether input is BNB

    Returns:
        Quote details
    """
    client = PancakeSwapClient()

    if not client.is_connected():
        return {'success': False, 'error': 'Failed to connect to BSC RPC'}

    if is_bnb_input:
        amount_raw = int(amount * 1e18)
    else:
        decimals = client.get_token_decimals(token_in)
        amount_raw = int(amount * (10 ** decimals))

    quote = client.get_quote(token_in, token_out, amount_raw)

    if not quote:
        return {'success': False, 'error': 'Failed to get quote'}

    out_decimals = client.get_token_decimals(token_out)

    return {
        'success': True,
        'amount_in': amount,
        'amount_out': quote.amount_out / (10 ** out_decimals),
        'amount_out_min': quote.amount_out_min / (10 ** out_decimals),
        'fee_tier': quote.fee_tier / 10000 if quote.fee_tier > 0 else 0.25,  # V2 is 0.25%
        'gas_estimate': quote.gas_estimate,
        'use_v2': quote.use_v2,
    }


def get_bnb_price() -> float:
    """Get current BNB price in USD"""
    try:
        import requests
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "binancecoin", "vs_currencies": "usd"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('binancecoin', {}).get('usd', 0)
    except:
        pass
    return 0
