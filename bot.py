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
import traceback
from datetime import datetime
from pathlib import Path

# Config
PORTFOLIOS_FILE = "data/portfolios.json"
LOG_FILE = "data/bot_log.txt"
DEBUG_FILE = "data/debug_log.json"
SCAN_INTERVAL = 60  # seconds between scans


def debug_log(category: str, message: str, context: dict = None, error: Exception = None):
    """
    Log debug information for troubleshooting.
    Categories: API, STRATEGY, DATA, FILE, TRADE, INDICATOR, SYSTEM
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    entry = {
        'timestamp': timestamp,
        'category': category,
        'message': message,
        'context': context or {},
    }

    if error:
        entry['error'] = {
            'type': type(error).__name__,
            'message': str(error),
            'traceback': traceback.format_exc()
        }

    # Load existing debug log
    debug_data = {'errors': [], 'warnings': [], 'info': []}
    try:
        if os.path.exists(DEBUG_FILE):
            with open(DEBUG_FILE, 'r', encoding='utf-8') as f:
                debug_data = json.load(f)
    except:
        pass

    # Determine severity
    if error:
        debug_data['errors'].append(entry)
        # Keep last 200 errors
        debug_data['errors'] = debug_data['errors'][-200:]
    elif 'warning' in message.lower() or 'failed' in message.lower():
        debug_data['warnings'].append(entry)
        debug_data['warnings'] = debug_data['warnings'][-100:]
    else:
        debug_data['info'].append(entry)
        debug_data['info'] = debug_data['info'][-50:]

    # Save
    try:
        os.makedirs("data", exist_ok=True)
        with open(DEBUG_FILE, 'w', encoding='utf-8') as f:
            json.dump(debug_data, f, indent=2, default=str)
    except:
        pass

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

    # ============ NEW STRATEGIES ============

    # EMA Crossover - Classic trend following
    "ema_crossover": {"auto": True, "use_ema_cross": True, "fast_ema": 9, "slow_ema": 21},
    "ema_crossover_slow": {"auto": True, "use_ema_cross": True, "fast_ema": 12, "slow_ema": 26},

    # VWAP Strategy - Intraday mean reversion
    "vwap_bounce": {"auto": True, "use_vwap": True, "deviation": 1.5},
    "vwap_trend": {"auto": True, "use_vwap": True, "deviation": 0.5, "trend_follow": True},

    # Supertrend - Dynamic support/resistance
    "supertrend": {"auto": True, "use_supertrend": True, "period": 10, "multiplier": 3.0},
    "supertrend_fast": {"auto": True, "use_supertrend": True, "period": 7, "multiplier": 2.0},

    # Stochastic RSI - Precise entries
    "stoch_rsi": {"auto": True, "use_stoch_rsi": True, "oversold": 20, "overbought": 80},
    "stoch_rsi_aggressive": {"auto": True, "use_stoch_rsi": True, "oversold": 25, "overbought": 75},

    # Breakout - Trade consolidation breaks
    "breakout": {"auto": True, "use_breakout": True, "lookback": 20, "volume_mult": 1.5},
    "breakout_tight": {"auto": True, "use_breakout": True, "lookback": 10, "volume_mult": 2.0},

    # Mean Reversion - Buy deviations from mean
    "mean_reversion": {"auto": True, "use_mean_rev": True, "std_dev": 2.0, "period": 20},
    "mean_reversion_tight": {"auto": True, "use_mean_rev": True, "std_dev": 1.5, "period": 14},

    # Grid Trading - Range trading
    "grid_trading": {"auto": True, "use_grid": True, "grid_size": 2.0, "levels": 5},
    "grid_tight": {"auto": True, "use_grid": True, "grid_size": 1.0, "levels": 10},

    # DCA Accumulator - Regular buys on dips
    "dca_accumulator": {"auto": True, "use_dca": True, "dip_threshold": 3.0},
    "dca_aggressive": {"auto": True, "use_dca": True, "dip_threshold": 2.0},

    # Ichimoku Cloud - Japanese trend system
    "ichimoku": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52},
    "ichimoku_fast": {"auto": True, "use_ichimoku": True, "tenkan": 7, "kijun": 22, "senkou": 44},

    # Martingale - Double down on losses (HIGH RISK!)
    "martingale": {"auto": True, "use_martingale": True, "multiplier": 2.0, "max_levels": 4},
    "martingale_safe": {"auto": True, "use_martingale": True, "multiplier": 1.5, "max_levels": 3},
}


def get_fear_greed_index() -> dict:
    """Fetch Fear & Greed Index from Alternative.me API"""
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('data') and len(data['data']) > 0:
                fng = data['data'][0]
                return {
                    'value': int(fng.get('value', 50)),
                    'classification': fng.get('value_classification', 'Neutral')
                }
        else:
            debug_log('API', f'Fear&Greed API returned status {response.status_code}',
                     {'url': url, 'status': response.status_code})
    except Exception as e:
        debug_log('API', 'Fear&Greed API failed', {'url': url}, error=e)
    return {'value': 50, 'classification': 'Neutral'}  # Default neutral


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


def log_decision(portfolio: dict, symbol: str, analysis: dict, action: str, reason: str):
    """Log a decision to the portfolio's decision log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Initialize logs array if needed
    if 'decision_logs' not in portfolio:
        portfolio['decision_logs'] = []

    # Create log entry with key indicators
    log_entry = {
        'timestamp': timestamp,
        'symbol': symbol.replace('/USDT', ''),
        'action': action,  # BUY, SELL, HOLD, SKIP
        'reason': reason,
        'price': analysis.get('price', 0),
        'rsi': round(analysis.get('rsi', 50), 1),
        'signal': analysis.get('signal', 'HOLD'),
        'trend': analysis.get('trend', 'unknown')
    }

    # Add relevant indicator based on strategy
    if analysis.get('ema_cross_up') or analysis.get('ema_cross_down'):
        log_entry['ema_cross'] = 'UP' if analysis.get('ema_cross_up') else 'DOWN'
    if analysis.get('stoch_rsi'):
        log_entry['stoch_rsi'] = round(analysis.get('stoch_rsi', 50), 1)
    if analysis.get('vwap_deviation'):
        log_entry['vwap_dev'] = round(analysis.get('vwap_deviation', 0), 2)
    if analysis.get('bb_position'):
        log_entry['bb_pos'] = round(analysis.get('bb_position', 0.5), 2)

    portfolio['decision_logs'].append(log_entry)

    # Keep only last 100 logs per portfolio
    if len(portfolio['decision_logs']) > 100:
        portfolio['decision_logs'] = portfolio['decision_logs'][-100:]


def load_portfolios() -> dict:
    """Load portfolios from JSON"""
    try:
        if os.path.exists(PORTFOLIOS_FILE):
            with open(PORTFOLIOS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                portfolios = data.get('portfolios', {})
                # Validate portfolios structure
                for pid, p in portfolios.items():
                    if 'config' not in p:
                        debug_log('DATA', f'Portfolio {pid} missing config', {'portfolio_id': pid})
                    if 'balance' not in p:
                        debug_log('DATA', f'Portfolio {pid} missing balance', {'portfolio_id': pid})
                return portfolios, data.get('counter', 0)
        else:
            debug_log('FILE', 'Portfolios file not found', {'path': PORTFOLIOS_FILE})
    except json.JSONDecodeError as e:
        debug_log('FILE', 'Portfolios JSON is corrupted', {'path': PORTFOLIOS_FILE}, error=e)
        log(f"Error loading portfolios: {e}")
    except Exception as e:
        debug_log('FILE', 'Failed to load portfolios', {'path': PORTFOLIOS_FILE}, error=e)
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
        debug_log('FILE', 'Failed to save portfolios', {'path': PORTFOLIOS_FILE, 'portfolio_count': len(portfolios)}, error=e)
        log(f"Error saving portfolios: {e}")


def calculate_indicators(df: pd.DataFrame) -> dict:
    """Calculate all technical indicators"""
    indicators = {}

    closes = df['close']
    highs = df['high']
    lows = df['low']
    volumes = df['volume']

    # RSI
    delta = closes.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    indicators['rsi'] = rsi.iloc[-1]

    # EMAs (multiple periods)
    indicators['ema_9'] = closes.ewm(span=9).mean().iloc[-1]
    indicators['ema_12'] = closes.ewm(span=12).mean().iloc[-1]
    indicators['ema_21'] = closes.ewm(span=21).mean().iloc[-1]
    indicators['ema_26'] = closes.ewm(span=26).mean().iloc[-1]
    indicators['ema_50'] = closes.ewm(span=50).mean().iloc[-1]

    # EMA crossover signals (9/21 fast)
    ema_9_prev = closes.ewm(span=9).mean().iloc[-2]
    ema_21_prev = closes.ewm(span=21).mean().iloc[-2]
    indicators['ema_cross_up'] = ema_9_prev < ema_21_prev and indicators['ema_9'] > indicators['ema_21']
    indicators['ema_cross_down'] = ema_9_prev > ema_21_prev and indicators['ema_9'] < indicators['ema_21']

    # EMA crossover signals (12/26 slow)
    ema_12_prev = closes.ewm(span=12).mean().iloc[-2]
    ema_26_prev = closes.ewm(span=26).mean().iloc[-2]
    indicators['ema_cross_up_slow'] = ema_12_prev < ema_26_prev and indicators['ema_12'] > indicators['ema_26']
    indicators['ema_cross_down_slow'] = ema_12_prev > ema_26_prev and indicators['ema_12'] < indicators['ema_26']

    # VWAP (Volume Weighted Average Price)
    typical_price = (highs + lows + closes) / 3
    vwap = (typical_price * volumes).cumsum() / volumes.cumsum()
    indicators['vwap'] = vwap.iloc[-1]
    indicators['vwap_deviation'] = ((closes.iloc[-1] - vwap.iloc[-1]) / vwap.iloc[-1]) * 100

    # Supertrend (normal: period=10, mult=3.0 | fast: period=7, mult=2.0)
    tr = pd.concat([highs - lows, abs(highs - closes.shift(1)), abs(lows - closes.shift(1))], axis=1).max(axis=1)
    hl2 = (highs + lows) / 2

    # Normal supertrend
    atr_10 = tr.rolling(window=10).mean()
    lower_band_10 = hl2 - (3.0 * atr_10)
    upper_band_10 = hl2 + (3.0 * atr_10)
    indicators['supertrend_up'] = closes.iloc[-1] > lower_band_10.iloc[-1]
    indicators['supertrend_value'] = lower_band_10.iloc[-1] if indicators['supertrend_up'] else upper_band_10.iloc[-1]

    # Fast supertrend
    atr_7 = tr.rolling(window=7).mean()
    lower_band_7 = hl2 - (2.0 * atr_7)
    upper_band_7 = hl2 + (2.0 * atr_7)
    indicators['supertrend_up_fast'] = closes.iloc[-1] > lower_band_7.iloc[-1]
    indicators['supertrend_value_fast'] = lower_band_7.iloc[-1] if indicators['supertrend_up_fast'] else upper_band_7.iloc[-1]

    # Stochastic RSI
    rsi_min = rsi.rolling(window=14).min()
    rsi_max = rsi.rolling(window=14).max()
    stoch_rsi = ((rsi - rsi_min) / (rsi_max - rsi_min)) * 100
    indicators['stoch_rsi'] = stoch_rsi.iloc[-1] if not pd.isna(stoch_rsi.iloc[-1]) else 50
    indicators['stoch_rsi_k'] = stoch_rsi.rolling(window=3).mean().iloc[-1] if not pd.isna(stoch_rsi.rolling(window=3).mean().iloc[-1]) else 50

    # Bollinger Bands (for mean reversion)
    sma_20 = closes.rolling(window=20).mean()
    std_20 = closes.rolling(window=20).std()
    indicators['bb_upper'] = sma_20.iloc[-1] + (2 * std_20.iloc[-1])
    indicators['bb_lower'] = sma_20.iloc[-1] - (2 * std_20.iloc[-1])
    indicators['bb_mid'] = sma_20.iloc[-1]
    indicators['bb_position'] = (closes.iloc[-1] - indicators['bb_lower']) / (indicators['bb_upper'] - indicators['bb_lower']) if indicators['bb_upper'] != indicators['bb_lower'] else 0.5

    # Breakout detection (normal: lookback=20, vol=1.5x | tight: lookback=10, vol=2.0x)
    vol_avg = volumes.rolling(window=20).mean().iloc[-1]

    # Normal breakout (20 period)
    high_20 = highs.rolling(window=20).max().iloc[-2]
    low_20 = lows.rolling(window=20).min().iloc[-2]
    indicators['breakout_up'] = closes.iloc[-1] > high_20 and volumes.iloc[-1] > vol_avg * 1.5
    indicators['breakout_down'] = closes.iloc[-1] < low_20 and volumes.iloc[-1] > vol_avg * 1.5
    indicators['consolidation_range'] = (high_20 - low_20) / low_20 * 100

    # Tight breakout (10 period, 2x volume)
    high_10 = highs.rolling(window=10).max().iloc[-2]
    low_10 = lows.rolling(window=10).min().iloc[-2]
    indicators['breakout_up_tight'] = closes.iloc[-1] > high_10 and volumes.iloc[-1] > vol_avg * 2.0
    indicators['breakout_down_tight'] = closes.iloc[-1] < low_10 and volumes.iloc[-1] > vol_avg * 2.0

    # Mean Reversion (normal: period=20 | tight: period=14)
    indicators['deviation_from_mean'] = (closes.iloc[-1] - sma_20.iloc[-1]) / std_20.iloc[-1] if std_20.iloc[-1] > 0 else 0

    # Tight mean reversion (14 period)
    sma_14 = closes.rolling(window=14).mean()
    std_14 = closes.rolling(window=14).std()
    indicators['deviation_from_mean_tight'] = (closes.iloc[-1] - sma_14.iloc[-1]) / std_14.iloc[-1] if std_14.iloc[-1] > 0 else 0

    # Ichimoku Cloud (normal: 9/26/52 | fast: 7/22/44)
    # Normal Ichimoku
    tenkan = (highs.rolling(window=9).max() + lows.rolling(window=9).min()) / 2
    kijun = (highs.rolling(window=26).max() + lows.rolling(window=26).min()) / 2
    senkou_a = ((tenkan + kijun) / 2).shift(26)
    senkou_b = ((highs.rolling(window=52).max() + lows.rolling(window=52).min()) / 2).shift(26)

    indicators['tenkan'] = tenkan.iloc[-1]
    indicators['kijun'] = kijun.iloc[-1]
    indicators['ichimoku_bullish'] = closes.iloc[-1] > tenkan.iloc[-1] and tenkan.iloc[-1] > kijun.iloc[-1]
    indicators['ichimoku_bearish'] = closes.iloc[-1] < tenkan.iloc[-1] and tenkan.iloc[-1] < kijun.iloc[-1]
    indicators['above_cloud'] = closes.iloc[-1] > max(senkou_a.iloc[-1] if not pd.isna(senkou_a.iloc[-1]) else 0, senkou_b.iloc[-1] if not pd.isna(senkou_b.iloc[-1]) else 0)

    # Fast Ichimoku (7/22/44)
    tenkan_fast = (highs.rolling(window=7).max() + lows.rolling(window=7).min()) / 2
    kijun_fast = (highs.rolling(window=22).max() + lows.rolling(window=22).min()) / 2
    senkou_a_fast = ((tenkan_fast + kijun_fast) / 2).shift(22)
    senkou_b_fast = ((highs.rolling(window=44).max() + lows.rolling(window=44).min()) / 2).shift(22)

    indicators['ichimoku_bullish_fast'] = closes.iloc[-1] > tenkan_fast.iloc[-1] and tenkan_fast.iloc[-1] > kijun_fast.iloc[-1]
    indicators['ichimoku_bearish_fast'] = closes.iloc[-1] < tenkan_fast.iloc[-1] and tenkan_fast.iloc[-1] < kijun_fast.iloc[-1]
    indicators['above_cloud_fast'] = closes.iloc[-1] > max(senkou_a_fast.iloc[-1] if not pd.isna(senkou_a_fast.iloc[-1]) else 0, senkou_b_fast.iloc[-1] if not pd.isna(senkou_b_fast.iloc[-1]) else 0)

    # Price changes for DCA
    indicators['change_1h'] = (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100 if len(closes) > 1 else 0
    indicators['change_24h'] = (closes.iloc[-1] - closes.iloc[-24]) / closes.iloc[-24] * 100 if len(closes) > 24 else 0

    # Volume analysis
    indicators['volume_ratio'] = volumes.iloc[-1] / vol_avg if vol_avg > 0 else 1

    # GOD MODE detection (extreme conditions)
    god_mode_buy = (
        indicators['rsi'] < 20 and  # Extremely oversold
        indicators['volume_ratio'] > 2.0 and  # Volume spike
        indicators['deviation_from_mean'] < -2.0 and  # Way below mean
        closes.iloc[-1] > closes.iloc[-2]  # Starting to bounce
    )
    god_mode_sell = (
        indicators['rsi'] > 80 and  # Extremely overbought
        indicators['volume_ratio'] > 2.0 and  # Volume spike
        indicators['deviation_from_mean'] > 2.0 and  # Way above mean
        closes.iloc[-1] < closes.iloc[-2]  # Starting to drop
    )
    indicators['god_mode_buy'] = god_mode_buy
    indicators['god_mode_sell'] = god_mode_sell

    # Momentum indicators for degen strategies
    indicators['momentum_1h'] = (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100
    indicators['momentum_4h'] = (closes.iloc[-1] - closes.iloc[-5]) / closes.iloc[-5] * 100 if len(closes) > 5 else 0

    # Scalping signals (quick reversals)
    indicators['scalp_buy'] = indicators['rsi'] < 25 and indicators['momentum_1h'] > 0.3
    indicators['scalp_sell'] = indicators['rsi'] > 75 and indicators['momentum_1h'] < -0.3

    # Momentum signals (riding the wave)
    indicators['momentum_buy'] = indicators['volume_ratio'] > 2.0 and indicators['momentum_1h'] > 1.0 and indicators['rsi'] < 65
    indicators['momentum_sell'] = indicators['volume_ratio'] > 2.0 and indicators['momentum_1h'] < -1.0 and indicators['rsi'] > 35

    return indicators


def analyze_crypto(symbol: str) -> dict:
    """Analyze a crypto - returns price and all indicators"""
    try:
        # Fetch OHLCV from Binance
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.replace('/', '')}&interval=1h&limit=100"
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            debug_log('API', f'Binance API error for {symbol}',
                     {'symbol': symbol, 'status': response.status_code, 'response': response.text[:200]})
            return None

        data = response.json()

        if isinstance(data, dict) and data.get('code'):
            # Binance error response
            debug_log('API', f'Binance returned error for {symbol}',
                     {'symbol': symbol, 'code': data.get('code'), 'msg': data.get('msg')})
            return None

        if not data or len(data) < 50:
            debug_log('DATA', f'Insufficient data for {symbol}',
                     {'symbol': symbol, 'candles_received': len(data) if data else 0, 'required': 50})
            return None

        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                          'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                                          'taker_buy_quote', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)

        # Calculate all indicators
        try:
            indicators = calculate_indicators(df)
        except Exception as e:
            debug_log('INDICATOR', f'Failed to calculate indicators for {symbol}',
                     {'symbol': symbol, 'df_shape': df.shape}, error=e)
            return None

        # Validate indicators
        if pd.isna(indicators.get('rsi')) or indicators.get('rsi') is None:
            debug_log('INDICATOR', f'Invalid RSI for {symbol}',
                     {'symbol': symbol, 'rsi': indicators.get('rsi')})
            indicators['rsi'] = 50  # Default

        current_price = df['close'].iloc[-1]

        # Determine basic signal (for confluence strategies)
        signal = "HOLD"
        if indicators.get('god_mode_buy'):
            signal = "GOD_MODE_BUY"
        elif indicators.get('god_mode_sell'):
            signal = "GOD_MODE_SELL"
        elif indicators['rsi'] < 30 and indicators['ema_12'] > indicators['ema_26']:
            signal = "STRONG_BUY"
        elif indicators['rsi'] < 35:
            signal = "BUY"
        elif indicators['rsi'] > 70 and indicators['ema_12'] < indicators['ema_26']:
            signal = "STRONG_SELL"
        elif indicators['rsi'] > 65:
            signal = "SELL"

        result = {
            'symbol': symbol,
            'price': current_price,
            'signal': signal,
            'trend': 'bullish' if indicators['ema_12'] > indicators['ema_26'] else 'bearish'
        }
        result.update(indicators)

        return result

    except requests.exceptions.Timeout:
        debug_log('API', f'Timeout fetching {symbol}', {'symbol': symbol, 'timeout': 10})
        return None
    except requests.exceptions.ConnectionError as e:
        debug_log('API', f'Connection error for {symbol}', {'symbol': symbol}, error=e)
        return None
    except Exception as e:
        debug_log('API', f'Unexpected error analyzing {symbol}', {'symbol': symbol}, error=e)
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


def should_trade(portfolio: dict, analysis: dict) -> tuple:
    """
    Determine if we should trade based on strategy.
    Returns: (action, reason) tuple where action is 'BUY', 'SELL', or None
    """
    strategy_id = portfolio.get('strategy_id', 'manuel')
    strategy = STRATEGIES.get(strategy_id, {})
    config = portfolio['config']

    if not strategy.get('auto', False):
        return (None, "Manual strategy - no auto-trade")

    if not config.get('auto_trade', True):
        return (None, "Auto-trade disabled in config")

    symbol = analysis['symbol']
    asset = symbol.split('/')[0]

    # Check max positions
    if len(portfolio['positions']) >= config.get('max_positions', 3):
        if symbol not in portfolio['positions']:
            return (None, f"Max positions ({config.get('max_positions', 3)}) reached")

    has_position = portfolio['balance'].get(asset, 0) > 0
    has_cash = portfolio['balance']['USDT'] > 100
    rsi = analysis.get('rsi', 50)

    # ============ NEW STRATEGIES ============

    # EMA Crossover
    if strategy.get('use_ema_cross'):
        fast = strategy.get('fast_ema', 9)
        # Use slow crossover (12/26) if specified
        if fast == 12:
            if analysis.get('ema_cross_up_slow') and has_cash:
                return ('BUY', f"EMA 12/26 crossover UP | RSI={rsi:.0f}")
            elif analysis.get('ema_cross_down_slow') and has_position:
                return ('SELL', f"EMA 12/26 crossover DOWN | RSI={rsi:.0f}")
        else:
            # Default fast crossover (9/21)
            if analysis.get('ema_cross_up') and has_cash:
                return ('BUY', f"EMA 9/21 crossover UP | RSI={rsi:.0f}")
            elif analysis.get('ema_cross_down') and has_position:
                return ('SELL', f"EMA 9/21 crossover DOWN | RSI={rsi:.0f}")
        return (None, f"EMA: No crossover signal | RSI={rsi:.0f}")

    # Degen strategies
    if strategy.get('use_degen'):
        mode = strategy.get('mode', 'hybrid')
        mom = analysis.get('momentum_1h', 0)

        if mode == 'scalping':
            # Quick reversals - tight entries/exits
            if analysis.get('scalp_buy') and has_cash:
                return ('BUY', f"SCALP: RSI={rsi:.0f}<25 + momentum>0.3%")
            elif analysis.get('scalp_sell') and has_position:
                return ('SELL', f"SCALP: RSI={rsi:.0f}>75 + momentum<-0.3%")
            elif analysis.get('rsi', 50) > 55 and has_position:
                return ('SELL', f"SCALP EXIT: RSI normalized to {rsi:.0f}")

        elif mode == 'momentum':
            # Ride the wave - volume + momentum
            if analysis.get('momentum_buy') and has_cash:
                return ('BUY', f"MOMENTUM: Vol spike + momentum={mom:.1f}%")
            elif analysis.get('momentum_sell') and has_position:
                return ('SELL', f"MOMENTUM: Vol spike + negative momentum")
            elif has_position and mom < -0.5:
                return ('SELL', f"MOMENTUM LOSS: {mom:.1f}% < -0.5%")

        else:  # hybrid - combines both
            if (analysis.get('scalp_buy') or analysis.get('momentum_buy')) and has_cash:
                return ('BUY', f"HYBRID: Scalp or momentum signal | RSI={rsi:.0f}")
            elif has_position:
                if analysis.get('scalp_sell') or analysis.get('momentum_sell'):
                    return ('SELL', f"HYBRID: Exit signal triggered")
                elif rsi > 70:
                    return ('SELL', f"HYBRID: RSI={rsi:.0f} > 70 overbought")

        return (None, f"DEGEN {mode}: No signal | RSI={rsi:.0f} | Mom={mom:.1f}%")

    # VWAP Strategy
    if strategy.get('use_vwap'):
        deviation = strategy.get('deviation', 1.5)
        vwap_dev = analysis.get('vwap_deviation', 0)
        trend_follow = strategy.get('trend_follow', False)

        if trend_follow:
            if vwap_dev > deviation and has_cash:
                return ('BUY', f"VWAP TREND: Price {vwap_dev:.1f}% above VWAP")
            elif vwap_dev < -deviation and has_position:
                return ('SELL', f"VWAP TREND: Price {vwap_dev:.1f}% below VWAP")
        else:
            if vwap_dev < -deviation and has_cash:
                return ('BUY', f"VWAP BOUNCE: Price {vwap_dev:.1f}% below VWAP")
            elif vwap_dev > deviation and has_position:
                return ('SELL', f"VWAP BOUNCE: Price {vwap_dev:.1f}% above VWAP")
        return (None, f"VWAP: Deviation={vwap_dev:.1f}% (threshold={deviation}%)")

    # Supertrend (normal vs fast)
    if strategy.get('use_supertrend'):
        period = strategy.get('period', 10)
        if period == 7:
            supertrend_up = analysis.get('supertrend_up_fast', False)
        else:
            supertrend_up = analysis.get('supertrend_up', False)

        if supertrend_up and not has_position and has_cash:
            if rsi < 70:
                return ('BUY', f"SUPERTREND: Uptrend confirmed | RSI={rsi:.0f}")
        elif not supertrend_up and has_position:
            return ('SELL', f"SUPERTREND: Downtrend signal")
        return (None, f"SUPERTREND: {'Up' if supertrend_up else 'Down'} | RSI={rsi:.0f}")

    # Stochastic RSI
    if strategy.get('use_stoch_rsi'):
        oversold = strategy.get('oversold', 20)
        overbought = strategy.get('overbought', 80)
        stoch = analysis.get('stoch_rsi', 50)

        if stoch < oversold and has_cash:
            return ('BUY', f"STOCH RSI: {stoch:.0f} < {oversold} oversold")
        elif stoch > overbought and has_position:
            return ('SELL', f"STOCH RSI: {stoch:.0f} > {overbought} overbought")
        return (None, f"STOCH RSI: {stoch:.0f} (range {oversold}-{overbought})")

    # Breakout (normal vs tight)
    if strategy.get('use_breakout'):
        lookback = strategy.get('lookback', 20)
        if lookback == 10:
            breakout_up = analysis.get('breakout_up_tight', False)
            breakout_down = analysis.get('breakout_down_tight', False)
        else:
            breakout_up = analysis.get('breakout_up', False)
            breakout_down = analysis.get('breakout_down', False)

        if breakout_up and has_cash:
            return ('BUY', f"BREAKOUT UP: Price broke {lookback}-period high with volume")
        elif breakout_down and has_position:
            return ('SELL', f"BREAKOUT DOWN: Price broke {lookback}-period low")
        return (None, f"BREAKOUT: Waiting for {lookback}-period break")

    # Mean Reversion (normal vs tight)
    if strategy.get('use_mean_rev'):
        std_threshold = strategy.get('std_dev', 2.0)
        period = strategy.get('period', 20)
        if period == 14:
            deviation = analysis.get('deviation_from_mean_tight', 0)
        else:
            deviation = analysis.get('deviation_from_mean', 0)

        if deviation < -std_threshold and has_cash:
            return ('BUY', f"MEAN REV: {deviation:.1f}σ below mean (threshold=-{std_threshold})")
        elif deviation > std_threshold and has_position:
            return ('SELL', f"MEAN REV: {deviation:.1f}σ above mean (threshold={std_threshold})")
        return (None, f"MEAN REV: Deviation={deviation:.1f}σ (threshold=±{std_threshold})")

    # Grid Trading
    if strategy.get('use_grid'):
        grid_size = strategy.get('grid_size', 2.0)
        bb_pos = analysis.get('bb_position', 0.5)
        buy_threshold = 0.15 + (grid_size * 0.025)
        sell_threshold = 0.85 - (grid_size * 0.025)

        if bb_pos < buy_threshold and has_cash:
            return ('BUY', f"GRID: BB position={bb_pos:.0%} < {buy_threshold:.0%}")
        elif bb_pos > sell_threshold and has_position:
            return ('SELL', f"GRID: BB position={bb_pos:.0%} > {sell_threshold:.0%}")
        return (None, f"GRID: BB position={bb_pos:.0%} (buy<{buy_threshold:.0%}, sell>{sell_threshold:.0%})")

    # DCA Accumulator
    if strategy.get('use_dca'):
        dip_threshold = strategy.get('dip_threshold', 3.0)
        change = analysis.get('change_24h', 0)

        if change < -dip_threshold and has_cash:
            return ('BUY', f"DCA: 24h change={change:.1f}% < -{dip_threshold}% dip")
        return (None, f"DCA: 24h change={change:.1f}% (waiting for -{dip_threshold}% dip)")

    # Ichimoku (normal vs fast)
    if strategy.get('use_ichimoku'):
        tenkan = strategy.get('tenkan', 9)
        if tenkan == 7:
            bullish = analysis.get('ichimoku_bullish_fast', False)
            bearish = analysis.get('ichimoku_bearish_fast', False)
            above = analysis.get('above_cloud_fast', False)
        else:
            bullish = analysis.get('ichimoku_bullish', False)
            bearish = analysis.get('ichimoku_bearish', False)
            above = analysis.get('above_cloud', False)

        if bullish and above and has_cash:
            return ('BUY', f"ICHIMOKU: Bullish + above cloud")
        elif bearish and has_position:
            return ('SELL', f"ICHIMOKU: Bearish signal")
        cloud_status = "above" if above else "below"
        trend = "bullish" if bullish else ("bearish" if bearish else "neutral")
        return (None, f"ICHIMOKU: {trend}, {cloud_status} cloud")

    # Martingale (uses multiplier and max_levels)
    if strategy.get('use_martingale'):
        multiplier = strategy.get('multiplier', 2.0)
        max_levels = strategy.get('max_levels', 4)

        # Count consecutive losses
        trades = portfolio.get('trades', [])
        consecutive_losses = 0
        for t in reversed(trades):
            if t.get('action') == 'SELL':
                if t.get('pnl', 0) < 0:
                    consecutive_losses += 1
                else:
                    break

        if consecutive_losses > 0 and consecutive_losses <= max_levels:
            if has_cash and rsi < 45:
                portfolio['_martingale_level'] = consecutive_losses
                portfolio['_martingale_multiplier'] = multiplier
                return ('BUY', f"MARTINGALE: Level {consecutive_losses}/{max_levels} | RSI={rsi:.0f}")
        elif consecutive_losses > max_levels:
            if has_cash and rsi < 25:
                portfolio['_martingale_level'] = 0
                return ('BUY', f"MARTINGALE RESET: Max level reached, extreme RSI={rsi:.0f}")

        if rsi < 35 and has_cash:
            portfolio['_martingale_level'] = 0
            return ('BUY', f"MARTINGALE: Normal entry RSI={rsi:.0f} < 35")
        elif rsi > 65 and has_position:
            return ('SELL', f"MARTINGALE: RSI={rsi:.0f} > 65")
        return (None, f"MARTINGALE: RSI={rsi:.0f} | Losses={consecutive_losses}")

    # ============ EXISTING STRATEGIES ============

    signal = analysis.get('signal', 'HOLD')

    # RSI Strategy
    if strategy.get('use_rsi', False):
        rsi_oversold = config.get('rsi_oversold', 30)
        rsi_overbought = config.get('rsi_overbought', 70)

        if rsi < rsi_oversold and has_cash:
            return ('BUY', f"RSI={rsi:.0f} < {rsi_oversold} oversold")
        elif rsi > rsi_overbought and has_position:
            return ('SELL', f"RSI={rsi:.0f} > {rsi_overbought} overbought")
        return (None, f"RSI={rsi:.0f} (buy<{rsi_oversold}, sell>{rsi_overbought})")

    # DCA Fear & Greed Strategy
    if strategy.get('use_fear_greed', False):
        fng = get_fear_greed_index()
        fear_value = fng['value']
        fear_class = fng['classification']

        if fear_value < 25 and has_cash:
            return ('BUY', f"FEAR&GREED: {fear_value} Extreme Fear!")
        elif fear_value < 40 and has_cash and rsi < 40:
            return ('BUY', f"FEAR&GREED: {fear_value} Fear + RSI={rsi:.0f}")
        elif fear_value > 80 and has_position:
            return ('SELL', f"FEAR&GREED: {fear_value} Extreme Greed!")
        return (None, f"FEAR&GREED: {fear_value} ({fear_class}) | RSI={rsi:.0f}")

    # HODL Strategy
    if strategy.get('buy_on') == ["ALWAYS_FIRST"]:
        if len(portfolio['trades']) == 0 and has_cash:
            return ('BUY', "HODL: First buy - will never sell")
        return (None, "HODL: Already bought, holding forever")

    # GOD MODE strategy
    if "GOD_MODE_BUY" in strategy.get('buy_on', []):
        if analysis.get('god_mode_buy') and has_cash:
            return ('BUY', f"GOD MODE: RSI={rsi:.0f}<20 + Vol spike + Below mean + Bouncing!")
        elif analysis.get('god_mode_sell') and has_position:
            return ('SELL', f"GOD MODE SELL: RSI={rsi:.0f}>80 + Vol spike + Above mean + Dropping!")
        return (None, f"GOD MODE: Waiting for extreme conditions | RSI={rsi:.0f}")

    # Signal-based strategies (confluence, conservative, aggressive, etc.)
    buy_signals = strategy.get('buy_on', [])
    sell_signals = strategy.get('sell_on', [])

    if signal in buy_signals and has_cash:
        return ('BUY', f"SIGNAL: {signal} matched buy signals {buy_signals}")
    elif signal in sell_signals and has_position:
        return ('SELL', f"SIGNAL: {signal} matched sell signals {sell_signals}")

    return (None, f"SIGNAL: {signal} | RSI={rsi:.0f} | Waiting for {buy_signals}")


def run_engine(portfolios: dict) -> list:
    """Run the trading engine for all portfolios"""
    results = []
    analyzed = {}

    # Get all unique cryptos
    all_cryptos = set()
    for p in portfolios.values():
        if p.get('active', True):
            all_cryptos.update(p['config'].get('cryptos', []))

    if not all_cryptos:
        debug_log('SYSTEM', 'No cryptos configured in any active portfolio',
                 {'active_portfolios': len([p for p in portfolios.values() if p.get('active')])})

    log(f"Scanning {len(all_cryptos)} cryptos for {len([p for p in portfolios.values() if p.get('active')])} active portfolios...")

    # Analyze each crypto once
    failed_cryptos = []
    for crypto in all_cryptos:
        analysis = analyze_crypto(crypto)
        if analysis:
            analyzed[crypto] = analysis
            log(f"  {crypto}: ${analysis['price']:,.2f} | RSI {analysis['rsi']:.1f} | {analysis['signal']}")
        else:
            failed_cryptos.append(crypto)

    if failed_cryptos:
        debug_log('API', f'Failed to analyze {len(failed_cryptos)} cryptos',
                 {'failed': failed_cryptos, 'total': len(all_cryptos)})

    # Check each portfolio
    for port_id, portfolio in portfolios.items():
        if not portfolio.get('active', True):
            continue

        for crypto in portfolio['config'].get('cryptos', []):
            if crypto not in analyzed:
                continue

            analysis = analyzed[crypto]

            try:
                action, reason = should_trade(portfolio, analysis)
            except Exception as e:
                debug_log('STRATEGY', f'Strategy error for {portfolio["name"]}',
                         {'portfolio': portfolio['name'], 'strategy': portfolio.get('strategy_id'),
                          'crypto': crypto, 'analysis': analysis}, error=e)
                action, reason = None, f"ERROR: {str(e)}"

            # Log all decisions for this portfolio
            log_decision(portfolio, crypto, analysis, action or 'HOLD', reason)

            if action:
                try:
                    result = execute_trade(portfolio, action, crypto, analysis['price'])
                    if result['success']:
                        log(f"  >> {portfolio['name']}: {result['message']}")
                        results.append({
                            'portfolio': portfolio['name'],
                            'crypto': crypto,
                            'action': action,
                            'reason': reason,
                            'price': analysis['price'],
                            'message': result['message']
                        })
                except Exception as e:
                    debug_log('TRADE', f'Trade execution failed for {portfolio["name"]}',
                             {'portfolio': portfolio['name'], 'action': action,
                              'crypto': crypto, 'price': analysis['price']}, error=e)

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
    except FileNotFoundError as e:
        debug_log('SYSTEM', 'Streamlit not found', {'python': sys.executable}, error=e)
        log(f"Could not start dashboard: {e}")
    except Exception as e:
        debug_log('SYSTEM', 'Failed to start dashboard', {'python': sys.executable}, error=e)
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
            elif response.status_code != 403:  # 403 is expected (blocked)
                debug_log('API', 'Pump.fun API error', {'status': response.status_code})
        except Exception as e:
            debug_log('API', 'Pump.fun scan failed', {}, error=e)

    except Exception as e:
        debug_log('API', 'DexScreener scan failed', {}, error=e)
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
            try:
                log("📊 Scanning existing cryptos...")
                classic_results = run_engine(portfolios)
                total_results.extend(classic_results)
            except Exception as e:
                debug_log('SYSTEM', 'Classic engine crashed', {'scan': scan_count}, error=e)
                classic_results = []

            # 2. Sniper engine (new tokens)
            try:
                log("🎯 Scanning for new tokens...")
                new_tokens = scan_new_tokens()

                # Filter out already seen tokens
                fresh_tokens = [t for t in new_tokens if t['address'] not in sniper_tokens_seen]
                for t in fresh_tokens:
                    sniper_tokens_seen.add(t['address'])
                    log(f"  🆕 {t['symbol']} | ${t['price']:.8f} | MC: ${t['market_cap']:,.0f} | Risk: {t['risk_score']}/100 | {t['dex']}")

                sniper_results = run_sniper_engine(portfolios, new_tokens)
                total_results.extend(sniper_results)
            except Exception as e:
                debug_log('SYSTEM', 'Sniper engine crashed', {'scan': scan_count}, error=e)
                sniper_results = []
                fresh_tokens = []

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
    except Exception as e:
        debug_log('SYSTEM', 'Main loop crashed', {'scan': scan_count}, error=e)
        log(f"FATAL ERROR: {e}")
        save_portfolios(portfolios, counter)


if __name__ == "__main__":
    main()
