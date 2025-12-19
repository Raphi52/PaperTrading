"""
DEX Trading - Trading sur exchanges decentralises
==================================================

Supporte:
- Solana: Jupiter, Raydium
- Ethereum/Base: Uniswap, 1inch
- BSC: PancakeSwap

Usage:
    from core.dex_trading import DEXTrader
    trader = DEXTrader(chain="solana", private_key="...")
    trader.swap("SOL", "BONK", amount=1.0)
"""
import os
import json
import base64
import asyncio
import aiohttp
import requests
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from dotenv import load_dotenv

load_dotenv()


class Chain(Enum):
    """Chains supportees"""
    SOLANA = "solana"
    ETHEREUM = "ethereum"
    BASE = "base"
    BSC = "bsc"
    ARBITRUM = "arbitrum"


@dataclass
class Token:
    """Information sur un token"""
    address: str
    symbol: str
    decimals: int
    name: str = ""
    price_usd: float = 0
    chain: Chain = Chain.SOLANA


@dataclass
class SwapQuote:
    """Quote pour un swap"""
    input_token: Token
    output_token: Token
    input_amount: float
    output_amount: float
    price_impact: float
    route: List[str]
    estimated_gas: float
    minimum_received: float


@dataclass
class SwapResult:
    """Resultat d'un swap"""
    success: bool
    tx_hash: str
    input_amount: float
    output_amount: float
    price: float
    gas_used: float
    error: str = ""


# ==================== SOLANA / JUPITER ====================

class JupiterTrader:
    """Trading via Jupiter (Solana)"""

    def __init__(self, private_key: str = None):
        self.private_key = private_key or os.getenv("SOLANA_PRIVATE_KEY", "")
        self.api_base = "https://quote-api.jup.ag/v6"

        # Token addresses courants
        self.tokens = {
            "SOL": "So11111111111111111111111111111111111111112",
            "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
            "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
            "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
            "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
        }

    async def get_token_price(self, token_address: str) -> float:
        """Recupere le prix d'un token"""
        try:
            url = f"https://price.jup.ag/v4/price?ids={token_address}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()
                    return float(data.get("data", {}).get(token_address, {}).get("price", 0))
        except:
            return 0

    async def get_quote(self, input_mint: str, output_mint: str,
                        amount: float, slippage_bps: int = 50) -> Optional[SwapQuote]:
        """
        Obtient une quote pour un swap

        Args:
            input_mint: Adresse du token d'entree
            output_mint: Adresse du token de sortie
            amount: Montant en tokens (pas en lamports)
            slippage_bps: Slippage en basis points (50 = 0.5%)
        """
        try:
            # Get decimals
            input_decimals = 9 if input_mint == self.tokens["SOL"] else 6
            amount_raw = int(amount * (10 ** input_decimals))

            url = f"{self.api_base}/quote"
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount_raw,
                "slippageBps": slippage_bps
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()

                    output_amount = float(data.get("outAmount", 0)) / (10 ** 6)  # Assuming 6 decimals
                    price_impact = float(data.get("priceImpactPct", 0))

                    return SwapQuote(
                        input_token=Token(input_mint, "", input_decimals),
                        output_token=Token(output_mint, "", 6),
                        input_amount=amount,
                        output_amount=output_amount,
                        price_impact=price_impact,
                        route=[r.get("label", "") for r in data.get("routePlan", [])],
                        estimated_gas=0.000005,  # ~5000 lamports
                        minimum_received=output_amount * (1 - slippage_bps / 10000)
                    )

        except Exception as e:
            print(f"Quote error: {e}")
            return None

    async def swap(self, input_mint: str, output_mint: str, amount: float,
                   slippage_bps: int = 50) -> SwapResult:
        """
        Execute un swap via Jupiter

        ATTENTION: Necessite une cle privee valide!
        """
        if not self.private_key:
            return SwapResult(
                success=False,
                tx_hash="",
                input_amount=amount,
                output_amount=0,
                price=0,
                gas_used=0,
                error="No private key configured"
            )

        try:
            # Get quote first
            quote = await self.get_quote(input_mint, output_mint, amount, slippage_bps)
            if not quote:
                return SwapResult(False, "", amount, 0, 0, 0, "Failed to get quote")

            # Get swap transaction
            url = f"{self.api_base}/swap"
            payload = {
                "quoteResponse": quote.__dict__,  # Simplified
                "userPublicKey": "",  # Would need to derive from private key
                "wrapAndUnwrapSol": True
            }

            # In a real implementation, you would:
            # 1. Get the swap transaction from Jupiter
            # 2. Sign it with the private key
            # 3. Send it to the Solana network

            print(f"Would swap {amount} {input_mint[:8]}... for ~{quote.output_amount} {output_mint[:8]}...")

            return SwapResult(
                success=True,
                tx_hash="simulation",
                input_amount=amount,
                output_amount=quote.output_amount,
                price=quote.output_amount / amount if amount > 0 else 0,
                gas_used=0.000005
            )

        except Exception as e:
            return SwapResult(False, "", amount, 0, 0, 0, str(e))

    def get_token_address(self, symbol: str) -> str:
        """Retourne l'adresse d'un token par son symbole"""
        return self.tokens.get(symbol.upper(), "")


# ==================== ETHEREUM / UNISWAP ====================

class UniswapTrader:
    """Trading via Uniswap (Ethereum/Base)"""

    def __init__(self, private_key: str = None, chain: Chain = Chain.ETHEREUM):
        self.private_key = private_key or os.getenv("ETH_PRIVATE_KEY", "")
        self.chain = chain

        # RPC URLs
        self.rpc_urls = {
            Chain.ETHEREUM: os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com"),
            Chain.BASE: os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
            Chain.ARBITRUM: os.getenv("ARB_RPC_URL", "https://arb1.arbitrum.io/rpc"),
        }

        # Router addresses
        self.routers = {
            Chain.ETHEREUM: "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",  # Uniswap V3
            Chain.BASE: "0x2626664c2603336E57B271c5C0b26F421741e481",  # Uniswap on Base
        }

        # Token addresses
        self.tokens = {
            Chain.ETHEREUM: {
                "ETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
                "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                "PEPE": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
            },
            Chain.BASE: {
                "ETH": "0x4200000000000000000000000000000000000006",  # WETH on Base
                "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            }
        }

    async def get_quote_1inch(self, from_token: str, to_token: str,
                              amount: float, chain_id: int = 1) -> Optional[SwapQuote]:
        """Obtient une quote via 1inch API"""
        try:
            # Convert to wei
            amount_wei = int(amount * 1e18)

            url = f"https://api.1inch.dev/swap/v5.2/{chain_id}/quote"
            params = {
                "src": from_token,
                "dst": to_token,
                "amount": str(amount_wei)
            }
            headers = {
                "Authorization": f"Bearer {os.getenv('ONEINCH_API_KEY', '')}"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()

                    output_amount = float(data.get("toAmount", 0)) / 1e18

                    return SwapQuote(
                        input_token=Token(from_token, "", 18),
                        output_token=Token(to_token, "", 18),
                        input_amount=amount,
                        output_amount=output_amount,
                        price_impact=0,
                        route=["1inch"],
                        estimated_gas=float(data.get("gas", 200000)),
                        minimum_received=output_amount * 0.99
                    )

        except Exception as e:
            print(f"1inch quote error: {e}")
            return None

    async def swap(self, from_token: str, to_token: str, amount: float,
                   slippage: float = 1.0) -> SwapResult:
        """Execute un swap (simulation)"""
        if not self.private_key:
            return SwapResult(False, "", amount, 0, 0, 0, "No private key")

        quote = await self.get_quote_1inch(from_token, to_token, amount)
        if not quote:
            return SwapResult(False, "", amount, 0, 0, 0, "Failed to get quote")

        print(f"Would swap {amount} for ~{quote.output_amount}")

        return SwapResult(
            success=True,
            tx_hash="simulation",
            input_amount=amount,
            output_amount=quote.output_amount,
            price=quote.output_amount / amount if amount > 0 else 0,
            gas_used=quote.estimated_gas
        )


# ==================== DEX TRADER UNIFIE ====================

class DEXTrader:
    """Interface unifiee pour le trading DEX"""

    def __init__(self, chain: Chain = Chain.SOLANA, private_key: str = None):
        self.chain = chain

        if chain == Chain.SOLANA:
            self.trader = JupiterTrader(private_key)
        else:
            self.trader = UniswapTrader(private_key, chain)

    async def get_price(self, token: str) -> float:
        """Recupere le prix d'un token"""
        if isinstance(self.trader, JupiterTrader):
            address = self.trader.get_token_address(token)
            if address:
                return await self.trader.get_token_price(address)
        return 0

    async def get_quote(self, from_token: str, to_token: str, amount: float) -> Optional[SwapQuote]:
        """Obtient une quote"""
        if isinstance(self.trader, JupiterTrader):
            from_addr = self.trader.get_token_address(from_token)
            to_addr = self.trader.get_token_address(to_token)
            if from_addr and to_addr:
                return await self.trader.get_quote(from_addr, to_addr, amount)
        else:
            from_addr = self.trader.tokens.get(self.chain, {}).get(from_token, from_token)
            to_addr = self.trader.tokens.get(self.chain, {}).get(to_token, to_token)
            return await self.trader.get_quote_1inch(from_addr, to_addr, amount)

        return None

    async def swap(self, from_token: str, to_token: str, amount: float,
                   slippage: float = 1.0) -> SwapResult:
        """Execute un swap"""
        if isinstance(self.trader, JupiterTrader):
            from_addr = self.trader.get_token_address(from_token)
            to_addr = self.trader.get_token_address(to_token)
            if from_addr and to_addr:
                return await self.trader.swap(from_addr, to_addr, amount, int(slippage * 100))
        else:
            from_addr = self.trader.tokens.get(self.chain, {}).get(from_token, from_token)
            to_addr = self.trader.tokens.get(self.chain, {}).get(to_token, to_token)
            return await self.trader.swap(from_addr, to_addr, amount, slippage)

        return SwapResult(False, "", amount, 0, 0, 0, "Unknown token")

    async def buy(self, token: str, amount_usd: float) -> SwapResult:
        """Achete un token avec USDC/USDT"""
        base_token = "USDC" if self.chain != Chain.SOLANA else "USDC"
        return await self.swap(base_token, token, amount_usd)

    async def sell(self, token: str, amount: float) -> SwapResult:
        """Vend un token pour USDC/USDT"""
        base_token = "USDC"
        return await self.swap(token, base_token, amount)


# ==================== EXAMPLE USAGE ====================

async def example():
    """Exemple d'utilisation"""
    print("DEX Trading Example")
    print("=" * 50)

    # Solana / Jupiter
    print("\n--- SOLANA (Jupiter) ---")
    sol_trader = DEXTrader(Chain.SOLANA)

    quote = await sol_trader.get_quote("SOL", "BONK", 1.0)
    if quote:
        print(f"1 SOL = {quote.output_amount:,.0f} BONK")
        print(f"Price impact: {quote.price_impact:.2f}%")

    # Ethereum / Uniswap
    print("\n--- ETHEREUM (1inch) ---")
    eth_trader = DEXTrader(Chain.ETHEREUM)

    quote = await eth_trader.get_quote("ETH", "USDC", 1.0)
    if quote:
        print(f"1 ETH = {quote.output_amount:,.2f} USDC")


if __name__ == "__main__":
    asyncio.run(example())
