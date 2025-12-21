"""
DEX Token Sniper - Real-time new token detection
=================================================

Scans for new tokens on:
- Solana (Raydium, Pump.fun)
- Binance new listings

Paper trading mode: detects real tokens, simulates trades
"""

import asyncio
import aiohttp
import json
import os
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import websockets

# Config
DATA_DIR = "data/sniper"
SNIPER_LOG = "data/sniper/sniper_log.json"
DETECTED_TOKENS = "data/sniper/detected_tokens.json"

@dataclass
class NewToken:
    symbol: str
    name: str
    address: str
    chain: str  # solana, eth, bsc
    dex: str    # raydium, pumpfun, uniswap
    price: float
    liquidity: float
    detected_at: str
    market_cap: float = 0
    holders: int = 0
    is_honeypot: bool = False
    risk_score: int = 0  # 0-100, higher = more risky


class DexSniper:
    """Real-time DEX sniper for new tokens"""

    def __init__(self):
        self.detected_tokens: Dict[str, NewToken] = {}
        self.paper_trades: List[dict] = []
        self.running = False

        # API endpoints
        self.dexscreener_api = "https://api.dexscreener.com/latest/dex"
        self.birdeye_api = "https://public-api.birdeye.so"
        self.pumpfun_api = "https://frontend-api.pump.fun"

        os.makedirs(DATA_DIR, exist_ok=True)
        self._load_state()

    def _load_state(self):
        """Load previous state"""
        try:
            if os.path.exists(DETECTED_TOKENS):
                with open(DETECTED_TOKENS, 'r') as f:
                    data = json.load(f)
                    self.detected_tokens = {k: NewToken(**v) for k, v in data.items()}
        except:
            pass

    def _save_state(self):
        """Save current state"""
        try:
            with open(DETECTED_TOKENS, 'w') as f:
                data = {k: v.__dict__ for k, v in self.detected_tokens.items()}
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving state: {e}")

    def log(self, message: str):
        """Log sniper activity"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        try:
            print(f"[SNIPE] {log_line}")
        except UnicodeEncodeError:
            print(f"[SNIPE] {log_line}".encode('ascii', 'replace').decode('ascii'))

        try:
            log_data = []
            if os.path.exists(SNIPER_LOG):
                with open(SNIPER_LOG, 'r') as f:
                    log_data = json.load(f)

            log_data.append({"timestamp": timestamp, "message": message})
            log_data = log_data[-1000:]  # Keep last 1000 entries

            with open(SNIPER_LOG, 'w') as f:
                json.dump(log_data, f, indent=2)
        except:
            pass

    async def scan_dexscreener_new_pairs(self) -> List[NewToken]:
        """Scan DexScreener for new token pairs"""
        new_tokens = []

        try:
            async with aiohttp.ClientSession() as session:
                # Get latest pairs on Solana
                url = f"{self.dexscreener_api}/search?q=sol"
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        pairs = data.get('pairs', [])

                        for pair in pairs[:50]:  # Check top 50
                            # Filter for new pairs (< 24h old)
                            created = pair.get('pairCreatedAt', 0)
                            if created:
                                age_hours = (time.time() * 1000 - created) / (1000 * 60 * 60)

                                if age_hours < 24:  # Less than 24h old
                                    liquidity = float(pair.get('liquidity', {}).get('usd', 0) or 0)

                                    if liquidity > 1000:  # Min $1k liquidity
                                        token = NewToken(
                                            symbol=pair.get('baseToken', {}).get('symbol', 'UNKNOWN'),
                                            name=pair.get('baseToken', {}).get('name', 'Unknown'),
                                            address=pair.get('baseToken', {}).get('address', ''),
                                            chain='solana',
                                            dex=pair.get('dexId', 'unknown'),
                                            price=float(pair.get('priceUsd', 0) or 0),
                                            liquidity=liquidity,
                                            detected_at=datetime.now().isoformat(),
                                            market_cap=float(pair.get('fdv', 0) or 0),
                                            risk_score=self._calculate_risk(pair)
                                        )

                                        if token.address not in self.detected_tokens:
                                            new_tokens.append(token)

        except Exception as e:
            self.log(f"DexScreener scan error: {e}")

        return new_tokens

    async def scan_pumpfun(self) -> List[NewToken]:
        """Scan Pump.fun for new Solana memecoins"""
        new_tokens = []

        try:
            async with aiohttp.ClientSession() as session:
                # Get latest coins from pump.fun
                url = f"{self.pumpfun_api}/coins?offset=0&limit=50&sort=created_timestamp&order=desc"
                headers = {"Accept": "application/json"}

                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        coins = await resp.json()

                        for coin in coins:
                            # Check if recently created
                            created = coin.get('created_timestamp', 0)
                            age_hours = (time.time() - created / 1000) / 3600 if created else 999

                            if age_hours < 12:  # Less than 12h old
                                mc = float(coin.get('usd_market_cap', 0) or 0)

                                if mc > 5000:  # Min $5k market cap
                                    token = NewToken(
                                        symbol=coin.get('symbol', 'UNKNOWN'),
                                        name=coin.get('name', 'Unknown'),
                                        address=coin.get('mint', ''),
                                        chain='solana',
                                        dex='pumpfun',
                                        price=float(coin.get('price', 0) or 0),
                                        liquidity=mc * 0.1,  # Estimate
                                        detected_at=datetime.now().isoformat(),
                                        market_cap=mc,
                                        risk_score=70  # Pump.fun = high risk
                                    )

                                    if token.address not in self.detected_tokens:
                                        new_tokens.append(token)

        except Exception as e:
            self.log(f"Pump.fun scan error: {e}")

        return new_tokens

    async def scan_binance_new_listings(self) -> List[NewToken]:
        """Check for new Binance listings"""
        new_tokens = []

        try:
            # Get all trading pairs
            url = "https://api.binance.com/api/v3/exchangeInfo"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        symbols = data.get('symbols', [])

                        # Check for recently added USDT pairs
                        for sym in symbols:
                            if sym.get('quoteAsset') == 'USDT' and sym.get('status') == 'TRADING':
                                # Check if we already know this token
                                base = sym.get('baseAsset', '')
                                pair = f"{base}/USDT"

                                if pair not in self.detected_tokens:
                                    # Get price
                                    price_url = f"https://api.binance.com/api/v3/ticker/price?symbol={base}USDT"
                                    async with session.get(price_url, timeout=5) as price_resp:
                                        if price_resp.status == 200:
                                            price_data = await price_resp.json()
                                            price = float(price_data.get('price', 0))

                                            if price > 0:
                                                token = NewToken(
                                                    symbol=base,
                                                    name=base,
                                                    address=f"binance:{base}USDT",
                                                    chain='binance',
                                                    dex='binance',
                                                    price=price,
                                                    liquidity=1000000,  # Binance has high liquidity
                                                    detected_at=datetime.now().isoformat(),
                                                    risk_score=20  # Binance = lower risk
                                                )
                                                new_tokens.append(token)

        except Exception as e:
            self.log(f"Binance scan error: {e}")

        return new_tokens

    def _calculate_risk(self, pair_data: dict) -> int:
        """Calculate risk score 0-100"""
        risk = 50  # Base risk

        # Liquidity check
        liquidity = float(pair_data.get('liquidity', {}).get('usd', 0) or 0)
        if liquidity < 10000:
            risk += 30
        elif liquidity < 50000:
            risk += 15
        elif liquidity > 500000:
            risk -= 20

        # Volume check
        volume = float(pair_data.get('volume', {}).get('h24', 0) or 0)
        if volume < 10000:
            risk += 20
        elif volume > 100000:
            risk -= 10

        # Price change check (too good = suspicious)
        price_change = float(pair_data.get('priceChange', {}).get('h24', 0) or 0)
        if price_change > 500:
            risk += 25  # Probably pump & dump
        elif price_change < -50:
            risk += 15  # Dumping

        # Transactions check
        txns = pair_data.get('txns', {}).get('h24', {})
        buys = txns.get('buys', 0)
        sells = txns.get('sells', 0)

        if buys + sells < 100:
            risk += 20  # Low activity
        if sells > buys * 2:
            risk += 15  # More sells than buys

        return min(100, max(0, risk))

    async def check_honeypot(self, token: NewToken) -> bool:
        """Check if token is a honeypot (can't sell)"""
        # Simplified check - in production use honeypot.is API
        if token.risk_score > 80:
            return True
        if token.liquidity < 5000:
            return True
        return False

    def paper_trade_buy(self, token: NewToken, amount_usd: float, portfolio_name: str) -> dict:
        """Simulate buying a new token"""
        if token.price <= 0:
            return {"success": False, "message": "Invalid price"}

        qty = amount_usd / token.price

        trade = {
            "timestamp": datetime.now().isoformat(),
            "action": "SNIPE_BUY",
            "portfolio": portfolio_name,
            "symbol": token.symbol,
            "address": token.address,
            "chain": token.chain,
            "dex": token.dex,
            "price": token.price,
            "quantity": qty,
            "amount_usd": amount_usd,
            "liquidity_at_buy": token.liquidity,
            "market_cap_at_buy": token.market_cap,
            "risk_score": token.risk_score,
            "status": "OPEN",
            "pnl": 0,
            "current_price": token.price
        }

        self.paper_trades.append(trade)
        self._save_trades()

        self.log(f"🟢 SNIPE BUY: {token.symbol} @ ${token.price:.8f} | ${amount_usd} | Risk: {token.risk_score}/100")

        return {"success": True, "trade": trade}

    def paper_trade_sell(self, trade_index: int, current_price: float) -> dict:
        """Simulate selling a sniped token"""
        if trade_index >= len(self.paper_trades):
            return {"success": False, "message": "Trade not found"}

        trade = self.paper_trades[trade_index]

        if trade["status"] != "OPEN":
            return {"success": False, "message": "Trade already closed"}

        pnl = (current_price - trade["price"]) * trade["quantity"]
        pnl_pct = ((current_price / trade["price"]) - 1) * 100

        trade["status"] = "CLOSED"
        trade["sell_price"] = current_price
        trade["sell_timestamp"] = datetime.now().isoformat()
        trade["pnl"] = pnl
        trade["pnl_percent"] = pnl_pct

        self._save_trades()

        self.log(f"🔴 SNIPE SELL: {trade['symbol']} @ ${current_price:.8f} | PnL: ${pnl:+.2f} ({pnl_pct:+.1f}%)")

        return {"success": True, "pnl": pnl, "pnl_percent": pnl_pct}

    async def update_open_positions(self):
        """Update prices for open positions"""
        for trade in self.paper_trades:
            if trade["status"] == "OPEN":
                try:
                    # Get current price from DexScreener
                    if trade["chain"] == "solana" and trade.get("address"):
                        url = f"{self.dexscreener_api}/tokens/{trade['address']}"
                        async with aiohttp.ClientSession() as session:
                            async with session.get(url, timeout=10) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    pairs = data.get('pairs', [])
                                    if pairs:
                                        current_price = float(pairs[0].get('priceUsd', 0) or 0)
                                        if current_price > 0:
                                            trade["current_price"] = current_price
                                            trade["pnl"] = (current_price - trade["price"]) * trade["quantity"]
                                            trade["pnl_percent"] = ((current_price / trade["price"]) - 1) * 100
                except:
                    pass

        self._save_trades()

    def _save_trades(self):
        """Save paper trades"""
        try:
            with open(f"{DATA_DIR}/paper_trades.json", 'w') as f:
                json.dump(self.paper_trades, f, indent=2, default=str)
        except:
            pass

    def _load_trades(self):
        """Load paper trades"""
        try:
            path = f"{DATA_DIR}/paper_trades.json"
            if os.path.exists(path):
                with open(path, 'r') as f:
                    self.paper_trades = json.load(f)
        except:
            pass

    def get_stats(self) -> dict:
        """Get sniper statistics"""
        total_trades = len(self.paper_trades)
        open_trades = len([t for t in self.paper_trades if t["status"] == "OPEN"])
        closed_trades = len([t for t in self.paper_trades if t["status"] == "CLOSED"])

        total_pnl = sum(t.get("pnl", 0) for t in self.paper_trades if t["status"] == "CLOSED")

        winners = len([t for t in self.paper_trades if t["status"] == "CLOSED" and t.get("pnl", 0) > 0])
        win_rate = (winners / closed_trades * 100) if closed_trades > 0 else 0

        return {
            "total_tokens_detected": len(self.detected_tokens),
            "total_trades": total_trades,
            "open_trades": open_trades,
            "closed_trades": closed_trades,
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "winners": winners,
            "losers": closed_trades - winners
        }

    async def run_scanner(self, callback=None):
        """Main scanner loop"""
        self.running = True
        self.log("🎯 DEX Sniper started - scanning for new tokens...")
        self._load_trades()

        scan_count = 0

        while self.running:
            scan_count += 1
            self.log(f"--- Scan #{scan_count} ---")

            # Scan all sources
            new_tokens = []

            # DexScreener (Solana pairs)
            dex_tokens = await self.scan_dexscreener_new_pairs()
            new_tokens.extend(dex_tokens)

            # Pump.fun (Solana memecoins)
            pump_tokens = await self.scan_pumpfun()
            new_tokens.extend(pump_tokens)

            # Process new tokens
            for token in new_tokens:
                # Check honeypot
                is_honeypot = await self.check_honeypot(token)
                token.is_honeypot = is_honeypot

                # Store token
                self.detected_tokens[token.address] = token

                if not is_honeypot and token.risk_score < 75:
                    self.log(f"🆕 NEW TOKEN: {token.symbol} | ${token.price:.8f} | MC: ${token.market_cap:,.0f} | Risk: {token.risk_score}/100 | {token.dex}")

                    # Callback for auto-trading
                    if callback:
                        await callback(token)

            # Update open positions
            await self.update_open_positions()

            # Save state
            self._save_state()

            # Stats
            stats = self.get_stats()
            self.log(f"📊 Detected: {stats['total_tokens_detected']} | Trades: {stats['total_trades']} | Open: {stats['open_trades']} | PnL: ${stats['total_pnl']:+.2f}")

            # Wait before next scan
            await asyncio.sleep(30)  # Scan every 30 seconds

    def stop(self):
        """Stop the scanner"""
        self.running = False
        self.log("🛑 Sniper stopped")


# Standalone runner
async def main():
    sniper = DexSniper()

    async def on_new_token(token: NewToken):
        """Called when a new token is detected"""
        # Auto paper trade on low-risk tokens
        if token.risk_score < 60 and token.liquidity > 10000:
            sniper.paper_trade_buy(token, 100, "Sniper Auto")  # $100 paper trade

    try:
        await sniper.run_scanner(callback=on_new_token)
    except KeyboardInterrupt:
        sniper.stop()


if __name__ == "__main__":
    asyncio.run(main())
