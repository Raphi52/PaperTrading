"""
Token Sniper - Detection de nouveaux tokens et listings
========================================================

Detecte et achete automatiquement les nouveaux tokens:
- Nouveaux listings sur Binance
- Nouvelles paires sur DEX (Uniswap, Raydium)
- Tokens pump.fun (Solana)

ATTENTION: Tres risque! Beaucoup de rugs et scams.

Usage:
    python sniper/token_sniper.py --mode binance
    python sniper/token_sniper.py --mode dex --chain solana
"""
import os
import sys
import time
import json
import asyncio
import aiohttp
import requests
import websocket
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from threading import Thread
from dotenv import load_dotenv

load_dotenv()

# Ajouter le parent path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SniperMode(Enum):
    """Modes de snipe"""
    BINANCE_LISTING = "binance"     # Nouveaux listings Binance
    DEX_NEW_PAIR = "dex"            # Nouvelles paires DEX
    PUMP_FUN = "pump_fun"           # Tokens pump.fun
    RAYDIUM_NEW = "raydium"         # Nouvelles pools Raydium


class TokenSafety(Enum):
    """Niveau de securite d'un token"""
    SAFE = "safe"
    RISKY = "risky"
    DANGEROUS = "dangerous"
    HONEYPOT = "honeypot"
    UNKNOWN = "unknown"


@dataclass
class NewToken:
    """Nouveau token detecte"""
    address: str
    symbol: str
    name: str
    chain: str
    dex: str
    liquidity_usd: float
    initial_price: float
    current_price: float
    holders: int
    created_at: datetime
    safety: TokenSafety
    safety_details: Dict = field(default_factory=dict)
    bought: bool = False
    buy_price: float = 0
    buy_amount: float = 0


@dataclass
class SniperConfig:
    """Configuration du sniper"""
    # General
    enabled: bool = True
    mode: SniperMode = SniperMode.BINANCE_LISTING

    # Filters
    min_liquidity_usd: float = 10000  # $10k minimum
    max_buy_tax: float = 10  # Max 10% buy tax
    max_sell_tax: float = 10  # Max 10% sell tax
    min_holders: int = 10

    # Buy settings
    auto_buy: bool = False  # Dangerous! Set to True to auto-buy
    buy_amount_usd: float = 50  # Amount to snipe
    max_slippage: float = 20  # 20% slippage max

    # Safety
    check_honeypot: bool = True
    check_rugpull: bool = True
    require_renounced: bool = False  # Require ownership renounced
    require_locked_lp: bool = False  # Require LP locked

    # Timing
    buy_delay_seconds: float = 0  # Delay before buying (0 = instant)
    sell_after_seconds: float = 300  # Sell after 5 min (0 = hold)

    # Take profit
    take_profit_percent: float = 100  # 2x = 100%
    stop_loss_percent: float = 50  # -50%


class TokenSafetyChecker:
    """Verifie la securite des tokens"""

    def __init__(self):
        self.honeypot_api = "https://api.honeypot.is/v2/IsHoneypot"
        self.gopluslab_api = "https://api.gopluslabs.io/api/v1/token_security"

    async def check_token(self, address: str, chain: str = "eth") -> Dict:
        """Verifie un token"""
        result = {
            "safety": TokenSafety.UNKNOWN,
            "is_honeypot": False,
            "buy_tax": 0,
            "sell_tax": 0,
            "is_mintable": False,
            "is_proxy": False,
            "owner_renounced": False,
            "lp_locked": False,
            "details": {}
        }

        # Check honeypot.is
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.honeypot_api}?address={address}&chainId=1"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        honeypot_data = data.get("honeypotResult", {})

                        result["is_honeypot"] = honeypot_data.get("isHoneypot", False)
                        result["buy_tax"] = honeypot_data.get("buyTax", 0)
                        result["sell_tax"] = honeypot_data.get("sellTax", 0)

        except Exception as e:
            print(f"Honeypot check error: {e}")

        # Check GoPlus
        try:
            chain_ids = {"eth": "1", "bsc": "56", "base": "8453"}
            chain_id = chain_ids.get(chain, "1")

            async with aiohttp.ClientSession() as session:
                url = f"{self.gopluslab_api}/{chain_id}?contract_addresses={address}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        token_data = data.get("result", {}).get(address.lower(), {})

                        result["is_mintable"] = token_data.get("is_mintable") == "1"
                        result["is_proxy"] = token_data.get("is_proxy") == "1"
                        result["owner_renounced"] = token_data.get("owner_address") == "0x0000000000000000000000000000000000000000"

                        result["details"] = token_data

        except Exception as e:
            print(f"GoPlus check error: {e}")

        # Determine safety level
        if result["is_honeypot"]:
            result["safety"] = TokenSafety.HONEYPOT
        elif result["buy_tax"] > 30 or result["sell_tax"] > 30:
            result["safety"] = TokenSafety.DANGEROUS
        elif result["is_mintable"] or result["buy_tax"] > 10:
            result["safety"] = TokenSafety.RISKY
        elif result["owner_renounced"] and result["buy_tax"] < 5:
            result["safety"] = TokenSafety.SAFE
        else:
            result["safety"] = TokenSafety.RISKY

        return result


class BinanceListingSniper:
    """Detecte les nouveaux listings sur Binance"""

    def __init__(self, config: SniperConfig):
        self.config = config
        self.known_symbols: Set[str] = set()
        self.new_listings: List[NewToken] = []
        self.running = False

        # Load known symbols
        self._load_known_symbols()

    def _load_known_symbols(self):
        """Charge les symboles existants"""
        try:
            url = "https://api.binance.com/api/v3/exchangeInfo"
            response = requests.get(url, timeout=10)
            data = response.json()

            for symbol_data in data.get("symbols", []):
                self.known_symbols.add(symbol_data["symbol"])

            print(f"Loaded {len(self.known_symbols)} existing symbols")

        except Exception as e:
            print(f"Error loading symbols: {e}")

    async def check_new_listings(self) -> List[str]:
        """Verifie les nouveaux listings"""
        new_symbols = []

        try:
            url = "https://api.binance.com/api/v3/exchangeInfo"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()

                    for symbol_data in data.get("symbols", []):
                        symbol = symbol_data["symbol"]

                        if symbol not in self.known_symbols:
                            # New listing!
                            new_symbols.append(symbol)
                            self.known_symbols.add(symbol)
                            print(f"NEW LISTING DETECTED: {symbol}")

        except Exception as e:
            print(f"Error checking listings: {e}")

        return new_symbols

    async def run(self, interval: int = 5):
        """Lance la surveillance"""
        self.running = True
        print("Binance Listing Sniper started")

        while self.running:
            try:
                new_symbols = await self.check_new_listings()

                for symbol in new_symbols:
                    await self._handle_new_listing(symbol)

            except Exception as e:
                print(f"Error: {e}")

            await asyncio.sleep(interval)

    async def _handle_new_listing(self, symbol: str):
        """Gere un nouveau listing"""
        print(f"\n{'='*50}")
        print(f"NEW LISTING: {symbol}")
        print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*50}\n")

        # Get initial price
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()
                    price = float(data.get("price", 0))
                    print(f"Initial price: ${price}")

        except:
            price = 0

        # Create token record
        token = NewToken(
            address="",  # Binance doesn't expose contract
            symbol=symbol.replace("USDT", ""),
            name=symbol,
            chain="binance",
            dex="binance",
            liquidity_usd=0,
            initial_price=price,
            current_price=price,
            holders=0,
            created_at=datetime.now(),
            safety=TokenSafety.UNKNOWN
        )

        self.new_listings.append(token)

        # Auto buy if enabled
        if self.config.auto_buy:
            await self._execute_buy(token)

    async def _execute_buy(self, token: NewToken):
        """Execute un achat"""
        print(f"Would buy {token.symbol} for ${self.config.buy_amount_usd}")
        # TODO: Implement actual buy via Binance API


class DEXSniper:
    """Detecte les nouvelles paires sur DEX"""

    def __init__(self, config: SniperConfig, chain: str = "solana"):
        self.config = config
        self.chain = chain
        self.safety_checker = TokenSafetyChecker()
        self.new_tokens: List[NewToken] = []
        self.running = False

        # WebSocket connections
        self.ws = None

    async def monitor_raydium(self):
        """Monitore les nouvelles pools Raydium"""
        print("Monitoring Raydium for new pools...")

        # Raydium API for new pools
        url = "https://api.raydium.io/v2/ammV3/ammPools"

        known_pools = set()

        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            pools = data.get("data", [])

                            for pool in pools:
                                pool_id = pool.get("id")
                                if pool_id and pool_id not in known_pools:
                                    known_pools.add(pool_id)

                                    # Check if new (created recently)
                                    liquidity = float(pool.get("tvl", 0))

                                    if liquidity >= self.config.min_liquidity_usd:
                                        print(f"New Raydium pool: {pool.get('mintA', {}).get('symbol')}/"
                                              f"{pool.get('mintB', {}).get('symbol')} | TVL: ${liquidity:,.0f}")

            except Exception as e:
                print(f"Raydium monitor error: {e}")

            await asyncio.sleep(10)

    async def monitor_pump_fun(self):
        """Monitore pump.fun pour nouveaux tokens"""
        print("Monitoring pump.fun for new tokens...")

        # pump.fun API (unofficial)
        url = "https://frontend-api.pump.fun/coins/latest"

        seen_tokens = set()

        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            tokens = await response.json()

                            for token in tokens[:20]:
                                mint = token.get("mint")
                                if mint and mint not in seen_tokens:
                                    seen_tokens.add(mint)

                                    symbol = token.get("symbol", "???")
                                    name = token.get("name", "Unknown")
                                    market_cap = float(token.get("usd_market_cap", 0))

                                    print(f"New pump.fun token: {symbol} ({name}) | MC: ${market_cap:,.0f}")

                                    new_token = NewToken(
                                        address=mint,
                                        symbol=symbol,
                                        name=name,
                                        chain="solana",
                                        dex="pump.fun",
                                        liquidity_usd=market_cap,
                                        initial_price=0,
                                        current_price=0,
                                        holders=0,
                                        created_at=datetime.now(),
                                        safety=TokenSafety.RISKY  # pump.fun = risky by default
                                    )

                                    self.new_tokens.append(new_token)

            except Exception as e:
                print(f"pump.fun monitor error: {e}")

            await asyncio.sleep(5)

    async def run(self):
        """Lance le monitoring"""
        self.running = True

        if self.chain == "solana":
            tasks = [
                self.monitor_raydium(),
                self.monitor_pump_fun()
            ]
        else:
            # TODO: Add Uniswap, Pancakeswap monitoring
            tasks = []

        await asyncio.gather(*tasks)


class TokenSniper:
    """Sniper principal"""

    def __init__(self, config: SniperConfig = None):
        self.config = config or SniperConfig()
        self.binance_sniper = None
        self.dex_sniper = None
        self.running = False

        # Telegram alerts
        try:
            from utils.telegram_alerts import telegram
            self.telegram = telegram
        except:
            self.telegram = None

    async def start(self, mode: SniperMode = SniperMode.BINANCE_LISTING,
                    chain: str = "solana"):
        """Demarre le sniper"""
        self.running = True

        print(f"\n{'='*60}")
        print(f"TOKEN SNIPER - Mode: {mode.value}")
        print(f"{'='*60}")
        print(f"Min Liquidity: ${self.config.min_liquidity_usd:,}")
        print(f"Auto Buy: {self.config.auto_buy}")
        print(f"Buy Amount: ${self.config.buy_amount_usd}")
        print(f"{'='*60}\n")

        if mode == SniperMode.BINANCE_LISTING:
            self.binance_sniper = BinanceListingSniper(self.config)
            await self.binance_sniper.run()

        elif mode in [SniperMode.DEX_NEW_PAIR, SniperMode.PUMP_FUN, SniperMode.RAYDIUM_NEW]:
            self.dex_sniper = DEXSniper(self.config, chain)
            await self.dex_sniper.run()

    def stop(self):
        """Arrete le sniper"""
        self.running = False
        if self.binance_sniper:
            self.binance_sniper.running = False
        if self.dex_sniper:
            self.dex_sniper.running = False


# ==================== CLI ====================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Token Sniper")
    parser.add_argument("--mode", type=str, default="binance",
                        choices=["binance", "dex", "pump_fun", "raydium"])
    parser.add_argument("--chain", type=str, default="solana",
                        choices=["solana", "ethereum", "bsc", "base"])
    parser.add_argument("--auto-buy", action="store_true", help="Enable auto-buy (DANGEROUS!)")
    parser.add_argument("--amount", type=float, default=50, help="Buy amount in USD")
    parser.add_argument("--min-liq", type=float, default=10000, help="Minimum liquidity USD")

    args = parser.parse_args()

    # Warning
    if args.auto_buy:
        print("\n" + "!"*60)
        print("WARNING: AUTO-BUY IS ENABLED!")
        print("This will automatically buy new tokens.")
        print("Most new tokens are SCAMS - you WILL lose money!")
        print("!"*60)
        confirm = input("\nType 'I UNDERSTAND' to continue: ")
        if confirm != "I UNDERSTAND":
            print("Aborted.")
            return

    config = SniperConfig(
        mode=SniperMode(args.mode),
        auto_buy=args.auto_buy,
        buy_amount_usd=args.amount,
        min_liquidity_usd=args.min_liq
    )

    sniper = TokenSniper(config)

    try:
        asyncio.run(sniper.start(
            mode=SniperMode(args.mode),
            chain=args.chain
        ))
    except KeyboardInterrupt:
        print("\nSniper stopped")
        sniper.stop()


if __name__ == "__main__":
    main()
