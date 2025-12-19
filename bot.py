"""
Paper Trading Bot - Runs independently of the dashboard
=========================================================
This script runs the trading engine in the background.
The dashboard is just for viewing results.
"""

import json
import os
import time
import requests
import pandas as pd
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

# Config
PORTFOLIOS_FILE = "data/portfolios.json"
LOG_FILE = "data/bot_log.txt"
SCAN_INTERVAL = 60  # seconds between scans

# Strategies
STRATEGIES = {
    # Manual
    "manuel": {"auto": False},
    "manual": {"auto": False},

    # Confluence strategies
    "confluence_strict": {"auto": True, "buy_on": ["STRONG_BUY"], "sell_on": ["STRONG_SELL"]},
    "confluence_normal": {"auto": True, "buy_on": ["BUY", "STRONG_BUY"], "sell_on": ["SELL", "STRONG_SELL"]},

    # Classic strategies
    "conservative": {"auto": True, "buy_on": ["STRONG_BUY"], "sell_on": ["STRONG_SELL"]},
    "aggressive": {"auto": True, "buy_on": ["BUY", "STRONG_BUY"], "sell_on": ["SELL", "STRONG_SELL"]},
    "god_mode_only": {"auto": True, "buy_on": ["GOD_MODE_BUY"], "sell_on": []},
    "hodl": {"auto": True, "buy_on": ["ALWAYS_FIRST"], "sell_on": []},

    # Indicator-based
    "rsi_strategy": {"auto": True, "use_rsi": True},
    "dca_fear": {"auto": True, "use_fear_greed": True},

    # DEGEN STRATEGIES
    "degen_scalp": {"auto": True, "use_degen": True, "mode": "scalping"},
    "degen_momentum": {"auto": True, "use_degen": True, "mode": "momentum"},
    "degen_hybrid": {"auto": True, "use_degen": True, "mode": "hybrid"},
    "degen_full": {"auto": True, "use_degen": True, "mode": "hybrid", "risk": 20},

    # SNIPER STRATEGIES - New token hunting
    "sniper_safe": {"auto": True, "use_sniper": True, "max_risk": 50, "min_liquidity": 50000},
    "sniper_degen": {"auto": True, "use_sniper": True, "max_risk": 75, "min_liquidity": 10000},
    "sniper_yolo": {"auto": True, "use_sniper": True, "max_risk": 90, "min_liquidity": 5000},
}


def log(message: str):
    """Log to console and file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)

    try:
        os.makedirs("data", exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except:
        pass


def load_portfolios() -> dict:
    """Load portfolios from JSON"""
    try:
        if os.path.exists(PORTFOLIOS_FILE):
            with open(PORTFOLIOS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('portfolios', {}), data.get('counter', 0)
    except Exception as e:
        log(f"Error loading portfolios: {e}")
    return {}, 0


def save_portfolios(portfolios: dict, counter: int):
    """Save portfolios to JSON"""
    try:
        os.makedirs("data", exist_ok=True)
        data = {'portfolios': portfolios, 'counter': counter}
        with open(PORTFOLIOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        log(f"Error saving portfolios: {e}")


def analyze_crypto(symbol: str) -> dict:
    """Analyze a crypto - returns price, RSI, signal"""
    try:
        # Fetch OHLCV from Binance
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.replace('/', '')}&interval=1h&limit=100"
        response = requests.get(url, timeout=10)
        data = response.json()

        if not data or len(data) < 50:
            return None

        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                          'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                                          'taker_buy_quote', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)

        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]

        # Calculate EMAs
        ema_12 = df['close'].ewm(span=12).mean().iloc[-1]
        ema_26 = df['close'].ewm(span=26).mean().iloc[-1]

        # Current price
        current_price = df['close'].iloc[-1]

        # Determine signal
        signal = "HOLD"
        if current_rsi < 30 and ema_12 > ema_26:
            signal = "STRONG_BUY"
        elif current_rsi < 35:
            signal = "BUY"
        elif current_rsi > 70 and ema_12 < ema_26:
            signal = "STRONG_SELL"
        elif current_rsi > 65:
            signal = "SELL"

        return {
            'symbol': symbol,
            'price': current_price,
            'rsi': current_rsi,
            'ema_12': ema_12,
            'ema_26': ema_26,
            'signal': signal,
            'trend': 'bullish' if ema_12 > ema_26 else 'bearish'
        }

    except Exception as e:
        log(f"Error analyzing {symbol}: {e}")
        return None


def execute_trade(portfolio: dict, action: str, symbol: str, price: float, amount_usdt: float = None) -> dict:
    """Execute a paper trade"""
    asset = symbol.split('/')[0]
    timestamp = datetime.now().isoformat()

    if action == 'BUY':
        if amount_usdt is None:
            allocation = portfolio['config'].get('allocation_percent', 10)
            amount_usdt = portfolio['balance']['USDT'] * (allocation / 100)

        if portfolio['balance']['USDT'] >= amount_usdt and amount_usdt > 10:
            qty = amount_usdt / price
            portfolio['balance']['USDT'] -= amount_usdt
            portfolio['balance'][asset] = portfolio['balance'].get(asset, 0) + qty

            # Track position
            if symbol not in portfolio['positions']:
                portfolio['positions'][symbol] = {
                    'entry_price': price,
                    'quantity': qty,
                    'entry_time': timestamp
                }
            else:
                # Average down
                pos = portfolio['positions'][symbol]
                total_qty = pos['quantity'] + qty
                avg_price = (pos['entry_price'] * pos['quantity'] + price * qty) / total_qty
                portfolio['positions'][symbol] = {
                    'entry_price': avg_price,
                    'quantity': total_qty,
                    'entry_time': pos['entry_time']
                }

            trade = {
                'timestamp': timestamp,
                'action': 'BUY',
                'symbol': symbol,
                'price': price,
                'quantity': qty,
                'amount_usdt': amount_usdt,
                'pnl': 0
            }
            portfolio['trades'].append(trade)
            return {'success': True, 'message': f"BUY {qty:.6f} {asset} @ ${price:,.2f}"}

    elif action == 'SELL':
        if portfolio['balance'].get(asset, 0) > 0:
            qty = portfolio['balance'][asset]
            sell_value = qty * price

            # Calculate PnL
            pnl = 0
            if symbol in portfolio['positions']:
                entry_price = portfolio['positions'][symbol]['entry_price']
                pnl = (price - entry_price) * qty
                del portfolio['positions'][symbol]

            portfolio['balance']['USDT'] += sell_value
            portfolio['balance'][asset] = 0

            trade = {
                'timestamp': timestamp,
                'action': 'SELL',
                'symbol': symbol,
                'price': price,
                'quantity': qty,
                'amount_usdt': sell_value,
                'pnl': pnl
            }
            portfolio['trades'].append(trade)
            return {'success': True, 'message': f"SELL {qty:.6f} {asset} @ ${price:,.2f} | PnL: ${pnl:+,.2f}"}

    return {'success': False, 'message': "No action"}


def should_trade(portfolio: dict, signal: str, symbol: str, rsi: float) -> str:
    """Determine if we should trade based on strategy"""
    strategy_id = portfolio.get('strategy_id', 'manuel')
    strategy = STRATEGIES.get(strategy_id, {})
    config = portfolio['config']

    if not strategy.get('auto', False):
        return None

    if not config.get('auto_trade', True):
        return None

    # Check max positions
    if len(portfolio['positions']) >= config.get('max_positions', 3):
        if symbol not in portfolio['positions']:
            return None

    asset = symbol.split('/')[0]

    # RSI Strategy
    if strategy.get('use_rsi', False):
        rsi_oversold = config.get('rsi_oversold', 30)
        rsi_overbought = config.get('rsi_overbought', 70)

        if rsi < rsi_oversold and portfolio['balance']['USDT'] > 100:
            return 'BUY'
        elif rsi > rsi_overbought and portfolio['balance'].get(asset, 0) > 0:
            return 'SELL'
        return None

    # HODL Strategy
    if strategy.get('buy_on') == ["ALWAYS_FIRST"]:
        if len(portfolio['trades']) == 0 and portfolio['balance']['USDT'] > 100:
            return 'BUY'
        return None

    # Signal-based strategies
    buy_signals = strategy.get('buy_on', [])
    sell_signals = strategy.get('sell_on', [])

    if signal in buy_signals and portfolio['balance']['USDT'] > 100:
        return 'BUY'
    elif signal in sell_signals and portfolio['balance'].get(asset, 0) > 0:
        return 'SELL'

    return None


def run_engine(portfolios: dict) -> list:
    """Run the trading engine for all portfolios"""
    results = []
    analyzed = {}

    # Get all unique cryptos
    all_cryptos = set()
    for p in portfolios.values():
        if p.get('active', True):
            all_cryptos.update(p['config'].get('cryptos', []))

    log(f"Scanning {len(all_cryptos)} cryptos for {len([p for p in portfolios.values() if p.get('active')])} active portfolios...")

    # Analyze each crypto once
    for crypto in all_cryptos:
        analysis = analyze_crypto(crypto)
        if analysis:
            analyzed[crypto] = analysis
            log(f"  {crypto}: ${analysis['price']:,.2f} | RSI {analysis['rsi']:.1f} | {analysis['signal']}")

    # Check each portfolio
    for port_id, portfolio in portfolios.items():
        if not portfolio.get('active', True):
            continue

        for crypto in portfolio['config'].get('cryptos', []):
            if crypto not in analyzed:
                continue

            analysis = analyzed[crypto]
            action = should_trade(portfolio, analysis['signal'], crypto, analysis['rsi'])

            if action:
                result = execute_trade(portfolio, action, crypto, analysis['price'])
                if result['success']:
                    log(f"  >> {portfolio['name']}: {result['message']}")
                    results.append({
                        'portfolio': portfolio['name'],
                        'crypto': crypto,
                        'action': action,
                        'price': analysis['price'],
                        'message': result['message']
                    })

    return results


def start_dashboard(open_browser: bool = True):
    """Start unified Streamlit dashboard in background"""
    try:
        log("Starting unified dashboard on port 8501...")
        subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py",
             "--server.address", "0.0.0.0",
             "--server.port", "8501",
             "--server.headless", "true",
             "--browser.gatherUsageStats", "false"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        log("Dashboard started: http://localhost:8501")
        log("Features: Dashboard | Degen Mode | Scanner | Portfolios | Settings")

        # Open browser after a short delay
        if open_browser:
            time.sleep(2)
            webbrowser.open("http://localhost:8501")
            log("Browser opened automatically")
    except Exception as e:
        log(f"Could not start dashboard: {e}")


def scan_new_tokens() -> list:
    """Scan for new tokens on DEX (Solana)"""
    new_tokens = []

    try:
        # Scan DexScreener for new Solana pairs
        url = "https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            pairs = data.get('pairs', [])

            for pair in pairs[:30]:
                created = pair.get('pairCreatedAt', 0)
                if created:
                    age_hours = (time.time() * 1000 - created) / (1000 * 60 * 60)

                    if age_hours < 24:  # Less than 24h old
                        liquidity = float(pair.get('liquidity', {}).get('usd', 0) or 0)
                        volume = float(pair.get('volume', {}).get('h24', 0) or 0)

                        # Calculate risk score
                        risk = 50
                        if liquidity < 10000: risk += 30
                        elif liquidity > 100000: risk -= 20
                        if volume < 10000: risk += 20
                        elif volume > 50000: risk -= 10

                        price_change = float(pair.get('priceChange', {}).get('h24', 0) or 0)
                        if price_change > 500: risk += 25

                        risk = min(100, max(0, risk))

                        token = {
                            'symbol': pair.get('baseToken', {}).get('symbol', 'UNKNOWN'),
                            'name': pair.get('baseToken', {}).get('name', 'Unknown'),
                            'address': pair.get('baseToken', {}).get('address', ''),
                            'price': float(pair.get('priceUsd', 0) or 0),
                            'liquidity': liquidity,
                            'volume_24h': volume,
                            'market_cap': float(pair.get('fdv', 0) or 0),
                            'age_hours': age_hours,
                            'risk_score': risk,
                            'dex': pair.get('dexId', 'unknown'),
                            'chain': 'solana'
                        }
                        new_tokens.append(token)

        # Scan Pump.fun
        try:
            pump_url = "https://frontend-api.pump.fun/coins?offset=0&limit=20&sort=created_timestamp&order=desc"
            response = requests.get(pump_url, timeout=10, headers={"Accept": "application/json"})
            if response.status_code == 200:
                coins = response.json()
                for coin in coins:
                    created = coin.get('created_timestamp', 0)
                    age_hours = (time.time() - created / 1000) / 3600 if created else 999

                    if age_hours < 12:
                        mc = float(coin.get('usd_market_cap', 0) or 0)
                        if mc > 5000:
                            token = {
                                'symbol': coin.get('symbol', 'UNKNOWN'),
                                'name': coin.get('name', 'Unknown'),
                                'address': coin.get('mint', ''),
                                'price': float(coin.get('price', 0) or 0),
                                'liquidity': mc * 0.1,
                                'volume_24h': 0,
                                'market_cap': mc,
                                'age_hours': age_hours,
                                'risk_score': 70,  # Pump.fun = higher risk
                                'dex': 'pumpfun',
                                'chain': 'solana'
                            }
                            new_tokens.append(token)
        except:
            pass

    except Exception as e:
        log(f"Error scanning new tokens: {e}")

    return new_tokens


def run_sniper_engine(portfolios: dict, new_tokens: list) -> list:
    """Run sniper strategy on new tokens"""
    results = []

    for port_id, portfolio in portfolios.items():
        if not portfolio.get('active', True):
            continue

        strategy_id = portfolio.get('strategy_id', '')
        strategy = STRATEGIES.get(strategy_id, {})

        if not strategy.get('use_sniper', False):
            continue

        config = portfolio['config']
        max_risk = config.get('max_risk', 75)
        min_liquidity = config.get('min_liquidity', 10000)
        allocation = config.get('allocation_percent', 10)
        max_positions = config.get('max_positions', 10)
        take_profit = config.get('take_profit', 100)  # %
        stop_loss = config.get('stop_loss', 50)  # %

        # Check max positions
        if len(portfolio['positions']) >= max_positions:
            continue

        # Check existing positions for TP/SL
        for symbol, pos in list(portfolio['positions'].items()):
            if pos.get('is_snipe'):
                # Find current price
                current_price = pos.get('current_price', pos['entry_price'])
                for token in new_tokens:
                    if token['address'] == pos.get('address'):
                        current_price = token['price']
                        break

                if current_price > 0:
                    pnl_pct = ((current_price / pos['entry_price']) - 1) * 100

                    # Take profit
                    if pnl_pct >= take_profit:
                        result = execute_trade(portfolio, 'SELL', symbol, current_price)
                        if result['success']:
                            log(f"🎯 SNIPER TP: {symbol} +{pnl_pct:.1f}%")
                            results.append({'portfolio': portfolio['name'], 'action': 'SNIPE_SELL_TP', 'symbol': symbol})

                    # Stop loss
                    elif pnl_pct <= -stop_loss:
                        result = execute_trade(portfolio, 'SELL', symbol, current_price)
                        if result['success']:
                            log(f"🎯 SNIPER SL: {symbol} {pnl_pct:.1f}%")
                            results.append({'portfolio': portfolio['name'], 'action': 'SNIPE_SELL_SL', 'symbol': symbol})

        # Look for new snipes
        for token in new_tokens:
            if token['risk_score'] > max_risk:
                continue
            if token['liquidity'] < min_liquidity:
                continue
            if token['price'] <= 0:
                continue

            # Check if we already have this token
            symbol = f"{token['symbol']}/USDT"
            if symbol in portfolio['positions']:
                continue
            if token['address'] in [p.get('address') for p in portfolio['positions'].values()]:
                continue

            # Check balance
            if portfolio['balance']['USDT'] < 100:
                continue

            # Calculate amount
            amount_usdt = portfolio['balance']['USDT'] * (allocation / 100)
            amount_usdt = min(amount_usdt, 500)  # Max $500 per snipe

            if amount_usdt < 50:
                continue

            # Execute snipe buy
            qty = amount_usdt / token['price']
            portfolio['balance']['USDT'] -= amount_usdt

            asset = token['symbol']
            portfolio['balance'][asset] = portfolio['balance'].get(asset, 0) + qty

            portfolio['positions'][symbol] = {
                'entry_price': token['price'],
                'quantity': qty,
                'entry_time': datetime.now().isoformat(),
                'is_snipe': True,
                'address': token['address'],
                'chain': token['chain'],
                'dex': token['dex'],
                'risk_score': token['risk_score'],
                'liquidity_at_entry': token['liquidity']
            }

            trade = {
                'timestamp': datetime.now().isoformat(),
                'action': 'SNIPE_BUY',
                'symbol': symbol,
                'price': token['price'],
                'quantity': qty,
                'amount_usdt': amount_usdt,
                'pnl': 0,
                'token_address': token['address'],
                'chain': token['chain'],
                'dex': token['dex'],
                'risk_score': token['risk_score'],
                'market_cap': token['market_cap'],
                'liquidity': token['liquidity']
            }
            portfolio['trades'].append(trade)

            log(f"🎯 SNIPE BUY: {token['symbol']} @ ${token['price']:.8f} | MC: ${token['market_cap']:,.0f} | Risk: {token['risk_score']}/100 | {portfolio['name']}")
            results.append({'portfolio': portfolio['name'], 'action': 'SNIPE_BUY', 'symbol': symbol, 'token': token})

    return results


def main():
    """Main bot loop - All-in-one trading engine"""
    print("\n" + "=" * 60)
    print("  🚀 TRADING BOT - FULL DEGEN EDITION")
    print("  Dashboard: http://localhost:8501")
    print("  Ctrl+C to stop")
    print("=" * 60)
    print("  Strategies: Conservative | Aggressive | RSI | Confluence")
    print("  Degen: Scalping | Momentum | Hybrid | Full Degen")
    print("  Sniper: Safe | Degen | YOLO (New Token Hunter)")
    print("=" * 60 + "\n")

    # Start dashboard
    start_dashboard()

    # Load portfolios
    portfolios, counter = load_portfolios()

    if not portfolios:
        log("No portfolios found! Run the dashboard first to create portfolios.")
        return

    # Count portfolio types
    sniper_count = len([p for p in portfolios.values() if STRATEGIES.get(p.get('strategy_id', ''), {}).get('use_sniper')])
    classic_count = len(portfolios) - sniper_count

    log(f"Loaded {len(portfolios)} portfolios ({classic_count} classic, {sniper_count} sniper)")
    for pid, p in portfolios.items():
        status = "✅" if p.get('active', True) else "⏸️"
        strategy = p.get('strategy_id', 'manual')
        is_sniper = "🎯" if STRATEGIES.get(strategy, {}).get('use_sniper') else ""
        log(f"  {status} {is_sniper} {p['name']} [{strategy}]")

    print("=" * 60)
    log(f"Starting unified bot loop (scan every {SCAN_INTERVAL}s)...")
    print("=" * 60)

    scan_count = 0
    sniper_tokens_seen = set()

    try:
        while True:
            scan_count += 1
            log(f"\n{'='*20} SCAN #{scan_count} {'='*20}")

            # Reload portfolios
            portfolios, counter = load_portfolios()

            total_results = []

            # 1. Classic trading engine (existing cryptos)
            log("📊 Scanning existing cryptos...")
            classic_results = run_engine(portfolios)
            total_results.extend(classic_results)

            # 2. Sniper engine (new tokens)
            log("🎯 Scanning for new tokens...")
            new_tokens = scan_new_tokens()

            # Filter out already seen tokens
            fresh_tokens = [t for t in new_tokens if t['address'] not in sniper_tokens_seen]
            for t in fresh_tokens:
                sniper_tokens_seen.add(t['address'])
                log(f"  🆕 {t['symbol']} | ${t['price']:.8f} | MC: ${t['market_cap']:,.0f} | Risk: {t['risk_score']}/100 | {t['dex']}")

            sniper_results = run_sniper_engine(portfolios, new_tokens)
            total_results.extend(sniper_results)

            # Save if any changes
            if total_results:
                save_portfolios(portfolios, counter)
                log(f"💾 Saved {len(total_results)} trades")

            # Summary
            log(f"📈 Classic: {len(classic_results)} trades | 🎯 Sniper: {len(sniper_results)} trades | 🆕 New tokens: {len(fresh_tokens)}")

            # Wait
            log(f"⏳ Next scan in {SCAN_INTERVAL}s...")
            time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        log("\n🛑 Bot stopped by user")
        save_portfolios(portfolios, counter)
        log("💾 Final state saved")


if __name__ == "__main__":
    main()
