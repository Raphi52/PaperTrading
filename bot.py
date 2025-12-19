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
from datetime import datetime
from pathlib import Path

# Config
PORTFOLIOS_FILE = "data/portfolios.json"
LOG_FILE = "data/bot_log.txt"
SCAN_INTERVAL = 60  # seconds between scans

# Strategies
STRATEGIES = {
    "manuel": {"auto": False},
    "confluence_strict": {"auto": True, "buy_on": ["STRONG_BUY"], "sell_on": ["STRONG_SELL"]},
    "confluence_normal": {"auto": True, "buy_on": ["BUY", "STRONG_BUY"], "sell_on": ["SELL", "STRONG_SELL"]},
    "god_mode_only": {"auto": True, "buy_on": ["GOD_MODE_BUY"], "sell_on": []},
    "dca_fear": {"auto": True, "use_fear_greed": True},
    "rsi_strategy": {"auto": True, "use_rsi": True},
    "aggressive": {"auto": True, "buy_on": ["BUY", "STRONG_BUY"], "sell_on": ["SELL", "STRONG_SELL"]},
    "conservative": {"auto": True, "buy_on": ["STRONG_BUY"], "sell_on": ["STRONG_SELL"]},
    "hodl": {"auto": True, "buy_on": ["ALWAYS_FIRST"], "sell_on": []}
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


def main():
    """Main bot loop"""
    print("=" * 60)
    print("  PAPER TRADING BOT")
    print("  Ctrl+C to stop")
    print("=" * 60)

    # Load portfolios
    portfolios, counter = load_portfolios()

    if not portfolios:
        log("No portfolios found! Run the dashboard first to create portfolios.")
        return

    log(f"Loaded {len(portfolios)} portfolios")
    for pid, p in portfolios.items():
        status = "ACTIVE" if p.get('active', True) else "PAUSED"
        cryptos = ", ".join(p['config'].get('cryptos', []))
        log(f"  [{status}] {p['name']}: {cryptos}")

    print("=" * 60)
    log(f"Starting bot loop (scan every {SCAN_INTERVAL}s)...")
    print("=" * 60)

    scan_count = 0

    try:
        while True:
            scan_count += 1
            log(f"\n--- SCAN #{scan_count} ---")

            # Reload portfolios (in case dashboard changed them)
            portfolios, counter = load_portfolios()

            # Run engine
            results = run_engine(portfolios)

            # Save if any trades
            if results:
                save_portfolios(portfolios, counter)
                log(f"Executed {len(results)} trades - saved to {PORTFOLIOS_FILE}")
            else:
                log("No trades executed")

            # Wait
            log(f"Next scan in {SCAN_INTERVAL}s...")
            time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        log("\nBot stopped by user")
        save_portfolios(portfolios, counter)
        log("Final state saved")


if __name__ == "__main__":
    main()
