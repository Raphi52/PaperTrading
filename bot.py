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

# Fix console encoding for emojis (Windows/Linux)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    else:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except:
    pass  # Ignore if encoding fix fails

# Config
PORTFOLIOS_FILE = "data/portfolios.json"
LOG_FILE = "data/bot_log.txt"
DEBUG_FILE = "data/debug_log.json"
SCAN_INTERVAL = 60  # seconds between scans


def get_debug_state() -> dict:
    """Load current debug state"""
    try:
        if os.path.exists(DEBUG_FILE):
            with open(DEBUG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {
        'bot_status': {'running': False, 'started_at': None, 'scan_count': 0},
        'last_scan': {},
        'api_health': {},
        'recent_errors': [],
        'recent_trades': []
    }


def save_debug_state(state: dict):
    """Save debug state"""
    try:
        os.makedirs("data", exist_ok=True)
        with open(DEBUG_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, default=str)
    except:
        pass


def debug_log(category: str, message: str, context: dict = None, error: Exception = None):
    """
    Log debug information. Categories: API, STRATEGY, DATA, FILE, TRADE, SYSTEM
    """
    state = get_debug_state()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Only log actual errors to recent_errors
    if error:
        entry = {
            'timestamp': timestamp,
            'category': category,
            'message': message,
            'context': context or {},
            'error_type': type(error).__name__,
            'error_msg': str(error),
            'traceback': traceback.format_exc()
        }
        state['recent_errors'].append(entry)
        state['recent_errors'] = state['recent_errors'][-20:]  # Keep last 20

    # Update API health for API category
    if category == 'API':
        api_name = context.get('api', 'unknown') if context else 'unknown'
        state['api_health'][api_name] = {
            'last_check': timestamp,
            'status': 'error' if error else 'ok',
            'message': message
        }

    save_debug_state(state)


def debug_update_bot_status(running: bool, scan_count: int = 0):
    """Update bot running status"""
    state = get_debug_state()
    state['bot_status'] = {
        'running': running,
        'last_update': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'scan_count': scan_count,
        'started_at': state['bot_status'].get('started_at') if running else None
    }
    if running and not state['bot_status'].get('started_at'):
        state['bot_status']['started_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_debug_state(state)


def debug_update_scan(scan_data: dict):
    """Update last scan info"""
    state = get_debug_state()
    state['last_scan'] = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **scan_data
    }
    save_debug_state(state)


def debug_log_trade(portfolio_name: str, action: str, symbol: str, price: float, reason: str):
    """Log a trade for debug"""
    state = get_debug_state()
    state['recent_trades'].append({
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'portfolio': portfolio_name,
        'action': action,
        'symbol': symbol,
        'price': price,
        'reason': reason
    })
    state['recent_trades'] = state['recent_trades'][-30:]  # Keep last 30
    save_debug_state(state)


# ============ PORTFOLIO HISTORY TRACKING ============

def get_portfolio_history() -> dict:
    """Load portfolio history from file"""
    try:
        with open('data/portfolio_history.json', 'r') as f:
            return json.load(f)
    except:
        return {"last_update": None, "portfolios": {}}

def save_portfolio_history(history: dict):
    """Save portfolio history to file"""
    try:
        with open('data/portfolio_history.json', 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Error saving portfolio history: {e}")

def record_portfolio_values(portfolios: dict, prices: dict = None):
    """Record current portfolio values to history (called every scan)"""
    history = get_portfolio_history()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Fetch prices if not provided
    if prices is None:
        prices = {}
        try:
            response = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=5)
            if response.status_code == 200:
                for p in response.json():
                    if p['symbol'].endswith('USDT'):
                        sym = p['symbol'].replace('USDT', '/USDT')
                        prices[sym] = float(p['price'])
        except:
            pass

    for port_id, portfolio in portfolios.items():
        if not portfolio.get('active', True):
            continue

        # Calculate current value
        total_value = portfolio['balance'].get('USDT', 0)
        for asset, qty in portfolio['balance'].items():
            if asset != 'USDT' and qty > 0:
                symbol = f"{asset}/USDT"
                price = prices.get(symbol, 0)
                total_value += qty * price

        # Initialize portfolio history if needed
        if port_id not in history['portfolios']:
            history['portfolios'][port_id] = {
                'name': portfolio.get('name', port_id),
                'initial_capital': portfolio.get('initial_capital', 10000),
                'history': []
            }

        # Add data point (keep max 720 points = 12 hours at 1 min intervals, or 30 days at 1h)
        history['portfolios'][port_id]['history'].append({
            'timestamp': timestamp,
            'value': round(total_value, 2)
        })

        # Keep last 720 data points
        history['portfolios'][port_id]['history'] = history['portfolios'][port_id]['history'][-720:]

    history['last_update'] = timestamp
    save_portfolio_history(history)


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
    "aggressive": {"auto": True, "use_aggressive": True},  # Custom logic - vraiment agressif
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
    "sniper_safe": {"auto": True, "use_sniper": True, "max_risk": 60, "min_liquidity": 10000, "take_profit": 100, "stop_loss": 50},
    "sniper_degen": {"auto": True, "use_sniper": True, "max_risk": 80, "min_liquidity": 1000, "take_profit": 75, "stop_loss": 40},
    "sniper_yolo": {"auto": True, "use_sniper": True, "max_risk": 100, "min_liquidity": 500, "take_profit": 50, "stop_loss": 30},

    # ULTRA DEGEN - Buy ALL new tokens, sell fast
    "sniper_all_in": {"auto": True, "use_sniper": True, "max_risk": 100, "min_liquidity": 100, "take_profit": 30, "stop_loss": 20, "max_hold_hours": 2},
    "sniper_spray": {"auto": True, "use_sniper": True, "max_risk": 100, "min_liquidity": 50, "take_profit": 50, "stop_loss": 25, "max_hold_hours": 4, "allocation_percent": 5},
    "sniper_quickflip": {"auto": True, "use_sniper": True, "max_risk": 100, "min_liquidity": 200, "take_profit": 20, "stop_loss": 15, "max_hold_hours": 1},

    # WHALE COPY TRADING - Follow legendary traders
    "whale_gcr": {"auto": True, "use_whale": True, "whale_ids": ["trader_1"], "take_profit": 50, "stop_loss": 20},
    "whale_hsaka": {"auto": True, "use_whale": True, "whale_ids": ["trader_2"], "take_profit": 30, "stop_loss": 15},
    "whale_cobie": {"auto": True, "use_whale": True, "whale_ids": ["trader_3"], "take_profit": 100, "stop_loss": 25},
    "whale_ansem": {"auto": True, "use_whale": True, "whale_ids": ["trader_4"], "take_profit": 100, "stop_loss": 30},
    "whale_degen": {"auto": True, "use_whale": True, "whale_ids": ["trader_5"], "take_profit": 50, "stop_loss": 25},
    "whale_smart_money": {"auto": True, "use_whale": True, "whale_ids": ["trader_1", "trader_2", "trader_3"], "take_profit": 40, "stop_loss": 20},

    # CONGRESS COPY TRADING - Follow US Congress members (famous for beating the market)
    "congress_pelosi": {"auto": True, "use_whale": True, "whale_ids": ["congress_pelosi"], "take_profit": 50, "stop_loss": 20},
    "congress_tuberville": {"auto": True, "use_whale": True, "whale_ids": ["congress_tuberville"], "take_profit": 40, "stop_loss": 20},
    "congress_crenshaw": {"auto": True, "use_whale": True, "whale_ids": ["congress_crenshaw"], "take_profit": 40, "stop_loss": 20},
    "congress_all": {"auto": True, "use_whale": True, "whale_ids": ["congress_pelosi", "congress_mccaul", "congress_tuberville"], "take_profit": 50, "stop_loss": 20},

    # LEGENDARY INVESTORS - World's best traders/investors
    "legend_buffett": {"auto": True, "use_whale": True, "whale_ids": ["legend_buffett"], "take_profit": 100, "stop_loss": 25},
    "legend_dalio": {"auto": True, "use_whale": True, "whale_ids": ["legend_dalio"], "take_profit": 40, "stop_loss": 15},
    "legend_simons": {"auto": True, "use_whale": True, "whale_ids": ["legend_simons"], "take_profit": 30, "stop_loss": 15},
    "legend_soros": {"auto": True, "use_whale": True, "whale_ids": ["legend_soros"], "take_profit": 50, "stop_loss": 20},
    "legend_burry": {"auto": True, "use_whale": True, "whale_ids": ["legend_burry"], "take_profit": 100, "stop_loss": 30},
    "legend_cathie": {"auto": True, "use_whale": True, "whale_ids": ["legend_cathie"], "take_profit": 100, "stop_loss": 35},
    "legend_ptj": {"auto": True, "use_whale": True, "whale_ids": ["legend_ptj"], "take_profit": 40, "stop_loss": 20},
    "legend_ackman": {"auto": True, "use_whale": True, "whale_ids": ["legend_ackman"], "take_profit": 50, "stop_loss": 20},

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
    # Ichimoku Variants - all performing well
    "ichimoku_scalp": {"auto": True, "use_ichimoku": True, "tenkan": 5, "kijun": 13, "senkou": 26, "rsi_filter": 40},
    "ichimoku_swing": {"auto": True, "use_ichimoku": True, "tenkan": 12, "kijun": 30, "senkou": 60},
    "ichimoku_long": {"auto": True, "use_ichimoku": True, "tenkan": 20, "kijun": 60, "senkou": 120},
    "ichimoku_kumo_break": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52, "kumo_break": True},
    "ichimoku_tk_cross": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52, "tk_cross": True},
    "ichimoku_chikou": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52, "chikou_confirm": True},
    "ichimoku_momentum": {"auto": True, "use_ichimoku": True, "tenkan": 7, "kijun": 22, "senkou": 44, "rsi_filter": 50},
    "ichimoku_conservative": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52, "require_all": True},

    # Martingale - Double down on losses (HIGH RISK!)
    "martingale": {"auto": True, "use_martingale": True, "multiplier": 2.0, "max_levels": 4},
    "martingale_safe": {"auto": True, "use_martingale": True, "multiplier": 1.5, "max_levels": 3},

    # ============ FUNDING RATE STRATEGIES ============
    # Funding Rate Arbitrage - Trade against crowded positions
    "funding_contrarian": {"auto": True, "use_funding": True, "mode": "contrarian"},
    "funding_extreme": {"auto": True, "use_funding": True, "mode": "extreme"},

    # Open Interest Strategies - Follow the smart money
    "oi_breakout": {"auto": True, "use_oi": True, "mode": "breakout"},
    "oi_divergence": {"auto": True, "use_oi": True, "mode": "divergence"},

    # Combined Funding + OI
    "funding_oi_combo": {"auto": True, "use_funding": True, "use_oi": True, "mode": "combo"},

    # ============ ADVANCED STRATEGIES ============

    # Bollinger Squeeze - Trade volatility expansion
    "bollinger_squeeze": {"auto": True, "use_bb_squeeze": True, "squeeze_threshold": 0.5},
    "bollinger_squeeze_tight": {"auto": True, "use_bb_squeeze": True, "squeeze_threshold": 0.3},

    # RSI Divergence - Spot trend reversals
    "rsi_divergence": {"auto": True, "use_rsi_div": True, "lookback": 14},
    "rsi_divergence_fast": {"auto": True, "use_rsi_div": True, "lookback": 7},

    # ADX Trend Strength - Only trade strong trends
    "adx_trend": {"auto": True, "use_adx": True, "threshold": 25},
    "adx_strong": {"auto": True, "use_adx": True, "threshold": 35},

    # MACD Histogram Reversal
    "macd_reversal": {"auto": True, "use_macd": True, "mode": "histogram"},
    "macd_crossover": {"auto": True, "use_macd": True, "mode": "crossover"},

    # Parabolic SAR - Trend following with trailing stops
    "parabolic_sar": {"auto": True, "use_psar": True, "af": 0.02, "max_af": 0.2},
    "parabolic_sar_fast": {"auto": True, "use_psar": True, "af": 0.04, "max_af": 0.3},

    # Williams %R - Momentum oscillator
    "williams_r": {"auto": True, "use_williams": True, "oversold": -80, "overbought": -20},
    "williams_r_extreme": {"auto": True, "use_williams": True, "oversold": -90, "overbought": -10},

    # Donchian Channel Breakout - Turtle trading
    "donchian_breakout": {"auto": True, "use_donchian": True, "period": 20},
    "donchian_fast": {"auto": True, "use_donchian": True, "period": 10},

    # Keltner Channel - ATR-based channel
    "keltner_channel": {"auto": True, "use_keltner": True, "period": 20, "mult": 2.0},
    "keltner_tight": {"auto": True, "use_keltner": True, "period": 10, "mult": 1.5},

    # CCI Momentum - Commodity Channel Index
    "cci_momentum": {"auto": True, "use_cci": True, "oversold": -100, "overbought": 100},
    "cci_extreme": {"auto": True, "use_cci": True, "oversold": -150, "overbought": 150},

    # Aroon Indicator - Trend direction
    "aroon_trend": {"auto": True, "use_aroon": True, "period": 25},
    "aroon_fast": {"auto": True, "use_aroon": True, "period": 14},

    # OBV Trend - On Balance Volume
    "obv_trend": {"auto": True, "use_obv": True, "signal_period": 20},
    "obv_fast": {"auto": True, "use_obv": True, "signal_period": 10},

    # Multi-indicator combos
    "rsi_macd_combo": {"auto": True, "use_rsi": True, "use_macd": True, "mode": "combo"},
    "bb_rsi_combo": {"auto": True, "use_bb": True, "use_rsi": True, "mode": "combo"},
    "trend_momentum": {"auto": True, "use_ema_cross": True, "use_rsi": True, "fast_ema": 9, "slow_ema": 21},

    # Trailing Stop strategies - tight entry, rising stop-loss
    "trailing_tight": {"auto": True, "use_trailing": True, "initial_stop": 2, "trail_pct": 2, "entry_rsi": 35},
    "trailing_medium": {"auto": True, "use_trailing": True, "initial_stop": 3, "trail_pct": 3, "entry_rsi": 40},
    "trailing_wide": {"auto": True, "use_trailing": True, "initial_stop": 5, "trail_pct": 4, "entry_rsi": 45},
    "trailing_scalp": {"auto": True, "use_trailing": True, "initial_stop": 1.5, "trail_pct": 1.5, "entry_rsi": 30},
    "trailing_swing": {"auto": True, "use_trailing": True, "initial_stop": 4, "trail_pct": 5, "entry_rsi": 35},

    # Scalping variants
    "scalp_rsi": {"auto": True, "use_scalp": True, "indicator": "rsi", "timeframe": "5m"},
    "scalp_bb": {"auto": True, "use_scalp": True, "indicator": "bb", "timeframe": "5m"},
    "scalp_macd": {"auto": True, "use_scalp": True, "indicator": "macd", "timeframe": "5m"},

    # Sector-specific
    "defi_hunter": {"auto": True, "sector": "defi", "use_momentum": True},
    "layer2_focus": {"auto": True, "sector": "layer2", "use_momentum": True},
    "gaming_tokens": {"auto": True, "sector": "gaming", "use_momentum": True},
    "ai_tokens": {"auto": True, "sector": "ai", "use_momentum": True},
    "meme_hunter": {"auto": True, "sector": "meme", "use_momentum": True},

    # Risk-adjusted
    "low_risk_dca": {"auto": True, "use_dca": True, "dip_threshold": 5.0, "max_positions": 5},
    "medium_risk_swing": {"auto": True, "use_swing": True, "risk_per_trade": 2},
    "high_risk_leverage": {"auto": True, "use_leverage": True, "leverage": 3, "risk": 5},

    # ============ MORE STRATEGIES ============

    # Pivot Points - Classic S/R levels
    "pivot_classic": {"auto": True, "use_pivot": True, "type": "classic"},
    "pivot_fibonacci": {"auto": True, "use_pivot": True, "type": "fibonacci"},

    # Volume Weighted
    "volume_breakout": {"auto": True, "use_volume": True, "mode": "breakout"},
    "volume_climax": {"auto": True, "use_volume": True, "mode": "climax"},

    # Multi-timeframe
    "mtf_trend": {"auto": True, "use_mtf": True, "timeframes": ["15m", "1h", "4h"]},
    "mtf_momentum": {"auto": True, "use_mtf": True, "mode": "momentum"},

    # Range trading
    "range_sniper": {"auto": True, "use_range": True, "atr_mult": 1.5},
    "range_breakout": {"auto": True, "use_range": True, "mode": "breakout"},

    # Heikin Ashi
    "heikin_ashi": {"auto": True, "use_ha": True, "mode": "trend"},
    "heikin_ashi_reversal": {"auto": True, "use_ha": True, "mode": "reversal"},

    # Order flow
    "orderflow_delta": {"auto": True, "use_orderflow": True, "mode": "delta"},
    "orderflow_imbalance": {"auto": True, "use_orderflow": True, "mode": "imbalance"},

    # Sentiment
    "social_sentiment": {"auto": True, "use_sentiment": True, "source": "social"},
    "fear_greed_extreme": {"auto": True, "use_sentiment": True, "source": "fear_greed"},
}

# Timeframes per strategy type - optimized for each trading style
STRATEGY_TIMEFRAMES = {
    # Fast strategies - M15 (15 minutes)
    "degen_scalp": "15m",
    "degen_full": "15m",
    "stoch_rsi_aggressive": "15m",
    "breakout_tight": "15m",
    "grid_tight": "15m",
    "mean_reversion_tight": "15m",
    "supertrend_fast": "15m",
    "ichimoku_fast": "15m",
    "ichimoku_scalp": "15m",
    "ichimoku_momentum": "15m",

    # Medium strategies - 1H (default)
    "ichimoku_swing": "1h",
    "ichimoku_kumo_break": "1h",
    "ichimoku_tk_cross": "1h",
    "ichimoku_chikou": "1h",
    "degen_momentum": "1h",
    "degen_hybrid": "1h",
    "aggressive": "1h",
    "ema_crossover": "1h",
    "vwap_bounce": "1h",
    "vwap_trend": "1h",
    "supertrend": "1h",
    "stoch_rsi": "1h",
    "breakout": "1h",
    "mean_reversion": "1h",
    "grid_trading": "1h",
    "rsi_strategy": "1h",
    "martingale": "1h",
    "martingale_safe": "1h",
    "sniper_safe": "1h",
    "sniper_degen": "1h",
    "sniper_yolo": "1h",
    "sniper_all_in": "15m",
    "sniper_spray": "15m",
    "sniper_quickflip": "15m",
    "whale_gcr": "1h",
    "whale_hsaka": "15m",
    "whale_cobie": "4h",
    "whale_ansem": "15m",
    "whale_degen": "15m",
    "whale_smart_money": "1h",
    "congress_pelosi": "1h",
    "congress_tuberville": "1h",
    "congress_crenshaw": "1h",
    "congress_all": "1h",
    "legend_buffett": "4h",
    "legend_dalio": "1h",
    "legend_simons": "15m",
    "legend_soros": "1h",
    "legend_burry": "4h",
    "legend_cathie": "1h",
    "legend_ptj": "15m",
    "legend_ackman": "1h",

    # Slow strategies - 4H (trend following)
    "conservative": "4h",
    "confluence_strict": "4h",
    "confluence_normal": "4h",
    "ema_crossover_slow": "4h",
    "ichimoku": "4h",
    "ichimoku_long": "4h",
    "ichimoku_conservative": "4h",
    "dca_fear": "4h",
    "dca_accumulator": "4h",
    "dca_aggressive": "4h",
    "hodl": "4h",
    "god_mode_only": "4h",

    # Funding rate strategies - 1H (funding updates every 8h)
    "funding_contrarian": "1h",
    "funding_extreme": "1h",
    "oi_breakout": "1h",
    "oi_divergence": "1h",
    "funding_oi_combo": "1h",

    # Advanced strategies - Fast (15m)
    "bollinger_squeeze_tight": "15m",
    "rsi_divergence_fast": "15m",
    "parabolic_sar_fast": "15m",
    "williams_r_extreme": "15m",
    "donchian_fast": "15m",
    "keltner_tight": "15m",
    "cci_extreme": "15m",
    "aroon_fast": "15m",
    "obv_fast": "15m",
    "scalp_rsi": "5m",
    "scalp_bb": "5m",
    "scalp_macd": "5m",
    "trailing_scalp": "15m",
    "trailing_tight": "15m",
    "trailing_medium": "1h",
    "trailing_wide": "1h",
    "trailing_swing": "4h",

    # Advanced strategies - Medium (1h)
    "bollinger_squeeze": "1h",
    "rsi_divergence": "1h",
    "adx_trend": "1h",
    "adx_strong": "1h",
    "macd_reversal": "1h",
    "macd_crossover": "1h",
    "parabolic_sar": "1h",
    "williams_r": "1h",
    "donchian_breakout": "1h",
    "keltner_channel": "1h",
    "cci_momentum": "1h",
    "aroon_trend": "1h",
    "obv_trend": "1h",
    "rsi_macd_combo": "1h",
    "bb_rsi_combo": "1h",
    "trend_momentum": "1h",
    "atr_breakout": "1h",
    "atr_trailing": "1h",
    "defi_hunter": "1h",
    "layer2_focus": "1h",
    "gaming_tokens": "1h",
    "ai_tokens": "1h",
    "meme_hunter": "15m",
    "medium_risk_swing": "1h",
    "high_risk_leverage": "1h",

    # Advanced strategies - Slow (4h)
    "low_risk_dca": "4h",
}

DEFAULT_TIMEFRAME = "1h"


def get_strategy_timeframe(strategy_id: str) -> str:
    """Get the optimal timeframe for a strategy"""
    return STRATEGY_TIMEFRAMES.get(strategy_id, DEFAULT_TIMEFRAME)


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


def get_funding_rate(symbol: str) -> dict:
    """Fetch funding rate from Binance Futures API"""
    try:
        # Convert symbol format: BTC/USDT -> BTCUSDT
        futures_symbol = symbol.replace('/', '')
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={futures_symbol}&limit=1"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                rate = float(data[0].get('fundingRate', 0))
                return {
                    'rate': rate * 100,  # Convert to percentage
                    'raw': rate,
                    'timestamp': data[0].get('fundingTime')
                }
    except Exception as e:
        pass  # Silently fail for non-futures pairs
    return {'rate': 0, 'raw': 0, 'timestamp': None}


def get_open_interest(symbol: str) -> dict:
    """Fetch open interest from Binance Futures API"""
    try:
        futures_symbol = symbol.replace('/', '')
        url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={futures_symbol}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data:
                return {
                    'oi': float(data.get('openInterest', 0)),
                    'symbol': data.get('symbol')
                }
    except Exception as e:
        pass  # Silently fail for non-futures pairs
    return {'oi': 0, 'symbol': None}


def get_funding_and_oi(symbol: str) -> dict:
    """Get both funding rate and open interest for a symbol"""
    funding = get_funding_rate(symbol)
    oi = get_open_interest(symbol)

    # Interpret funding rate
    rate = funding['rate']
    if rate > 0.1:
        funding_signal = 'very_positive'  # Many longs, potential dump
    elif rate > 0.05:
        funding_signal = 'positive'
    elif rate < -0.1:
        funding_signal = 'very_negative'  # Many shorts, potential squeeze
    elif rate < -0.05:
        funding_signal = 'negative'
    else:
        funding_signal = 'neutral'

    return {
        'funding_rate': rate,
        'funding_signal': funding_signal,
        'open_interest': oi['oi'],
    }


def safe_print(text: str):
    """Print that handles Unicode on Windows"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'))


def log(message: str):
    """Log to console and file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    safe_print(log_line)

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
    """Save portfolios - PROTECTION ABSOLUE"""
    try:
        os.makedirs("data", exist_ok=True)
        new_count = len(portfolios)

        # PROTECTION ABSOLUE
        if os.path.exists(PORTFOLIOS_FILE):
            try:
                with open(PORTFOLIOS_FILE, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    existing_count = len(existing.get('portfolios', {}))

                    if existing_count > new_count:
                        backup_file = f"data/portfolios_BLOCKED_{existing_count}_vs_{new_count}.json"
                        with open(backup_file, 'w', encoding='utf-8') as bf:
                            json.dump(existing, bf, indent=2, default=str)
                        log(f"🚫 BLOQUÉ! {existing_count} -> {new_count}")
                        return existing.get('portfolios', {}), existing.get('counter', 0)
            except:
                return portfolios, counter  # En cas d'erreur, ne pas risquer

        data = {'portfolios': portfolios, 'counter': counter}
        with open(PORTFOLIOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
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

    # Scalping signals (quick reversals) - ASSOUPLI pour plus de trades
    indicators['scalp_buy'] = indicators['rsi'] < 40 and indicators['momentum_1h'] > 0.1
    indicators['scalp_sell'] = indicators['rsi'] > 60 and indicators['momentum_1h'] < -0.1

    # Momentum signals (riding the wave) - ASSOUPLI pour plus de trades
    indicators['momentum_buy'] = indicators['volume_ratio'] > 1.3 and indicators['momentum_1h'] > 0.3 and indicators['rsi'] < 70
    indicators['momentum_sell'] = indicators['volume_ratio'] > 1.3 and indicators['momentum_1h'] < -0.3 and indicators['rsi'] > 30

    # ============ ADDITIONAL INDICATORS FOR MISSING STRATEGIES ============

    # MACD (12, 26, 9)
    ema_12 = closes.ewm(span=12).mean()
    ema_26 = closes.ewm(span=26).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9).mean()
    macd_hist = macd_line - macd_signal
    indicators['macd'] = macd_line.iloc[-1]
    indicators['macd_signal'] = macd_signal.iloc[-1]
    indicators['macd_histogram'] = macd_hist.iloc[-1]
    indicators['macd_hist_prev'] = macd_hist.iloc[-2] if len(macd_hist) > 1 else 0

    # Bollinger Band Width (for squeeze detection)
    indicators['bb_width'] = (indicators['bb_upper'] - indicators['bb_lower']) / indicators['sma_20'] if indicators['sma_20'] > 0 else 0

    # ADX (Average Directional Index)
    tr1 = highs - lows
    tr2 = abs(highs - closes.shift(1))
    tr3 = abs(lows - closes.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr_14 = tr.rolling(window=14).mean()

    plus_dm = highs.diff()
    minus_dm = -lows.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    plus_di = 100 * (plus_dm.rolling(window=14).mean() / atr_14)
    minus_di = 100 * (minus_dm.rolling(window=14).mean() / atr_14)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 0.0001)
    adx = dx.rolling(window=14).mean()

    indicators['adx'] = adx.iloc[-1] if not pd.isna(adx.iloc[-1]) else 0
    indicators['plus_di'] = plus_di.iloc[-1] if not pd.isna(plus_di.iloc[-1]) else 0
    indicators['minus_di'] = minus_di.iloc[-1] if not pd.isna(minus_di.iloc[-1]) else 0

    # Parabolic SAR (simplified)
    psar = closes.rolling(window=5).min()  # Simplified SAR approximation
    indicators['psar'] = psar.iloc[-1]

    # Williams %R
    highest_high = highs.rolling(window=14).max()
    lowest_low = lows.rolling(window=14).min()
    williams_r = -100 * (highest_high - closes) / (highest_high - lowest_low + 0.0001)
    indicators['williams_r'] = williams_r.iloc[-1] if not pd.isna(williams_r.iloc[-1]) else -50

    # CCI (Commodity Channel Index)
    tp = (highs + lows + closes) / 3
    tp_sma = tp.rolling(window=20).mean()
    tp_mad = tp.rolling(window=20).apply(lambda x: abs(x - x.mean()).mean())
    cci = (tp - tp_sma) / (0.015 * tp_mad + 0.0001)
    indicators['cci'] = cci.iloc[-1] if not pd.isna(cci.iloc[-1]) else 0

    # Donchian Channel
    indicators['donchian_high'] = highs.rolling(window=20).max().iloc[-1]
    indicators['donchian_low'] = lows.rolling(window=20).min().iloc[-1]

    # Keltner Channel
    keltner_mid = closes.ewm(span=20).mean()
    keltner_atr = atr_14 * 2
    indicators['keltner_upper'] = (keltner_mid + keltner_atr).iloc[-1]
    indicators['keltner_lower'] = (keltner_mid - keltner_atr).iloc[-1]

    # Aroon
    aroon_up = 100 * (14 - highs.rolling(window=14).apply(lambda x: 14 - x.argmax() - 1)) / 14
    aroon_down = 100 * (14 - lows.rolling(window=14).apply(lambda x: 14 - x.argmin() - 1)) / 14
    indicators['aroon_up'] = aroon_up.iloc[-1] if not pd.isna(aroon_up.iloc[-1]) else 50
    indicators['aroon_down'] = aroon_down.iloc[-1] if not pd.isna(aroon_down.iloc[-1]) else 50

    # OBV Signal
    obv = (volumes * ((closes > closes.shift(1)).astype(int) * 2 - 1)).cumsum()
    obv_ema = obv.ewm(span=20).mean()
    indicators['obv_signal'] = obv.iloc[-1] - obv_ema.iloc[-1]

    # RSI previous value (for divergence)
    indicators['rsi_prev'] = rsi_values.iloc[-2] if len(rsi_values) > 1 else indicators['rsi']
    indicators['close_prev'] = closes.iloc[-2] if len(closes) > 1 else closes.iloc[-1]

    return indicators


def analyze_crypto(symbol: str, timeframe: str = "1h") -> dict:
    """Analyze a crypto - returns price and all indicators"""
    try:
        # Fetch OHLCV from Binance with specified timeframe
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.replace('/', '')}&interval={timeframe}&limit=100"
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

        # Add funding rate and open interest data (for futures-enabled pairs)
        try:
            funding_oi = get_funding_and_oi(symbol)
            result['funding_rate'] = funding_oi['funding_rate']
            result['funding_signal'] = funding_oi['funding_signal']
            result['open_interest'] = funding_oi['open_interest']
        except:
            result['funding_rate'] = 0
            result['funding_signal'] = 'neutral'
            result['open_interest'] = 0

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

    # Degen strategies - ASSOUPLI pour plus d'action
    if strategy.get('use_degen'):
        mode = strategy.get('mode', 'hybrid')
        mom = analysis.get('momentum_1h', 0)

        if mode == 'scalping':
            # Quick reversals - entries/exits plus frequentes
            if analysis.get('scalp_buy') and has_cash:
                return ('BUY', f"SCALP: RSI={rsi:.0f}<40 + momentum>0.1%")
            elif analysis.get('scalp_sell') and has_position:
                return ('SELL', f"SCALP: RSI={rsi:.0f}>60 + momentum<-0.1%")
            elif has_position and rsi > 50 and mom < 0:
                return ('SELL', f"SCALP EXIT: RSI={rsi:.0f} + momentum negatif")

        elif mode == 'momentum':
            # Ride the wave - volume + momentum
            if analysis.get('momentum_buy') and has_cash:
                return ('BUY', f"MOMENTUM: Vol spike + momentum={mom:.1f}%")
            elif analysis.get('momentum_sell') and has_position:
                return ('SELL', f"MOMENTUM: Vol spike + negative momentum")
            elif has_position and mom < -0.2:
                return ('SELL', f"MOMENTUM LOSS: {mom:.1f}% negatif")

        else:  # hybrid - combines both - le plus actif
            if (analysis.get('scalp_buy') or analysis.get('momentum_buy')) and has_cash:
                return ('BUY', f"HYBRID: Signal detected | RSI={rsi:.0f} | Mom={mom:.1f}%")
            elif has_position:
                if analysis.get('scalp_sell') or analysis.get('momentum_sell'):
                    return ('SELL', f"HYBRID: Exit signal triggered")
                elif rsi > 65 or mom < -0.2:
                    return ('SELL', f"HYBRID: RSI={rsi:.0f} ou Mom={mom:.1f}% negatif")

        return (None, f"DEGEN {mode}: Waiting | RSI={rsi:.0f} | Mom={mom:.1f}%")

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

    # Mean Reversion (normal vs tight) - assoupli (1.5σ au lieu de 2σ)
    if strategy.get('use_mean_rev'):
        std_threshold = strategy.get('std_dev', 1.5)  # 1.5 au lieu de 2.0
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

    # Grid Trading - assoupli (25%/75% au lieu de 15%/85%)
    if strategy.get('use_grid'):
        grid_size = strategy.get('grid_size', 2.0)
        bb_pos = analysis.get('bb_position', 0.5)
        buy_threshold = 0.25 + (grid_size * 0.02)   # 25% au lieu de 15%
        sell_threshold = 0.75 - (grid_size * 0.02)  # 75% au lieu de 85%

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

    # Ichimoku Cloud - Enhanced with variants
    if strategy.get('use_ichimoku'):
        tenkan = strategy.get('tenkan', 9)
        rsi_filter = strategy.get('rsi_filter', 0)
        rsi = analysis.get('rsi', 50)

        # Use fast indicators for tenkan <= 7, normal otherwise
        if tenkan <= 7:
            bullish = analysis.get('ichimoku_bullish_fast', False)
            bearish = analysis.get('ichimoku_bearish_fast', False)
            above = analysis.get('above_cloud_fast', False)
        else:
            bullish = analysis.get('ichimoku_bullish', False)
            bearish = analysis.get('ichimoku_bearish', False)
            above = analysis.get('above_cloud', False)

        # Additional filters for variants
        rsi_ok = rsi > rsi_filter if rsi_filter > 0 else True

        # Kumo breakout - price just broke above cloud
        if strategy.get('kumo_break'):
            price = analysis.get('close', 0)
            cloud_top = max(analysis.get('senkou_a', 0), analysis.get('senkou_b', 0))
            if price > cloud_top * 1.005 and has_cash:  # 0.5% above cloud
                return ('BUY', f"ICHIMOKU KUMO BREAK: Price broke above cloud")

        # TK Cross - Tenkan crosses above Kijun
        if strategy.get('tk_cross'):
            tk = analysis.get('tenkan', 0)
            kj = analysis.get('kijun', 0)
            if tk > kj and above and has_cash:
                return ('BUY', f"ICHIMOKU TK CROSS: Tenkan > Kijun + above cloud")

        # Chikou confirmation - lagging span confirms
        if strategy.get('chikou_confirm'):
            if bullish and above and rsi > 45 and has_cash:
                return ('BUY', f"ICHIMOKU CHIKOU: Bullish + RSI {rsi:.0f} confirms")

        # Conservative - require all conditions
        if strategy.get('require_all'):
            if bullish and above and rsi > 50 and rsi < 70 and has_cash:
                return ('BUY', f"ICHIMOKU SAFE: All conditions met, RSI={rsi:.0f}")
            elif bearish and has_position:
                return ('SELL', f"ICHIMOKU SAFE: Bearish signal")
            return (None, f"ICHIMOKU SAFE: Waiting for all conditions")

        # Standard Ichimoku logic with optional RSI filter
        if bullish and above and rsi_ok and has_cash:
            return ('BUY', f"ICHIMOKU: Bullish + above cloud" + (f" RSI={rsi:.0f}" if rsi_filter else ""))
        elif bearish and has_position:
            return ('SELL', f"ICHIMOKU: Bearish signal")
        cloud_status = "above" if above else "below"
        trend = "bullish" if bullish else ("bearish" if bearish else "neutral")
        return (None, f"ICHIMOKU: {trend}, {cloud_status} cloud")

    # Trailing Stop Strategy - tight entry, rising stop-loss that locks in gains
    if strategy.get('use_trailing'):
        initial_stop = strategy.get('initial_stop', 3)  # Initial stop-loss %
        trail_pct = strategy.get('trail_pct', 3)  # Trailing stop %
        entry_rsi = strategy.get('entry_rsi', 40)  # RSI level to enter
        rsi = analysis.get('rsi', 50)
        current_price = analysis.get('close', 0)
        momentum = analysis.get('momentum', 0)

        if has_position:
            # Get position data
            position = positions.get(symbol, {})
            entry_price = position.get('entry_price', current_price)
            highest_price = position.get('highest_price', entry_price)

            # Update highest price if current is higher
            if current_price > highest_price:
                position['highest_price'] = current_price
                highest_price = current_price

            # Calculate stops
            initial_stop_price = entry_price * (1 - initial_stop / 100)
            trailing_stop_price = highest_price * (1 - trail_pct / 100)

            # Use the higher of the two stops (more protective)
            effective_stop = max(initial_stop_price, trailing_stop_price)

            # Calculate current gain from entry
            gain_pct = ((current_price / entry_price) - 1) * 100 if entry_price > 0 else 0
            gain_from_peak = ((current_price / highest_price) - 1) * 100 if highest_price > 0 else 0

            # SELL if price drops below effective stop
            if current_price <= effective_stop:
                if trailing_stop_price > initial_stop_price:
                    return ('SELL', f"TRAILING STOP HIT: Locked {gain_pct:+.1f}% gain (peak was higher)")
                else:
                    return ('SELL', f"INITIAL STOP HIT: -{initial_stop}% from entry")

            # Status update
            stop_type = "trailing" if trailing_stop_price > initial_stop_price else "initial"
            return (None, f"TRAILING: {gain_pct:+.1f}% gain, {stop_type} stop at ${effective_stop:.4f}")

        else:
            # Entry logic: buy on oversold RSI with positive momentum
            if rsi < entry_rsi and momentum > 0 and has_cash:
                return ('BUY', f"TRAILING ENTRY: RSI={rsi:.0f} < {entry_rsi}, momentum={momentum:.2f}%")
            elif rsi < entry_rsi - 10 and has_cash:  # Very oversold, enter anyway
                return ('BUY', f"TRAILING ENTRY: RSI={rsi:.0f} very oversold")

            return (None, f"TRAILING: Waiting for RSI < {entry_rsi} (currently {rsi:.0f})")

    # ============ MISSING STRATEGY IMPLEMENTATIONS ============

    # MACD Strategy
    if strategy.get('use_macd'):
        macd = analysis.get('macd', 0)
        macd_signal = analysis.get('macd_signal', 0)
        macd_hist = analysis.get('macd_histogram', 0)
        mode = strategy.get('mode', 'crossover')

        if mode == 'crossover':
            if macd > macd_signal and macd_hist > 0 and has_cash:
                return ('BUY', f"MACD CROSS: MACD crossed above signal")
            elif macd < macd_signal and macd_hist < 0 and has_position:
                return ('SELL', f"MACD CROSS: MACD crossed below signal")
        else:  # histogram reversal
            if macd_hist > 0 and analysis.get('macd_hist_prev', 0) < 0 and has_cash:
                return ('BUY', f"MACD REVERSAL: Histogram turned positive")
            elif macd_hist < 0 and analysis.get('macd_hist_prev', 0) > 0 and has_position:
                return ('SELL', f"MACD REVERSAL: Histogram turned negative")
        return (None, f"MACD: hist={macd_hist:.4f}")

    # Bollinger Bands Strategy
    if strategy.get('use_bb'):
        bb_pos = analysis.get('bb_position', 0.5)
        rsi = analysis.get('rsi', 50)

        if strategy.get('mode') == 'combo':
            if bb_pos < 0.2 and rsi < 35 and has_cash:
                return ('BUY', f"BB+RSI: Near lower band + oversold")
            elif bb_pos > 0.8 and rsi > 65 and has_position:
                return ('SELL', f"BB+RSI: Near upper band + overbought")
        else:
            if bb_pos < 0.1 and has_cash:
                return ('BUY', f"BB: Price at lower band ({bb_pos:.2f})")
            elif bb_pos > 0.9 and has_position:
                return ('SELL', f"BB: Price at upper band ({bb_pos:.2f})")
        return (None, f"BB: position={bb_pos:.2f}")

    # Bollinger Squeeze Strategy
    if strategy.get('use_bb_squeeze'):
        bb_width = analysis.get('bb_width', 0)
        squeeze_threshold = strategy.get('threshold', 0.02)
        momentum = analysis.get('momentum', 0)

        if bb_width < squeeze_threshold:
            if momentum > 0.3 and has_cash:
                return ('BUY', f"BB SQUEEZE: Breakout up, momentum={momentum:.2f}%")
            elif momentum < -0.3 and has_position:
                return ('SELL', f"BB SQUEEZE: Breakout down")
        return (None, f"BB SQUEEZE: width={bb_width:.4f}, waiting for squeeze")

    # ADX Trend Strategy
    if strategy.get('use_adx'):
        adx = analysis.get('adx', 0)
        plus_di = analysis.get('plus_di', 0)
        minus_di = analysis.get('minus_di', 0)
        threshold = strategy.get('threshold', 25)

        if adx > threshold:
            if plus_di > minus_di and has_cash:
                return ('BUY', f"ADX TREND: Strong uptrend ADX={adx:.0f}")
            elif minus_di > plus_di and has_position:
                return ('SELL', f"ADX TREND: Strong downtrend ADX={adx:.0f}")
        return (None, f"ADX: {adx:.0f} (need >{threshold} for trend)")

    # Parabolic SAR Strategy
    if strategy.get('use_psar'):
        psar = analysis.get('psar', 0)
        price = analysis.get('close', 0)

        if price > psar and has_cash:
            return ('BUY', f"PSAR: Price above SAR (bullish)")
        elif price < psar and has_position:
            return ('SELL', f"PSAR: Price below SAR (bearish)")
        return (None, f"PSAR: price={price:.2f}, sar={psar:.2f}")

    # Williams %R Strategy
    if strategy.get('use_williams'):
        williams = analysis.get('williams_r', -50)
        oversold = strategy.get('oversold', -80)
        overbought = strategy.get('overbought', -20)

        if williams < oversold and has_cash:
            return ('BUY', f"WILLIAMS: Oversold W%R={williams:.0f}")
        elif williams > overbought and has_position:
            return ('SELL', f"WILLIAMS: Overbought W%R={williams:.0f}")
        return (None, f"WILLIAMS: W%R={williams:.0f}")

    # CCI Strategy
    if strategy.get('use_cci'):
        cci = analysis.get('cci', 0)
        oversold = strategy.get('oversold', -100)
        overbought = strategy.get('overbought', 100)

        if cci < oversold and has_cash:
            return ('BUY', f"CCI: Oversold CCI={cci:.0f}")
        elif cci > overbought and has_position:
            return ('SELL', f"CCI: Overbought CCI={cci:.0f}")
        return (None, f"CCI: {cci:.0f}")

    # Donchian Channel Strategy
    if strategy.get('use_donchian'):
        price = analysis.get('close', 0)
        donchian_high = analysis.get('donchian_high', 0)
        donchian_low = analysis.get('donchian_low', 0)

        if price >= donchian_high * 0.99 and has_cash:
            return ('BUY', f"DONCHIAN: Breakout above channel")
        elif price <= donchian_low * 1.01 and has_position:
            return ('SELL', f"DONCHIAN: Breakdown below channel")
        return (None, f"DONCHIAN: price in channel")

    # Keltner Channel Strategy
    if strategy.get('use_keltner'):
        price = analysis.get('close', 0)
        keltner_upper = analysis.get('keltner_upper', 0)
        keltner_lower = analysis.get('keltner_lower', 0)

        if price <= keltner_lower and has_cash:
            return ('BUY', f"KELTNER: Price at lower band")
        elif price >= keltner_upper and has_position:
            return ('SELL', f"KELTNER: Price at upper band")
        return (None, f"KELTNER: price in channel")

    # Aroon Strategy
    if strategy.get('use_aroon'):
        aroon_up = analysis.get('aroon_up', 50)
        aroon_down = analysis.get('aroon_down', 50)

        if aroon_up > 70 and aroon_down < 30 and has_cash:
            return ('BUY', f"AROON: Strong uptrend (up={aroon_up:.0f})")
        elif aroon_down > 70 and aroon_up < 30 and has_position:
            return ('SELL', f"AROON: Strong downtrend (down={aroon_down:.0f})")
        return (None, f"AROON: up={aroon_up:.0f}, down={aroon_down:.0f}")

    # OBV Strategy
    if strategy.get('use_obv'):
        obv_signal = analysis.get('obv_signal', 0)
        price_trend = analysis.get('ema_9', 0) > analysis.get('ema_21', 0)

        if obv_signal > 0 and price_trend and has_cash:
            return ('BUY', f"OBV: Volume confirms uptrend")
        elif obv_signal < 0 and not price_trend and has_position:
            return ('SELL', f"OBV: Volume confirms downtrend")
        return (None, f"OBV: signal={obv_signal:.0f}")

    # RSI Divergence Strategy
    if strategy.get('use_rsi_div'):
        rsi = analysis.get('rsi', 50)
        rsi_prev = analysis.get('rsi_prev', 50)
        price = analysis.get('close', 0)
        price_prev = analysis.get('close_prev', price)

        # Bullish divergence: price lower low, RSI higher low
        if price < price_prev and rsi > rsi_prev and rsi < 40 and has_cash:
            return ('BUY', f"RSI DIV: Bullish divergence RSI={rsi:.0f}")
        # Bearish divergence: price higher high, RSI lower high
        elif price > price_prev and rsi < rsi_prev and rsi > 60 and has_position:
            return ('SELL', f"RSI DIV: Bearish divergence RSI={rsi:.0f}")
        return (None, f"RSI DIV: watching for divergence")

    # Scalping Strategy
    if strategy.get('use_scalp'):
        indicator = strategy.get('indicator', 'rsi')
        rsi = analysis.get('rsi', 50)
        bb_pos = analysis.get('bb_position', 0.5)
        macd_hist = analysis.get('macd_histogram', 0)

        if indicator == 'rsi':
            if rsi < 25 and has_cash:
                return ('BUY', f"SCALP RSI: Very oversold RSI={rsi:.0f}")
            elif rsi > 75 and has_position:
                return ('SELL', f"SCALP RSI: Very overbought RSI={rsi:.0f}")
        elif indicator == 'bb':
            if bb_pos < 0.05 and has_cash:
                return ('BUY', f"SCALP BB: At lower band")
            elif bb_pos > 0.95 and has_position:
                return ('SELL', f"SCALP BB: At upper band")
        elif indicator == 'macd':
            if macd_hist > 0 and analysis.get('macd_hist_prev', 0) < 0 and has_cash:
                return ('BUY', f"SCALP MACD: Histogram flip positive")
            elif macd_hist < 0 and analysis.get('macd_hist_prev', 0) > 0 and has_position:
                return ('SELL', f"SCALP MACD: Histogram flip negative")
        return (None, f"SCALP: waiting for signal")

    # Momentum/Sector Strategy (for defi_hunter, gaming_tokens, etc.)
    if strategy.get('use_momentum'):
        momentum = analysis.get('momentum', 0)
        rsi = analysis.get('rsi', 50)
        volume_ratio = analysis.get('volume_ratio', 1)

        if momentum > 0.5 and rsi < 60 and volume_ratio > 1.2 and has_cash:
            return ('BUY', f"MOMENTUM: Strong move +{momentum:.2f}% with volume")
        elif momentum < -0.5 and rsi > 40 and has_position:
            return ('SELL', f"MOMENTUM: Weakness -{abs(momentum):.2f}%")
        return (None, f"MOMENTUM: {momentum:+.2f}%")

    # Volume Strategy
    if strategy.get('use_volume'):
        volume_ratio = analysis.get('volume_ratio', 1)
        momentum = analysis.get('momentum', 0)

        if volume_ratio > 2 and momentum > 0.3 and has_cash:
            return ('BUY', f"VOLUME: Spike {volume_ratio:.1f}x with upward move")
        elif volume_ratio > 2 and momentum < -0.3 and has_position:
            return ('SELL', f"VOLUME: Spike {volume_ratio:.1f}x with downward move")
        return (None, f"VOLUME: ratio={volume_ratio:.1f}x")

    # Martingale - assoupli (RSI < 40 au lieu de 35)
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
            if has_cash and rsi < 50:  # 50 au lieu de 45
                portfolio['_martingale_level'] = consecutive_losses
                portfolio['_martingale_multiplier'] = multiplier
                return ('BUY', f"MARTINGALE: Level {consecutive_losses}/{max_levels} | RSI={rsi:.0f}")
        elif consecutive_losses > max_levels:
            if has_cash and rsi < 30:  # 30 au lieu de 25
                portfolio['_martingale_level'] = 0
                return ('BUY', f"MARTINGALE RESET: Max level reached, RSI={rsi:.0f}")

        if rsi < 40 and has_cash:  # 40 au lieu de 35
            portfolio['_martingale_level'] = 0
            return ('BUY', f"MARTINGALE: Normal entry RSI={rsi:.0f} < 40")
        elif rsi > 60 and has_position:  # 60 au lieu de 65
            return ('SELL', f"MARTINGALE: RSI={rsi:.0f} > 60")
        return (None, f"MARTINGALE: RSI={rsi:.0f} | Losses={consecutive_losses}")

    # ============ EXISTING STRATEGIES ============

    # Aggressive Strategy - vraiment agressif (RSI < 45, sell > 55)
    if strategy.get('use_aggressive'):
        mom = analysis.get('momentum_1h', 0)
        if rsi < 45 and has_cash:
            return ('BUY', f"AGGRESSIVE: RSI={rsi:.0f} < 45")
        elif rsi < 50 and mom > 0.2 and has_cash:
            return ('BUY', f"AGGRESSIVE: RSI={rsi:.0f} + momentum={mom:.1f}%")
        elif rsi > 55 and has_position:
            return ('SELL', f"AGGRESSIVE: RSI={rsi:.0f} > 55")
        elif mom < -0.3 and has_position:
            return ('SELL', f"AGGRESSIVE: Momentum={mom:.1f}% negatif")
        return (None, f"AGGRESSIVE: RSI={rsi:.0f} | Mom={mom:.1f}%")

    signal = analysis.get('signal', 'HOLD')

    # RSI Strategy - Classic 30/70 levels
    if strategy.get('use_rsi', False):
        rsi_oversold = config.get('rsi_oversold', 30)  # Classic RSI oversold
        rsi_overbought = config.get('rsi_overbought', 70)  # Classic RSI overbought

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

    # ============ FUNDING RATE & OPEN INTEREST STRATEGIES ============

    # Funding Rate Contrarian - Trade against crowded positions
    if strategy.get('use_funding'):
        funding_rate = analysis.get('funding_rate', 0)
        funding_signal = analysis.get('funding_signal', 'neutral')
        mode = strategy.get('mode', 'contrarian')

        if mode == 'extreme':
            # Only trade on extreme funding rates
            if funding_rate < -0.1 and has_cash:
                return ('BUY', f"FUNDING EXTREME: Rate={funding_rate:.3f}% very negative (shorts crowded)")
            elif funding_rate > 0.1 and has_position:
                return ('SELL', f"FUNDING EXTREME: Rate={funding_rate:.3f}% very positive (longs crowded)")
            return (None, f"FUNDING EXTREME: Rate={funding_rate:.3f}% waiting for extreme")

        elif mode == 'contrarian':
            # Trade against the crowd
            if funding_signal == 'very_negative' and has_cash:
                return ('BUY', f"FUNDING: Rate={funding_rate:.3f}% shorts crowded, expecting squeeze")
            elif funding_signal == 'negative' and has_cash and rsi < 40:
                return ('BUY', f"FUNDING: Rate={funding_rate:.3f}% negative + RSI={rsi:.0f}")
            elif funding_signal == 'very_positive' and has_position:
                return ('SELL', f"FUNDING: Rate={funding_rate:.3f}% longs crowded, expecting dump")
            elif funding_signal == 'positive' and has_position and rsi > 60:
                return ('SELL', f"FUNDING: Rate={funding_rate:.3f}% positive + RSI={rsi:.0f}")
            return (None, f"FUNDING: Rate={funding_rate:.3f}% ({funding_signal}) | RSI={rsi:.0f}")

        elif mode == 'combo':
            # Combined with OI for stronger signals
            oi = analysis.get('open_interest', 0)
            trend = analysis.get('trend', 'neutral')

            if funding_rate < -0.05 and trend == 'bullish' and has_cash:
                return ('BUY', f"FUNDING+OI: Negative funding + bullish trend")
            elif funding_rate > 0.05 and trend == 'bearish' and has_position:
                return ('SELL', f"FUNDING+OI: Positive funding + bearish trend")
            return (None, f"FUNDING+OI: Rate={funding_rate:.3f}% | Trend={trend}")

    # Open Interest Strategies
    if strategy.get('use_oi'):
        oi = analysis.get('open_interest', 0)
        trend = analysis.get('trend', 'neutral')
        mode = strategy.get('mode', 'breakout')

        if mode == 'breakout':
            # Rising OI + bullish = new money entering longs
            if oi > 0 and trend == 'bullish' and has_cash and rsi < 65:
                return ('BUY', f"OI BREAKOUT: Rising OI + bullish trend | RSI={rsi:.0f}")
            elif trend == 'bearish' and has_position:
                return ('SELL', f"OI BREAKOUT: Bearish trend detected")
            return (None, f"OI: Waiting for trend + OI confirmation | Trend={trend}")

        elif mode == 'divergence':
            # Price up but OI down = potential reversal
            change_1h = analysis.get('change_1h', 0)
            if change_1h < -2 and has_cash and rsi < 35:
                return ('BUY', f"OI DIVERGENCE: Price dropped {change_1h:.1f}% | RSI={rsi:.0f}")
            elif change_1h > 2 and has_position and rsi > 70:
                return ('SELL', f"OI DIVERGENCE: Price up {change_1h:.1f}% + overbought")
            return (None, f"OI DIVERGENCE: Change={change_1h:.1f}% | RSI={rsi:.0f}")

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
    analyzed = {}  # (crypto, timeframe) -> analysis

    # Get all unique cryptos and required timeframes
    crypto_timeframes = {}  # crypto -> set of timeframes needed
    for p in portfolios.values():
        if p.get('active', True):
            strategy_id = p.get('strategy_id', 'manual')
            timeframe = get_strategy_timeframe(strategy_id)
            for crypto in p['config'].get('cryptos', []):
                if crypto not in crypto_timeframes:
                    crypto_timeframes[crypto] = set()
                crypto_timeframes[crypto].add(timeframe)

    if not crypto_timeframes:
        debug_log('SYSTEM', 'No cryptos configured in any active portfolio',
                 {'active_portfolios': len([p for p in portfolios.values() if p.get('active')])})

    # Count unique timeframes for logging
    all_timeframes = set()
    for tfs in crypto_timeframes.values():
        all_timeframes.update(tfs)

    log(f"Scanning {len(crypto_timeframes)} cryptos @ {len(all_timeframes)} timeframes ({', '.join(sorted(all_timeframes))})...")

    # Analyze each crypto at each required timeframe
    failed_analyses = []
    for crypto, timeframes in crypto_timeframes.items():
        for timeframe in timeframes:
            analysis = analyze_crypto(crypto, timeframe)
            if analysis:
                analysis['timeframe'] = timeframe  # Store which timeframe was used
                analyzed[(crypto, timeframe)] = analysis
                log(f"  {crypto} [{timeframe}]: ${analysis['price']:,.2f} | RSI {analysis['rsi']:.1f} | {analysis['signal']}")
            else:
                failed_analyses.append(f"{crypto}@{timeframe}")

    if failed_analyses:
        debug_log('API', f'Failed to analyze {len(failed_analyses)} crypto/timeframe pairs',
                 {'failed': failed_analyses[:10], 'total': len(failed_analyses)})

    # Check each portfolio with its strategy's timeframe
    for port_id, portfolio in portfolios.items():
        if not portfolio.get('active', True):
            continue

        strategy_id = portfolio.get('strategy_id', 'manual')
        timeframe = get_strategy_timeframe(strategy_id)

        for crypto in portfolio['config'].get('cryptos', []):
            key = (crypto, timeframe)
            if key not in analyzed:
                continue

            analysis = analyzed[key]

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
    """Scan for new tokens on ALL chains via DexScreener"""
    new_tokens = []

    try:
        from sniper.dexscreener import DexScreenerSniper

        sniper = DexScreenerSniper({
            'min_liquidity': 500,      # $500 min
            'max_age_minutes': 120,    # Max 2h
            'min_volume': 100          # $100 min volume
        })

        # Recuperer les tokens trending/nouveaux
        tokens = sniper.get_trending_new()

        for t in tokens:
            # Calculer risk score
            risk = 50
            if t.liquidity_usd < 5000: risk += 30
            elif t.liquidity_usd > 50000: risk -= 20
            if t.volume_24h < 5000: risk += 15
            elif t.volume_24h > 50000: risk -= 10
            if t.age_minutes < 10: risk += 20  # Tres nouveau = plus risque
            if t.price_change_5m > 100: risk += 15  # Pump violent = risque

            risk = min(100, max(0, risk))

            token = {
                'symbol': t.symbol,
                'name': t.name,
                'address': t.token_address,
                'pair_address': t.pair_address,
                'price': t.price_usd,
                'liquidity': t.liquidity_usd,
                'volume_24h': t.volume_24h,
                'market_cap': t.liquidity_usd * 2,  # Estimation
                'age_hours': t.age_minutes / 60,
                'age_minutes': t.age_minutes,
                'risk_score': risk,
                'dex': t.dex,
                'chain': t.chain,
                'price_change_5m': t.price_change_5m,
                'price_change_1h': t.price_change_1h,
                'buys': t.buys,
                'sells': t.sells,
                'url': t.url
            }
            new_tokens.append(token)

        log(f"🔍 Scanned {len(new_tokens)} new tokens across all chains")

    except Exception as e:
        debug_log('API', 'DexScreener scan failed', {}, error=e)
        log(f"Error scanning new tokens: {e}")

    return new_tokens


# ============ DEX TRADING SIMULATION (PRODUCTION-READY) ============

import random

# Gas fees per chain (in USD) - realistic averages
DEX_GAS_FEES = {
    'solana': 0.01,      # SOL is very cheap
    'bsc': 0.30,         # BSC is cheap
    'polygon': 0.05,     # Polygon is cheap
    'arbitrum': 0.50,    # L2 moderate
    'optimism': 0.40,    # L2 moderate
    'base': 0.30,        # L2 cheap
    'avalanche': 0.50,   # AVAX moderate
    'ethereum': 15.00,   # ETH is expensive (varies a lot)
}

# Minimum trade sizes per chain (to cover gas)
DEX_MIN_TRADE = {
    'solana': 5,         # $5 min
    'bsc': 10,           # $10 min
    'polygon': 5,        # $5 min
    'arbitrum': 20,      # $20 min
    'optimism': 20,      # $20 min
    'base': 15,          # $15 min
    'avalanche': 20,     # $20 min
    'ethereum': 100,     # $100 min (gas is expensive)
}

# Maximum position size as % of liquidity (realistic constraint)
MAX_POSITION_PCT_OF_LIQUIDITY = 0.10  # Max 10% of liquidity

# MEV/Front-running simulation
MEV_CHANCE = 0.15  # 15% chance of being front-run
MEV_EXTRA_SLIPPAGE = 0.03  # 3% extra slippage when front-run

# Transaction failure rates
TX_FAIL_RATE = {
    'solana': 0.03,      # 3% fail (network congestion)
    'bsc': 0.02,         # 2% fail
    'polygon': 0.04,     # 4% fail
    'arbitrum': 0.02,    # 2% fail
    'optimism': 0.02,    # 2% fail
    'base': 0.02,        # 2% fail
    'avalanche': 0.02,   # 2% fail
    'ethereum': 0.05,    # 5% fail (gas price volatility)
}

# Execution delay price change (price moves while tx confirms)
EXECUTION_DELAY_VOLATILITY = 0.02  # 2% max price change during execution

# Token approval tracking (first trade needs approval)
_approved_tokens = set()  # Track which tokens have been approved

def calculate_dex_slippage(trade_size_usd: float, liquidity_usd: float, is_buy: bool = True) -> float:
    """
    Calculate realistic slippage based on trade size vs liquidity.
    Returns slippage as a decimal (e.g., 0.05 = 5%)
    """
    if liquidity_usd <= 0:
        return 0.50  # 50% slippage if no liquidity

    # Price impact = (trade_size / liquidity) * impact_factor
    # Impact is higher for sells (less buyers)
    impact_factor = 0.5 if is_buy else 0.8

    price_impact = (trade_size_usd / liquidity_usd) * impact_factor

    # Base slippage (DEX swap fee ~0.3% + MEV + spread)
    base_slippage = 0.01  # 1% minimum

    # Total slippage capped at 30%
    total_slippage = min(0.30, base_slippage + price_impact)

    return total_slippage

def calculate_dex_fees(chain: str, trade_size_usd: float) -> dict:
    """
    Calculate all DEX trading fees.
    Returns dict with gas, swap_fee, and total
    """
    gas_fee = DEX_GAS_FEES.get(chain, 1.0)

    # DEX swap fee (0.3% typical for Uniswap/Raydium)
    swap_fee = trade_size_usd * 0.003

    return {
        'gas': gas_fee,
        'swap_fee': swap_fee,
        'total': gas_fee + swap_fee
    }

def simulate_rug_pull(risk_score: int, age_minutes: float) -> bool:
    """
    Simulate if a token rugs. Higher risk + newer = more likely to rug.
    Returns True if token rugged.
    """
    import random

    # Base rug chance based on risk score
    if risk_score >= 90:
        base_chance = 0.30  # 30% chance for very risky tokens
    elif risk_score >= 75:
        base_chance = 0.15  # 15% chance
    elif risk_score >= 50:
        base_chance = 0.05  # 5% chance
    else:
        base_chance = 0.01  # 1% chance for safer tokens

    # Newer tokens more likely to rug
    if age_minutes < 10:
        base_chance *= 2
    elif age_minutes < 30:
        base_chance *= 1.5

    return random.random() < base_chance

def get_realistic_entry_price(token_price: float, slippage: float, is_buy: bool) -> float:
    """Get the actual execution price after slippage"""
    if is_buy:
        return token_price * (1 + slippage)  # Pay more when buying
    else:
        return token_price * (1 - slippage)  # Get less when selling


def check_max_position_size(trade_size_usd: float, liquidity_usd: float) -> tuple:
    """
    Check if trade size is realistic vs liquidity.
    Returns (allowed_size, was_reduced, reason)
    """
    if liquidity_usd <= 0:
        return 0, True, "No liquidity"

    max_size = liquidity_usd * MAX_POSITION_PCT_OF_LIQUIDITY

    if trade_size_usd <= max_size:
        return trade_size_usd, False, None

    return max_size, True, f"Reduced to {MAX_POSITION_PCT_OF_LIQUIDITY*100:.0f}% of liquidity (${max_size:.2f})"


def simulate_mev_frontrun(is_buy: bool) -> tuple:
    """
    Simulate MEV bot front-running.
    Returns (was_frontrun, extra_slippage)
    """
    # MEV bots mostly target buys (sandwich attacks)
    if is_buy and random.random() < MEV_CHANCE:
        return True, MEV_EXTRA_SLIPPAGE
    return False, 0


def simulate_transaction_failure(chain: str) -> tuple:
    """
    Simulate transaction failure (network issues, gas issues, etc.)
    Returns (failed, reason)
    """
    fail_rate = TX_FAIL_RATE.get(chain, 0.03)

    if random.random() < fail_rate:
        reasons = [
            "Transaction reverted",
            "Insufficient gas",
            "Slippage tolerance exceeded",
            "Network congestion timeout",
            "RPC node error",
            "Nonce too low"
        ]
        return True, random.choice(reasons)

    return False, None


def simulate_execution_delay(token_price: float) -> float:
    """
    Simulate price change during transaction confirmation.
    Returns new price after delay.
    """
    # Random price movement during execution (can be + or -)
    change = random.uniform(-EXECUTION_DELAY_VOLATILITY, EXECUTION_DELAY_VOLATILITY)
    return token_price * (1 + change)


def calculate_approval_gas(chain: str, token_address: str) -> float:
    """
    Calculate gas for token approval (first trade only).
    Returns approval gas cost, 0 if already approved.
    """
    if token_address in _approved_tokens:
        return 0

    # Approval costs roughly same as a swap
    base_gas = DEX_GAS_FEES.get(chain, 1.0)

    # Mark as approved for future trades
    _approved_tokens.add(token_address)

    return base_gas


def execute_dex_trade_realistic(
    chain: str,
    token_address: str,
    token_price: float,
    trade_size_usd: float,
    liquidity_usd: float,
    is_buy: bool
) -> dict:
    """
    Execute a DEX trade with ALL realistic constraints.
    Returns dict with success, execution details, or failure reason.

    For BUYS: tokens_received, total_cost, execution_price
    For SELLS: net_proceeds, execution_price
    """
    result = {
        'success': False,
        'tx_failed': False,
        'gas_lost': 0,
        'fail_reason': None,
        # Trade details
        'requested_size': trade_size_usd,
        'actual_trade_size': trade_size_usd,
        'execution_price': 0,
        'slippage_pct': 0,
        'total_fees': 0,
        'approval_gas': 0,
        # Buy-specific
        'tokens_received': 0,
        'total_cost': 0,
        # Sell-specific
        'net_proceeds': 0,
        # Flags
        'was_frontrun': False,
        'size_reduced': False,
        'price_changed': False,
        'price_impact_pct': 0,
        'warnings': []
    }

    # 1. Check minimum trade size
    min_trade = DEX_MIN_TRADE.get(chain, 50)
    if trade_size_usd < min_trade:
        result['fail_reason'] = f"Below minimum trade size (${min_trade})"
        return result

    # 2. Check max position size vs liquidity (only for buys)
    if is_buy:
        allowed_size, was_reduced, reduce_reason = check_max_position_size(trade_size_usd, liquidity_usd)
        if allowed_size == 0:
            result['fail_reason'] = reduce_reason
            return result
        if was_reduced:
            result['size_reduced'] = True
            result['warnings'].append(reduce_reason)
            trade_size_usd = allowed_size
            result['actual_trade_size'] = allowed_size

    # 3. Calculate approval gas (first trade only for buys)
    approval_gas = 0
    if is_buy:
        approval_gas = calculate_approval_gas(chain, token_address)
        if approval_gas > 0:
            result['approval_gas'] = approval_gas
            result['warnings'].append(f"First trade: approval gas ${approval_gas:.2f}")

    # 4. Simulate transaction failure
    tx_failed, fail_reason = simulate_transaction_failure(chain)
    if tx_failed:
        gas_lost = DEX_GAS_FEES.get(chain, 1.0) + approval_gas
        result['tx_failed'] = True
        result['gas_lost'] = gas_lost
        result['fail_reason'] = fail_reason
        result['warnings'].append(f"Lost ${gas_lost:.2f} in gas")
        return result

    # 5. Simulate price change during execution
    delayed_price = simulate_execution_delay(token_price)
    price_change_pct = ((delayed_price / token_price) - 1) * 100
    if abs(price_change_pct) > 1:
        result['price_changed'] = True
        result['warnings'].append(f"Price moved {price_change_pct:+.1f}% during execution")

    # 6. Calculate base slippage
    base_slippage = calculate_dex_slippage(trade_size_usd, liquidity_usd, is_buy)

    # 7. Simulate MEV front-running (mostly affects buys)
    was_frontrun, mev_slippage = simulate_mev_frontrun(is_buy)
    if was_frontrun:
        result['was_frontrun'] = True
        result['warnings'].append(f"MEV bot front-ran: +{mev_slippage*100:.1f}% slippage")

    total_slippage = base_slippage + mev_slippage
    result['slippage_pct'] = total_slippage * 100  # as percentage

    # 8. Calculate execution price
    execution_price = get_realistic_entry_price(delayed_price, total_slippage, is_buy)
    result['execution_price'] = execution_price

    # 9. Calculate price impact
    price_impact = abs((execution_price / token_price) - 1) * 100
    result['price_impact_pct'] = price_impact

    # 10. Calculate fees
    fees = calculate_dex_fees(chain, trade_size_usd)
    total_fees = fees['total'] + approval_gas
    result['total_fees'] = total_fees

    # 11. Calculate final amounts
    if is_buy:
        # Buying: spend USDT, receive tokens
        tokens_received = trade_size_usd / execution_price
        total_cost = trade_size_usd + total_fees
        result['tokens_received'] = tokens_received
        result['total_cost'] = total_cost
    else:
        # Selling: trade_size_usd is the gross value of tokens
        # We receive less due to slippage and fees
        net_proceeds = trade_size_usd * (1 - total_slippage) - total_fees
        result['net_proceeds'] = max(0, net_proceeds)

    result['success'] = True
    return result


def check_sniper_positions_realtime(portfolios: dict) -> list:
    """
    Check real prices and detect rugs for all sniper positions.
    Uses DexScreener API to get current prices.
    """
    results = []

    try:
        from sniper.dexscreener import DexScreenerSniper
        sniper = DexScreenerSniper()
    except Exception as e:
        log(f"Error loading DexScreener: {e}")
        return results

    for port_id, portfolio in portfolios.items():
        if not portfolio.get('active', True):
            continue

        strategy_id = portfolio.get('strategy_id', '')
        strategy = STRATEGIES.get(strategy_id, {})

        if not strategy.get('use_sniper', False):
            continue

        # Check each sniper position
        for symbol, pos in list(portfolio['positions'].items()):
            if not pos.get('is_snipe'):
                continue

            token_address = pos.get('address')
            if not token_address:
                continue

            # Get real-time status from DexScreener
            status = sniper.get_token_status(token_address)

            current_price = status['price']
            current_liquidity = status['liquidity']
            is_rugged = status['is_rugged']
            rug_reason = status.get('rug_reason', 'Unknown')

            # Update position with current price
            pos['current_price'] = current_price
            pos['current_liquidity'] = current_liquidity

            entry_price = pos.get('entry_price', 0)
            qty = pos.get('quantity', 0)

            # Handle rug pull
            if is_rugged:
                # Token rugged - lose everything
                asset = symbol.replace('/USDT', '')
                entry_cost = entry_price * qty + pos.get('fees_paid', 0)

                portfolio['balance'][asset] = 0
                del portfolio['positions'][symbol]

                trade = {
                    'timestamp': datetime.now().isoformat(),
                    'action': 'RUGGED',
                    'symbol': symbol,
                    'price': 0,
                    'quantity': qty,
                    'amount_usdt': 0,
                    'pnl': -entry_cost,
                    'reason': f"RUG DETECTED: {rug_reason}"
                }
                portfolio['trades'].append(trade)

                log(f"💀 RUG DETECTED: {symbol} | {rug_reason} | Lost ${entry_cost:.2f} | {portfolio['name']}")
                results.append({'portfolio': portfolio['name'], 'action': 'RUGGED', 'symbol': symbol, 'loss': entry_cost})

            # Check for massive loss (>90% down = effective rug)
            elif current_price > 0 and entry_price > 0:
                pnl_pct = ((current_price / entry_price) - 1) * 100

                if pnl_pct <= -90:  # Down 90%+
                    # Treat as rug - sell at current price
                    chain = pos.get('chain', 'ethereum')
                    fees = calculate_dex_fees(chain, current_price * qty)

                    net_value = (current_price * qty) - fees['total']
                    net_value = max(0, net_value)  # Can't be negative

                    asset = symbol.replace('/USDT', '')
                    portfolio['balance']['USDT'] += net_value
                    portfolio['balance'][asset] = 0
                    del portfolio['positions'][symbol]

                    entry_cost = entry_price * qty + pos.get('fees_paid', 0)
                    real_pnl = net_value - entry_cost

                    trade = {
                        'timestamp': datetime.now().isoformat(),
                        'action': 'DUMP_SOLD',
                        'symbol': symbol,
                        'price': current_price,
                        'quantity': qty,
                        'amount_usdt': net_value,
                        'pnl': real_pnl,
                        'reason': f"DUMPED {pnl_pct:.0f}% - Emergency exit"
                    }
                    portfolio['trades'].append(trade)

                    log(f"📉 DUMP EXIT: {symbol} | {pnl_pct:.0f}% | Got ${net_value:.2f} back | {portfolio['name']}")
                    results.append({'portfolio': portfolio['name'], 'action': 'DUMP_SOLD', 'symbol': symbol})

    return results


def run_sniper_engine(portfolios: dict, new_tokens: list) -> list:
    """Run sniper strategy on new tokens with realistic DEX simulation"""
    results = []

    for port_id, portfolio in portfolios.items():
        if not portfolio.get('active', True):
            continue

        strategy_id = portfolio.get('strategy_id', '')
        strategy = STRATEGIES.get(strategy_id, {})

        if not strategy.get('use_sniper', False):
            continue

        config = portfolio['config']
        # Use STRATEGY defaults, then portfolio config overrides
        max_risk = config.get('max_risk', strategy.get('max_risk', 75))
        min_liquidity = config.get('min_liquidity', strategy.get('min_liquidity', 1000))
        allocation = config.get('allocation_percent', 10)
        max_positions = config.get('max_positions', 20)
        take_profit = config.get('take_profit', 100)  # %
        stop_loss = config.get('stop_loss', 50)  # %

        # Check max positions
        if len(portfolio['positions']) >= max_positions:
            continue

        # Get max hold time
        max_hold_hours = config.get('max_hold_hours', strategy.get('max_hold_hours', 0))

        # Check existing positions for TP/SL/Time exit/Rug
        for symbol, pos in list(portfolio['positions'].items()):
            if pos.get('is_snipe'):
                chain = pos.get('chain', 'ethereum')
                liquidity = pos.get('liquidity_at_entry', 1000)
                risk_score = pos.get('risk_score', 50)

                # Find current price and liquidity
                current_price = pos.get('current_price', pos['entry_price'])
                current_liquidity = liquidity
                token_age = 60  # Default 1 hour

                for token in new_tokens:
                    if token['address'] == pos.get('address'):
                        current_price = token['price']
                        current_liquidity = token['liquidity']
                        token_age = token.get('age_minutes', 60)
                        break

                # Check hold time
                entry_time = datetime.fromisoformat(pos.get('entry_time', datetime.now().isoformat()))
                hold_hours = (datetime.now() - entry_time).total_seconds() / 3600

                # === SIMULATE RUG PULL ===
                if simulate_rug_pull(risk_score, token_age):
                    # Token rugged - lose everything
                    asset = symbol.replace('/USDT', '')
                    qty = pos['quantity']
                    portfolio['balance'][asset] = 0
                    del portfolio['positions'][symbol]

                    trade = {
                        'timestamp': datetime.now().isoformat(),
                        'action': 'SNIPE_RUGGED',
                        'symbol': symbol,
                        'price': 0,
                        'quantity': qty,
                        'amount_usdt': 0,
                        'pnl': -(pos['entry_price'] * qty),
                        'reason': f"RUG PULL | Lost 100% | Risk was {risk_score}/100"
                    }
                    portfolio['trades'].append(trade)
                    log(f"💀 RUGGED: {symbol} | Lost ${pos['entry_price'] * qty:.2f} | {portfolio['name']}")
                    results.append({'portfolio': portfolio['name'], 'action': 'SNIPE_RUGGED', 'symbol': symbol})
                    continue

                if current_price > 0:
                    qty = pos['quantity']
                    gross_value = qty * current_price

                    # Gross PNL (for TP/SL trigger decision)
                    gross_pnl_pct = ((current_price / pos['entry_price']) - 1) * 100

                    should_sell = False
                    sell_reason = ""

                    # Take profit trigger
                    if gross_pnl_pct >= take_profit:
                        should_sell = True
                        sell_reason = f"TP hit {gross_pnl_pct:.1f}%"

                    # Stop loss trigger
                    elif gross_pnl_pct <= -stop_loss:
                        should_sell = True
                        sell_reason = f"SL hit {gross_pnl_pct:.1f}%"

                    # Time-based exit
                    elif max_hold_hours > 0 and hold_hours >= max_hold_hours:
                        should_sell = True
                        sell_reason = f"Time exit {hold_hours:.1f}h"

                    if should_sell:
                        # Execute sell with realistic simulation
                        sell_result = execute_dex_trade_realistic(
                            chain=chain,
                            token_address=pos.get('address', ''),
                            token_price=current_price,
                            trade_size_usd=gross_value,
                            liquidity_usd=current_liquidity,
                            is_buy=False
                        )

                        # Check if sell tx failed
                        if not sell_result['success']:
                            if sell_result.get('tx_failed'):
                                gas_lost = sell_result.get('gas_lost', 0)
                                if gas_lost > 0 and portfolio['balance']['USDT'] >= gas_lost:
                                    portfolio['balance']['USDT'] -= gas_lost
                                    log(f"[SELL TX FAIL] {symbol} | Lost ${gas_lost:.2f} gas | {sell_result.get('fail_reason')} | {portfolio['name']}")
                            continue

                        # Sell succeeded
                        actual_price = sell_result['execution_price']
                        net_value = sell_result['net_proceeds']
                        total_fees = sell_result['total_fees']
                        sell_slippage = sell_result['slippage_pct'] / 100

                        # Calculate real PNL after fees
                        entry_cost = pos['entry_price'] * qty + pos.get('fees_paid', 0)
                        real_pnl = net_value - entry_cost
                        real_pnl_pct = (real_pnl / entry_cost) * 100 if entry_cost > 0 else 0

                        if net_value > total_fees:  # Only if we get something back
                            asset = symbol.replace('/USDT', '')
                            portfolio['balance']['USDT'] += net_value
                            portfolio['balance'][asset] = 0
                            del portfolio['positions'][symbol]

                            # Build detailed reason
                            reason_parts = [sell_reason, f"Net: {real_pnl_pct:.1f}%"]
                            if sell_result.get('price_changed'):
                                reason_parts.append("Price moved during TX")

                            trade = {
                                'timestamp': datetime.now().isoformat(),
                                'action': 'SNIPE_SELL',
                                'symbol': symbol,
                                'price': actual_price,
                                'quantity': qty,
                                'amount_usdt': net_value,
                                'fees': total_fees,
                                'slippage_pct': sell_slippage * 100,
                                'pnl': real_pnl,
                                'reason': " | ".join(reason_parts)
                            }
                            portfolio['trades'].append(trade)

                            pnl_emoji = "[WIN]" if real_pnl >= 0 else "[LOSS]"
                            log(f"{pnl_emoji} SNIPE SELL: {symbol} | PNL: ${real_pnl:+.2f} ({real_pnl_pct:+.1f}%) | Slip: {sell_slippage*100:.1f}% | {portfolio['name']}")
                            results.append({'portfolio': portfolio['name'], 'action': 'SNIPE_SELL', 'symbol': symbol, 'pnl': real_pnl})

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

            # === PRODUCTION-READY DEX SIMULATION ===
            chain = token.get('chain', 'ethereum')

            # Calculate desired trade size
            amount_usdt = portfolio['balance']['USDT'] * (allocation / 100)
            amount_usdt = min(amount_usdt, 500)  # Max $500 per snipe

            # Execute trade with ALL realistic constraints
            trade_result = execute_dex_trade_realistic(
                chain=chain,
                token_address=token['address'],
                token_price=token['price'],
                trade_size_usd=amount_usdt,
                liquidity_usd=token['liquidity'],
                is_buy=True
            )

            # Check if trade failed
            if not trade_result['success']:
                if trade_result.get('tx_failed'):
                    # Transaction failed - log it and count as loss
                    gas_lost = trade_result.get('gas_lost', 0)
                    if gas_lost > 0 and portfolio['balance']['USDT'] >= gas_lost:
                        portfolio['balance']['USDT'] -= gas_lost
                        trade = {
                            'timestamp': datetime.now().isoformat(),
                            'action': 'SNIPE_TX_FAILED',
                            'symbol': symbol,
                            'price': 0,
                            'quantity': 0,
                            'amount_usdt': -gas_lost,
                            'pnl': -gas_lost,
                            'reason': f"TX FAILED: {trade_result.get('fail_reason', 'Unknown')} | Gas lost: ${gas_lost:.2f}"
                        }
                        portfolio['trades'].append(trade)
                        log(f"[TX FAIL] {symbol} | Lost ${gas_lost:.2f} gas | {trade_result.get('fail_reason')} | {portfolio['name']}")
                continue

            # Trade succeeded - apply results
            execution_price = trade_result['execution_price']
            tokens_received = trade_result['tokens_received']
            total_cost = trade_result['total_cost']
            total_fees = trade_result['total_fees']
            slippage = trade_result['slippage_pct'] / 100

            # Check if we have enough balance
            if portfolio['balance']['USDT'] < total_cost:
                continue

            # Deduct from balance
            portfolio['balance']['USDT'] -= total_cost

            asset = token['symbol']
            portfolio['balance'][asset] = portfolio['balance'].get(asset, 0) + tokens_received

            portfolio['positions'][symbol] = {
                'entry_price': execution_price,
                'quantity': tokens_received,
                'entry_time': datetime.now().isoformat(),
                'is_snipe': True,
                'address': token['address'],
                'chain': chain,
                'dex': token['dex'],
                'risk_score': token['risk_score'],
                'liquidity_at_entry': token['liquidity'],
                'slippage_paid': slippage,
                'fees_paid': total_fees,
                'original_price': token['price'],
                'was_frontrun': trade_result.get('was_frontrun', False),
                'size_reduced': trade_result.get('size_reduced', False),
                'had_approval': trade_result.get('approval_gas', 0) > 0
            }

            # Build reason with all simulation details
            reason_parts = [f"DEX Snipe {chain.upper()}"]
            reason_parts.append(f"Slip: {slippage*100:.1f}%")
            reason_parts.append(f"Fees: ${total_fees:.2f}")
            if trade_result.get('was_frontrun'):
                reason_parts.append("FRONTRUN!")
            if trade_result.get('size_reduced'):
                reason_parts.append(f"Size reduced to 10% liq")
            if trade_result.get('approval_gas', 0) > 0:
                reason_parts.append(f"Approval: ${trade_result['approval_gas']:.2f}")
            if trade_result.get('price_impact_pct', 0) > 1:
                reason_parts.append(f"Impact: {trade_result['price_impact_pct']:.1f}%")

            trade = {
                'timestamp': datetime.now().isoformat(),
                'action': 'SNIPE_BUY',
                'symbol': symbol,
                'price': execution_price,
                'quantity': tokens_received,
                'amount_usdt': trade_result['actual_trade_size'],
                'fees': total_fees,
                'slippage_pct': slippage * 100,
                'pnl': 0,
                'token_address': token['address'],
                'chain': chain,
                'dex': token['dex'],
                'risk_score': token['risk_score'],
                'market_cap': token['market_cap'],
                'liquidity': token['liquidity'],
                'was_frontrun': trade_result.get('was_frontrun', False),
                'reason': " | ".join(reason_parts)
            }
            portfolio['trades'].append(trade)

            # Log with details
            log_msg = f"SNIPE: {token['symbol']} @ ${execution_price:.6f}"
            if trade_result.get('was_frontrun'):
                log_msg = f"[FRONTRUN] " + log_msg
            log(f"{log_msg} | Slip: {slippage*100:.1f}% | Fees: ${total_fees:.2f} | {chain} | {portfolio['name']}")
            results.append({'portfolio': portfolio['name'], 'action': 'SNIPE_BUY', 'symbol': symbol, 'token': token})

    return results


def run_whale_engine(portfolios: dict) -> list:
    """Run whale copy-trading strategy"""
    results = []

    try:
        from sniper.whale_tracker import WhaleTracker
        tracker = WhaleTracker()
    except Exception as e:
        log(f"Whale tracker import error: {e}")
        return results

    for port_id, portfolio in portfolios.items():
        if not portfolio.get('active', True):
            continue

        strategy_id = portfolio.get('strategy_id', '')
        strategy = STRATEGIES.get(strategy_id, {})

        if not strategy.get('use_whale', False):
            continue

        config = portfolio['config']
        whale_ids = config.get('whale_ids', strategy.get('whale_ids', []))
        allocation = config.get('allocation_percent', 10)
        take_profit = config.get('take_profit', strategy.get('take_profit', 50))
        stop_loss = config.get('stop_loss', strategy.get('stop_loss', 25))

        # Get whale signals
        try:
            signals = tracker.get_whale_signals(whale_ids)
        except Exception as e:
            log(f"Error getting whale signals for {portfolio['name']}: {e}")
            continue

        # Get current prices
        all_prices = {}
        try:
            response = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=5)
            for p in response.json():
                if p['symbol'].endswith('USDT'):
                    sym = p['symbol'].replace('USDT', '/USDT')
                    all_prices[sym] = float(p['price'])
        except:
            pass

        # Check existing positions for TP/SL
        for symbol, pos in list(portfolio['positions'].items()):
            if pos.get('is_whale_trade'):
                current_price = all_prices.get(symbol, pos['entry_price'])
                if current_price > 0:
                    pnl_pct = ((current_price / pos['entry_price']) - 1) * 100

                    if pnl_pct >= take_profit:
                        result = execute_trade(portfolio, 'SELL', symbol, current_price)
                        if result['success']:
                            log(f"🐋 WHALE TP: {symbol} +{pnl_pct:.1f}% [{portfolio['name']}]")
                            results.append({'portfolio': portfolio['name'], 'action': 'WHALE_SELL_TP', 'symbol': symbol})

                    elif pnl_pct <= -stop_loss:
                        result = execute_trade(portfolio, 'SELL', symbol, current_price)
                        if result['success']:
                            log(f"🐋 WHALE SL: {symbol} {pnl_pct:.1f}% [{portfolio['name']}]")
                            results.append({'portfolio': portfolio['name'], 'action': 'WHALE_SELL_SL', 'symbol': symbol})

        # Execute new whale signals
        for signal in signals:
            if signal['action'] != 'BUY':
                continue

            symbol = signal['symbol']
            if symbol not in all_prices:
                continue

            # Skip if already have position
            if symbol in portfolio['positions']:
                continue

            # Check balance
            if portfolio['balance']['USDT'] < 100:
                continue

            # Only act on high confidence signals
            if signal.get('confidence', 0) < 60:
                continue

            # Calculate amount
            price = all_prices[symbol]
            amount_usdt = portfolio['balance']['USDT'] * (allocation / 100)
            amount_usdt = min(amount_usdt, 500)

            if amount_usdt < 50:
                continue

            # Execute buy
            qty = amount_usdt / price
            asset = symbol.split('/')[0]

            portfolio['balance']['USDT'] -= amount_usdt
            portfolio['balance'][asset] = portfolio['balance'].get(asset, 0) + qty

            portfolio['positions'][symbol] = {
                'entry_price': price,
                'quantity': qty,
                'entry_time': datetime.now().isoformat(),
                'is_whale_trade': True,
                'whale': signal['whale'],
                'confidence': signal['confidence']
            }

            trade = {
                'timestamp': datetime.now().isoformat(),
                'action': 'WHALE_BUY',
                'symbol': symbol,
                'price': price,
                'quantity': qty,
                'amount_usdt': amount_usdt,
                'pnl': 0,
                'whale': signal['whale'],
                'reason': signal['reason']
            }
            portfolio['trades'].append(trade)

            log(f"🐋 WHALE BUY: {symbol} @ ${price:.4f} | {signal['whale']} ({signal['confidence']}%) | {portfolio['name']}")
            results.append({'portfolio': portfolio['name'], 'action': 'WHALE_BUY', 'symbol': symbol, 'whale': signal['whale']})

    return results


def main():
    """Main bot loop - All-in-one trading engine"""
    safe_print("\n" + "=" * 60)
    safe_print("  TRADING BOT - FULL DEGEN EDITION")
    safe_print("  Dashboard: http://localhost:8501")
    safe_print("  Ctrl+C to stop")
    safe_print("=" * 60)
    safe_print("  Strategies: Conservative | Aggressive | RSI | Confluence")
    safe_print("  Degen: Scalping | Momentum | Hybrid | Full Degen")
    safe_print("  Sniper: Safe | Degen | YOLO (New Token Hunter)")
    safe_print("=" * 60 + "\n")

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
        status = "[ON]" if p.get('active', True) else "[OFF]"
        strategy = p.get('strategy_id', 'manual')
        is_sniper = "[SNIPE]" if STRATEGIES.get(strategy, {}).get('use_sniper') else ""
        log(f"  {status} {is_sniper} {p['name']} [{strategy}]")

    safe_print("=" * 60)
    log(f"Starting unified bot loop (scan every {SCAN_INTERVAL}s)...")
    safe_print("=" * 60)

    scan_count = 0
    sniper_tokens_seen = set()

    # Initialize debug state
    debug_update_bot_status(running=True, scan_count=0)

    try:
        while True:
            scan_count += 1
            scan_start = time.time()
            log(f"\n{'='*20} SCAN #{scan_count} {'='*20}")

            # Update status at START of scan (heartbeat)
            debug_update_bot_status(running=True, scan_count=scan_count)

            # Reload portfolios
            portfolios, counter = load_portfolios()
            active_portfolios = len([p for p in portfolios.values() if p.get('active', True)])

            total_results = []
            cryptos_scanned = 0
            api_errors = 0

            # 1. Classic trading engine (existing cryptos)
            try:
                log("📊 Scanning existing cryptos...")
                classic_results = run_engine(portfolios)
                total_results.extend(classic_results)

                # Log trades to debug
                for r in classic_results:
                    debug_log_trade(r['portfolio'], r['action'], r['crypto'], r['price'], r['reason'])

            except Exception as e:
                debug_log('SYSTEM', 'Classic engine crashed', {'scan': scan_count}, error=e)
                classic_results = []
                api_errors += 1

            # 2. Sniper engine (new tokens)
            try:
                log("🎯 Scanning for new tokens...")
                new_tokens = scan_new_tokens()

                # Filter out already seen tokens
                fresh_tokens = [t for t in new_tokens if t['address'] not in sniper_tokens_seen]
                for t in fresh_tokens:
                    sniper_tokens_seen.add(t['address'])
                    log(f"  🆕 {t['symbol']} | ${t['price']:.8f} | MC: ${t['market_cap']:,.0f} | Risk: {t['risk_score']}/100 | {t['dex']}")

                # Check real prices and detect rugs for existing positions
                log("🔍 Checking sniper positions (real prices)...")
                rug_results = check_sniper_positions_realtime(portfolios)
                total_results.extend(rug_results)
                if rug_results:
                    log(f"  ⚠️ {len(rug_results)} positions closed (rugs/dumps)")

                sniper_results = run_sniper_engine(portfolios, new_tokens)
                total_results.extend(sniper_results)

                # Log sniper trades
                for r in sniper_results:
                    if 'token' in r:
                        debug_log_trade(r['portfolio'], r['action'], r['symbol'], r['token']['price'], 'Sniper')

            except Exception as e:
                debug_log('SYSTEM', 'Sniper engine crashed', {'scan': scan_count}, error=e)
                sniper_results = []
                fresh_tokens = []
                api_errors += 1

            # 3. Whale copy-trading engine
            whale_results = []
            try:
                log("🐋 Checking whale signals...")
                whale_results = run_whale_engine(portfolios)
                total_results.extend(whale_results)

                for r in whale_results:
                    if 'whale' in r:
                        debug_log_trade(r['portfolio'], r['action'], r['symbol'], 0, f"Whale: {r['whale']}")

            except Exception as e:
                debug_log('SYSTEM', 'Whale engine crashed', {'scan': scan_count}, error=e)
                whale_results = []
                api_errors += 1

            # Save if any changes
            if total_results:
                save_portfolios(portfolios, counter)
                log(f"💾 Saved {len(total_results)} trades")

            # Summary
            scan_duration = time.time() - scan_start
            log(f"📈 Classic: {len(classic_results)} | 🎯 Sniper: {len(sniper_results)} | 🐋 Whale: {len(whale_results)} | 🆕 New: {len(fresh_tokens)}")

            # Calculate timeframes used
            timeframes_used = set()
            for p in portfolios.values():
                if p.get('active', True):
                    timeframes_used.add(get_strategy_timeframe(p.get('strategy_id', 'manual')))

            # Update debug state with scan info
            debug_update_bot_status(running=True, scan_count=scan_count)
            debug_update_scan({
                'scan_number': scan_count,
                'duration_seconds': round(scan_duration, 2),
                'active_portfolios': active_portfolios,
                'timeframes': sorted(list(timeframes_used)),
                'classic_trades': len(classic_results),
                'sniper_trades': len(sniper_results),
                'new_tokens_found': len(fresh_tokens),
                'total_tokens_seen': len(sniper_tokens_seen),
                'api_errors': api_errors
            })

            # Record portfolio values for history charts
            try:
                record_portfolio_values(portfolios)
                log("📊 Portfolio history recorded")
            except Exception as e:
                log(f"Warning: Could not record history: {e}")

            # Wait
            log(f"⏳ Next scan in {SCAN_INTERVAL}s...")
            time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        log("\n🛑 Bot stopped by user")
        debug_update_bot_status(running=False, scan_count=scan_count)
        save_portfolios(portfolios, counter)
        log("💾 Final state saved")
    except Exception as e:
        debug_log('SYSTEM', 'Main loop crashed', {'scan': scan_count}, error=e)
        debug_update_bot_status(running=False, scan_count=scan_count)
        log(f"FATAL ERROR: {e}")
        save_portfolios(portfolios, counter)


if __name__ == "__main__":
    main()
