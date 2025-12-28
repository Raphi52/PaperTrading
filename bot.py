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
import random
from datetime import datetime
from pathlib import Path

# REAL DATA - No simulation
try:
    from core.real_data import get_real_alpha_signal, get_fear_greed_real, get_funding_rates_real
    from core.risk_manager import get_risk_manager, check_trade_risk, get_optimal_size
    REAL_DATA_ENABLED = True
    RISK_ENABLED = True
except ImportError as e:
    print(f"[WARNING] Real data/risk modules not loaded: {e}")
    REAL_DATA_ENABLED = False
    RISK_ENABLED = False

# SQLite Database for trade history
try:
    from core.database import insert_trade_from_dict
    DB_ENABLED = True
except ImportError as e:
    print(f"[WARNING] Database module not loaded: {e}")
    DB_ENABLED = False
    def insert_trade_from_dict(*args, **kwargs):
        pass

# Auto-update crypto list
try:
    from core.auto_update_cryptos import run_auto_update, should_update
    AUTO_UPDATE_ENABLED = True
except ImportError as e:
    print(f"[WARNING] Auto-update module not loaded: {e}")
    AUTO_UPDATE_ENABLED = False


# Max trades to keep in JSON (for dashboard display)
MAX_TRADES_IN_JSON = 500


def record_trade(portfolio: dict, trade: dict):
    """Record trade to both JSON (limited) and SQLite (unlimited)"""
    # Generate unique trade ID if not present
    if 'id' not in trade:
        import hashlib
        ts = trade.get('timestamp', datetime.now().isoformat())
        unique_str = f"{portfolio.get('id', '')}-{ts}-{trade.get('symbol', '')}-{random.random()}"
        trade['id'] = 'T' + hashlib.md5(unique_str.encode()).hexdigest()[:8].upper()

    # Add to portfolio JSON (keep last 50)
    if 'trades' not in portfolio:
        portfolio['trades'] = []
    portfolio['trades'] = (portfolio['trades'] + [trade])[-MAX_TRADES_IN_JSON:]

    # Also save to SQLite for permanent history
    if DB_ENABLED:
        try:
            insert_trade_from_dict(
                portfolio_id=portfolio.get('id', 'unknown'),
                portfolio_name=portfolio.get('name', 'Unknown'),
                strategy_id=portfolio.get('strategy_id', 'manual'),
                trade=trade
            )
        except Exception as e:
            print(f"[DB] Error recording trade: {e}")


# Fallback functions if real data not available
if not REAL_DATA_ENABLED:
    def get_real_alpha_signal():
        return {'action': 'HOLD', 'confidence': 0, 'reasons': [], 'source': 'unavailable'}

if not RISK_ENABLED:
    def check_trade_risk(portfolio, action, amount):
        return True, "OK"
    def get_optimal_size(portfolio, analysis):
        return 5.0

# Legacy compatibility
ALPHA_ENABLED = REAL_DATA_ENABLED
def get_alpha_signal(symbol='BTC/USDT'):
    return get_real_alpha_signal()
def get_alpha_boost(symbol='BTC/USDT'):
    signal = get_real_alpha_signal()
    if signal['action'] == 'STRONG_BUY':
        return (1.3, "Real data: Strong buy signal")
    elif signal['action'] == 'BUY':
        return (1.15, "Real data: Buy signal")
    elif signal['action'] == 'STRONG_SELL':
        return (0.5, "Real data: Strong sell - reducing size")
    elif signal['action'] == 'SELL':
        return (0.7, "Real data: Sell signal")
    return (1.0, "Real data: Neutral")

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

# BTC reference cache for beta lag strategies
_btc_cache = {
    'change_1h': 0,
    'change_24h': 0,
    'price': 0,
    'last_update': 0
}


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


# ============ SMART TRADING FILTERS ============

# Risky tokens to avoid for non-degen strategies
RISKY_TOKEN_PATTERNS = ['PEPE', 'SHIB', 'DOGE', 'FLOKI', 'BONK', 'WIF', 'MEME', 'BOME', 'COQ', 'SLERF']
SAFE_MAJOR_TOKENS = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOT', 'LINK', 'MATIC', 'UNI', 'AAVE', 'LTC']

# SCAM TOKEN PATTERNS - Avoid these for snipers (based on common rug patterns)
SCAM_TOKEN_PATTERNS = [
    # Celebrity/influencer tokens (almost always rugs)
    'TRUMP', 'ELON', 'MUSK', 'JAKE', 'PAUL', 'LOGAN', 'TATE', 'KARDASHIAN', 'KANYE', 'YE',
    # Obvious scam keywords
    'SCAM', 'RUG', 'HONEYPOT', 'SAFE', 'MOON', '100X', '1000X', 'RICH', 'LAMBO',
    # Copycat/fake tokens
    'FAKE', 'REAL', 'TRUE', 'OFFICIAL', 'V2', 'V3', 'NEW', 'ORIGINAL',
    # Drug/explicit (often rugs)
    'WEED', 'DRUG', 'SEX', 'PORN', 'XXX', 'NSFW',
    # Misc red flags
    'FREE', 'AIRDROP', 'GIVEAWAY', 'WIN', 'LUCKY', 'CASINO', 'BET',
    # Animal memes (oversaturated, many rugs)
    'INU', 'CAT', 'DOG', 'FROG', 'PIG', 'COW', 'HAMSTER',
]


def is_scam_token(symbol: str) -> tuple:
    """
    Check if token name matches common scam patterns.
    Returns (is_scam, reason)
    """
    asset = symbol.split('/')[0].upper()

    for pattern in SCAM_TOKEN_PATTERNS:
        if pattern in asset:
            return (True, f"Token name contains '{pattern}' - likely scam")

    # Check for very short names (often rugs)
    if len(asset) <= 2:
        return (True, f"Token name too short ({asset}) - suspicious")

    # Check for names starting with $ (memecoin convention, higher risk)
    if asset.startswith('$'):
        return (True, f"Token starts with $ - high rug risk")

    return (False, None)


def is_safe_for_strategy(symbol: str, strategy: dict) -> bool:
    """Check if token is safe for the given strategy"""
    asset = symbol.split('/')[0].upper()

    # Degen/sniper strategies can trade anything
    if strategy.get('use_degen') or strategy.get('use_sniper') or strategy.get('use_whale'):
        return True

    # Conservative strategies only trade majors
    if strategy.get('buy_on') == ["STRONG_BUY"]:  # Conservative/confluence_strict
        return asset in SAFE_MAJOR_TOKENS

    # Block risky memecoins for regular strategies
    for risky in RISKY_TOKEN_PATTERNS:
        if risky in asset:
            return False

    return True


def should_skip_pump_chase(analysis: dict, strategy: dict) -> tuple:
    """
    Don't buy coins that already pumped too much.
    Returns (should_skip, reason)
    """
    # Degen strategies are allowed to chase pumps
    if strategy.get('use_degen') or strategy.get('use_sniper') or strategy.get('use_whale'):
        return (False, None)

    momentum_1h = analysis.get('momentum_1h', 0)
    change_24h = analysis.get('change_24h', 0)

    # Don't buy if already up >10% in last hour (was 5%)
    if momentum_1h > 10:
        return (True, f"Already pumped +{momentum_1h:.1f}% in 1h - too late")

    # Don't buy if up >30% in 24h (was 15%)
    if change_24h > 30:
        return (True, f"Already pumped +{change_24h:.1f}% in 24h - overextended")

    return (False, None)


def check_trend_alignment(analysis: dict, strategy: dict) -> tuple:
    """
    Check if trend supports the trade direction.
    Returns (is_aligned, reason)
    DISABLED: In bear markets this blocks all entries - now always returns True
    """
    # DISABLED - Allow all entries regardless of trend
    # In a bear market, this filter was blocking ALL trades
    # RSI and other indicators are better for timing entries
    return (True, None)


def calculate_smart_position_size(portfolio: dict, analysis: dict, strategy: dict = None, base_percent: float = 10) -> float:
    """
    Calculate position size based on volatility, confidence, and signal quality.
    Returns percentage of portfolio to allocate.
    """
    atr_pct = analysis.get('atr_percent', 2)  # Default 2% ATR
    rsi = analysis.get('rsi', 50)

    # Base allocation from config or default
    allocation = base_percent

    # 1. Adjust for volatility (ATR)
    if atr_pct > 4:
        allocation *= 0.5  # Half size for very volatile
    elif atr_pct > 3:
        allocation *= 0.75
    elif atr_pct < 1.5:
        allocation *= 1.25  # Slightly larger for low volatility

    # 2. Adjust for RSI quality (extreme = better entry)
    if rsi < 25:  # Very oversold = excellent entry
        allocation *= 1.3
    elif rsi < 35:  # Oversold = good entry
        allocation *= 1.15
    elif rsi > 75:  # Overbought = risky entry
        allocation *= 0.6
    elif rsi > 65:
        allocation *= 0.8

    # 3. Adjust for signal confluence (multiple indicators agreeing)
    confluence_score = 0
    if analysis.get('ema_cross_up') or analysis.get('ema_cross_up_slow'):
        confluence_score += 1
    if analysis.get('supertrend_up'):
        confluence_score += 1
    if analysis.get('ichimoku_bullish'):
        confluence_score += 1
    if analysis.get('bb_position', 0.5) < 0.3:  # Near lower band
        confluence_score += 1
    if analysis.get('stoch_rsi', 50) < 25:
        confluence_score += 1

    # More confluence = larger position
    if confluence_score >= 4:
        allocation *= 1.4  # 4+ signals = 40% more
    elif confluence_score >= 3:
        allocation *= 1.25  # 3 signals = 25% more
    elif confluence_score >= 2:
        allocation *= 1.1  # 2 signals = 10% more
    elif confluence_score == 0:
        allocation *= 0.7  # No confluence = 30% less

    # 4. Adjust for volume confirmation
    volume_ratio = analysis.get('volume_ratio', 1.0)
    if volume_ratio > 2.0:  # High volume = strong signal
        allocation *= 1.2
    elif volume_ratio < 0.5:  # Low volume = weak signal
        allocation *= 0.7

    # 5. Adjust for trend strength (ADX if available)
    adx = analysis.get('adx', 25)
    if adx > 40:  # Strong trend
        allocation *= 1.15
    elif adx < 20:  # Weak/no trend
        allocation *= 0.85

    # 6. ALPHA SIGNAL BOOST - Real edge from whale/liquidation/flow data
    if ALPHA_ENABLED:
        try:
            symbol = analysis.get('symbol', 'BTC/USDT')
            alpha_mult, alpha_reason = get_alpha_boost(symbol)
            allocation *= alpha_mult
            if alpha_mult != 1.0:
                log(f"  [ALPHA] {alpha_reason} (mult: {alpha_mult:.2f})")
        except Exception as e:
            pass  # Silent fail for alpha

    # Cap between 5% min and 25% max per position
    return max(5, min(allocation, 25))


def get_trailing_stop(entry_price: float, current_price: float, highest_price: float,
                       initial_sl_pct: float = 10, trail_pct: float = 5) -> tuple:
    """
    Calculate trailing stop loss.
    Returns (stop_price, triggered, reason)
    """
    if entry_price <= 0 or current_price <= 0:
        return (0, False, None)

    pnl_pct = ((current_price / entry_price) - 1) * 100

    # If in profit, use trailing stop
    if pnl_pct > 0 and highest_price > entry_price:
        # Trail from highest price
        trail_stop = highest_price * (1 - trail_pct / 100)

        if current_price <= trail_stop:
            return (trail_stop, True, f"TRAILING STOP: Price dropped {trail_pct}% from high ${highest_price:.4f}")

    # If in loss, use regular stop loss
    stop_price = entry_price * (1 - initial_sl_pct / 100)
    if current_price <= stop_price:
        return (stop_price, True, f"STOP LOSS: Down {-pnl_pct:.1f}% (limit {initial_sl_pct}%)")

    return (stop_price, False, None)


def should_take_partial_profit(entry_price: float, current_price: float,
                                 partial_taken: bool, first_target_pct: float = 15) -> tuple:
    """
    Check if we should take partial profit (sell 50% at first target).
    Returns (should_sell, percent_to_sell, reason)
    """
    if entry_price <= 0 or current_price <= 0 or partial_taken:
        return (False, 0, None)

    pnl_pct = ((current_price / entry_price) - 1) * 100

    # First target hit - sell 50%
    if pnl_pct >= first_target_pct:
        return (True, 50, f"PARTIAL TP: +{pnl_pct:.1f}% hit first target {first_target_pct}%")

    return (False, 0, None)


# ============ ADVANCED TRADING FILTERS ============

def check_rsi_entry_quality(rsi: float, strategy: dict) -> tuple:
    """
    Check if RSI supports a good entry.
    Returns (is_good_entry, quality_score, reason)
    RELAXED: Now allows entries up to RSI 75 (was 60)
    """
    # Degen strategies can ignore RSI
    if strategy.get('use_degen') or strategy.get('use_sniper'):
        return (True, 1.0, None)

    # Optimal buy zones - RELAXED
    if rsi < 30:
        return (True, 1.3, f"RSI {rsi:.0f} - Oversold, excellent entry")
    elif rsi < 45:  # Was 40
        return (True, 1.1, f"RSI {rsi:.0f} - Good entry zone")
    elif rsi < 55:  # Was 50
        return (True, 1.0, f"RSI {rsi:.0f} - Neutral entry")
    elif rsi < 65:  # Was 60
        return (True, 0.9, f"RSI {rsi:.0f} - Slightly high but OK")
    elif rsi < 75:  # Was 70 - now we allow these
        return (True, 0.7, f"RSI {rsi:.0f} - High but acceptable")
    else:
        return (False, 0.4, f"RSI {rsi:.0f} - Too overbought, skip")


def check_volume_confirmation(analysis: dict, strategy: dict) -> tuple:
    """
    Check if volume supports the trade.
    Returns (has_volume, reason)
    """
    # Skip for degen/sniper
    if strategy.get('use_degen') or strategy.get('use_sniper'):
        return (True, None)

    volume_ratio = analysis.get('volume_ratio', 1.0)  # Current vs average

    # RELAXED: Only reject very low volume (was 0.5)
    if volume_ratio < 0.3:
        return (False, f"Very low volume ({volume_ratio:.1f}x avg) - no conviction")
    elif volume_ratio > 1.5:
        return (True, f"Good volume ({volume_ratio:.1f}x avg) - confirmed")

    return (True, None)


def detect_market_regime(btc_data: dict) -> str:
    """
    Detect overall market regime based on BTC.
    Returns: 'bull', 'bear', or 'sideways'
    """
    if not btc_data:
        return 'sideways'

    change_24h = btc_data.get('change_24h', 0)
    change_7d = btc_data.get('change_7d', 0)
    rsi = btc_data.get('rsi', 50)
    ema_9 = btc_data.get('ema_9', 0)
    ema_21 = btc_data.get('ema_21', 0)
    price = btc_data.get('price', 0)

    # Strong bull: Price above EMAs, positive momentum, RSI healthy
    if price > ema_9 > ema_21 and change_24h > 2 and rsi > 50:
        return 'bull'

    # Strong bear: Price below EMAs, negative momentum
    if price < ema_9 < ema_21 and change_24h < -2 and rsi < 50:
        return 'bear'

    return 'sideways'


def get_regime_multiplier(regime: str, strategy: dict) -> float:
    """
    Get position size multiplier based on market regime.
    """
    # Degen strategies ignore regime
    if strategy.get('use_degen') or strategy.get('use_sniper'):
        return 1.0

    if regime == 'bull':
        return 1.2  # Larger positions in bull market
    elif regime == 'bear':
        return 0.5  # Smaller positions in bear market
    else:
        return 0.8  # Cautious in sideways


def check_loss_cooldown(portfolio: dict, cooldown_hours: float = 1) -> tuple:
    """
    Check if portfolio should pause after consecutive losses.
    Returns (should_pause, reason)
    RELAXED: Now requires 5 losses (was 3) and only 1h cooldown (was 2h)
    """
    trades = portfolio.get('trades', [])
    if len(trades) < 3:
        return (False, None)

    # Check last 5 trades
    recent_trades = trades[-5:]
    consecutive_losses = 0

    for trade in reversed(recent_trades):
        if trade.get('pnl', 0) < 0:
            consecutive_losses += 1
        else:
            break

    # Pause after 5 consecutive losses (was 3)
    if consecutive_losses >= 5:
        last_trade_time = trades[-1].get('timestamp', '')
        if last_trade_time:
            try:
                last_time = datetime.fromisoformat(last_trade_time)
                hours_since = (datetime.now() - last_time).total_seconds() / 3600
                if hours_since < cooldown_hours:
                    return (True, f"COOLDOWN: {consecutive_losses} losses in a row, wait {cooldown_hours - hours_since:.1f}h")
            except:
                pass

    return (False, None)


def get_dynamic_tp_sl(analysis: dict, base_tp: float, base_sl: float) -> tuple:
    """
    Calculate dynamic TP/SL based on ATR (volatility).
    Returns (tp_pct, sl_pct)
    """
    atr_pct = analysis.get('atr_percent', 2.0)

    # Scale TP/SL with volatility
    # High ATR = wider stops, Low ATR = tighter stops
    volatility_mult = max(0.5, min(2.0, atr_pct / 2.0))

    dynamic_tp = base_tp * volatility_mult
    dynamic_sl = base_sl * volatility_mult

    # Maintain at least 1.5:1 reward-to-risk
    if dynamic_tp < dynamic_sl * 1.5:
        dynamic_tp = dynamic_sl * 1.5

    return (round(dynamic_tp, 1), round(dynamic_sl, 1))


def calculate_win_streak_bonus(portfolio: dict) -> float:
    """
    Calculate position size bonus based on win streak.
    Returns multiplier (1.0 to 1.5)
    """
    trades = portfolio.get('trades', [])
    if len(trades) < 3:
        return 1.0

    # Count recent wins
    win_streak = 0
    for trade in reversed(trades[-5:]):
        if trade.get('pnl', 0) > 0:
            win_streak += 1
        else:
            break

    # Bonus: 5% per win, max 50%
    bonus = min(1.5, 1.0 + (win_streak * 0.1))
    return bonus


def check_correlation_limit(portfolio: dict, symbol: str, max_correlated: int = 4) -> tuple:
    """
    Check if adding this position would over-expose to correlated assets.
    Returns (is_ok, reason)
    """
    # Define correlated groups
    CORRELATION_GROUPS = {
        'BTC_RELATED': ['BTC', 'WBTC', 'BTCB'],
        'ETH_RELATED': ['ETH', 'WETH', 'STETH', 'CBETH'],
        'MEME_COINS': ['DOGE', 'SHIB', 'PEPE', 'FLOKI', 'BONK', 'WIF', 'MEME'],
        'DEFI_BLUE': ['UNI', 'AAVE', 'COMP', 'MKR', 'SNX', 'CRV'],
        'LAYER2': ['MATIC', 'ARB', 'OP', 'IMX', 'METIS'],
        'SOLANA_ECO': ['SOL', 'RAY', 'SRM', 'MNGO', 'ORCA'],
    }

    asset = symbol.split('/')[0].upper()

    # Find which group this asset belongs to
    asset_group = None
    for group_name, assets in CORRELATION_GROUPS.items():
        if asset in assets:
            asset_group = group_name
            break

    if not asset_group:
        return (True, None)  # Not in any correlated group

    # Count existing positions in same group
    positions = portfolio.get('positions', {})
    correlated_count = 0

    for pos_symbol in positions.keys():
        pos_asset = pos_symbol.split('/')[0].upper()
        if pos_asset in CORRELATION_GROUPS.get(asset_group, []):
            correlated_count += 1

    if correlated_count >= max_correlated:
        return (False, f"Already {correlated_count} {asset_group} positions (max {max_correlated})")

    return (True, None)


def detect_market_regime(analysis: dict) -> dict:
    """
    Detect current market regime to adapt strategy.
    Returns: regime type, strength, and recommended approach
    """
    rsi = analysis.get('rsi', 50)
    stoch = analysis.get('stoch_rsi', 50)
    bb_pos = analysis.get('bb_position', 0.5)
    mom_1h = analysis.get('momentum_1h', 0)
    mom_4h = analysis.get('momentum_4h', 0)
    volume_ratio = analysis.get('volume_ratio', 1.0)
    trend = analysis.get('trend', 'neutral')
    atr_pct = analysis.get('atr_percent', 2.0)

    # Detect regime
    if abs(mom_4h) > 3 and volume_ratio > 1.5:
        regime = 'TRENDING'
        strength = min(abs(mom_4h) / 5, 1.0)
        direction = 'UP' if mom_4h > 0 else 'DOWN'
    elif atr_pct > 4 and volume_ratio > 2:
        regime = 'VOLATILE'
        strength = min(atr_pct / 6, 1.0)
        direction = 'NEUTRAL'
    elif 0.3 < bb_pos < 0.7 and abs(mom_1h) < 1:
        regime = 'RANGING'
        strength = 1 - abs(bb_pos - 0.5) * 2
        direction = 'NEUTRAL'
    elif rsi < 25 or rsi > 75:
        regime = 'EXTREME'
        strength = abs(rsi - 50) / 50
        direction = 'OVERSOLD' if rsi < 25 else 'OVERBOUGHT'
    else:
        regime = 'NORMAL'
        strength = 0.5
        direction = trend.upper()

    return {
        'regime': regime,
        'strength': strength,
        'direction': direction,
        'rsi': rsi,
        'stoch': stoch,
        'bb_pos': bb_pos,
        'mom_1h': mom_1h,
        'volume': volume_ratio
    }


def detect_reversal_pattern(analysis: dict) -> dict:
    """
    ADVANCED PATTERN DETECTION
    Detects multiple reversal and continuation patterns for optimal entries.
    """
    # Get all indicators
    rsi = analysis.get('rsi', 50)
    rsi_prev = analysis.get('rsi_prev', rsi)
    stoch = analysis.get('stoch_rsi', 50)
    stoch_prev = analysis.get('stoch_rsi_prev', stoch)
    bb_pos = analysis.get('bb_position', 0.5)
    bb_width = analysis.get('bb_width', 0.05)
    mom_1h = analysis.get('momentum_1h', 0)
    mom_4h = analysis.get('momentum_4h', 0)
    volume_ratio = analysis.get('volume_ratio', 1.0)
    vwap_dev = analysis.get('vwap_deviation', 0)
    macd = analysis.get('macd', 0)
    macd_signal = analysis.get('macd_signal', 0)
    macd_hist = analysis.get('macd_histogram', 0)
    macd_hist_prev = analysis.get('macd_hist_prev', macd_hist)
    ema_9 = analysis.get('ema_9', 0)
    ema_21 = analysis.get('ema_21', 0)
    price = analysis.get('price', 0)
    high = analysis.get('high_24h', price)
    low = analysis.get('low_24h', price)
    atr_pct = analysis.get('atr_percent', 2.0)

    patterns = []
    bullish_score = 0
    bearish_score = 0
    pattern_details = {}

    # ============ BULLISH PATTERNS ============

    # 1. RSI BULLISH DIVERGENCE (price lower, RSI higher)
    # Strong signal when RSI makes higher low while price makes lower low
    if rsi < 40 and rsi > rsi_prev and mom_1h < 0:
        patterns.append('RSI_BULL_DIV')
        bullish_score += 25
        pattern_details['RSI_BULL_DIV'] = f"RSI rising ({rsi_prev:.0f}→{rsi:.0f}) while price falling"

    # 2. STOCH RSI HOOK FROM OVERSOLD
    # Stoch turning up from extreme oversold
    if stoch < 20 and stoch > stoch_prev and stoch_prev < 15:
        patterns.append('STOCH_HOOK_UP')
        bullish_score += 20
        pattern_details['STOCH_HOOK_UP'] = f"Stoch reversing from {stoch_prev:.0f} to {stoch:.0f}"

    # 3. MACD BULLISH CROSSOVER
    # MACD line crossing above signal line
    if macd > macd_signal and macd_hist > 0 and macd_hist_prev <= 0:
        patterns.append('MACD_CROSS_UP')
        bullish_score += 20
        pattern_details['MACD_CROSS_UP'] = "MACD crossed above signal"

    # 4. MACD HISTOGRAM REVERSAL
    # Histogram turning positive after being negative
    if macd_hist > macd_hist_prev and macd_hist_prev < 0 and macd_hist > -0.5:
        patterns.append('MACD_HIST_REV')
        bullish_score += 15
        pattern_details['MACD_HIST_REV'] = f"Histogram improving {macd_hist_prev:.2f}→{macd_hist:.2f}"

    # 5. BOLLINGER BAND BOUNCE
    # Price touching lower band and bouncing with volume
    if bb_pos < 0.1 and mom_1h > 0 and volume_ratio > 1.0:
        patterns.append('BB_BOUNCE')
        bullish_score += 25
        pattern_details['BB_BOUNCE'] = f"Bouncing from BB bottom with {volume_ratio:.1f}x volume"

    # 6. BOLLINGER SQUEEZE BREAKOUT UP
    # Tight bands expanding upward
    if bb_width < 0.03 and mom_1h > 0.3 and bb_pos > 0.5:
        patterns.append('BB_SQUEEZE_UP')
        bullish_score += 30
        pattern_details['BB_SQUEEZE_UP'] = "Squeeze breakout to upside"

    # 7. VWAP RECLAIM
    # Price reclaiming VWAP from below with momentum
    if vwap_dev > -0.5 and vwap_dev < 1.0 and mom_1h > 0.2:
        if analysis.get('vwap_dev_prev', vwap_dev) < -1:
            patterns.append('VWAP_RECLAIM')
            bullish_score += 20
            pattern_details['VWAP_RECLAIM'] = "Price reclaiming VWAP"

    # 8. VOLUME CLIMAX BOTTOM (Capitulation)
    # Extreme volume spike at lows = potential capitulation
    if volume_ratio > 2.5 and rsi < 30 and mom_1h > -0.5:
        patterns.append('VOLUME_CLIMAX')
        bullish_score += 30
        pattern_details['VOLUME_CLIMAX'] = f"Capitulation volume {volume_ratio:.1f}x with RSI={rsi:.0f}"

    # 9. HIGHER LOW FORMING
    # Price above recent low with RSI/Stoch improving
    if bb_pos > 0.15 and bb_pos < 0.4 and rsi > rsi_prev and stoch > stoch_prev:
        patterns.append('HIGHER_LOW')
        bullish_score += 15
        pattern_details['HIGHER_LOW'] = "Potential higher low forming"

    # 10. EMA SUPPORT BOUNCE
    # Price bouncing off EMA21 support
    if price > ema_21 and ema_9 > ema_21 and bb_pos < 0.35:
        patterns.append('EMA_SUPPORT')
        bullish_score += 15
        pattern_details['EMA_SUPPORT'] = "Holding EMA21 support"

    # 11. MOMENTUM SHIFT (4h down, 1h up)
    # Short-term recovery while still in 4h downtrend
    if mom_4h < -1.5 and mom_1h > 0.5:
        patterns.append('MOM_SHIFT_UP')
        bullish_score += 20
        pattern_details['MOM_SHIFT_UP'] = f"1h recovery ({mom_1h:+.1f}%) vs 4h ({mom_4h:+.1f}%)"

    # 12. TRIPLE OVERSOLD
    # Multiple indicators all oversold together
    oversold_count = sum([rsi < 30, stoch < 20, bb_pos < 0.15, vwap_dev < -2])
    if oversold_count >= 3:
        patterns.append('TRIPLE_OVERSOLD')
        bullish_score += 25
        pattern_details['TRIPLE_OVERSOLD'] = f"{oversold_count} indicators oversold"

    # 13. BULLISH ENGULFING (approximation with momentum)
    # Strong reversal candle pattern
    if mom_1h > 1.0 and rsi < 45 and volume_ratio > 1.5:
        patterns.append('BULL_ENGULF')
        bullish_score += 20
        pattern_details['BULL_ENGULF'] = f"Strong reversal candle +{mom_1h:.1f}%"

    # 14. HAMMER PATTERN (approximation)
    # Price near low but closing higher with volume
    price_range = high - low if high > low else 1
    if low > 0 and price > 0:
        wick_ratio = (price - low) / price_range if price_range > 0 else 0
        if wick_ratio > 0.6 and rsi < 40 and mom_1h > 0:
            patterns.append('HAMMER')
            bullish_score += 20
            pattern_details['HAMMER'] = "Hammer candle pattern"

    # ============ BEARISH PATTERNS ============

    # 1. RSI BEARISH DIVERGENCE
    if rsi > 60 and rsi < rsi_prev and mom_1h > 0:
        patterns.append('RSI_BEAR_DIV')
        bearish_score += 25
        pattern_details['RSI_BEAR_DIV'] = f"RSI falling ({rsi_prev:.0f}→{rsi:.0f}) while price rising"

    # 2. STOCH RSI HOOK DOWN FROM OVERBOUGHT
    if stoch > 80 and stoch < stoch_prev and stoch_prev > 85:
        patterns.append('STOCH_HOOK_DOWN')
        bearish_score += 20
        pattern_details['STOCH_HOOK_DOWN'] = f"Stoch reversing from {stoch_prev:.0f}"

    # 3. MACD BEARISH CROSSOVER
    if macd < macd_signal and macd_hist < 0 and macd_hist_prev >= 0:
        patterns.append('MACD_CROSS_DOWN')
        bearish_score += 20
        pattern_details['MACD_CROSS_DOWN'] = "MACD crossed below signal"

    # 4. BOLLINGER BAND REJECTION
    if bb_pos > 0.9 and mom_1h < 0 and volume_ratio > 1.0:
        patterns.append('BB_REJECTION')
        bearish_score += 25
        pattern_details['BB_REJECTION'] = "Rejected from BB top"

    # 5. LOWER HIGH FORMING
    if bb_pos < 0.85 and bb_pos > 0.6 and rsi < rsi_prev and stoch < stoch_prev:
        patterns.append('LOWER_HIGH')
        bearish_score += 15
        pattern_details['LOWER_HIGH'] = "Potential lower high forming"

    # 6. TRIPLE OVERBOUGHT
    overbought_count = sum([rsi > 70, stoch > 80, bb_pos > 0.85, vwap_dev > 2])
    if overbought_count >= 3:
        patterns.append('TRIPLE_OVERBOUGHT')
        bearish_score += 25
        pattern_details['TRIPLE_OVERBOUGHT'] = f"{overbought_count} indicators overbought"

    # 7. BEARISH ENGULFING
    if mom_1h < -1.0 and rsi > 55 and volume_ratio > 1.5:
        patterns.append('BEAR_ENGULF')
        bearish_score += 20
        pattern_details['BEAR_ENGULF'] = f"Strong reversal candle {mom_1h:.1f}%"

    # ============ CALCULATE SIGNAL STRENGTH ============

    # Bonus for multiple aligned patterns
    if len([p for p in patterns if 'BULL' in p or 'UP' in p or 'BOUNCE' in p or 'HAMMER' in p or 'OVERSOLD' in p or 'HIGHER' in p or 'SUPPORT' in p or 'RECLAIM' in p or 'CLIMAX' in p]) >= 3:
        bullish_score += 15  # Multi-pattern bonus

    if len([p for p in patterns if 'BEAR' in p or 'DOWN' in p or 'REJECTION' in p or 'OVERBOUGHT' in p or 'LOWER' in p]) >= 3:
        bearish_score += 15

    # Determine final signal
    if bullish_score >= 50 and bullish_score > bearish_score + 20:
        signal = 'STRONG_BUY'
    elif bullish_score >= 35 and bullish_score > bearish_score:
        signal = 'BUY'
    elif bearish_score >= 50 and bearish_score > bullish_score + 20:
        signal = 'STRONG_SELL'
    elif bearish_score >= 35 and bearish_score > bullish_score:
        signal = 'SELL'
    else:
        signal = 'HOLD'

    return {
        'patterns': patterns,
        'bullish_score': bullish_score,
        'bearish_score': bearish_score,
        'signal': signal,
        'strength': max(bullish_score, bearish_score),
        'details': pattern_details,
        'pattern_count': len(patterns)
    }


def calculate_confluence_score(analysis: dict, strategy: dict = None) -> dict:
    """
    ADVANCED CONFLUENCE SYSTEM
    Calculates a smart entry score based on multiple aligned signals.
    Only triggers when multiple independent indicators agree.
    """
    rsi = analysis.get('rsi', 50)
    stoch = analysis.get('stoch_rsi', 50)
    bb_pos = analysis.get('bb_position', 0.5)
    mom_1h = analysis.get('momentum_1h', 0)
    mom_4h = analysis.get('momentum_4h', 0)
    volume_ratio = analysis.get('volume_ratio', 1.0)
    trend = analysis.get('trend', 'neutral')
    vwap_dev = analysis.get('vwap_deviation', 0)

    # Get market regime and reversal patterns
    regime = detect_market_regime(analysis)
    reversal = detect_reversal_pattern(analysis)

    # ============ BULLISH CONFLUENCE ============
    bullish_signals = 0
    bullish_reasons = []

    # Category 1: Oversold indicators (need 2+ to confirm)
    oversold_count = 0
    if rsi < 35:
        oversold_count += 1
        bullish_reasons.append(f"RSI={rsi:.0f}")
    if stoch < 30:
        oversold_count += 1
        bullish_reasons.append(f"Stoch={stoch:.0f}")
    if bb_pos < 0.2:
        oversold_count += 1
        bullish_reasons.append(f"BB={bb_pos:.0%}")
    if vwap_dev < -2:
        oversold_count += 1
        bullish_reasons.append(f"VWAP={vwap_dev:.1f}%")

    if oversold_count >= 2:
        bullish_signals += oversold_count * 10

    # Category 2: Momentum turning up
    if mom_1h > 0 and mom_4h < 0:  # Short-term recovery
        bullish_signals += 15
        bullish_reasons.append(f"MomShift")
    elif mom_1h > 0.2:
        bullish_signals += 10
        bullish_reasons.append(f"Mom+")

    # Category 3: Volume confirmation
    if volume_ratio > 1.3 and mom_1h > 0:
        bullish_signals += 15
        bullish_reasons.append(f"Vol={volume_ratio:.1f}x")

    # Category 4: Trend support
    if trend == 'bullish':
        bullish_signals += 10
        bullish_reasons.append("Trend↑")
    elif trend == 'neutral' and mom_1h > 0:
        bullish_signals += 5

    # Category 5: Reversal patterns
    if reversal['bullish_score'] > 30:
        bullish_signals += reversal['bullish_score'] // 2
        bullish_reasons.extend(reversal['patterns'][:2])

    # Category 6: Market regime bonus
    if regime['regime'] == 'EXTREME' and regime['direction'] == 'OVERSOLD':
        bullish_signals += 20
        bullish_reasons.append("Extreme↓")

    # ============ BEARISH PENALTIES ============
    # Reduce score if bearish signals present
    if rsi > 70:
        bullish_signals -= 20
    if mom_1h < -1:
        bullish_signals -= 15
    if trend == 'bearish' and mom_4h < -2:
        bullish_signals -= 25
    if regime['regime'] == 'VOLATILE' and mom_1h < 0:
        bullish_signals -= 15

    # ============ FINAL SCORE ============
    score = max(0, min(100, bullish_signals))

    # Determine action
    if score >= 60:
        action = 'STRONG_BUY'
        min_confirmations = 4
    elif score >= 45:
        action = 'BUY'
        min_confirmations = 3
    elif score >= 30:
        action = 'WEAK_BUY'
        min_confirmations = 2
    else:
        action = 'NO_ENTRY'
        min_confirmations = 0

    # Final check: must have minimum unique confirmations
    actual_confirmations = len(bullish_reasons)
    if actual_confirmations < min_confirmations:
        action = 'NO_ENTRY'
        score = min(score, 25)

    return {
        'score': score,
        'action': action,
        'confirmations': actual_confirmations,
        'min_required': min_confirmations,
        'reasons': bullish_reasons,
        'regime': regime['regime'],
        'reversal_patterns': reversal['patterns']
    }


def get_best_entry_score(analysis: dict, strategy: dict, portfolio: dict) -> dict:
    """
    Calculate overall entry quality using advanced confluence system.
    """
    # Use the new confluence system
    confluence = calculate_confluence_score(analysis, strategy)

    # Map to old format for compatibility
    score = confluence['score']

    if confluence['action'] == 'STRONG_BUY':
        recommendation = "STRONG_BUY"
    elif confluence['action'] == 'BUY':
        recommendation = "BUY"
    elif confluence['action'] == 'WEAK_BUY':
        recommendation = "NEUTRAL"
    else:
        recommendation = "SKIP"

    return {
        'score': score,
        'factors': confluence['reasons'],
        'recommendation': recommendation,
        'confluence': confluence
    }


# ============ POSITION ROTATION ============

def find_worst_position(portfolio: dict, current_prices: dict = None) -> tuple:
    """
    Find the worst performing position in a portfolio.
    Returns (symbol, position, pnl_pct) or (None, None, 0) if no positions.
    """
    positions = portfolio.get('positions', {})
    if not positions:
        return (None, None, 0)

    worst_symbol = None
    worst_pos = None
    worst_pnl = float('inf')

    for symbol, pos in positions.items():
        # Skip shorts (handled differently)
        if pos.get('type') == 'SHORT':
            continue

        entry_price = pos.get('entry_price', 0)
        if entry_price <= 0:
            continue

        # Get current price
        current_price = pos.get('current_price', entry_price)
        if current_prices and symbol in current_prices:
            current_price = current_prices[symbol]

        # Calculate PnL %
        pnl_pct = ((current_price - entry_price) / entry_price) * 100

        if pnl_pct < worst_pnl:
            worst_pnl = pnl_pct
            worst_symbol = symbol
            worst_pos = pos

    return (worst_symbol, worst_pos, worst_pnl)


def should_rotate_position(portfolio: dict, new_opportunity_score: int, analysis: dict, strategy: dict) -> tuple:
    """
    Determine if we should close worst position for a better opportunity.
    Returns (should_rotate, worst_symbol, reason)
    """
    config = portfolio.get('config', {})

    # Check if rotation is enabled (default: True for aggressive strategies)
    rotation_enabled = config.get('position_rotation', True)
    if not rotation_enabled:
        return (False, None, "Rotation disabled")

    # Find worst position
    worst_symbol, worst_pos, worst_pnl = find_worst_position(portfolio)
    if not worst_symbol:
        return (False, None, "No positions to rotate")

    # Rotation thresholds
    min_score_advantage = config.get('rotation_min_score', 25)  # New opp must be 25+ better
    max_loss_to_keep = config.get('rotation_max_loss', -3)  # Auto-rotate if position is -3%+

    # Case 1: Worst position is at significant loss - always rotate for better opp
    if worst_pnl <= max_loss_to_keep and new_opportunity_score >= 50:
        return (True, worst_symbol, f"Rotating {worst_symbol} ({worst_pnl:.1f}%) for better opportunity (score: {new_opportunity_score})")

    # Case 2: New opportunity is significantly better
    # Estimate worst position's "score" based on its current state
    worst_score = max(0, 50 + worst_pnl * 2)  # Rough estimate: 0% = 50, -5% = 40, +5% = 60

    score_advantage = new_opportunity_score - worst_score
    if score_advantage >= min_score_advantage:
        return (True, worst_symbol, f"Rotating {worst_symbol} (score ~{worst_score:.0f}) for better opportunity (score: {new_opportunity_score})")

    return (False, None, f"Not worth rotating (advantage: {score_advantage:.0f} < {min_score_advantage})")


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
    "manuel": {"auto": False, "tooltip": "Trading manuel - aucune exécution automatique"},
    "manual": {"auto": False, "tooltip": "Manual trading - no auto execution"},

    # Confluence strategies
    "confluence_strict": {"auto": True, "buy_on": ["STRONG_BUY"], "sell_on": ["STRONG_SELL"], "take_profit": 30, "stop_loss": 15, "tooltip": "Attend signaux STRONG uniquement - très sélectif"},
    "confluence_normal": {"auto": True, "buy_on": ["BUY", "STRONG_BUY"], "sell_on": ["SELL", "STRONG_SELL"], "take_profit": 25, "stop_loss": 12, "tooltip": "Confluence multi-indicateurs - signaux BUY/SELL"},

    # Classic strategies
    "conservative": {"auto": True, "buy_on": ["STRONG_BUY"], "sell_on": ["STRONG_SELL"], "take_profit": 20, "stop_loss": 10, "tooltip": "Approche prudente - signaux forts uniquement"},
    "aggressive": {"auto": True, "use_aggressive": True, "take_profit": 50, "stop_loss": 25, "tooltip": "Trading agressif - RSI relaxé, gros gains visés"},
    "god_mode_only": {"auto": True, "buy_on": ["GOD_MODE_BUY"], "sell_on": [], "take_profit": 100, "stop_loss": 30, "tooltip": "Attend le signal parfait (tous indicateurs alignés)"},
    "hodl": {"auto": True, "buy_on": ["ALWAYS_FIRST"], "sell_on": [], "take_profit": 200, "stop_loss": 50, "tooltip": "Buy & Hold long terme - TP élevé"},

    # BTC CORRELATION / BETA LAG STRATEGIES (Long only)
    "btc_beta_lag": {"auto": True, "use_btc_lag": True, "min_btc_gain": 1.0, "max_alt_gain": 0.3, "take_profit": 12, "stop_loss": 6, "tooltip": "Achète altcoins en retard sur BTC (BTC +1%, alt <0.3%)"},
    "btc_beta_lag_aggressive": {"auto": True, "use_btc_lag": True, "min_btc_gain": 0.5, "max_alt_gain": 0.1, "take_profit": 8, "stop_loss": 4, "tooltip": "Beta lag agressif - écarts plus petits"},
    "btc_beta_lag_safe": {"auto": True, "use_btc_lag": True, "min_btc_gain": 2.0, "max_alt_gain": 0.5, "take_profit": 15, "stop_loss": 8, "tooltip": "Beta lag conservateur - gros écarts seulement"},

    # SHORT STRATEGIES (Paper shorting) - DAY TRADING (TP 8-12%, SL 4-6%)
    "btc_beta_lag_short": {"auto": True, "use_btc_lag_short": True, "min_btc_drop": 1.0, "max_alt_drop": 0.3, "take_profit": 8, "stop_loss": 4, "can_short": True, "tooltip": "SHORT altcoins en retard sur baisse BTC"},
    "rsi_short": {"auto": True, "use_rsi_short": True, "overbought": 75, "take_profit": 10, "stop_loss": 5, "can_short": True, "tooltip": "SHORT quand RSI > 75 + patterns bearish"},
    "rsi_short_aggressive": {"auto": True, "use_rsi_short": True, "overbought": 70, "take_profit": 6, "stop_loss": 3, "can_short": True, "tooltip": "SHORT agressif RSI > 70"},
    "mean_reversion_short": {"auto": True, "use_mean_rev_short": True, "std_dev": 2.0, "take_profit": 8, "stop_loss": 4, "can_short": True, "tooltip": "SHORT les pumps excessifs (+2 std dev)"},

    # Indicator-based - SWING (TP 15-20%, SL 8-10%)
    "rsi_strategy": {"auto": True, "use_rsi": True, "take_profit": 18, "stop_loss": 9, "tooltip": "RSI <30 buy, >70 sell - oscillateur classique"},
    "dca_fear": {"auto": True, "use_fear_greed": True, "take_profit": 25, "stop_loss": 12, "tooltip": "Achète quand Fear & Greed < 25 (peur extrême)"},

    # DEGEN STRATEGIES - Fast exits (SCALP/DAY)
    "degen_scalp": {"auto": True, "use_degen": True, "mode": "scalping", "take_profit": 6, "stop_loss": 5, "max_hold_hours": 2, "tooltip": "Scalping rapide - SL élargi"},
    "degen_momentum": {"auto": True, "use_degen": True, "mode": "momentum", "take_profit": 15, "stop_loss": 7, "max_hold_hours": 6, "tooltip": "Suit le momentum - trades directionnels"},
    "degen_hybrid": {"auto": True, "use_degen": True, "mode": "hybrid", "take_profit": 10, "stop_loss": 5, "max_hold_hours": 4, "tooltip": "Mix scalping + momentum"},
    "degen_full": {"auto": True, "use_degen": True, "mode": "hybrid", "risk": 20, "take_profit": 20, "stop_loss": 10, "max_hold_hours": 8, "tooltip": "Mode DEGEN complet - risque élevé"},

    # SNIPER STRATEGIES - QUICK FLIP (TP 8-15%, SL 4-8%)
    "sniper_safe": {"auto": True, "use_sniper": True, "max_risk": 20, "min_liquidity": 300000, "take_profit": 10, "stop_loss": 5, "max_hold_hours": 2, "allocation_percent": 1, "max_positions": 3, "tooltip": "Snipe tokens DEX - liquidité $300k+, risque faible"},
    "sniper_degen": {"auto": True, "use_sniper": True, "max_risk": 30, "min_liquidity": 200000, "take_profit": 12, "stop_loss": 6, "max_hold_hours": 2, "allocation_percent": 1, "max_positions": 5, "tooltip": "Snipe DEX modéré - liquidité $200k+"},
    "sniper_yolo": {"auto": True, "use_sniper": True, "max_risk": 40, "min_liquidity": 150000, "take_profit": 15, "stop_loss": 8, "max_hold_hours": 1.5, "allocation_percent": 1, "max_positions": 5, "tooltip": "Snipe agressif - liquidité $150k+, high risk"},

    # QUICK FLIP ONLY - Very short holds (TP 5-10%, SL 2.5-5%)
    "sniper_all_in": {"auto": True, "use_sniper": True, "max_risk": 35, "min_liquidity": 150000, "take_profit": 8, "stop_loss": 4, "max_hold_hours": 1, "allocation_percent": 1, "max_positions": 3, "tooltip": "Quick flip - sort en 1h max"},
    "sniper_spray": {"auto": True, "use_sniper": True, "max_risk": 40, "min_liquidity": 100000, "take_profit": 10, "stop_loss": 5, "max_hold_hours": 1, "allocation_percent": 1, "max_positions": 5, "tooltip": "Spray & pray - plusieurs petites positions"},
    "sniper_quickflip": {"auto": True, "use_sniper": True, "max_risk": 35, "min_liquidity": 100000, "take_profit": 6, "stop_loss": 3, "max_hold_hours": 0.5, "allocation_percent": 1, "max_positions": 3, "tooltip": "Ultra quick flip - 30min max hold"},

    # WHALE COPY TRADING
    "whale_gcr": {"auto": True, "use_whale": True, "whale_ids": ["trader_1"], "take_profit": 25, "stop_loss": 10, "max_hold_hours": 48, "tooltip": "Copie GCR - légendaire trader crypto"},
    "whale_hsaka": {"auto": True, "use_whale": True, "whale_ids": ["trader_2"], "take_profit": 20, "stop_loss": 8, "max_hold_hours": 24, "tooltip": "Copie Hsaka - analyste technique réputé"},
    "whale_cobie": {"auto": True, "use_whale": True, "whale_ids": ["trader_3"], "take_profit": 30, "stop_loss": 12, "max_hold_hours": 72, "tooltip": "Copie Cobie - VC & early investor"},
    "whale_ansem": {"auto": True, "use_whale": True, "whale_ids": ["trader_4"], "take_profit": 30, "stop_loss": 12, "max_hold_hours": 48, "tooltip": "Copie Ansem - spécialiste SOL memecoins"},
    "whale_degen": {"auto": True, "use_whale": True, "whale_ids": ["trader_5"], "take_profit": 20, "stop_loss": 10, "max_hold_hours": 24, "tooltip": "Copie whale degen anonyme"},
    "whale_smart_money": {"auto": True, "use_whale": True, "whale_ids": ["trader_1", "trader_2", "trader_3"], "take_profit": 20, "stop_loss": 10, "max_hold_hours": 48, "tooltip": "Agrège plusieurs top whales"},

    # CONGRESS COPY TRADING
    "congress_pelosi": {"auto": True, "use_whale": True, "whale_ids": ["congress_pelosi"], "take_profit": 50, "stop_loss": 20, "tooltip": "Copie Nancy Pelosi - rendements légendaires"},
    "congress_tuberville": {"auto": True, "use_whale": True, "whale_ids": ["congress_tuberville"], "take_profit": 40, "stop_loss": 20, "tooltip": "Copie Tommy Tuberville - sénateur trader"},
    "congress_crenshaw": {"auto": True, "use_whale": True, "whale_ids": ["congress_crenshaw"], "take_profit": 40, "stop_loss": 20, "tooltip": "Copie Dan Crenshaw - représentant TX"},
    "congress_all": {"auto": True, "use_whale": True, "whale_ids": ["congress_pelosi", "congress_mccaul", "congress_tuberville"], "take_profit": 50, "stop_loss": 20, "tooltip": "Agrège tous les trades du Congrès"},

    # LEGENDARY INVESTORS
    "legend_buffett": {"auto": True, "use_whale": True, "whale_ids": ["legend_buffett"], "take_profit": 100, "stop_loss": 25, "tooltip": "Style Warren Buffett - value investing"},
    "legend_dalio": {"auto": True, "use_whale": True, "whale_ids": ["legend_dalio"], "take_profit": 40, "stop_loss": 15, "tooltip": "Style Ray Dalio - All Weather"},
    "legend_simons": {"auto": True, "use_whale": True, "whale_ids": ["legend_simons"], "take_profit": 30, "stop_loss": 15, "tooltip": "Style Jim Simons - quant trading"},
    "legend_soros": {"auto": True, "use_whale": True, "whale_ids": ["legend_soros"], "take_profit": 50, "stop_loss": 20, "tooltip": "Style George Soros - macro trades"},
    "legend_burry": {"auto": True, "use_whale": True, "whale_ids": ["legend_burry"], "take_profit": 100, "stop_loss": 30, "tooltip": "Style Michael Burry - contrarian bets"},
    "legend_cathie": {"auto": True, "use_whale": True, "whale_ids": ["legend_cathie"], "take_profit": 100, "stop_loss": 35, "tooltip": "Style Cathie Wood - innovation disruptive"},
    "legend_ptj": {"auto": True, "use_whale": True, "whale_ids": ["legend_ptj"], "take_profit": 40, "stop_loss": 20, "tooltip": "Style Paul Tudor Jones - macro + technique"},
    "legend_ackman": {"auto": True, "use_whale": True, "whale_ids": ["legend_ackman"], "take_profit": 50, "stop_loss": 20, "tooltip": "Style Bill Ackman - activist investing"},

    # EMA Crossover - DAY/SWING (TP 12-18%, SL 6-9%)
    "ema_crossover": {"auto": True, "use_ema_cross": True, "fast_ema": 9, "slow_ema": 21, "take_profit": 12, "stop_loss": 6, "tooltip": "EMA 9/21 crossover - trend following classique"},
    "ema_crossover_slow": {"auto": True, "use_ema_cross": True, "fast_ema": 12, "slow_ema": 26, "take_profit": 18, "stop_loss": 9, "tooltip": "EMA 12/26 crossover - moins de faux signaux"},

    # VWAP Strategy - INTRADAY (TP 5-10%, SL 2.5-5%)
    "vwap_bounce": {"auto": True, "use_vwap": True, "deviation": 1.5, "take_profit": 5, "stop_loss": 2.5, "tooltip": "Achète sous VWAP, vend au-dessus"},
    "vwap_trend": {"auto": True, "use_vwap": True, "deviation": 0.5, "trend_follow": True, "take_profit": 8, "stop_loss": 4, "tooltip": "Suit la tendance relative au VWAP"},

    # Supertrend - DAY TRADING (TP 10-15%, SL 5-7%)
    "supertrend": {"auto": True, "use_supertrend": True, "period": 10, "multiplier": 3.0, "take_profit": 14, "stop_loss": 7, "tooltip": "Supertrend ATR - support/résistance dynamique"},
    "supertrend_fast": {"auto": True, "use_supertrend": True, "period": 7, "multiplier": 2.0, "take_profit": 8, "stop_loss": 4, "tooltip": "Supertrend rapide - signaux fréquents"},

    # Stochastic RSI - DAY TRADING (TP 8-12%, SL 4-6%)
    "stoch_rsi": {"auto": True, "use_stoch_rsi": True, "oversold": 30, "overbought": 70, "take_profit": 10, "stop_loss": 5, "tooltip": "Stoch RSI - momentum oscillator"},
    "stoch_rsi_aggressive": {"auto": True, "use_stoch_rsi": True, "oversold": 30, "overbought": 75, "take_profit": 10, "stop_loss": 5, "tooltip": "Stoch RSI - seuils élargis"},

    # Breakout - SWING (TP 15-20%, SL 7-10%)
    "breakout": {"auto": True, "use_breakout": True, "lookback": 20, "volume_mult": 1.5, "take_profit": 18, "stop_loss": 9, "tooltip": "Breakout des ranges avec volume"},
    "breakout_tight": {"auto": True, "use_breakout": True, "lookback": 10, "volume_mult": 2.0, "take_profit": 10, "stop_loss": 5, "tooltip": "Breakout rapide - confirmation volume forte"},

    # Mean Reversion - SHORT TERM (TP 6-10%, SL 3-5%)
    "mean_reversion": {"auto": True, "use_mean_rev": True, "std_dev": 2.0, "period": 20, "take_profit": 8, "stop_loss": 4, "tooltip": "Retour à la moyenne - achète les excès"},
    "mean_reversion_tight": {"auto": True, "use_mean_rev": True, "std_dev": 1.5, "period": 14, "take_profit": 6, "stop_loss": 3, "tooltip": "Mean reversion serrée - trades fréquents"},

    # Grid Trading - RANGE (TP 4-6%, SL 2-3%)
    "grid_trading": {"auto": True, "use_grid": True, "grid_size": 2.0, "levels": 5, "take_profit": 6, "stop_loss": 3, "tooltip": "Grille de niveaux - range trading"},
    "grid_tight": {"auto": True, "use_grid": True, "grid_size": 1.0, "levels": 10, "take_profit": 5, "stop_loss": 4, "tooltip": "Grille serrée - SL élargi"},

    # DCA Accumulator
    "dca_accumulator": {"auto": True, "use_dca": True, "dip_threshold": 3.0, "take_profit": 15, "stop_loss": 10, "tooltip": "DCA sur dips de 3%+"},
    "dca_aggressive": {"auto": True, "use_dca": True, "dip_threshold": 2.0, "take_profit": 12, "stop_loss": 8, "tooltip": "DCA agressif - achète dès 2% dip"},

    # AVERAGING DOWN - Renforcement de positions en perte
    "reinforce_safe": {"auto": True, "use_reinforce": True, "reinforce_threshold": -5, "reinforce_levels": 2, "reinforce_mult": 1.0, "take_profit": 12, "stop_loss": 0, "tooltip": "Renforce à -5%, max 2x, même taille"},
    "reinforce_moderate": {"auto": True, "use_reinforce": True, "reinforce_threshold": -4, "reinforce_levels": 3, "reinforce_mult": 1.5, "take_profit": 15, "stop_loss": 0, "tooltip": "Renforce à -4%, max 3x, taille x1.5"},
    "reinforce_aggressive": {"auto": True, "use_reinforce": True, "reinforce_threshold": -3, "reinforce_levels": 4, "reinforce_mult": 2.0, "take_profit": 18, "stop_loss": 0, "tooltip": "Renforce à -3%, max 4x, taille x2"},

    # Ichimoku Cloud - SWING/POSITION (different timeframes)
    "ichimoku": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52, "take_profit": 18, "stop_loss": 9, "tooltip": "Ichimoku classique - système complet"},
    "ichimoku_fast": {"auto": True, "use_ichimoku": True, "tenkan": 7, "kijun": 22, "senkou": 44, "take_profit": 12, "stop_loss": 6, "tooltip": "Ichimoku rapide - périodes réduites"},
    "ichimoku_scalp": {"auto": True, "use_ichimoku": True, "tenkan": 5, "kijun": 13, "senkou": 26, "rsi_filter": 40, "take_profit": 5, "stop_loss": 2.5, "tooltip": "Ichimoku scalping + filtre RSI"},
    "ichimoku_swing": {"auto": True, "use_ichimoku": True, "tenkan": 12, "kijun": 30, "senkou": 60, "take_profit": 22, "stop_loss": 11, "tooltip": "Ichimoku swing - trades journaliers"},
    "ichimoku_long": {"auto": True, "use_ichimoku": True, "tenkan": 20, "kijun": 60, "senkou": 120, "take_profit": 40, "stop_loss": 18, "tooltip": "Ichimoku long terme - position trading"},
    "ichimoku_kumo_break": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52, "kumo_break": True, "take_profit": 20, "stop_loss": 10, "tooltip": "Trade le breakout du nuage Kumo"},
    "ichimoku_tk_cross": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52, "tk_cross": True, "take_profit": 15, "stop_loss": 7, "tooltip": "Tenkan/Kijun crossover"},
    "ichimoku_chikou": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52, "chikou_confirm": True, "take_profit": 18, "stop_loss": 9, "tooltip": "Confirmation Chikou Span"},
    "ichimoku_momentum": {"auto": True, "use_ichimoku": True, "tenkan": 7, "kijun": 22, "senkou": 44, "rsi_filter": 50, "take_profit": 8, "stop_loss": 4, "tooltip": "Ichimoku + RSI momentum"},
    "ichimoku_conservative": {"auto": True, "use_ichimoku": True, "tenkan": 9, "kijun": 26, "senkou": 52, "require_all": True, "take_profit": 28, "stop_loss": 14, "tooltip": "Ichimoku - tous signaux requis"},

    # Martingale
    "martingale": {"auto": True, "use_martingale": True, "multiplier": 2.0, "max_levels": 999, "take_profit": 15, "stop_loss": 0, "tooltip": "Martingale x2 - NO LIMIT, tout ou rien"},
    "martingale_safe": {"auto": True, "use_martingale": True, "multiplier": 1.5, "max_levels": 999, "take_profit": 12, "stop_loss": 0, "tooltip": "Martingale x1.5 - NO LIMIT"},

    # Funding Rate Strategies - DAY TRADING (TP 10-15%, SL 5-7%)
    "funding_contrarian": {"auto": True, "use_mean_rev": True, "std_dev": 1.8, "take_profit": 12, "stop_loss": 6, "tooltip": "Contre le funding rate extrême"},
    "funding_extreme": {"auto": True, "use_mean_rev": True, "std_dev": 2.5, "take_profit": 16, "stop_loss": 8, "tooltip": "Funding rate très extrême seulement"},

    # Open Interest Strategies - DAY TRADING (TP 12-16%, SL 6-8%)
    "oi_breakout": {"auto": True, "use_breakout": True, "lookback": 15, "take_profit": 14, "stop_loss": 7, "tooltip": "Breakout avec hausse Open Interest"},
    "oi_divergence": {"auto": True, "use_mean_rev": True, "std_dev": 2.0, "take_profit": 10, "stop_loss": 5, "tooltip": "Divergence prix/OI"},

    # Combined Funding + OI - DAY TRADING
    "funding_oi_combo": {"auto": True, "use_breakout": True, "use_mean_rev": True, "take_profit": 12, "stop_loss": 6, "tooltip": "Combo Funding + Open Interest"},

    # Bollinger Squeeze - DAY TRADING (TP 10-14%, SL 5-7%)
    "bollinger_squeeze": {"auto": True, "use_breakout": True, "lookback": 20, "take_profit": 12, "stop_loss": 6, "tooltip": "Squeeze Bollinger - bandes serrées avant explosion"},
    "bollinger_squeeze_tight": {"auto": True, "use_breakout": True, "lookback": 10, "take_profit": 8, "stop_loss": 4, "tooltip": "Squeeze rapide - breakout imminent"},

    # RSI Divergence - DAY TRADING (TP 10-14%, SL 5-7%)
    "rsi_divergence": {"auto": True, "use_rsi": True, "oversold": 30, "overbought": 70, "take_profit": 12, "stop_loss": 6, "tooltip": "Divergence RSI/prix - reversal signal"},
    "rsi_divergence_fast": {"auto": True, "use_rsi": True, "oversold": 35, "overbought": 65, "take_profit": 8, "stop_loss": 4, "tooltip": "Divergence RSI rapide"},

    # ADX Trend - SWING (TP 14-20%, SL 7-10%)
    "adx_trend": {"auto": True, "use_ema_cross": True, "fast_ema": 9, "take_profit": 14, "stop_loss": 7, "tooltip": "ADX fort - suit les tendances établies"},
    "adx_strong": {"auto": True, "use_ema_cross": True, "fast_ema": 12, "take_profit": 20, "stop_loss": 10, "tooltip": "ADX très fort - tendances puissantes"},

    # MACD - DAY TRADING (TP 8-12%, SL 4-6%)
    "macd_reversal": {"auto": True, "use_stoch_rsi": True, "oversold": 20, "overbought": 80, "take_profit": 10, "stop_loss": 5, "tooltip": "Reversal MACD - changement de momentum"},
    "macd_crossover": {"auto": True, "use_ema_cross": True, "fast_ema": 12, "take_profit": 12, "stop_loss": 6, "tooltip": "MACD signal crossover"},

    # Parabolic SAR - DAY TRADING (TP 10-14%, SL 5-7%)
    "parabolic_sar": {"auto": True, "use_supertrend": True, "period": 10, "take_profit": 12, "stop_loss": 6, "tooltip": "Parabolic SAR - stop & reverse"},
    "parabolic_sar_fast": {"auto": True, "use_supertrend": True, "period": 7, "take_profit": 8, "stop_loss": 4, "tooltip": "Parabolic SAR rapide"},

    # Williams %R - DAY TRADING (TP 8-12%, SL 4-6%)
    "williams_r": {"auto": True, "use_stoch_rsi": True, "oversold": 20, "overbought": 80, "take_profit": 10, "stop_loss": 5, "tooltip": "Williams %R - momentum oscillator"},
    "williams_r_extreme": {"auto": True, "use_stoch_rsi": True, "oversold": 10, "overbought": 90, "take_profit": 12, "stop_loss": 6, "tooltip": "Williams %R extrême - niveaux stricts"},

    # Donchian Channel - SWING (TP 14-18%, SL 7-9%)
    "donchian_breakout": {"auto": True, "use_breakout": True, "lookback": 20, "take_profit": 16, "stop_loss": 8, "tooltip": "Donchian 20 - breakout channel"},
    "donchian_fast": {"auto": True, "use_breakout": True, "lookback": 10, "take_profit": 10, "stop_loss": 5, "tooltip": "Donchian rapide - breakout court"},

    # Keltner Channel - DAY TRADING (TP 8-12%, SL 4-6%)
    "keltner_channel": {"auto": True, "use_mean_rev": True, "std_dev": 2.0, "take_profit": 10, "stop_loss": 5, "tooltip": "Keltner Channel - bandes ATR"},
    "keltner_tight": {"auto": True, "use_mean_rev": True, "std_dev": 1.5, "take_profit": 6, "stop_loss": 3, "tooltip": "Keltner serré - range trading"},

    # CCI Momentum - DAY TRADING (TP 8-14%, SL 4-7%)
    "cci_momentum": {"auto": True, "use_stoch_rsi": True, "oversold": 20, "overbought": 80, "take_profit": 10, "stop_loss": 5, "tooltip": "CCI momentum - trend strength"},
    "cci_extreme": {"auto": True, "use_stoch_rsi": True, "oversold": 10, "overbought": 90, "take_profit": 14, "stop_loss": 7, "tooltip": "CCI extrême - reversals"},

    # Aroon Indicator - DAY TRADING (TP 10-14%, SL 5-7%)
    "aroon_trend": {"auto": True, "use_ema_cross": True, "fast_ema": 9, "take_profit": 12, "stop_loss": 6, "tooltip": "Aroon - identifie nouvelles tendances"},
    "aroon_fast": {"auto": True, "use_ema_cross": True, "fast_ema": 7, "take_profit": 8, "stop_loss": 4, "tooltip": "Aroon rapide - tendances courtes"},

    # OBV Trend - DAY TRADING (TP 10-14%, SL 5-7%)
    "obv_trend": {"auto": True, "use_breakout": True, "lookback": 20, "volume_mult": 1.5, "take_profit": 12, "stop_loss": 6, "tooltip": "OBV - On Balance Volume trend"},
    "obv_fast": {"auto": True, "use_breakout": True, "lookback": 10, "volume_mult": 2.0, "take_profit": 8, "stop_loss": 4, "tooltip": "OBV rapide - volume spikes"},

    # Multi-indicator combos - DAY/SWING (TP 10-14%, SL 5-7%)
    "rsi_macd_combo": {"auto": True, "use_rsi": True, "oversold": 35, "overbought": 65, "take_profit": 12, "stop_loss": 6, "tooltip": "Combo RSI + MACD confirmation"},
    "bb_rsi_combo": {"auto": True, "use_stoch_rsi": True, "oversold": 25, "overbought": 75, "take_profit": 10, "stop_loss": 5, "tooltip": "Combo Bollinger + RSI"},
    "trend_momentum": {"auto": True, "use_ema_cross": True, "fast_ema": 9, "take_profit": 12, "stop_loss": 6, "tooltip": "Trend + Momentum alignment"},

    # Trailing Stop strategies - SCALPING (TP élargis, SL élargis)
    "trailing_tight": {"auto": True, "use_degen": True, "mode": "scalping", "take_profit": 6, "stop_loss": 4, "tooltip": "Trailing - SL élargi"},
    "trailing_medium": {"auto": True, "use_degen": True, "mode": "scalping", "take_profit": 8, "stop_loss": 5, "tooltip": "Trailing medium - balance"},
    "trailing_wide": {"auto": True, "use_degen": True, "mode": "momentum", "take_profit": 12, "stop_loss": 6, "tooltip": "Trailing wide - laisse courir"},
    "trailing_scalp": {"auto": True, "use_degen": True, "mode": "scalping", "take_profit": 5, "stop_loss": 3, "tooltip": "Trailing scalp - micro gains"},
    "trailing_swing": {"auto": True, "use_degen": True, "mode": "momentum", "take_profit": 20, "stop_loss": 10, "tooltip": "Trailing swing - gros moves"},

    # Scalping variants - SCALPING (TP/SL élargis)
    "scalp_rsi": {"auto": True, "use_degen": True, "mode": "scalping", "take_profit": 6, "stop_loss": 4, "tooltip": "Scalp RSI - SL élargi"},
    "scalp_bb": {"auto": True, "use_degen": True, "mode": "scalping", "take_profit": 3, "stop_loss": 1.5, "tooltip": "Scalp Bollinger touches"},
    "scalp_macd": {"auto": True, "use_degen": True, "mode": "scalping", "take_profit": 5, "stop_loss": 2.5, "tooltip": "Scalp MACD crosses"},

    # Sector-specific - SWING (TP 15-25%, SL 7-12%)
    "defi_hunter": {"auto": True, "use_degen": True, "mode": "momentum", "take_profit": 18, "stop_loss": 9, "tooltip": "Focus tokens DeFi (AAVE, UNI...)"},
    "layer2_focus": {"auto": True, "use_degen": True, "mode": "momentum", "take_profit": 16, "stop_loss": 8, "tooltip": "Focus Layer 2 (ARB, OP, MATIC)"},
    "gaming_tokens": {"auto": True, "use_degen": True, "mode": "momentum", "take_profit": 22, "stop_loss": 11, "tooltip": "Focus Gaming/Metaverse tokens"},
    "ai_tokens": {"auto": True, "use_degen": True, "mode": "momentum", "take_profit": 22, "stop_loss": 11, "tooltip": "Focus tokens AI (FET, AGIX, RNDR)"},
    "meme_hunter": {"auto": True, "use_degen": True, "mode": "hybrid", "take_profit": 25, "stop_loss": 12, "tooltip": "Chasse aux memecoins (DOGE, SHIB, PEPE)"},

    # Risk-adjusted - POSITION (varies by risk)
    "low_risk_dca": {"auto": True, "use_dca": True, "dip_threshold": 5.0, "take_profit": 18, "stop_loss": 9, "tooltip": "DCA conservateur - dips de 5%+ seulement"},
    "medium_risk_swing": {"auto": True, "use_ema_cross": True, "fast_ema": 12, "take_profit": 16, "stop_loss": 8, "tooltip": "Swing trading risque modéré"},
    "high_risk_leverage": {"auto": True, "use_degen": True, "mode": "hybrid", "take_profit": 25, "stop_loss": 12, "tooltip": "Style leverage - gros gains/pertes"},

    # Pivot Points - INTRADAY (TP 6-10%, SL 3-5%)
    "pivot_classic": {"auto": True, "use_grid": True, "grid_size": 2.0, "take_profit": 8, "stop_loss": 4, "tooltip": "Pivots classiques - S1/S2/R1/R2"},
    "pivot_fibonacci": {"auto": True, "use_grid": True, "grid_size": 1.5, "take_profit": 10, "stop_loss": 5, "tooltip": "Pivots Fibonacci - retracements"},

    # Volume Weighted - DAY TRADING (TP 10-15%, SL 5-7%)
    "volume_breakout": {"auto": True, "use_breakout": True, "volume_mult": 2.0, "take_profit": 14, "stop_loss": 7, "tooltip": "Breakout avec volume 2x normal"},
    "volume_climax": {"auto": True, "use_mean_rev": True, "std_dev": 2.5, "take_profit": 10, "stop_loss": 5, "tooltip": "Climax de volume - reversal probable"},

    # Multi-timeframe - SWING (TP 15-20%, SL 8-10%)
    "mtf_trend": {"auto": True, "use_ema_cross": True, "fast_ema": 9, "slow_ema": 21, "take_profit": 18, "stop_loss": 9, "tooltip": "Multi-timeframe trend alignment"},
    "mtf_momentum": {"auto": True, "use_degen": True, "mode": "momentum", "take_profit": 12, "stop_loss": 6, "tooltip": "MTF momentum confirmation"},

    # Range trading - SCALP (TP 5-8%, SL 2.5-4%)
    "range_sniper": {"auto": True, "use_grid": True, "grid_size": 1.5, "take_profit": 6, "stop_loss": 3, "tooltip": "Snipe les bords du range"},
    "range_breakout": {"auto": True, "use_breakout": True, "lookback": 15, "take_profit": 12, "stop_loss": 6, "tooltip": "Attend le breakout du range"},

    # Heikin Ashi - DAY TRADING (TP 10-15%, SL 5-7%)
    "heikin_ashi": {"auto": True, "use_ema_cross": True, "use_rsi": True, "fast_ema": 9, "take_profit": 12, "stop_loss": 6, "tooltip": "Heikin Ashi - bougies lissées"},
    "heikin_ashi_reversal": {"auto": True, "use_stoch_rsi": True, "oversold": 20, "overbought": 80, "take_profit": 10, "stop_loss": 5, "tooltip": "HA reversal patterns"},

    # Order flow - DAY TRADING (TP 8-12%, SL 4-6%)
    "orderflow_delta": {"auto": True, "use_breakout": True, "volume_mult": 2.5, "take_profit": 10, "stop_loss": 5, "tooltip": "Delta volume - buy vs sell pressure"},
    "orderflow_imbalance": {"auto": True, "use_mean_rev": True, "std_dev": 2.0, "take_profit": 8, "stop_loss": 4, "tooltip": "Order imbalance detection"},

    # Sentiment - SWING (TP 15-22%, SL 8-11%)
    "social_sentiment": {"auto": True, "use_fear_greed": True, "take_profit": 20, "stop_loss": 12, "tooltip": "Sentiment social - SL élargi pour volatilité"},
    "fear_greed_extreme": {"auto": True, "use_fear_greed": True, "extreme_only": True, "take_profit": 22, "stop_loss": 11, "tooltip": "Fear <20 ou Greed >80 seulement"},

    # ICT/SMC STRATEGIES
    # Fibonacci Retracement - SWING (TP 12-18%, SL 6-9%)
    "fib_retracement": {"auto": True, "use_mean_rev": True, "std_dev": 1.5, "take_profit": 14, "stop_loss": 7, "tooltip": "Fib retracement 38.2/50/61.8%"},
    "fib_aggressive": {"auto": True, "use_mean_rev": True, "std_dev": 1.2, "take_profit": 10, "stop_loss": 5, "tooltip": "Fib agressif - 23.6% entries"},
    "fib_conservative": {"auto": True, "use_mean_rev": True, "std_dev": 2.0, "take_profit": 18, "stop_loss": 9, "tooltip": "Fib conservateur - 61.8%+ seulement"},

    # Volume Profile - INTRADAY (TP 6-10%, SL 3-5%)
    "volume_profile": {"auto": True, "use_grid": True, "grid_size": 1.0, "take_profit": 8, "stop_loss": 4, "tooltip": "Volume Profile - POC trading"},
    "volume_profile_vah": {"auto": True, "use_grid": True, "grid_size": 1.5, "take_profit": 10, "stop_loss": 5, "tooltip": "Trade au Value Area High"},
    "volume_profile_val": {"auto": True, "use_grid": True, "grid_size": 1.5, "take_profit": 10, "stop_loss": 5, "tooltip": "Trade au Value Area Low"},

    # Order Blocks ICT - DAY TRADING (TP 10-15%, SL 5-7%)
    "order_block_bull": {"auto": True, "use_stoch_rsi": True, "oversold": 25, "take_profit": 12, "stop_loss": 6, "tooltip": "Order block bullish - support institutionnel"},
    "order_block_bear": {"auto": True, "use_stoch_rsi": True, "overbought": 75, "take_profit": 12, "stop_loss": 6, "tooltip": "Order block bearish - résistance instit."},
    "order_block_all": {"auto": True, "use_stoch_rsi": True, "oversold": 30, "overbought": 70, "take_profit": 10, "stop_loss": 5, "tooltip": "Order blocks bull & bear"},

    # Fair Value Gaps - DAY TRADING (TP 8-12%, SL 4-6%)
    "fvg_fill": {"auto": True, "use_mean_rev": True, "std_dev": 1.8, "take_profit": 8, "stop_loss": 4, "tooltip": "FVG fill - comble les gaps"},
    "fvg_rejection": {"auto": True, "use_breakout": True, "lookback": 10, "take_profit": 10, "stop_loss": 5, "tooltip": "FVG rejection - rebond sur gap"},
    "fvg_aggressive": {"auto": True, "use_degen": True, "mode": "momentum", "take_profit": 12, "stop_loss": 6, "tooltip": "FVG agressif - trade tous les gaps"},

    # Liquidity Sweep/Stop Hunt - SWING (TP 12-20%, SL 6-10%)
    "liquidity_sweep": {"auto": True, "use_dca": True, "dip_threshold": 3.0, "take_profit": 12, "stop_loss": 6, "tooltip": "Liquidity sweep - faux breakdowns"},
    "liquidity_grab": {"auto": True, "use_dca": True, "dip_threshold": 4.0, "take_profit": 16, "stop_loss": 8, "tooltip": "Liquidity grab - stop hunt puis reversal"},
    "stop_hunt": {"auto": True, "use_dca": True, "dip_threshold": 5.0, "take_profit": 20, "stop_loss": 10, "tooltip": "Stop hunt recovery - après cascade de SL"},

    # Session Trading - INTRADAY (TP 6-12%, SL 3-6%)
    "session_asian": {"auto": True, "use_ema_cross": True, "fast_ema": 9, "take_profit": 6, "stop_loss": 3, "tooltip": "Session Asie - range trading"},
    "session_london": {"auto": True, "use_ema_cross": True, "fast_ema": 9, "take_profit": 10, "stop_loss": 5, "tooltip": "Session Londres - breakout matinal"},
    "session_newyork": {"auto": True, "use_ema_cross": True, "fast_ema": 9, "take_profit": 10, "stop_loss": 5, "tooltip": "Session NY - volatilité US"},
    "session_overlap": {"auto": True, "use_breakout": True, "lookback": 15, "take_profit": 12, "stop_loss": 6, "tooltip": "Overlap London/NY - max volatilité"},

    # RSI Divergence variants - DAY TRADING (TP 10-14%, SL 5-7%)
    "rsi_divergence_bull": {"auto": True, "use_rsi": True, "oversold": 30, "take_profit": 12, "stop_loss": 6, "tooltip": "Divergence RSI bullish - reversal haut"},
    "rsi_divergence_bear": {"auto": True, "use_rsi": True, "overbought": 70, "take_profit": 12, "stop_loss": 6, "tooltip": "Divergence RSI bearish - reversal bas"},
    "rsi_divergence_hidden": {"auto": True, "use_stoch_rsi": True, "oversold": 25, "overbought": 75, "take_profit": 10, "stop_loss": 5, "tooltip": "Divergence cachée - continuation"},
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
    "reinforce_safe": "1h",
    "reinforce_moderate": "1h",
    "reinforce_aggressive": "1h",
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


def get_btc_reference() -> dict:
    """Get BTC price change for beta lag comparison"""
    global _btc_cache
    import time

    # Cache for 60 seconds
    if time.time() - _btc_cache['last_update'] < 60 and _btc_cache['price'] > 0:
        return _btc_cache

    try:
        from core.exchange import get_exchange
        exchange = get_exchange()
        if exchange:
            ticker = exchange.fetch_ticker('BTC/USDT')
            if ticker:
                _btc_cache['price'] = ticker.get('last', 0)
                _btc_cache['change_24h'] = ticker.get('percentage', 0) or 0
                # Estimate 1h change from OHLCV
                try:
                    ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=2)
                    if ohlcv and len(ohlcv) >= 2:
                        prev_close = ohlcv[-2][4]
                        curr_close = ohlcv[-1][4]
                        if prev_close > 0:
                            _btc_cache['change_1h'] = ((curr_close / prev_close) - 1) * 100
                except:
                    _btc_cache['change_1h'] = _btc_cache['change_24h'] / 24  # Rough estimate
                _btc_cache['last_update'] = time.time()
    except Exception as e:
        pass  # Keep cached values

    return _btc_cache


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


LOCK_FILE = "data/portfolios.lock"

def acquire_lock(timeout=5):
    """Acquire file lock with timeout"""
    start = time.time()
    while os.path.exists(LOCK_FILE):
        if time.time() - start > timeout:
            # Lock is stale, remove it
            try:
                os.remove(LOCK_FILE)
            except:
                pass
            break
        time.sleep(0.1)
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except:
        return False

def release_lock():
    """Release file lock"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass


def save_portfolios(portfolios: dict, counter: int):
    """Save portfolios with file locking (no blocking)"""
    if not acquire_lock():
        log("Could not acquire lock for saving portfolios")
        return portfolios, counter

    try:
        os.makedirs("data", exist_ok=True)
        data = {'portfolios': portfolios, 'counter': counter}

        # Write to temp file first, then rename (atomic operation)
        temp_file = PORTFOLIOS_FILE + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)

        # Atomic rename
        if os.path.exists(PORTFOLIOS_FILE):
            os.replace(temp_file, PORTFOLIOS_FILE)
        else:
            os.rename(temp_file, PORTFOLIOS_FILE)

    except Exception as e:
        log(f"Error saving portfolios: {e}")
    finally:
        release_lock()


def calculate_indicators(df: pd.DataFrame) -> dict:
    """Calculate all technical indicators"""
    indicators = {}

    # Ensure numeric types (fix for numpy type errors)
    closes = pd.to_numeric(df['close'], errors='coerce').fillna(0)
    highs = pd.to_numeric(df['high'], errors='coerce').fillna(0)
    lows = pd.to_numeric(df['low'], errors='coerce').fillna(0)
    opens = pd.to_numeric(df['open'], errors='coerce').fillna(0)
    volumes = pd.to_numeric(df['volume'], errors='coerce').fillna(0)

    # RSI (with division by zero protection)
    delta = closes.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    # Protect against division by zero: if loss is 0, RSI = 100 (max overbought)
    loss_safe = loss.replace(0, 0.0001)
    rs = gain / loss_safe
    rsi = 100 - (100 / (1 + rs))
    rsi_values = rsi.fillna(50)  # Fill NaN with neutral 50
    indicators['rsi'] = rsi_values.iloc[-1]

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
    indicators['stoch_rsi_prev'] = stoch_rsi.iloc[-2] if len(stoch_rsi) > 1 and not pd.isna(stoch_rsi.iloc[-2]) else indicators['stoch_rsi']
    indicators['stoch_rsi_k'] = stoch_rsi.rolling(window=3).mean().iloc[-1] if not pd.isna(stoch_rsi.rolling(window=3).mean().iloc[-1]) else 50

    # Bollinger Bands (for mean reversion)
    sma_20 = closes.rolling(window=20).mean()
    std_20 = closes.rolling(window=20).std()
    indicators['bb_upper'] = sma_20.iloc[-1] + (2 * std_20.iloc[-1])
    indicators['bb_lower'] = sma_20.iloc[-1] - (2 * std_20.iloc[-1])
    indicators['bb_mid'] = sma_20.iloc[-1]
    indicators['sma_20'] = sma_20.iloc[-1]
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

    # 24h High/Low for pattern detection
    indicators['high_24h'] = highs.iloc[-24:].max() if len(highs) >= 24 else highs.max()
    indicators['low_24h'] = lows.iloc[-24:].min() if len(lows) >= 24 else lows.min()
    indicators['price_range_24h'] = indicators['high_24h'] - indicators['low_24h']
    indicators['price_position_24h'] = (closes.iloc[-1] - indicators['low_24h']) / indicators['price_range_24h'] if indicators['price_range_24h'] > 0 else 0.5

    # Scalping signals - CONFLUENCE required (multiple conditions)
    # Buy: RSI low + momentum turning up + not at BB top
    scalp_buy_conditions = (
        indicators['rsi'] < 40 and  # Actually oversold, not just below 50
        indicators['momentum_1h'] > 0.1 and  # Momentum clearly positive
        indicators['bb_position'] < 0.4 and  # Not at top of BB
        indicators['stoch_rsi'] < 50  # Stoch also suggests low
    )
    indicators['scalp_buy'] = scalp_buy_conditions
    indicators['scalp_sell'] = indicators['rsi'] > 65 and indicators['momentum_1h'] < -0.2

    # Momentum signals - CONFLUENCE required
    # Buy: Strong volume + good momentum + RSI not overbought + trend confirmation
    momentum_buy_conditions = (
        indicators['volume_ratio'] > 1.5 and  # Strong volume spike, not just 1.1x
        indicators['momentum_1h'] > 0.3 and  # Clear positive momentum
        indicators['rsi'] < 60 and  # Not overbought
        indicators['rsi'] > 30 and  # Not panic selling
        indicators.get('trend', 'neutral') != 'bearish'  # Trend not against us
    )
    indicators['momentum_buy'] = momentum_buy_conditions
    indicators['momentum_sell'] = indicators['volume_ratio'] > 1.5 and indicators['momentum_1h'] < -0.3 and indicators['rsi'] > 40

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

    # ============ HIGH PRIORITY INDICATORS ============

    # 1. Fibonacci Retracement Levels
    swing_high = highs.rolling(window=50).max().iloc[-1]
    swing_low = lows.rolling(window=50).min().iloc[-1]
    fib_range = swing_high - swing_low
    indicators['fib_0'] = swing_low  # 0%
    indicators['fib_236'] = swing_low + fib_range * 0.236
    indicators['fib_382'] = swing_low + fib_range * 0.382
    indicators['fib_500'] = swing_low + fib_range * 0.5
    indicators['fib_618'] = swing_low + fib_range * 0.618
    indicators['fib_786'] = swing_low + fib_range * 0.786
    indicators['fib_100'] = swing_high  # 100%
    indicators['swing_high'] = swing_high
    indicators['swing_low'] = swing_low

    # 2. Volume Profile (POC, VAH, VAL)
    # Create price bins and sum volume at each level
    price_bins = 20
    price_range = highs.max() - lows.min()
    bin_size = price_range / price_bins if price_range > 0 else 1
    volume_by_price = {}
    for i in range(len(closes)):
        bin_idx = int((closes.iloc[i] - lows.min()) / bin_size) if bin_size > 0 else 0
        bin_idx = min(bin_idx, price_bins - 1)
        price_level = lows.min() + bin_idx * bin_size
        volume_by_price[price_level] = volume_by_price.get(price_level, 0) + volumes.iloc[i]

    if volume_by_price:
        # POC = Price level with highest volume
        poc = max(volume_by_price, key=volume_by_price.get)
        indicators['vpvr_poc'] = poc

        # Value Area (70% of volume)
        total_vol = sum(volume_by_price.values())
        sorted_levels = sorted(volume_by_price.items(), key=lambda x: x[1], reverse=True)
        cumulative = 0
        va_levels = []
        for level, vol in sorted_levels:
            cumulative += vol
            va_levels.append(level)
            if cumulative >= total_vol * 0.7:
                break
        indicators['vpvr_vah'] = max(va_levels) if va_levels else poc
        indicators['vpvr_val'] = min(va_levels) if va_levels else poc
    else:
        indicators['vpvr_poc'] = closes.iloc[-1]
        indicators['vpvr_vah'] = closes.iloc[-1]
        indicators['vpvr_val'] = closes.iloc[-1]

    # 3. Order Blocks Detection (ICT)
    # Bullish OB = Last down candle before strong up move
    # Bearish OB = Last up candle before strong down move
    indicators['bullish_ob'] = None
    indicators['bearish_ob'] = None
    indicators['ob_bullish_top'] = None
    indicators['ob_bullish_bottom'] = None
    indicators['ob_bearish_top'] = None
    indicators['ob_bearish_bottom'] = None

    for i in range(len(closes) - 3, 5, -1):
        # Check for bullish OB (down candle followed by strong up)
        if opens.iloc[i] > closes.iloc[i]:  # Down candle
            # Check next candles for strong upward move
            if closes.iloc[i+1] > opens.iloc[i+1] and closes.iloc[i+2] > closes.iloc[i+1]:
                move = (closes.iloc[i+2] - closes.iloc[i]) / closes.iloc[i] * 100
                if move > 1:  # At least 1% move
                    indicators['bullish_ob'] = lows.iloc[i]
                    indicators['ob_bullish_top'] = opens.iloc[i]
                    indicators['ob_bullish_bottom'] = closes.iloc[i]
                    break

    for i in range(len(closes) - 3, 5, -1):
        # Check for bearish OB (up candle followed by strong down)
        if closes.iloc[i] > opens.iloc[i]:  # Up candle
            # Check next candles for strong downward move
            if closes.iloc[i+1] < opens.iloc[i+1] and closes.iloc[i+2] < closes.iloc[i+1]:
                move = (closes.iloc[i] - closes.iloc[i+2]) / closes.iloc[i] * 100
                if move > 1:  # At least 1% move
                    indicators['bearish_ob'] = highs.iloc[i]
                    indicators['ob_bearish_top'] = closes.iloc[i]
                    indicators['ob_bearish_bottom'] = opens.iloc[i]
                    break

    # 4. Fair Value Gaps (FVG) Detection
    # Bullish FVG = Gap between candle 1 high and candle 3 low
    # Bearish FVG = Gap between candle 1 low and candle 3 high
    indicators['bullish_fvg'] = None
    indicators['bearish_fvg'] = None
    indicators['fvg_bull_top'] = None
    indicators['fvg_bull_bottom'] = None
    indicators['fvg_bear_top'] = None
    indicators['fvg_bear_bottom'] = None

    for i in range(len(closes) - 3, 0, -1):
        # Bullish FVG
        if lows.iloc[i+2] > highs.iloc[i]:
            indicators['bullish_fvg'] = (highs.iloc[i] + lows.iloc[i+2]) / 2
            indicators['fvg_bull_top'] = lows.iloc[i+2]
            indicators['fvg_bull_bottom'] = highs.iloc[i]
            break

    for i in range(len(closes) - 3, 0, -1):
        # Bearish FVG
        if highs.iloc[i+2] < lows.iloc[i]:
            indicators['bearish_fvg'] = (lows.iloc[i] + highs.iloc[i+2]) / 2
            indicators['fvg_bear_top'] = lows.iloc[i]
            indicators['fvg_bear_bottom'] = highs.iloc[i+2]
            break

    # 5. Liquidity Sweep Detection
    # Detect sweeps of recent highs/lows followed by reversal
    recent_high = highs.rolling(window=20).max().iloc[-2]
    recent_low = lows.rolling(window=20).min().iloc[-2]
    current_high = highs.iloc[-1]
    current_low = lows.iloc[-1]
    current_close = closes.iloc[-1]

    # High sweep (price went above recent high but closed below)
    indicators['high_swept'] = current_high > recent_high and current_close < recent_high
    # Low sweep (price went below recent low but closed above)
    indicators['low_swept'] = current_low < recent_low and current_close > recent_low
    indicators['recent_high'] = recent_high
    indicators['recent_low'] = recent_low

    # 6. Session Time Detection (UTC)
    from datetime import datetime, timezone
    current_hour = datetime.now(timezone.utc).hour
    indicators['session_asian'] = 0 <= current_hour < 8  # 00:00-08:00 UTC
    indicators['session_london'] = 7 <= current_hour < 16  # 07:00-16:00 UTC
    indicators['session_newyork'] = 13 <= current_hour < 22  # 13:00-22:00 UTC
    indicators['session_overlap'] = 13 <= current_hour < 16  # London/NY overlap

    # 7. RSI Divergence Detection
    # Bullish divergence: Price makes lower low, RSI makes higher low
    # Bearish divergence: Price makes higher high, RSI makes lower high
    indicators['rsi_bullish_div'] = False
    indicators['rsi_bearish_div'] = False
    indicators['rsi_hidden_bull_div'] = False
    indicators['rsi_hidden_bear_div'] = False

    if len(rsi_values) > 10 and len(closes) > 10:
        # Compare current vs 5 candles ago
        price_now = closes.iloc[-1]
        price_prev = closes.iloc[-6]
        rsi_now = rsi_values.iloc[-1]
        rsi_prev = rsi_values.iloc[-6]

        # Regular bullish divergence
        if price_now < price_prev and rsi_now > rsi_prev:
            indicators['rsi_bullish_div'] = True

        # Regular bearish divergence
        if price_now > price_prev and rsi_now < rsi_prev:
            indicators['rsi_bearish_div'] = True

        # Hidden bullish divergence (trend continuation)
        if price_now > price_prev and rsi_now < rsi_prev and rsi_now < 50:
            indicators['rsi_hidden_bull_div'] = True

        # Hidden bearish divergence (trend continuation)
        if price_now < price_prev and rsi_now > rsi_prev and rsi_now > 50:
            indicators['rsi_hidden_bear_div'] = True

    # ============ ADAPTIVE TP INDICATORS ============

    # ATR as percentage of price (for adaptive TP)
    tr = pd.concat([highs - lows, abs(highs - closes.shift(1)), abs(lows - closes.shift(1))], axis=1).max(axis=1)
    atr_14 = tr.rolling(window=14).mean()
    current_price = closes.iloc[-1]
    atr_value = atr_14.iloc[-1] if not pd.isna(atr_14.iloc[-1]) else current_price * 0.02
    indicators['atr'] = atr_value
    indicators['atr_percent'] = (atr_value / current_price * 100) if current_price > 0 else 2.0

    # Market type detection: choppy vs trending
    # Uses ADX (already calculated) + EMA crossover frequency
    adx_value = indicators.get('adx', 20)

    # Count EMA crossovers in last 20 candles (many crossings = choppy)
    ema_9_series = closes.ewm(span=9).mean()
    ema_21_series = closes.ewm(span=21).mean()
    crossovers = 0
    for i in range(-20, -1):
        if (ema_9_series.iloc[i] > ema_21_series.iloc[i]) != (ema_9_series.iloc[i+1] > ema_21_series.iloc[i+1]):
            crossovers += 1

    # Determine market type
    # ADX < 20 = no trend (choppy)
    # ADX > 25 = trending
    # Many crossovers (>4) = very choppy
    if adx_value < 20 or crossovers > 4:
        indicators['market_type'] = 'choppy'
        indicators['market_type_score'] = max(0, 50 - adx_value + crossovers * 5)  # Higher = more choppy
    elif adx_value > 30 and crossovers < 2:
        indicators['market_type'] = 'trending'
        indicators['market_type_score'] = min(100, adx_value + (2 - crossovers) * 10)  # Higher = stronger trend
    else:
        indicators['market_type'] = 'mixed'
        indicators['market_type_score'] = 50

    indicators['ema_crossovers'] = crossovers

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


def execute_real_trade_wrapper(portfolio: dict, action: str, symbol: str, price: float, amount_usdt: float = None) -> dict:
    """
    Execute a REAL trade via the RealExecutor.
    This is called when portfolio trading_mode == 'real'
    """
    try:
        from core.real_executor import execute_real_trade, is_real_trading_ready

        # Load settings
        settings = {}
        try:
            with open('data/settings.json', 'r') as f:
                settings = json.load(f)
        except:
            return {'success': False, 'message': 'Cannot load settings for real trading'}

        # Check if ready
        ready, reason = is_real_trading_ready(portfolio, settings)
        if not ready:
            log(f"[REAL] Not ready: {reason}")
            return {'success': False, 'message': f'Real trading not ready: {reason}'}

        # Calculate amount if not provided
        if amount_usdt is None:
            allocation = portfolio['config'].get('allocation_percent', 10)
            amount_usdt = portfolio['balance']['USDT'] * (allocation / 100)

        # Execute via RealExecutor
        log(f"[REAL TRADE] {action} {symbol} ${amount_usdt:.2f}")
        result = execute_real_trade(
            portfolio=portfolio,
            action=action,
            symbol=symbol,
            price=price,
            amount_usdt=amount_usdt,
            settings=settings
        )

        if result.get('success'):
            # Update portfolio balance for successful real trade
            asset = symbol.split('/')[0]
            timestamp = datetime.now().isoformat()

            if action == 'BUY':
                qty = amount_usdt / price
                portfolio['balance']['USDT'] -= amount_usdt
                portfolio['balance'][asset] = portfolio['balance'].get(asset, 0) + qty

                if symbol not in portfolio['positions']:
                    portfolio['positions'][symbol] = {
                        'entry_price': price,
                        'quantity': qty,
                        'entry_time': timestamp,
                        'is_real': True
                    }

                trade = {
                    'timestamp': timestamp,
                    'action': 'BUY',
                    'symbol': symbol,
                    'price': price,
                    'quantity': qty,
                    'amount_usdt': amount_usdt,
                    'pnl': 0,
                    'is_real': True,
                    'order_id': result.get('order_id')
                }
                record_trade(portfolio, trade)
                log(f"[REAL] BUY {qty:.6f} {asset} @ ${price:,.2f} - Order: {result.get('order_id')}")
                return {'success': True, 'message': f"[REAL] BUY {qty:.6f} {asset} @ ${price:,.2f}"}

            elif action == 'SELL':
                qty = portfolio['balance'].get(asset, 0)
                sell_value = qty * price
                pnl = result.get('pnl', 0)

                if symbol in portfolio['positions']:
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
                    'pnl': pnl,
                    'is_real': True,
                    'order_id': result.get('order_id')
                }
                record_trade(portfolio, trade)
                log(f"[REAL] SELL {qty:.6f} {asset} @ ${price:,.2f} | PnL: ${pnl:+,.2f}")
                return {'success': True, 'message': f"[REAL] SELL {qty:.6f} {asset} | PnL: ${pnl:+,.2f}"}

        else:
            error = result.get('error', 'Unknown error')
            log(f"[REAL] Trade failed: {error}")
            return {'success': False, 'message': f'Real trade failed: {error}'}

    except ImportError as e:
        log(f"[REAL] Import error: {e}")
        return {'success': False, 'message': f'Real trading modules not available: {e}'}
    except Exception as e:
        log(f"[REAL] Execution error: {e}")
        return {'success': False, 'message': f'Real trade error: {e}'}


def execute_trade(portfolio: dict, action: str, symbol: str, price: float, amount_usdt: float = None, reason: str = "") -> dict:
    """Execute a trade - paper or real based on portfolio trading_mode"""

    # Check if this is a REAL trade
    trading_mode = portfolio.get('trading_mode', 'paper')

    if trading_mode == 'real':
        return execute_real_trade_wrapper(portfolio, action, symbol, price, amount_usdt)

    # Paper trading logic below
    asset = symbol.split('/')[0]
    timestamp = datetime.now().isoformat()

    # === REALISTIC FEE & SLIPPAGE SIMULATION ===
    # Binance fees: 0.1% maker/taker (0.075% with BNB discount)
    # We use 0.1% to be conservative
    FEE_RATE = 0.001  # 0.1%

    # Slippage: depends on order size and liquidity
    # Small orders: 0.01-0.05%, Large orders: 0.1-0.5%
    # We simulate based on trade size
    def calculate_slippage(trade_size_usdt: float, is_buy: bool) -> float:
        """Calculate realistic slippage based on order size"""
        if trade_size_usdt < 1000:
            slip = random.uniform(0.0001, 0.0005)  # 0.01-0.05%
        elif trade_size_usdt < 5000:
            slip = random.uniform(0.0005, 0.001)   # 0.05-0.1%
        elif trade_size_usdt < 10000:
            slip = random.uniform(0.001, 0.002)    # 0.1-0.2%
        else:
            slip = random.uniform(0.002, 0.005)    # 0.2-0.5%

        # Buys get worse price (higher), sells get worse price (lower)
        return slip if is_buy else -slip

    # Track cumulative fees for portfolio
    if 'total_fees_paid' not in portfolio:
        portfolio['total_fees_paid'] = 0.0

    if action == 'BUY':
        if amount_usdt is None:
            allocation = portfolio['config'].get('allocation_percent', 10)
            amount_usdt = portfolio['balance']['USDT'] * (allocation / 100)

            # Apply Martingale multiplier if set
            martingale_mult = portfolio.pop('_martingale_multiplier', None)
            martingale_level = portfolio.pop('_martingale_level', 0)
            if martingale_mult and martingale_level > 0:
                amount_usdt = amount_usdt * (martingale_mult ** martingale_level)
                amount_usdt = min(amount_usdt, portfolio['balance']['USDT'] * 0.5)  # Cap at 50% of balance

        if portfolio['balance']['USDT'] >= amount_usdt and amount_usdt > 10:
            # Apply slippage to price (buy at slightly higher price)
            slippage = calculate_slippage(amount_usdt, is_buy=True)
            execution_price = price * (1 + slippage)

            # Calculate fee
            fee = amount_usdt * FEE_RATE
            net_amount = amount_usdt - fee  # Amount after fee

            qty = net_amount / execution_price  # Less quantity due to fee + slippage
            portfolio['balance']['USDT'] -= amount_usdt
            portfolio['balance'][asset] = portfolio['balance'].get(asset, 0) + qty
            portfolio['total_fees_paid'] += fee

            # Track position with highest_price for trailing stop
            # Use execution_price (with slippage) as the real entry
            if symbol not in portfolio['positions']:
                portfolio['positions'][symbol] = {
                    'entry_price': execution_price,  # Real execution price with slippage
                    'quantity': qty,
                    'entry_time': timestamp,
                    'highest_price': execution_price,  # For trailing stop
                    'partial_profit_taken': False  # For partial TP
                }
            else:
                # Average down
                pos = portfolio['positions'][symbol]
                total_qty = pos['quantity'] + qty
                avg_price = (pos['entry_price'] * pos['quantity'] + execution_price * qty) / total_qty
                portfolio['positions'][symbol] = {
                    'entry_price': avg_price,
                    'quantity': total_qty,
                    'entry_time': pos['entry_time'],
                    'highest_price': max(pos.get('highest_price', avg_price), execution_price),
                    'partial_profit_taken': pos.get('partial_profit_taken', False)
                }

            trade = {
                'timestamp': timestamp,
                'action': 'BUY',
                'symbol': symbol,
                'price': execution_price,  # Actual execution price
                'market_price': price,  # Original market price
                'quantity': qty,
                'amount_usdt': amount_usdt,
                'fee': fee,
                'slippage_pct': slippage * 100,
                'pnl': 0,
                'reason': reason
            }
            record_trade(portfolio, trade)
            return {'success': True, 'message': f"BUY {qty:.6f} {asset} @ ${execution_price:,.2f} (fee: ${fee:.2f}, slip: {slippage*100:.3f}%)"}

    elif action == 'REINFORCE':
        # Reinforcement buy - averaging down on existing position
        reinforce_level = portfolio.pop('_reinforce_level', 1)
        old_qty = portfolio.pop('_reinforce_old_qty', 0)
        old_price = portfolio.pop('_reinforce_old_price', price)

        if amount_usdt is None:
            allocation = portfolio['config'].get('allocation_percent', 5)
            reinforce_mult = 1.5  # Default multiplier
            amount_usdt = portfolio['balance']['USDT'] * (allocation / 100) * (reinforce_mult ** (reinforce_level - 1))

        if portfolio['balance']['USDT'] >= amount_usdt and amount_usdt > 10:
            # Apply slippage
            slippage = calculate_slippage(amount_usdt, is_buy=True)
            execution_price = price * (1 + slippage)

            # Calculate fee
            fee = amount_usdt * FEE_RATE
            net_amount = amount_usdt - fee

            qty = net_amount / execution_price
            portfolio['balance']['USDT'] -= amount_usdt
            portfolio['balance'][asset] = portfolio['balance'].get(asset, 0) + qty
            portfolio['total_fees_paid'] += fee

            # Calculate new average price
            total_qty = old_qty + qty
            avg_price = (old_price * old_qty + execution_price * qty) / total_qty if total_qty > 0 else execution_price

            # Update position with new average and reinforce level
            portfolio['positions'][symbol] = {
                'entry_price': avg_price,
                'quantity': total_qty,
                'entry_time': portfolio['positions'].get(symbol, {}).get('entry_time', timestamp),
                'highest_price': max(portfolio['positions'].get(symbol, {}).get('highest_price', avg_price), execution_price),
                'partial_profit_taken': False,
                'reinforce_level': reinforce_level  # Track reinforcement level
            }

            trade = {
                'timestamp': timestamp,
                'action': 'REINFORCE',
                'symbol': symbol,
                'price': execution_price,
                'market_price': price,
                'quantity': qty,
                'amount_usdt': amount_usdt,
                'fee': fee,
                'slippage_pct': slippage * 100,
                'pnl': 0,
                'reason': reason,
                'reinforce_level': reinforce_level,
                'new_avg_price': avg_price
            }
            record_trade(portfolio, trade)
            return {'success': True, 'message': f"REINFORCE L{reinforce_level}: +{qty:.6f} {asset} @ ${execution_price:,.2f} | New avg: ${avg_price:,.2f}"}

    elif action == 'SELL':
        if portfolio['balance'].get(asset, 0) > 0:
            # BUG FIX: Use position quantity instead of balance to prevent overselling
            # The balance can get corrupted if shared between portfolios
            if symbol in portfolio['positions']:
                pos_qty = portfolio['positions'][symbol].get('quantity', 0)
                balance_qty = portfolio['balance'].get(asset, 0)

                # Use the SMALLER of balance or position to be safe
                qty = min(pos_qty, balance_qty) if pos_qty > 0 else balance_qty

                # Log warning if there's a discrepancy
                if abs(balance_qty - pos_qty) > pos_qty * 0.01:  # More than 1% difference
                    log(f"⚠️ BALANCE MISMATCH: {symbol} balance={balance_qty:.2f} position={pos_qty:.2f} - using {qty:.2f}")
            else:
                # No position tracked, use balance (legacy compatibility)
                qty = portfolio['balance'][asset]

            # Apply slippage to price (sell at slightly lower price)
            gross_value = qty * price
            slippage = calculate_slippage(gross_value, is_buy=False)
            execution_price = price * (1 + slippage)  # slippage is negative for sells

            sell_value = qty * execution_price

            # Apply fee
            fee = sell_value * FEE_RATE
            net_sell_value = sell_value - fee
            portfolio['total_fees_paid'] += fee

            # Calculate PnL (including fees and slippage)
            pnl = 0
            entry_price = 0
            if symbol in portfolio['positions']:
                entry_price = portfolio['positions'][symbol]['entry_price']
                # Real PnL = what we receive - what we paid (already includes buy fees)
                pnl = net_sell_value - (entry_price * qty)
                del portfolio['positions'][symbol]

            portfolio['balance']['USDT'] += net_sell_value
            portfolio['balance'][asset] = 0

            trade = {
                'timestamp': timestamp,
                'action': 'SELL',
                'symbol': symbol,
                'price': execution_price,  # Actual execution price
                'market_price': price,  # Original market price
                'quantity': qty,
                'amount_usdt': net_sell_value,
                'gross_value': sell_value,
                'fee': fee,
                'slippage_pct': slippage * 100,
                'pnl': pnl,
                'reason': reason,
                'entry_price': entry_price  # Store entry price for chart display
            }
            record_trade(portfolio, trade)
            return {'success': True, 'message': f"SELL {qty:.6f} {asset} @ ${execution_price:,.2f} | PnL: ${pnl:+,.2f} (fee: ${fee:.2f})"}

    # ============ SHORT SELLING (Paper Trading) ============
    # SHORT = Open a short position (bet price will go down)
    # COVER = Close a short position (buy back to close)

    elif action == 'SHORT':
        if 'short_positions' not in portfolio:
            portfolio['short_positions'] = {}

        # Don't short if already have a short on this symbol
        if symbol in portfolio.get('short_positions', {}):
            return {'success': False, 'message': f"Already short {symbol}"}

        if amount_usdt is None:
            allocation = portfolio['config'].get('allocation_percent', 10)
            amount_usdt = portfolio['balance']['USDT'] * (allocation / 100)

        # Need margin (collateral) to short - use 100% margin (1x leverage)
        margin_required = amount_usdt  # 1x leverage = full collateral

        if portfolio['balance']['USDT'] >= margin_required and amount_usdt > 10:
            # Apply slippage (short at slightly lower price = worse for us)
            slippage = calculate_slippage(amount_usdt, is_buy=False)
            execution_price = price * (1 + slippage)

            # Calculate fee on notional value
            fee = amount_usdt * FEE_RATE
            qty = amount_usdt / execution_price

            # Lock margin
            portfolio['balance']['USDT'] -= margin_required
            portfolio['total_fees_paid'] += fee

            # Track short position
            portfolio['short_positions'][symbol] = {
                'entry_price': execution_price,
                'quantity': qty,
                'margin_used': margin_required,
                'entry_time': timestamp,
                'lowest_price': execution_price  # For trailing stop on shorts
            }

            trade = {
                'timestamp': timestamp,
                'action': 'SHORT',
                'symbol': symbol,
                'price': execution_price,
                'market_price': price,
                'quantity': qty,
                'amount_usdt': amount_usdt,
                'margin_used': margin_required,
                'fee': fee,
                'slippage_pct': slippage * 100,
                'pnl': 0,
                'reason': reason
            }
            record_trade(portfolio, trade)
            return {'success': True, 'message': f"SHORT {qty:.6f} {asset} @ ${execution_price:,.2f} (margin: ${margin_required:.2f}, fee: ${fee:.2f})"}

    elif action == 'COVER':
        # Close short position
        if 'short_positions' not in portfolio:
            portfolio['short_positions'] = {}

        if symbol in portfolio.get('short_positions', {}):
            pos = portfolio['short_positions'][symbol]
            qty = pos['quantity']
            entry_price = pos['entry_price']
            margin_used = pos['margin_used']

            # Apply slippage (cover at slightly higher price = worse for us)
            slippage = calculate_slippage(qty * price, is_buy=True)
            execution_price = price * (1 + slippage)

            # Calculate PnL for short: profit if price went DOWN
            # PnL = (entry_price - exit_price) * quantity
            gross_pnl = (entry_price - execution_price) * qty

            # Fee on cover
            cover_value = qty * execution_price
            fee = cover_value * FEE_RATE
            portfolio['total_fees_paid'] += fee

            # Net PnL after fee
            net_pnl = gross_pnl - fee

            # Return margin + PnL to balance
            portfolio['balance']['USDT'] += margin_used + net_pnl

            # Remove short position
            del portfolio['short_positions'][symbol]

            trade = {
                'timestamp': timestamp,
                'action': 'COVER',
                'symbol': symbol,
                'price': execution_price,
                'market_price': price,
                'quantity': qty,
                'amount_usdt': cover_value,
                'fee': fee,
                'slippage_pct': slippage * 100,
                'pnl': net_pnl,
                'reason': reason
            }
            record_trade(portfolio, trade)

            pnl_emoji = "📈" if net_pnl > 0 else "📉"
            return {'success': True, 'message': f"COVER {qty:.6f} {asset} @ ${execution_price:,.2f} | PnL: ${net_pnl:+,.2f} {pnl_emoji} (fee: ${fee:.2f})"}

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
    current_price = analysis.get('price', 0)

    # ============ CHECK EXITS FIRST (TP/SL/TRAILING/PARTIAL) ============
    # This ensures positions are closed when hitting targets regardless of signals
    if symbol in portfolio['positions']:
        pos = portfolio['positions'][symbol]
        entry_price = pos.get('entry_price', 0)
        highest_price = pos.get('highest_price', entry_price)

        if entry_price > 0 and current_price > 0:
            pnl_pct = ((current_price / entry_price) - 1) * 100

            # Update highest price for trailing stop
            if current_price > highest_price:
                pos['highest_price'] = current_price
                highest_price = current_price

            # Get TP/SL from strategy or config
            base_take_profit = strategy.get('take_profit', config.get('take_profit', 50))
            base_stop_loss = strategy.get('stop_loss', config.get('stop_loss', 25))

            # ============ ADAPTIVE TP based on market conditions ============
            # In choppy markets, reduce TP to capture small waves
            # In trending markets, keep full TP to ride the trend
            market_type = analysis.get('market_type', 'mixed') if analysis else 'mixed'
            atr_pct = analysis.get('atr_percent', 2.0) if analysis else 2.0

            if config.get('use_adaptive_tp', True):  # Enabled by default
                if market_type == 'choppy':
                    # Choppy market: reduce TP significantly (min 1.5x ATR or half of base TP)
                    adaptive_tp = max(atr_pct * 1.5, base_take_profit * 0.4)
                    take_profit = min(base_take_profit, adaptive_tp)
                    # Also tighten SL in choppy markets
                    stop_loss = min(base_stop_loss, max(atr_pct * 1.0, base_stop_loss * 0.6))
                elif market_type == 'trending':
                    # Trending market: use full TP, can even extend if strong trend
                    adx_val = analysis.get('adx', 25) if analysis else 25
                    if adx_val > 40:  # Very strong trend
                        take_profit = base_take_profit * 1.2
                    else:
                        take_profit = base_take_profit
                    stop_loss = base_stop_loss
                else:  # Mixed
                    # Use ATR-based adjustment
                    volatility_mult = max(0.6, min(1.2, atr_pct / 2.0))
                    take_profit = base_take_profit * volatility_mult
                    stop_loss = base_stop_loss * volatility_mult
            else:
                take_profit = base_take_profit
                stop_loss = base_stop_loss

            # ============ FORCE MINIMUM 1.5:1 REWARD/RISK RATIO ============
            # This is critical - never risk more than potential reward
            min_ratio = 1.5
            if take_profit < stop_loss * min_ratio:
                # Either increase TP or decrease SL
                if stop_loss > 5:  # If SL is too wide, tighten it
                    stop_loss = take_profit / min_ratio
                else:  # Otherwise extend TP
                    take_profit = stop_loss * min_ratio

            # 1. Check trailing stop loss (MORE AGGRESSIVE - activate at 2% instead of 5%)
            # Also check for profit give-back (was up, now giving back gains)
            trail_activation = config.get('trailing_activation', 2)  # Activate at 2% profit
            trail_pct = config.get('trailing_stop_pct', 3)  # Trail by 3%

            if config.get('use_trailing_stop', True) and pnl_pct > trail_activation:
                _, trail_triggered, trail_reason = get_trailing_stop(
                    entry_price, current_price, highest_price, stop_loss, trail_pct
                )
                if trail_triggered:
                    return ('SELL', trail_reason)

            # 1b. SECURE PROFIT: Multiple levels to protect gains
            highest_pnl = ((highest_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

            # Level 1: Was up 2%+, now lost 60% of gains but still positive
            if highest_pnl >= 2 and pnl_pct < highest_pnl * 0.4 and pnl_pct > 0.5:
                return ('SELL', f"SECURE PROFIT L1: Was +{highest_pnl:.1f}%, securing +{pnl_pct:.1f}%")

            # Level 2: Was up 4%+, now lost 40% of gains
            if highest_pnl >= 4 and pnl_pct < highest_pnl * 0.6 and pnl_pct > 1:
                return ('SELL', f"SECURE PROFIT L2: Was +{highest_pnl:.1f}%, securing +{pnl_pct:.1f}%")

            # Level 3: Was up 6%+, now lost 30% of gains
            if highest_pnl >= 6 and pnl_pct < highest_pnl * 0.7 and pnl_pct > 2:
                return ('SELL', f"SECURE PROFIT L3: Was +{highest_pnl:.1f}%, securing +{pnl_pct:.1f}%")

            # Level 4: Momentum reversal - was up, now dropping fast
            if highest_pnl >= 1.5 and pnl_pct < 0.5 and pnl_pct > 0:
                # Almost gave back all gains, exit now
                return ('SELL', f"SECURE PROFIT URGENT: Was +{highest_pnl:.1f}%, now only +{pnl_pct:.1f}%")

            # 2. Check partial profit (sell 50% at first target)
            if config.get('use_partial_tp', False):
                partial_taken = pos.get('partial_profit_taken', False)
                first_target = config.get('partial_tp_pct', take_profit / 2)
                should_partial, pct_sell, partial_reason = should_take_partial_profit(
                    entry_price, current_price, partial_taken, first_target
                )
                if should_partial:
                    pos['partial_profit_taken'] = True
                    return ('PARTIAL_SELL', partial_reason)

            # 3. Check take profit (full) - may be adaptive
            if pnl_pct >= take_profit:
                # Show if adaptive TP was used
                adaptive_note = f" [{market_type}]" if take_profit != base_take_profit else ""
                return ('SELL', f"TP HIT: +{pnl_pct:.1f}% (target: {take_profit:.1f}%{adaptive_note})")

            # 4. Check stop loss (skip if stop_loss=0, e.g. Martingale)
            if stop_loss > 0 and pnl_pct <= -stop_loss:
                return ('SELL', f"SL HIT: {pnl_pct:.1f}% (limit: -{stop_loss}%)")

            # 5. Check max hold time if configured
            max_hold_hours = strategy.get('max_hold_hours', config.get('max_hold_hours', 0))
            if max_hold_hours > 0:
                try:
                    entry_time = datetime.fromisoformat(pos.get('entry_time', datetime.now().isoformat()))
                    hold_hours = (datetime.now() - entry_time).total_seconds() / 3600
                    if hold_hours >= max_hold_hours:
                        return ('SELL', f"TIME EXIT: Held {hold_hours:.1f}h (max: {max_hold_hours}h)")
                except:
                    pass

    # ============ CHECK SHORT POSITION EXITS (TP/SL for shorts) ============
    # For shorts: profit when price goes DOWN, loss when price goes UP
    if 'short_positions' not in portfolio:
        portfolio['short_positions'] = {}

    if symbol in portfolio.get('short_positions', {}):
        pos = portfolio['short_positions'][symbol]
        entry_price = pos.get('entry_price', 0)
        lowest_price = pos.get('lowest_price', entry_price)

        if entry_price > 0 and current_price > 0:
            # Short PnL: positive when price drops
            pnl_pct = ((entry_price - current_price) / entry_price) * 100

            # Update lowest price for trailing stop on shorts
            if current_price < lowest_price:
                pos['lowest_price'] = current_price
                lowest_price = current_price

            # Get TP/SL from strategy or config
            base_take_profit = strategy.get('take_profit', config.get('take_profit', 50))
            base_stop_loss = strategy.get('stop_loss', config.get('stop_loss', 25))

            # ADAPTIVE TP for shorts (same logic as longs)
            market_type = analysis.get('market_type', 'mixed') if analysis else 'mixed'
            atr_pct = analysis.get('atr_percent', 2.0) if analysis else 2.0

            if config.get('use_adaptive_tp', True):
                if market_type == 'choppy':
                    adaptive_tp = max(atr_pct * 1.5, base_take_profit * 0.4)
                    take_profit = min(base_take_profit, adaptive_tp)
                    stop_loss = min(base_stop_loss, max(atr_pct * 1.0, base_stop_loss * 0.6))
                elif market_type == 'trending':
                    adx_val = analysis.get('adx', 25) if analysis else 25
                    take_profit = base_take_profit * 1.2 if adx_val > 40 else base_take_profit
                    stop_loss = base_stop_loss
                else:
                    volatility_mult = max(0.6, min(1.2, atr_pct / 2.0))
                    take_profit = base_take_profit * volatility_mult
                    stop_loss = base_stop_loss * volatility_mult
            else:
                take_profit = base_take_profit
                stop_loss = base_stop_loss

            # FORCE MINIMUM 1.5:1 RATIO for shorts too
            min_ratio = 1.5
            if take_profit < stop_loss * min_ratio:
                if stop_loss > 5:
                    stop_loss = take_profit / min_ratio
                else:
                    take_profit = stop_loss * min_ratio

            # 1. Check trailing stop for shorts (MORE AGGRESSIVE)
            trail_activation = config.get('trailing_activation', 2)
            trail_pct = config.get('trailing_stop_pct', 3)

            if config.get('use_trailing_stop', True) and pnl_pct > trail_activation:
                # For shorts: trail from lowest price going UP
                trail_price = lowest_price * (1 + trail_pct / 100)
                if current_price >= trail_price:
                    return ('COVER', f"SHORT TRAIL: Price rose to ${current_price:.2f} from low ${lowest_price:.2f}")

            # 1b. SECURE SHORT PROFIT - Multiple levels
            lowest_pnl = ((entry_price - lowest_price) / entry_price * 100) if entry_price > 0 else 0
            if lowest_pnl >= 2 and pnl_pct < lowest_pnl * 0.4 and pnl_pct > 0.5:
                return ('COVER', f"SECURE SHORT L1: Was +{lowest_pnl:.1f}%, securing +{pnl_pct:.1f}%")
            if lowest_pnl >= 4 and pnl_pct < lowest_pnl * 0.6 and pnl_pct > 1:
                return ('COVER', f"SECURE SHORT L2: Was +{lowest_pnl:.1f}%, securing +{pnl_pct:.1f}%")

            # 2. Check take profit (price dropped enough) - may be adaptive
            if pnl_pct >= take_profit:
                adaptive_note = f" [{market_type}]" if take_profit != base_take_profit else ""
                return ('COVER', f"SHORT TP HIT: +{pnl_pct:.1f}% (target: {take_profit:.1f}%{adaptive_note})")

            # 3. Check stop loss (price rose too much) - skip if stop_loss=0
            if stop_loss > 0 and pnl_pct <= -stop_loss:
                return ('COVER', f"SHORT SL HIT: {pnl_pct:.1f}% (limit: -{stop_loss}%)")

            # 4. Check max hold time for shorts
            max_hold_hours = strategy.get('max_hold_hours', config.get('max_hold_hours', 0))
            if max_hold_hours > 0:
                try:
                    entry_time = datetime.fromisoformat(pos.get('entry_time', datetime.now().isoformat()))
                    hold_hours = (datetime.now() - entry_time).total_seconds() / 3600
                    if hold_hours >= max_hold_hours:
                        return ('COVER', f"SHORT TIME EXIT: Held {hold_hours:.1f}h (max: {max_hold_hours}h)")
                except:
                    pass

    # Check max positions (include shorts) - WITH ROTATION LOGIC
    max_positions = config.get('max_positions', 10)
    at_max_positions = len(portfolio['positions']) >= max_positions
    rotation_candidate = None  # Symbol to close if rotating

    if at_max_positions and symbol not in portfolio['positions']:
        # Calculate opportunity score for potential rotation
        entry_score = get_best_entry_score(analysis, strategy, portfolio)
        new_score = entry_score.get('score', 0)

        # Check if we should rotate
        should_rotate, worst_symbol, rotate_reason = should_rotate_position(
            portfolio, new_score, analysis, strategy
        )

        if should_rotate and worst_symbol:
            # Mark for rotation - we'll close worst position and buy new one
            rotation_candidate = worst_symbol
            log_trade(f"🔄 ROTATION: {rotate_reason}")
        else:
            return (None, f"Max positions ({max_positions}) - {rotate_reason}")

    has_position = portfolio['balance'].get(asset, 0) > 0
    has_cash = portfolio['balance']['USDT'] > 100 or rotation_candidate is not None
    rsi = analysis.get('rsi', 50)

    # ============ SMART ENTRY FILTERS ============
    # Only apply to new buys (not sells)
    # SKIP filters only for strategies that MUST have their own timing
    skip_filters = (
        strategy.get('buy_on') == ["ALWAYS_FIRST"] or  # HODL
        strategy.get('use_fear_greed') or  # DCA Fear - timing based on Fear index
        strategy.get('use_martingale') or  # Martingale - has its own logic
        strategy.get('use_btc_lag') or  # BTC Beta Lag - timing specific
        strategy.get('use_btc_lag_short') or  # BTC Beta Lag SHORT
        strategy.get('use_rsi_short') or  # RSI Overbought SHORT
        strategy.get('use_mean_rev_short')  # Mean Reversion SHORT
    )

    # ============ UNIVERSAL SAFETY FILTERS (apply to ALL strategies) ============
    if has_cash and symbol not in portfolio['positions']:
        # A. Don't buy in strong downtrend (price far below EMA50)
        ema50 = analysis.get('ema_50', current_price)
        price_vs_ema50 = ((current_price - ema50) / ema50 * 100) if ema50 > 0 else 0
        if price_vs_ema50 < -8:  # More than 8% below EMA50 = strong downtrend
            return (None, f"DOWNTREND: Price {price_vs_ema50:.1f}% below EMA50")

        # B. Don't chase massive pumps (>10% in last 4h)
        mom_4h = analysis.get('momentum_4h', 0)
        if mom_4h > 10 and not strategy.get('use_breakout'):
            return (None, f"PUMP CHASE: Already +{mom_4h:.1f}% in 4h")

        # C. Check loss streak - reduce activity after losses
        recent_trades = portfolio.get('trades', [])[-10:]
        recent_losses = sum(1 for t in recent_trades if t.get('pnl', 0) < 0)
        if recent_losses >= 7:  # 7+ losses in last 10 trades
            # Only allow very high quality entries
            entry_score = get_best_entry_score(analysis, strategy, portfolio)
            if entry_score['score'] < 70:
                return (None, f"LOSS STREAK: {recent_losses}/10 losses, need score>70 (got {entry_score['score']})")

    if has_cash and symbol not in portfolio['positions'] and not skip_filters:
        # 1. Check loss cooldown (pause after 3 consecutive losses)
        should_pause, cooldown_reason = check_loss_cooldown(portfolio)
        if should_pause:
            return (None, cooldown_reason)

        # 2. Check if token is safe for this strategy
        if not is_safe_for_strategy(symbol, strategy):
            return (None, f"Token {asset} too risky for {strategy_id}")

        # 3. Don't chase pumps (unless degen strategy)
        skip_pump, pump_reason = should_skip_pump_chase(analysis, strategy)
        if skip_pump:
            return (None, pump_reason)

        # 4. Check trend alignment (EMA stack)
        trend_ok, trend_reason = check_trend_alignment(analysis, strategy)
        if not trend_ok:
            return (None, trend_reason)

        # 5. Check RSI entry quality (skip overbought)
        rsi_ok, rsi_quality, rsi_reason = check_rsi_entry_quality(rsi, strategy)
        if not rsi_ok:
            return (None, rsi_reason)

        # 6. Check volume confirmation
        volume_ok, volume_reason = check_volume_confirmation(analysis, strategy)
        if not volume_ok:
            return (None, volume_reason)

        # 7. Check correlation limit (don't overload similar assets)
        corr_ok, corr_reason = check_correlation_limit(portfolio, symbol)
        if not corr_ok:
            return (None, corr_reason)

        # 8. Calculate entry quality score
        entry_score = get_best_entry_score(analysis, strategy, portfolio)
        if entry_score['recommendation'] == 'SKIP':
            return (None, f"Entry score too low: {entry_score['score']}/100")

    # ============ STRATEGY SIGNALS ============

    # EMA Crossover - SMART ENTRY with pattern detection
    if strategy.get('use_ema_cross'):
        fast = strategy.get('fast_ema', 9)
        stoch = analysis.get('stoch_rsi', 50)
        mom_1h = analysis.get('momentum_1h', 0)
        mom_4h = analysis.get('momentum_4h', 0)
        bb_pos = analysis.get('bb_position', 0.5)
        volume_ratio = analysis.get('volume_ratio', 1.0)

        # Get pattern and regime data
        reversal = detect_reversal_pattern(analysis)
        regime = detect_market_regime(analysis)

        # Determine which crossover signal to use
        if fast == 12:
            cross_up = analysis.get('ema_cross_up_slow')
            cross_down = analysis.get('ema_cross_down_slow')
            ema_type = "12/26"
        else:
            cross_up = analysis.get('ema_cross_up')
            cross_down = analysis.get('ema_cross_down')
            ema_type = "9/21"

        if cross_up and has_cash:
            # SMART CONFLUENCE: EMA crossover + multiple confirmations
            confirmations = 0
            reasons = [f"EMA{ema_type}✓"]

            # Price action quality
            if rsi < 55 and rsi > 30:  # Not overbought, not oversold
                confirmations += 1
                reasons.append(f"RSI={rsi:.0f}")

            if stoch < 65:
                confirmations += 1
                reasons.append(f"Stoch={stoch:.0f}")

            if mom_1h > 0.1:  # Clear positive momentum
                confirmations += 1
                reasons.append(f"Mom+{mom_1h:.1f}%")

            if bb_pos < 0.6 and bb_pos > 0.2:  # Room to run
                confirmations += 1
                reasons.append(f"BB={bb_pos:.0%}")

            if volume_ratio > 1.1:  # Volume confirms
                confirmations += 1
                reasons.append(f"Vol={volume_ratio:.1f}x")

            # Pattern bonus
            if reversal['bullish_score'] >= 20:
                confirmations += 1
                if reversal['patterns']:
                    reasons.append(reversal['patterns'][0])

            # Regime check - don't enter in volatile downtrend
            if regime['regime'] == 'VOLATILE' and mom_4h < -1:
                return (None, f"EMA: Crossover UP but volatile regime ({regime['regime']}) - wait")

            # Need 2+ confirmations for entry (was 4, too restrictive)
            if confirmations >= 2:
                return ('BUY', f"EMA SMART ({confirmations}/6): {' | '.join(reasons[:5])}")
            else:
                return (None, f"EMA: Crossover UP but only {confirmations}/2 confirms")

        elif cross_down and has_position:
            if rsi > 55 or stoch > 60 or reversal['bearish_score'] >= 25:
                return ('SELL', f"EMA {ema_type} DOWN | RSI={rsi:.0f} | Stoch={stoch:.0f}")

        return (None, f"EMA: No crossover | RSI={rsi:.0f} | Regime={regime['regime']}")

    # Degen strategies - USE ADVANCED CONFLUENCE + VOLUME
    if strategy.get('use_degen'):
        mode = strategy.get('mode', 'hybrid')
        mom = analysis.get('momentum_1h', 0)
        volume_ratio = analysis.get('volume_ratio', 1.0)
        confluence = calculate_confluence_score(analysis, strategy)
        reversal = detect_reversal_pattern(analysis)
        ema9 = analysis.get('ema_9', current_price)
        ema21 = analysis.get('ema_21', current_price)

        # SELL conditions - MORE PATIENT (was too nervous)
        if has_position:
            if analysis.get('scalp_sell') and analysis.get('momentum_sell'):
                return ('SELL', f"DEGEN EXIT: Strong sell signal")
            elif rsi > 75 and mom < -1:  # Only exit on real overbought + weakness
                return ('SELL', f"DEGEN EXIT: RSI={rsi:.0f} overbought + Mom={mom:.1f}%")
            elif mom < -3:  # Strong momentum drop only
                return ('SELL', f"DEGEN EXIT: Strong drop Mom={mom:.1f}%")
            elif ema9 < ema21 * 0.98:  # Significant EMA cross (2%+ gap)
                return ('SELL', f"DEGEN EXIT: EMA bearish cross")

        # BUY conditions - STRICTER now
        if has_cash:
            # MUST have volume confirmation
            if volume_ratio < 0.8:
                return (None, f"DEGEN: Low volume ({volume_ratio:.1f}x) - waiting")

            # MUST be in uptrend (EMA9 > EMA21)
            if ema9 < ema21:
                return (None, f"DEGEN: Downtrend (EMA9 < EMA21) - waiting")

            # Higher thresholds for safety
            min_score = 45 if mode == 'hybrid' else 50
            min_confirms = 3 if mode == 'hybrid' else 4

            if confluence['score'] >= min_score and confluence['confirmations'] >= min_confirms:
                if rsi < 60:  # Don't buy overbought
                    reasons = ' | '.join(confluence['reasons'][:4])
                    return ('BUY', f"DEGEN {mode.upper()} ({confluence['score']}/100): {reasons}")

            # Stricter reversal pattern requirements
            if reversal['bullish_score'] >= 50 and mom > 0.5 and rsi < 40:
                patterns = ', '.join(reversal['patterns'][:2])
                return ('BUY', f"DEGEN REVERSAL: {patterns} | Mom={mom:+.1f}%")

        return (None, f"DEGEN {mode}: Score={confluence['score']} | Need {min_score}+ with {min_confirms}+ confirmations")

    # VWAP Strategy - WITH CONFLUENCE
    if strategy.get('use_vwap'):
        deviation = strategy.get('deviation', 1.5)
        vwap_dev = analysis.get('vwap_deviation', 0)
        trend_follow = strategy.get('trend_follow', False)
        confluence = calculate_confluence_score(analysis, strategy)
        mom_1h = analysis.get('momentum_1h', 0)

        if trend_follow:
            # Trend following: buy above VWAP with confluence
            if vwap_dev > deviation and has_cash:
                if confluence['score'] >= 40 and mom_1h > 0:
                    return ('BUY', f"VWAP TREND ({confluence['score']}/100): VWAP+{vwap_dev:.1f}% | Mom={mom_1h:+.1f}%")
            elif vwap_dev < -deviation and has_position:
                return ('SELL', f"VWAP TREND: Price {vwap_dev:.1f}% below VWAP")
        else:
            # Mean reversion: buy below VWAP with confluence
            if vwap_dev < -deviation and has_cash:
                if confluence['score'] >= 35 and confluence['confirmations'] >= 2:
                    reasons = ' | '.join(confluence['reasons'][:3])
                    return ('BUY', f"VWAP BOUNCE ({confluence['score']}/100): {reasons}")
            elif vwap_dev > deviation and has_position:
                return ('SELL', f"VWAP BOUNCE: Price {vwap_dev:.1f}% above VWAP")
        return (None, f"VWAP: Dev={vwap_dev:.1f}% | Score={confluence['score']}")

    # Supertrend - WITH CONFLUENCE
    if strategy.get('use_supertrend'):
        period = strategy.get('period', 10)
        if period == 7:
            supertrend_up = analysis.get('supertrend_up_fast', False)
        else:
            supertrend_up = analysis.get('supertrend_up', False)

        confluence = calculate_confluence_score(analysis, strategy)
        mom_1h = analysis.get('momentum_1h', 0)

        if supertrend_up and not has_position and has_cash:
            # Supertrend up + confluence confirmation
            if confluence['score'] >= 35 and rsi < 65:
                reasons = ' | '.join(confluence['reasons'][:3])
                return ('BUY', f"SUPERTREND UP ({confluence['score']}/100): {reasons}")
        elif not supertrend_up and has_position:
            return ('SELL', f"SUPERTREND: Downtrend signal")
        return (None, f"SUPERTREND: {'Up' if supertrend_up else 'Down'} | Score={confluence['score']}")

    # Stochastic RSI - USE ADVANCED CONFLUENCE
    if strategy.get('use_stoch_rsi'):
        oversold = strategy.get('oversold', 30)
        overbought = strategy.get('overbought', 70)
        stoch = analysis.get('stoch_rsi', 50)
        confluence = calculate_confluence_score(analysis, strategy)

        if stoch < oversold and has_cash:
            # Use confluence system - require good score AND confirmations
            if confluence['score'] >= 40 and confluence['confirmations'] >= 3:
                reasons = ' | '.join(confluence['reasons'][:4])
                return ('BUY', f"STOCH RSI ({confluence['score']}/100): {reasons}")
            else:
                return (None, f"STOCH RSI: {stoch:.0f} oversold | Score={confluence['score']} (need 40+, {confluence['confirmations']} confirms)")

        elif stoch > overbought and has_position:
            return ('SELL', f"STOCH RSI: {stoch:.0f} > {overbought} overbought")
        return (None, f"STOCH RSI: {stoch:.0f} | Score={confluence['score']}")

    # Breakout - WITH CONFLUENCE
    if strategy.get('use_breakout'):
        lookback = strategy.get('lookback', 20)
        if lookback == 10:
            breakout_up = analysis.get('breakout_up_tight', False)
            breakout_down = analysis.get('breakout_down_tight', False)
        else:
            breakout_up = analysis.get('breakout_up', False)
            breakout_down = analysis.get('breakout_down', False)

        confluence = calculate_confluence_score(analysis, strategy)

        if breakout_up and has_cash:
            # Breakout + minimal confluence for confirmation
            if confluence['score'] >= 15 and rsi < 75:
                return ('BUY', f"BREAKOUT UP ({confluence['score']}/100): {lookback}-period high | RSI={rsi:.0f}")
            else:
                return (None, f"BREAKOUT: Signal but score {confluence['score']} < 15")
        elif breakout_down and has_position:
            return ('SELL', f"BREAKOUT DOWN: Price broke {lookback}-period low")
        return (None, f"BREAKOUT: Waiting | Score={confluence['score']}")

    # Mean Reversion - WITH CONFLUENCE
    if strategy.get('use_mean_rev'):
        std_threshold = strategy.get('std_dev', 1.5)
        period = strategy.get('period', 20)
        if period == 14:
            deviation = analysis.get('deviation_from_mean_tight', 0)
        else:
            deviation = analysis.get('deviation_from_mean', 0)

        confluence = calculate_confluence_score(analysis, strategy)
        mom_1h = analysis.get('momentum_1h', 0)

        if deviation < -std_threshold and has_cash:
            # Mean reversion + minimal confluence
            if confluence['score'] >= 20 and mom_1h > -3:
                reasons = ' | '.join(confluence['reasons'][:3])
                return ('BUY', f"MEAN REV ({confluence['score']}/100): {deviation:.1f}σ | {reasons}")
            else:
                return (None, f"MEAN REV: {deviation:.1f}σ but score={confluence['score']} < 20 or mom={mom_1h:.1f}%")
        elif deviation > std_threshold and has_position:
            return ('SELL', f"MEAN REV: {deviation:.1f}σ above mean")
        return (None, f"MEAN REV: {deviation:.1f}σ | Score={confluence['score']}")

    # Grid Trading - IMPROVED with volume and trend filter
    if strategy.get('use_grid'):
        bb_pos = analysis.get('bb_position', 0.5)
        buy_threshold = 0.15  # Stricter: only buy at extreme lows
        sell_threshold = 0.85  # Exit at 85% BB (was 70%)
        confluence = calculate_confluence_score(analysis, strategy)
        regime = detect_market_regime(analysis)
        volume_ratio = analysis.get('volume_ratio', 1.0)
        ema9 = analysis.get('ema_9', current_price)
        ema21 = analysis.get('ema_21', current_price)
        mom_1h = analysis.get('momentum_1h', 0)

        # SELL conditions - more patient exits
        if has_position:
            if bb_pos > sell_threshold:
                return ('SELL', f"GRID: BB={bb_pos:.0%} > {sell_threshold:.0%}")
            if mom_1h < -3:  # Only exit on strong momentum drop (was -1.5)
                return ('SELL', f"GRID EXIT: Momentum dropping ({mom_1h:.1f}%)")
            if ema9 < ema21 * 0.98 and bb_pos > 0.6:  # Stricter EMA cross condition
                return ('SELL', f"GRID EXIT: EMA bearish cross, BB={bb_pos:.0%}")

        # BUY conditions - STRICTER
        if bb_pos < buy_threshold and has_cash:
            # Grid buy: need confluence + not in volatile crash
            if regime['regime'] == 'VOLATILE' and regime['direction'] == 'DOWN':
                return (None, f"GRID: Volatile down market - waiting")

            # Need volume confirmation
            if volume_ratio < 0.7:
                return (None, f"GRID: Low volume ({volume_ratio:.1f}x) - waiting")

            # Need uptrend or at least not strong downtrend
            if ema9 < ema21 * 0.98:  # More than 2% below EMA21
                return (None, f"GRID: Strong downtrend - waiting for reversal")

            # Need momentum stabilizing
            if mom_1h < -2:
                return (None, f"GRID: Momentum still falling ({mom_1h:.1f}%) - waiting")

            # Higher confluence requirement
            if confluence['score'] >= 50 and confluence['confirmations'] >= 4:
                reasons = ' | '.join(confluence['reasons'][:4])
                return ('BUY', f"GRID ({confluence['score']}/100): BB={bb_pos:.0%} | {reasons}")
            else:
                return (None, f"GRID: BB={bb_pos:.0%} | Score={confluence['score']} (need 50+)")
        return (None, f"GRID: BB={bb_pos:.0%} | Score={confluence['score']} | Regime={regime['regime']}")

    # DCA Accumulator - USE ADVANCED CONFLUENCE
    if strategy.get('use_dca'):
        dip_threshold = strategy.get('dip_threshold', 3.0)
        change = analysis.get('change_24h', 0)
        mom_1h = analysis.get('momentum_1h', 0)
        confluence = calculate_confluence_score(analysis, strategy)
        reversal = detect_reversal_pattern(analysis)
        regime = detect_market_regime(analysis)

        if change < -dip_threshold and has_cash:
            # DCA: Buy dips but only with confluence + momentum recovery

            # Don't buy during panic (extremely high volume + falling)
            if regime['regime'] == 'VOLATILE' and mom_1h < -2:
                return (None, f"DCA: Panic selling detected - waiting for stabilization")

            # Check for reversal signals (ideal for DCA)
            if reversal['bullish_score'] >= 35 and mom_1h > -0.5:
                patterns = ', '.join(reversal['patterns'][:2]) if reversal['patterns'] else 'Recovery'
                return ('BUY', f"DCA REVERSAL: Dip={change:.1f}% | {patterns} | Mom={mom_1h:+.1f}%")

            # Or use confluence score
            if confluence['score'] >= 40 and confluence['confirmations'] >= 3:
                reasons = ' | '.join(confluence['reasons'][:3])
                return ('BUY', f"DCA ({confluence['score']}/100): Dip={change:.1f}% | {reasons}")
            else:
                return (None, f"DCA: Dip={change:.1f}% | Score={confluence['score']} | Reversal={reversal['bullish_score']}")

        return (None, f"DCA: 24h={change:.1f}% | Waiting for -{dip_threshold}% dip")

    # AVERAGING DOWN - Renforce les positions en perte
    if strategy.get('use_reinforce'):
        reinforce_threshold = strategy.get('reinforce_threshold', -5)  # Renforce si position à -5%
        max_levels = strategy.get('reinforce_levels', 3)  # Max 3 renforcements
        reinforce_mult = strategy.get('reinforce_mult', 1.5)  # Multiplier pour chaque renforcement

        # Check current position
        if has_position:
            pos = portfolio['positions'].get(symbol, {})
            entry_price = pos.get('entry_price', current_price)
            current_level = pos.get('reinforce_level', 0)
            pnl_pct = ((current_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

            # TP check - exit with profit
            take_profit = strategy.get('take_profit', 12)
            if pnl_pct >= take_profit:
                return ('SELL', f"REINFORCE TP: +{pnl_pct:.1f}% (avg entry: ${entry_price:.2f})")

            # Should we reinforce?
            if pnl_pct <= reinforce_threshold and current_level < max_levels:
                # Check if price is stabilizing (not free falling)
                mom_1h = analysis.get('momentum_1h', 0)
                rsi = analysis.get('rsi', 50)
                reversal = detect_reversal_pattern(analysis)

                # Only reinforce if showing signs of recovery
                if mom_1h > -2 and rsi < 70:
                    # Calculate new position size
                    old_qty = pos.get('quantity', 0)
                    base_amount = portfolio.get('config', {}).get('allocation_percent', 5) / 100 * portfolio['balance'].get('USDT', 0)
                    reinforce_amount = base_amount * (reinforce_mult ** current_level)

                    # Check we have enough capital
                    available = portfolio['balance'].get('USDT', 0)
                    max_position_pct = 0.3  # Max 30% of portfolio in one position
                    max_allowed = portfolio.get('initial_capital', 10000) * max_position_pct
                    current_value = old_qty * current_price

                    if available >= reinforce_amount and (current_value + reinforce_amount) <= max_allowed:
                        # Store reinforcement info for execute_trade
                        portfolio['_reinforce_level'] = current_level + 1
                        portfolio['_reinforce_old_qty'] = old_qty
                        portfolio['_reinforce_old_price'] = entry_price
                        return ('REINFORCE', f"REINFORCE L{current_level+1}: P&L={pnl_pct:.1f}% | Adding ${reinforce_amount:.0f} @ ${current_price:.2f}")
                    else:
                        return (None, f"REINFORCE: Would reinforce but capital limit reached")
                else:
                    return (None, f"REINFORCE: P&L={pnl_pct:.1f}% but still falling (mom={mom_1h:.1f}%)")

            return (None, f"REINFORCE: P&L={pnl_pct:.1f}% (threshold={reinforce_threshold}%) | Level={current_level}/{max_levels}")

        # No position yet - initial buy on dip
        else:
            change = analysis.get('change_24h', 0)
            mom_1h = analysis.get('momentum_1h', 0)
            confluence = calculate_confluence_score(analysis, strategy)

            # Buy on initial dip with reversal signals
            if change < -3 and confluence['score'] >= 35 and mom_1h > -1:
                return ('BUY', f"REINFORCE INIT: Dip={change:.1f}% | Score={confluence['score']}")

            return (None, f"REINFORCE: Waiting for entry (24h={change:.1f}%)")

    # Ichimoku Cloud - Enhanced with variants
    if strategy.get('use_ichimoku'):
        tenkan = strategy.get('tenkan', 9)
        rsi_filter = strategy.get('rsi_filter', 0)
        rsi = analysis.get('rsi', 50)

        # Get smart confirmations
        reversal = detect_reversal_pattern(analysis)
        regime = detect_market_regime(analysis)
        stoch = analysis.get('stoch_rsi', 50)
        mom_1h = analysis.get('momentum_1h', 0)
        volume_ratio = analysis.get('volume_ratio', 1.0)

        # Use fast indicators for tenkan <= 7, normal otherwise
        if tenkan <= 7:
            bullish = analysis.get('ichimoku_bullish_fast', False)
            bearish = analysis.get('ichimoku_bearish_fast', False)
            above = analysis.get('above_cloud_fast', False)
        else:
            bullish = analysis.get('ichimoku_bullish', False)
            bearish = analysis.get('ichimoku_bearish', False)
            above = analysis.get('above_cloud', False)

        rsi_ok = rsi > rsi_filter if rsi_filter > 0 else True

        # Kumo breakout - SMART with volume confirmation
        if strategy.get('kumo_break'):
            price = analysis.get('close', 0)
            cloud_top = max(analysis.get('senkou_a', 0), analysis.get('senkou_b', 0))
            if price > cloud_top * 1.005 and has_cash:
                # Need volume or momentum confirmation
                if volume_ratio > 1.2 or mom_1h > 0.3:
                    return ('BUY', f"ICHIMOKU KUMO: Break + Vol={volume_ratio:.1f}x Mom={mom_1h:+.1f}%")
                return (None, f"ICHIMOKU: Kumo break but no volume confirmation")

        # TK Cross - SMART with multiple confirmations
        if strategy.get('tk_cross'):
            tk = analysis.get('tenkan', 0)
            kj = analysis.get('kijun', 0)
            if tk > kj and above and has_cash:
                confirmations = 1  # TK cross
                if rsi < 65:
                    confirmations += 1
                if stoch < 70:
                    confirmations += 1
                if mom_1h > 0:
                    confirmations += 1
                if confirmations >= 3:
                    return ('BUY', f"ICHIMOKU TK SMART: TK cross + {confirmations} confirms")
                return (None, f"ICHIMOKU: TK cross but only {confirmations}/3 confirms")

        # Chikou confirmation - with pattern detection
        if strategy.get('chikou_confirm'):
            if bullish and above and rsi > 45 and has_cash:
                if reversal['bullish_score'] >= 15 or mom_1h > 0:
                    return ('BUY', f"ICHIMOKU CHIKOU: Bullish + Pattern score {reversal['bullish_score']}")
                return (None, f"ICHIMOKU: Chikou ok but no pattern confirmation")

        # Conservative - require ALL conditions including smart checks
        if strategy.get('require_all'):
            if bullish and above and rsi > 50 and rsi < 70 and has_cash:
                if stoch < 75 and mom_1h > -0.5 and regime['regime'] != 'VOLATILE':
                    return ('BUY', f"ICHIMOKU SAFE: All conditions + regime={regime['regime']}")
                return (None, f"ICHIMOKU: Bullish but regime={regime['regime']} or stoch={stoch:.0f}")
            elif bearish and has_position:
                return ('SELL', f"ICHIMOKU SAFE: Bearish signal")
            return (None, f"ICHIMOKU SAFE: Waiting for all conditions")

        # Standard Ichimoku - SMART: need 3+ confirmations
        if bullish and above and rsi_ok and has_cash:
            confirmations = 2  # Bullish + above cloud
            reasons = ["Bullish", "Above cloud"]

            if rsi < 60:
                confirmations += 1
                reasons.append(f"RSI={rsi:.0f}")
            if stoch < 65:
                confirmations += 1
                reasons.append(f"Stoch={stoch:.0f}")
            if mom_1h > 0:
                confirmations += 1
                reasons.append(f"Mom+")
            if volume_ratio > 1.1:
                confirmations += 1
                reasons.append(f"Vol={volume_ratio:.1f}x")

            if confirmations >= 3:
                return ('BUY', f"ICHIMOKU SMART ({confirmations}/6): {' | '.join(reasons[:4])}")
            return (None, f"ICHIMOKU: Bullish but only {confirmations}/3 confirms")

        elif bearish and has_position:
            if rsi > 55 or stoch > 60:
                return ('SELL', f"ICHIMOKU: Bearish + RSI={rsi:.0f}")

        cloud_status = "above" if above else "below"
        trend = "bullish" if bullish else ("bearish" if bearish else "neutral")
        return (None, f"ICHIMOKU: {trend}, {cloud_status} cloud | Regime={regime['regime']}")

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

    # ============ SMART STRATEGY IMPLEMENTATIONS ============

    # MACD Strategy - SMART with confluence
    if strategy.get('use_macd'):
        macd = analysis.get('macd', 0)
        macd_signal = analysis.get('macd_signal', 0)
        macd_hist = analysis.get('macd_histogram', 0)
        macd_hist_prev = analysis.get('macd_hist_prev', macd_hist)
        mode = strategy.get('mode', 'crossover')

        # Get smart confirmations
        stoch = analysis.get('stoch_rsi', 50)
        mom_1h = analysis.get('momentum_1h', 0)
        bb_pos = analysis.get('bb_position', 0.5)
        volume_ratio = analysis.get('volume_ratio', 1.0)
        reversal = detect_reversal_pattern(analysis)

        if mode == 'crossover':
            if macd > macd_signal and macd_hist > 0 and has_cash:
                # SMART: MACD cross needs confirmations
                confirmations = 1  # MACD cross
                reasons = ["MACD✓"]

                if rsi < 60:
                    confirmations += 1
                    reasons.append(f"RSI={rsi:.0f}")
                if stoch < 65:
                    confirmations += 1
                    reasons.append(f"Stoch={stoch:.0f}")
                if mom_1h > 0:
                    confirmations += 1
                    reasons.append(f"Mom+")
                if bb_pos < 0.7:
                    confirmations += 1
                    reasons.append(f"BB={bb_pos:.0%}")
                if volume_ratio > 1.1:
                    confirmations += 1
                    reasons.append(f"Vol={volume_ratio:.1f}x")

                if confirmations >= 4:
                    return ('BUY', f"MACD SMART ({confirmations}/6): {' | '.join(reasons[:4])}")
                return (None, f"MACD: Cross UP but only {confirmations}/4 confirms")

            elif macd < macd_signal and macd_hist < 0 and has_position:
                if rsi > 50 or stoch > 55:
                    return ('SELL', f"MACD CROSS DOWN + RSI={rsi:.0f}")

        else:  # histogram reversal
            if macd_hist > 0 and macd_hist_prev < 0 and has_cash:
                if rsi < 55 and mom_1h > -0.5:
                    return ('BUY', f"MACD REVERSAL: Hist+ | RSI={rsi:.0f} | Mom={mom_1h:+.1f}%")
                return (None, f"MACD: Hist reversal but RSI={rsi:.0f} or Mom={mom_1h:.1f}%")
            elif macd_hist < 0 and macd_hist_prev > 0 and has_position:
                return ('SELL', f"MACD REVERSAL: Histogram turned negative")

        return (None, f"MACD: hist={macd_hist:.4f} | RSI={rsi:.0f}")

    # Bollinger Bands Strategy - SMART with momentum check
    if strategy.get('use_bb'):
        bb_pos = analysis.get('bb_position', 0.5)
        rsi = analysis.get('rsi', 50)
        stoch = analysis.get('stoch_rsi', 50)
        mom_1h = analysis.get('momentum_1h', 0)
        volume_ratio = analysis.get('volume_ratio', 1.0)
        reversal = detect_reversal_pattern(analysis)

        if strategy.get('mode') == 'combo':
            if bb_pos < 0.2 and rsi < 35 and has_cash:
                # Need momentum confirmation - not still falling
                if mom_1h > -0.5 and (stoch < 30 or reversal['bullish_score'] >= 20):
                    return ('BUY', f"BB+RSI SMART: BB={bb_pos:.0%} RSI={rsi:.0f} Mom={mom_1h:+.1f}%")
                return (None, f"BB+RSI: Oversold but still falling (mom={mom_1h:.1f}%)")
            elif bb_pos > 0.8 and rsi > 65 and has_position:
                return ('SELL', f"BB+RSI: Near upper band + overbought")
        else:
            if bb_pos < 0.1 and has_cash:
                # Need confirmation - volume or pattern
                if volume_ratio > 1.2 or reversal['bullish_score'] >= 25 or mom_1h > 0:
                    return ('BUY', f"BB SMART: Lower band + confirmed (Vol={volume_ratio:.1f}x)")
                return (None, f"BB: At lower band but no confirmation")
            elif bb_pos > 0.9 and has_position:
                return ('SELL', f"BB: Price at upper band ({bb_pos:.2f})")

        return (None, f"BB: pos={bb_pos:.0%} | RSI={rsi:.0f}")

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

    # Swing Trading Strategy
    if strategy.get('use_swing'):
        rsi = analysis.get('rsi', 50)
        ema_cross = analysis.get('ema_9', 0) > analysis.get('ema_21', 0)
        momentum = analysis.get('momentum', 0)

        if rsi < 35 and momentum > 0.2 and has_cash:
            return ('BUY', f"SWING: Oversold bounce RSI={rsi:.0f}")
        elif rsi > 65 and momentum < -0.2 and has_position:
            return ('SELL', f"SWING: Overbought reversal RSI={rsi:.0f}")
        return (None, f"SWING: RSI={rsi:.0f}, waiting for setup")

    # Leverage Strategy (high risk)
    if strategy.get('use_leverage'):
        rsi = analysis.get('rsi', 50)
        momentum = analysis.get('momentum', 0)
        volume_ratio = analysis.get('volume_ratio', 1)

        # More aggressive entries for leverage
        if rsi < 30 and momentum > 0.5 and volume_ratio > 1.5 and has_cash:
            return ('BUY', f"LEVERAGE: Strong setup RSI={rsi:.0f}, vol={volume_ratio:.1f}x")
        elif rsi > 70 or momentum < -1.0 and has_position:
            return ('SELL', f"LEVERAGE: Exit signal")
        return (None, f"LEVERAGE: waiting for high-conviction setup")

    # Heikin Ashi Strategy
    if strategy.get('use_ha'):
        # Simplified HA logic using momentum and trend
        ema_trend = analysis.get('ema_9', 0) > analysis.get('ema_21', 0)
        momentum = analysis.get('momentum', 0)
        rsi = analysis.get('rsi', 50)

        if ema_trend and momentum > 0.3 and rsi < 65 and has_cash:
            return ('BUY', f"HEIKIN ASHI: Bullish trend + momentum")
        elif not ema_trend and momentum < -0.3 and has_position:
            return ('SELL', f"HEIKIN ASHI: Bearish reversal")
        return (None, f"HEIKIN ASHI: trend={'up' if ema_trend else 'down'}")

    # Range Strategy
    if strategy.get('use_range'):
        bb_pos = analysis.get('bb_position', 0.5)
        rsi = analysis.get('rsi', 50)

        if bb_pos < 0.15 and rsi < 35 and has_cash:
            return ('BUY', f"RANGE: Bottom of range, BB={bb_pos:.2f}")
        elif bb_pos > 0.85 and rsi > 65 and has_position:
            return ('SELL', f"RANGE: Top of range, BB={bb_pos:.2f}")
        return (None, f"RANGE: position={bb_pos:.2f}")

    # Pivot Strategy
    if strategy.get('use_pivot'):
        price = analysis.get('close', 0)
        sma_20 = analysis.get('sma_20', price)
        rsi = analysis.get('rsi', 50)

        # Pivot around SMA as support/resistance
        if price < sma_20 * 0.98 and rsi < 40 and has_cash:
            return ('BUY', f"PIVOT: Below support, expecting bounce")
        elif price > sma_20 * 1.02 and rsi > 60 and has_position:
            return ('SELL', f"PIVOT: Above resistance")
        return (None, f"PIVOT: price near SMA")

    # Sentiment Strategy (using RSI as proxy)
    if strategy.get('use_sentiment'):
        rsi = analysis.get('rsi', 50)
        volume_ratio = analysis.get('volume_ratio', 1)

        # Extreme sentiment readings
        if rsi < 20 and has_cash:
            return ('BUY', f"SENTIMENT: Extreme fear RSI={rsi:.0f}")
        elif rsi > 80 and has_position:
            return ('SELL', f"SENTIMENT: Extreme greed RSI={rsi:.0f}")
        return (None, f"SENTIMENT: neutral RSI={rsi:.0f}")

    # Multi-Timeframe Strategy (simplified)
    if strategy.get('use_mtf'):
        ema_short = analysis.get('ema_9', 0) > analysis.get('ema_21', 0)
        ema_long = analysis.get('sma_20', 0) < analysis.get('close', 0)
        rsi = analysis.get('rsi', 50)

        if ema_short and ema_long and rsi < 60 and has_cash:
            return ('BUY', f"MTF: All timeframes aligned bullish")
        elif not ema_short and not ema_long and has_position:
            return ('SELL', f"MTF: All timeframes bearish")
        return (None, f"MTF: waiting for alignment")

    # Orderflow Strategy (simplified using volume)
    if strategy.get('use_orderflow'):
        volume_ratio = analysis.get('volume_ratio', 1)
        momentum = analysis.get('momentum', 0)

        if volume_ratio > 2.5 and momentum > 0.5 and has_cash:
            return ('BUY', f"ORDERFLOW: Heavy buying pressure")
        elif volume_ratio > 2.5 and momentum < -0.5 and has_position:
            return ('SELL', f"ORDERFLOW: Heavy selling pressure")
        return (None, f"ORDERFLOW: vol={volume_ratio:.1f}x")

    # Martingale - assoupli (RSI < 40 au lieu de 35)
    if strategy.get('use_martingale'):
        multiplier = strategy.get('multiplier', 2.0)
        max_levels = strategy.get('max_levels', 4)

        # Get smart confirmations
        stoch = analysis.get('stoch_rsi', 50)
        mom_1h = analysis.get('momentum_1h', 0)
        bb_pos = analysis.get('bb_position', 0.5)
        reversal = detect_reversal_pattern(analysis)
        regime = detect_market_regime(analysis)

        # Count consecutive losses
        trades = portfolio.get('trades', [])
        consecutive_losses = 0
        for t in reversed(trades):
            if t.get('action') == 'SELL':
                if t.get('pnl', 0) < 0:
                    consecutive_losses += 1
                else:
                    break

        # SMART MARTINGALE: Only double down when market shows reversal signs
        if consecutive_losses > 0 and consecutive_losses <= max_levels:
            if has_cash:
                # Need multiple confirmations for martingale entry
                confirmations = 0
                reasons = [f"Level {consecutive_losses}"]

                if rsi < 45:
                    confirmations += 1
                    reasons.append(f"RSI={rsi:.0f}")
                if stoch < 40:
                    confirmations += 1
                    reasons.append(f"Stoch={stoch:.0f}")
                if mom_1h > -1:  # Not crashing hard
                    confirmations += 1
                    reasons.append("Mom stable")
                if reversal['bullish_score'] >= 20:
                    confirmations += 1
                    reasons.append("Pattern+")
                if regime['regime'] != 'VOLATILE':
                    confirmations += 1

                # Need 3+ confirmations for martingale
                if confirmations >= 3:
                    portfolio['_martingale_level'] = consecutive_losses
                    portfolio['_martingale_multiplier'] = multiplier
                    return ('BUY', f"MARTINGALE SMART ({confirmations}/5): {' | '.join(reasons[:4])}")
                return (None, f"MARTINGALE: Level {consecutive_losses} but only {confirmations}/3 confirms")

        elif consecutive_losses > max_levels:
            # Max level - need strong reversal signal
            if has_cash and rsi < 30 and reversal['bullish_score'] >= 30:
                portfolio['_martingale_level'] = 0
                return ('BUY', f"MARTINGALE RESET: RSI={rsi:.0f} + Pattern={reversal['bullish_score']}")
            return (None, f"MARTINGALE: Max level - waiting for strong reversal")

        # Normal entry - smart conditions
        if has_cash:
            if rsi < 35 and stoch < 35 and mom_1h > -0.5:
                portfolio['_martingale_level'] = 0
                return ('BUY', f"MARTINGALE ENTRY: RSI={rsi:.0f} Stoch={stoch:.0f} Mom={mom_1h:+.1f}%")
        elif has_position:
            if rsi > 65 and stoch > 70:
                return ('SELL', f"MARTINGALE: RSI={rsi:.0f} Stoch={stoch:.0f}")

        return (None, f"MARTINGALE: RSI={rsi:.0f} Stoch={stoch:.0f} | Losses={consecutive_losses}")

    # ============ EXISTING STRATEGIES ============

    # Aggressive Strategy - SMART: agressif mais avec confirmations
    if strategy.get('use_aggressive'):
        mom_1h = analysis.get('momentum_1h', 0)
        stoch = analysis.get('stoch_rsi', 50)
        bb_pos = analysis.get('bb_position', 0.5)
        volume_ratio = analysis.get('volume_ratio', 1.0)
        reversal = detect_reversal_pattern(analysis)

        if has_cash:
            # Aggressive but need 2+ confirmations
            confirmations = 0
            reasons = []

            if rsi < 45:
                confirmations += 1
                reasons.append(f"RSI={rsi:.0f}")
            if stoch < 50:
                confirmations += 1
                reasons.append(f"Stoch={stoch:.0f}")
            if mom_1h > 0:
                confirmations += 1
                reasons.append(f"Mom+{mom_1h:.1f}%")
            if bb_pos < 0.5:
                confirmations += 1
                reasons.append(f"BB={bb_pos:.0%}")
            if reversal['bullish_score'] >= 15:
                confirmations += 1
                reasons.append("Pattern+")

            if confirmations >= 3:
                return ('BUY', f"AGGRESSIVE ({confirmations}/5): {' | '.join(reasons[:4])}")
            elif rsi < 35 and mom_1h > -0.3:  # Very oversold exception
                return ('BUY', f"AGGRESSIVE: RSI={rsi:.0f} very low + mom stable")

        elif has_position:
            if rsi > 60 and stoch > 55:
                return ('SELL', f"AGGRESSIVE: RSI={rsi:.0f} Stoch={stoch:.0f}")
            elif mom_1h < -0.5 and reversal['bearish_score'] >= 20:
                return ('SELL', f"AGGRESSIVE: Mom={mom_1h:.1f}% + bearish pattern")

        return (None, f"AGGRESSIVE: RSI={rsi:.0f} Stoch={stoch:.0f} | Mom={mom_1h:+.1f}%")

    signal = analysis.get('signal', 'HOLD')

    # RSI Strategy - SMART ENTRY with confluence
    if strategy.get('use_rsi', False):
        rsi_oversold = config.get('rsi_oversold', 35)
        rsi_overbought = config.get('rsi_overbought', 70)

        # Get confluence and pattern data
        confluence = calculate_confluence_score(analysis, strategy)
        reversal = detect_reversal_pattern(analysis)
        regime = detect_market_regime(analysis)

        stoch = analysis.get('stoch_rsi', 50)
        mom_1h = analysis.get('momentum_1h', 0)
        bb_pos = analysis.get('bb_position', 0.5)
        volume_ratio = analysis.get('volume_ratio', 1.0)

        if has_cash:
            # RSI oversold - but need confirmation!
            if rsi < rsi_oversold:
                confirmations = 0
                reasons = [f"RSI={rsi:.0f}"]

                # Check for multiple confirmations
                if stoch < 25:
                    confirmations += 1
                    reasons.append(f"Stoch={stoch:.0f}")
                if bb_pos < 0.2:
                    confirmations += 1
                    reasons.append(f"BB={bb_pos:.0%}")
                if mom_1h > -0.5:  # Not falling hard
                    confirmations += 1
                    reasons.append("Mom stable")
                if volume_ratio > 1.2:  # Volume confirmation
                    confirmations += 1
                    reasons.append(f"Vol={volume_ratio:.1f}x")
                if reversal['bullish_score'] >= 20:
                    confirmations += 1
                    reasons.append(f"Pattern:{reversal['patterns'][0] if reversal['patterns'] else 'none'}")
                if regime['regime'] != 'VOLATILE' or regime['direction'] == 'OVERSOLD':
                    confirmations += 1

                # Need 3+ confirmations to enter
                if confirmations >= 3:
                    return ('BUY', f"RSI SMART ({confluence['score']}/100): {' | '.join(reasons[:4])}")
                else:
                    return (None, f"RSI: {rsi:.0f} oversold but only {confirmations} confirms (need 3)")

        elif has_position:
            if rsi > rsi_overbought and stoch > 75:
                return ('SELL', f"RSI={rsi:.0f} > {rsi_overbought} overbought + Stoch={stoch:.0f}")

        return (None, f"RSI={rsi:.0f} | Stoch={stoch:.0f} | Confluence={confluence['score']}")

    # DCA Fear & Greed Strategy - SMART with technical confirmation
    if strategy.get('use_fear_greed', False):
        fng = get_fear_greed_index()
        fear_value = fng['value']
        fear_class = fng['classification']

        # Get technical confirmation
        confluence = calculate_confluence_score(analysis, strategy)
        reversal = detect_reversal_pattern(analysis)

        stoch = analysis.get('stoch_rsi', 50)
        mom_1h = analysis.get('momentum_1h', 0)
        bb_pos = analysis.get('bb_position', 0.5)

        if has_cash:
            # Extreme Fear (<20) - still need SOME technical confirmation
            if fear_value < 20:
                if rsi < 45 and mom_1h > -2:  # Not in freefall
                    return ('BUY', f"F&G EXTREME ({fear_value}): Fear={fear_value} + RSI={rsi:.0f} | Not freefall")
                else:
                    return (None, f"F&G: Extreme fear {fear_value} but market still falling (mom={mom_1h:.1f}%)")

            # Fear (20-40) - need more confirmation
            elif fear_value < 40:
                confirmations = 0
                reasons = [f"Fear={fear_value}"]

                if rsi < 40:
                    confirmations += 1
                    reasons.append(f"RSI={rsi:.0f}")
                if stoch < 35:
                    confirmations += 1
                    reasons.append(f"Stoch={stoch:.0f}")
                if bb_pos < 0.3:
                    confirmations += 1
                    reasons.append(f"BB low")
                if mom_1h > -0.5:  # Momentum stabilizing
                    confirmations += 1
                    reasons.append("Mom stable")
                if reversal['bullish_score'] >= 25:
                    confirmations += 1
                    reasons.append("Pattern+")

                if confirmations >= 3:
                    return ('BUY', f"F&G SMART ({confluence['score']}/100): {' | '.join(reasons[:4])}")
                else:
                    return (None, f"F&G: Fear={fear_value} but only {confirmations} confirms (need 3)")

        elif has_position:
            if fear_value > 80 and rsi > 65 and stoch > 70:
                return ('SELL', f"F&G GREED: {fear_value} + RSI={rsi:.0f} + Stoch={stoch:.0f}")
            elif fear_value > 75 and reversal['bearish_score'] >= 30:
                return ('SELL', f"F&G GREED: {fear_value} + Bearish pattern detected")

        return (None, f"F&G: {fear_value} ({fear_class}) | RSI={rsi:.0f} | Score={confluence['score']}")

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

    # ============ HIGH PRIORITY STRATEGY HANDLERS ============

    # 1. Fibonacci Retracement Strategy
    if strategy.get('use_fib'):
        levels = strategy.get('levels', [0.382, 0.5, 0.618])
        aggressive = strategy.get('aggressive', False)
        price = analysis.get('close', 0)
        fib_382 = analysis.get('fib_382', 0)
        fib_500 = analysis.get('fib_500', 0)
        fib_618 = analysis.get('fib_618', 0)
        fib_236 = analysis.get('fib_236', 0)
        fib_786 = analysis.get('fib_786', 0)
        swing_high = analysis.get('swing_high', 0)
        swing_low = analysis.get('swing_low', 0)

        # Check if price is near any fib level (within 0.5%)
        tolerance = 0.005 if aggressive else 0.003
        near_382 = abs(price - fib_382) / fib_382 < tolerance if fib_382 > 0 else False
        near_500 = abs(price - fib_500) / fib_500 < tolerance if fib_500 > 0 else False
        near_618 = abs(price - fib_618) / fib_618 < tolerance if fib_618 > 0 else False
        near_236 = abs(price - fib_236) / fib_236 < tolerance if fib_236 > 0 else False
        near_786 = abs(price - fib_786) / fib_786 < tolerance if fib_786 > 0 else False

        # Buy at support levels (fib retracement from high)
        if has_cash:
            if 0.618 in levels and near_618 and rsi < 45:
                return ('BUY', f"FIB 61.8%: Price at golden ratio support | RSI={rsi:.0f}")
            if 0.5 in levels and near_500 and rsi < 50:
                return ('BUY', f"FIB 50%: Price at 50% retracement | RSI={rsi:.0f}")
            if 0.382 in levels and near_382 and rsi < 55:
                return ('BUY', f"FIB 38.2%: Price at key support | RSI={rsi:.0f}")
            if aggressive and 0.236 in levels and near_236:
                return ('BUY', f"FIB 23.6%: Aggressive entry at shallow pullback")

        # Sell at resistance levels
        if has_position:
            if near_786 and rsi > 60:
                return ('SELL', f"FIB 78.6%: Price at deep resistance")
            if price >= swing_high * 0.99:
                return ('SELL', f"FIB: Price near swing high, taking profit")

        return (None, f"FIB: Price ${price:.4f} | 38.2%=${fib_382:.4f} | 61.8%=${fib_618:.4f}")

    # 2. Volume Profile (VPVR) Strategy
    if strategy.get('use_vpvr'):
        mode = strategy.get('mode', 'poc')
        price = analysis.get('close', 0)
        poc = analysis.get('vpvr_poc', 0)
        vah = analysis.get('vpvr_vah', 0)
        val = analysis.get('vpvr_val', 0)
        tolerance = 0.005  # 0.5%

        if mode == 'poc':
            # Trade at Point of Control (highest volume node)
            near_poc = abs(price - poc) / poc < tolerance if poc > 0 else False
            if near_poc and price > poc and has_cash and rsi < 55:
                return ('BUY', f"VPVR POC: Price bouncing off POC=${poc:.4f}")
            elif near_poc and price < poc and has_position:
                return ('SELL', f"VPVR POC: Price rejected at POC=${poc:.4f}")

        elif mode == 'vah':
            # Trade at Value Area High (resistance)
            near_vah = abs(price - vah) / vah < tolerance if vah > 0 else False
            if price < vah * 0.99 and has_cash and rsi < 50:
                return ('BUY', f"VPVR VAH: Price below VAH, room to run")
            elif near_vah and has_position:
                return ('SELL', f"VPVR VAH: Price at Value Area High=${vah:.4f}")

        elif mode == 'val':
            # Trade at Value Area Low (support)
            near_val = abs(price - val) / val < tolerance if val > 0 else False
            if near_val and has_cash and rsi < 45:
                return ('BUY', f"VPVR VAL: Price at Value Area Low=${val:.4f}")
            elif price > vah and has_position:
                return ('SELL', f"VPVR: Price broke above VAH")

        return (None, f"VPVR: POC=${poc:.4f} | VAH=${vah:.4f} | VAL=${val:.4f}")

    # 3. Order Blocks (ICT) Strategy
    if strategy.get('use_ob'):
        mode = strategy.get('mode', 'bullish')
        price = analysis.get('close', 0)
        bullish_ob = analysis.get('bullish_ob')
        bearish_ob = analysis.get('bearish_ob')
        ob_bull_top = analysis.get('ob_bullish_top')
        ob_bull_bottom = analysis.get('ob_bullish_bottom')

        if mode in ['bullish', 'all'] and bullish_ob:
            # Price entering bullish order block = buy zone
            if ob_bull_bottom and ob_bull_top:
                if price >= ob_bull_bottom * 0.995 and price <= ob_bull_top * 1.005 and has_cash:
                    return ('BUY', f"ICT OB: Price in bullish order block ${ob_bull_bottom:.4f}-${ob_bull_top:.4f}")

        if mode in ['bearish', 'all'] and bearish_ob:
            # Price entering bearish order block = sell zone
            ob_bear_top = analysis.get('ob_bearish_top')
            ob_bear_bottom = analysis.get('ob_bearish_bottom')
            if ob_bear_bottom and ob_bear_top:
                if price >= ob_bear_bottom * 0.995 and price <= ob_bear_top * 1.005 and has_position:
                    return ('SELL', f"ICT OB: Price in bearish order block")

        return (None, f"ICT OB: Bull OB=${bullish_ob or 'none'} | Bear OB=${bearish_ob or 'none'}")

    # 4. Fair Value Gap (FVG) Strategy
    if strategy.get('use_fvg'):
        mode = strategy.get('mode', 'fill')
        price = analysis.get('close', 0)
        bull_fvg = analysis.get('bullish_fvg')
        bear_fvg = analysis.get('bearish_fvg')
        fvg_bull_top = analysis.get('fvg_bull_top')
        fvg_bull_bottom = analysis.get('fvg_bull_bottom')

        if mode == 'fill':
            # Buy when price fills bullish FVG (imbalance)
            if bull_fvg and fvg_bull_bottom and fvg_bull_top:
                if price >= fvg_bull_bottom and price <= fvg_bull_top and has_cash:
                    return ('BUY', f"FVG FILL: Price filling bullish gap ${fvg_bull_bottom:.4f}-${fvg_bull_top:.4f}")

        elif mode == 'rejection':
            # Sell when price rejects at bearish FVG
            if bear_fvg and has_position:
                fvg_bear_bottom = analysis.get('fvg_bear_bottom')
                fvg_bear_top = analysis.get('fvg_bear_top')
                if fvg_bear_bottom and fvg_bear_top:
                    if price >= fvg_bear_bottom and price <= fvg_bear_top:
                        return ('SELL', f"FVG REJECTION: Price at bearish gap")

        elif mode == 'aggressive':
            # More aggressive FVG entries
            if bull_fvg and has_cash and rsi < 50:
                if price <= bull_fvg * 1.01:
                    return ('BUY', f"FVG AGG: Near bullish FVG=${bull_fvg:.4f}")
            if bear_fvg and has_position and rsi > 50:
                if price >= bear_fvg * 0.99:
                    return ('SELL', f"FVG AGG: Near bearish FVG=${bear_fvg:.4f}")

        return (None, f"FVG: Bull=${bull_fvg or 'none'} | Bear=${bear_fvg or 'none'}")

    # 5. Liquidity Sweep Strategy
    if strategy.get('use_liquidity'):
        mode = strategy.get('mode', 'sweep')
        high_swept = analysis.get('high_swept', False)
        low_swept = analysis.get('low_swept', False)
        recent_high = analysis.get('recent_high', 0)
        recent_low = analysis.get('recent_low', 0)
        price = analysis.get('close', 0)

        if mode == 'sweep':
            # Liquidity sweep = price swept level then reversed
            if low_swept and has_cash:
                return ('BUY', f"LIQUIDITY SWEEP: Swept lows at ${recent_low:.4f}, now reversing up")
            if high_swept and has_position:
                return ('SELL', f"LIQUIDITY SWEEP: Swept highs at ${recent_high:.4f}, now reversing down")

        elif mode == 'grab':
            # Liquidity grab with momentum confirmation
            momentum = analysis.get('momentum', 0)
            if low_swept and momentum > 0.2 and has_cash:
                return ('BUY', f"LIQUIDITY GRAB: Swept ${recent_low:.4f} + momentum={momentum:.2f}%")
            if high_swept and momentum < -0.2 and has_position:
                return ('SELL', f"LIQUIDITY GRAB: Swept ${recent_high:.4f} + reversal")

        elif mode == 'hunt':
            # Stop hunt detection
            if low_swept and rsi < 40 and has_cash:
                return ('BUY', f"STOP HUNT: Stops hit at ${recent_low:.4f}, RSI={rsi:.0f}")
            if high_swept and rsi > 60 and has_position:
                return ('SELL', f"STOP HUNT: Stops hit at ${recent_high:.4f}")

        return (None, f"LIQUIDITY: High swept={high_swept} | Low swept={low_swept}")

    # 6. Session Trading Strategy
    if strategy.get('use_session'):
        session = strategy.get('session', 'london')
        is_asian = analysis.get('session_asian', False)
        is_london = analysis.get('session_london', False)
        is_ny = analysis.get('session_newyork', False)
        is_overlap = analysis.get('session_overlap', False)
        momentum = analysis.get('momentum', 0)

        active_session = False
        session_name = ""

        if session == 'asian' and is_asian:
            active_session = True
            session_name = "ASIAN"
        elif session == 'london' and is_london:
            active_session = True
            session_name = "LONDON"
        elif session == 'newyork' and is_ny:
            active_session = True
            session_name = "NEW YORK"
        elif session == 'overlap' and is_overlap:
            active_session = True
            session_name = "OVERLAP"

        if active_session:
            if momentum > 0.3 and has_cash and rsi < 60:
                return ('BUY', f"SESSION {session_name}: Momentum={momentum:.2f}% + RSI={rsi:.0f}")
            elif momentum < -0.3 and has_position:
                return ('SELL', f"SESSION {session_name}: Negative momentum")
            return (None, f"SESSION {session_name}: Active, waiting for momentum")

        return (None, f"SESSION: Waiting for {session.upper()} session")

    # 7. RSI Divergence Strategy - SMART with confirmations
    if strategy.get('use_divergence'):
        div_type = strategy.get('type', 'bullish')
        bull_div = analysis.get('rsi_bullish_div', False)
        bear_div = analysis.get('rsi_bearish_div', False)
        hidden_bull = analysis.get('rsi_hidden_bull_div', False)
        hidden_bear = analysis.get('rsi_hidden_bear_div', False)

        # Get confirmations
        stoch = analysis.get('stoch_rsi', 50)
        mom_1h = analysis.get('momentum_1h', 0)
        volume_ratio = analysis.get('volume_ratio', 1.0)
        reversal = detect_reversal_pattern(analysis)

        if div_type == 'bullish':
            if bull_div and has_cash:
                # Need confirmation for divergence entry
                confirmations = 1  # Divergence itself
                reasons = ["Bull Div"]

                if rsi < 45:
                    confirmations += 1
                    reasons.append(f"RSI={rsi:.0f}")
                if stoch < 40:
                    confirmations += 1
                    reasons.append(f"Stoch={stoch:.0f}")
                if mom_1h > -0.5:  # Not still falling hard
                    confirmations += 1
                    reasons.append("Mom stable")
                if volume_ratio > 1.1:
                    confirmations += 1
                    reasons.append(f"Vol={volume_ratio:.1f}x")

                if confirmations >= 3:
                    return ('BUY', f"RSI DIV SMART ({confirmations}/5): {' | '.join(reasons[:4])}")
                return (None, f"RSI DIV: Divergence but only {confirmations}/3 confirms")

        elif div_type == 'bearish':
            if bear_div and has_position:
                if rsi > 55 or stoch > 60:
                    return ('SELL', f"RSI DIVERGENCE: Bearish + RSI={rsi:.0f} Stoch={stoch:.0f}")

        elif div_type == 'hidden':
            if hidden_bull and has_cash:
                if rsi < 50 and mom_1h > 0:
                    return ('BUY', f"HIDDEN DIV: Bullish continuation | RSI={rsi:.0f} Mom+")
            if hidden_bear and has_position:
                if rsi > 50 and mom_1h < 0:
                    return ('SELL', f"HIDDEN DIV: Bearish continuation | RSI={rsi:.0f}")

        return (None, f"RSI DIV: Bull={bull_div} | Bear={bear_div} | Stoch={stoch:.0f}")

    # ============ BTC CORRELATION / BETA LAG STRATEGY ============

    if strategy.get('use_btc_lag'):
        # Get BTC reference data
        btc_ref = get_btc_reference()
        btc_change_1h = btc_ref.get('change_1h', 0)

        # Get altcoin change
        alt_change_1h = analysis.get('momentum_1h', 0)
        alt_symbol = symbol.split('/')[0]

        # Skip BTC itself
        if alt_symbol == 'BTC':
            return (None, "BTC LAG: Cannot trade BTC against itself")

        # Strategy parameters
        min_btc_gain = strategy.get('min_btc_gain', 1.0)  # BTC must be up at least this %
        max_alt_gain = strategy.get('max_alt_gain', 0.3)  # Alt must be up less than this %

        # Get confirmations
        stoch = analysis.get('stoch_rsi', 50)
        bb_pos = analysis.get('bb_position', 0.5)
        volume_ratio = analysis.get('volume_ratio', 1.0)
        reversal = detect_reversal_pattern(analysis)

        if has_cash:
            # BUY condition: BTC up, altcoin lagging
            if btc_change_1h >= min_btc_gain and alt_change_1h < max_alt_gain:
                lag = btc_change_1h - alt_change_1h

                # Need confirmations for quality entry
                confirmations = 1  # Lag detected
                reasons = [f"BTC+{btc_change_1h:.1f}%", f"{alt_symbol}{alt_change_1h:+.1f}%", f"Lag={lag:.1f}%"]

                if rsi < 60:  # Not overbought
                    confirmations += 1
                    reasons.append(f"RSI={rsi:.0f}")
                if stoch < 65:
                    confirmations += 1
                if bb_pos < 0.7:  # Room to run
                    confirmations += 1
                if volume_ratio > 0.8:  # Decent volume
                    confirmations += 1
                if reversal['bullish_score'] >= 15:
                    confirmations += 1
                    reasons.append("Pattern+")

                if confirmations >= 2:
                    return ('BUY', f"BTC LAG ({confirmations}/6): {' | '.join(reasons[:4])}")
                return (None, f"BTC LAG: Lag detected but only {confirmations}/2 confirms")

            # Check if alt is AHEAD of BTC (potential short opportunity - log only)
            elif btc_change_1h < -min_btc_gain and alt_change_1h > -max_alt_gain:
                return (None, f"BTC LAG SHORT: BTC{btc_change_1h:+.1f}% vs {alt_symbol}{alt_change_1h:+.1f}% (no short in paper)")

        elif has_position:
            # Sell when alt catches up or BTC reverses
            if alt_change_1h >= btc_change_1h or btc_change_1h < 0:
                if rsi > 55 or stoch > 60:
                    return ('SELL', f"BTC LAG EXIT: {alt_symbol} caught up or BTC reversed")

        return (None, f"BTC LAG: BTC{btc_change_1h:+.1f}% | {alt_symbol}{alt_change_1h:+.1f}% | Wait for gap")

    # ============ SHORT STRATEGIES (PAPER ONLY) ============

    # BTC Beta Lag SHORT - Short alts that haven't followed BTC down
    if strategy.get('use_btc_lag_short'):
        btc_ref = get_btc_reference()
        btc_change_1h = btc_ref.get('change_1h', 0)
        alt_change_1h = analysis.get('momentum_1h', 0)
        alt_symbol = symbol.split('/')[0]

        if alt_symbol == 'BTC':
            return (None, "BTC LAG SHORT: Cannot trade BTC against itself")

        min_btc_drop = strategy.get('min_btc_drop', 1.0)  # BTC must be DOWN at least this %
        max_alt_drop = strategy.get('max_alt_drop', 0.3)  # Alt must be down LESS than this %

        stoch = analysis.get('stoch_rsi', 50)
        bb_pos = analysis.get('bb_position', 0.5)
        reversal = detect_reversal_pattern(analysis)

        # Check for existing short position - handle exit
        has_short = symbol in portfolio.get('short_positions', {})

        if has_cash and not has_short:
            # SHORT condition: BTC dropping, altcoin NOT dropping (lagging behind)
            if btc_change_1h <= -min_btc_drop and alt_change_1h > -max_alt_drop:
                lag = alt_change_1h - btc_change_1h  # Positive = alt hasn't dropped

                confirmations = 1  # Lag detected
                reasons = [f"BTC{btc_change_1h:+.1f}%", f"{alt_symbol}{alt_change_1h:+.1f}%", f"Lag={lag:.1f}%"]

                if rsi > 45:  # Not oversold
                    confirmations += 1
                    reasons.append(f"RSI={rsi:.0f}")
                if stoch > 40:
                    confirmations += 1
                if bb_pos > 0.4:  # Room to fall
                    confirmations += 1
                if reversal['bearish_score'] >= 15:
                    confirmations += 1
                    reasons.append("BearPattern")

                if confirmations >= 3:
                    return ('SHORT', f"BTC LAG SHORT ({confirmations}/5): {' | '.join(reasons[:4])}")
                return (None, f"BTC LAG SHORT: Lag detected but only {confirmations}/3 confirms")

        elif has_short:
            # Cover when alt catches up (drops) or BTC reverses (goes up)
            if alt_change_1h <= btc_change_1h or btc_change_1h > 0:
                if rsi < 45 or stoch < 40:
                    return ('COVER', f"BTC LAG SHORT EXIT: {alt_symbol} caught down or BTC reversed up")

        return (None, f"BTC LAG SHORT: BTC{btc_change_1h:+.1f}% | {alt_symbol}{alt_change_1h:+.1f}% | Wait for drop gap")

    # RSI Overbought SHORT - Short when RSI extremely high with bearish patterns
    if strategy.get('use_rsi_short'):
        overbought = strategy.get('overbought', 75)
        stoch = analysis.get('stoch_rsi', 50)
        reversal = detect_reversal_pattern(analysis)
        bb_pos = analysis.get('bb_position', 0.5)

        has_short = symbol in portfolio.get('short_positions', {})

        if has_cash and not has_short:
            if rsi >= overbought:
                confirmations = 1  # RSI overbought
                reasons = [f"RSI={rsi:.0f}"]

                if stoch > 75:
                    confirmations += 1
                    reasons.append(f"Stoch={stoch:.0f}")
                if bb_pos > 0.85:  # At upper band
                    confirmations += 1
                    reasons.append("BB_HIGH")
                if reversal['bearish_score'] >= 20:
                    confirmations += 1
                    reasons.append(f"Bear={reversal['bearish_score']}")
                if trend == 'bearish':
                    confirmations += 1
                    reasons.append("TREND_DOWN")

                # Require 3+ confirmations for short
                if confirmations >= 3:
                    return ('SHORT', f"RSI SHORT ({confirmations}/5): {' | '.join(reasons)}")
                return (None, f"RSI SHORT: Overbought but only {confirmations}/3 confirms")

        elif has_short:
            # Cover when RSI drops or hits support
            if rsi < 50 or bb_pos < 0.3:
                return ('COVER', f"RSI SHORT EXIT: RSI={rsi:.0f} BB={bb_pos:.2f}")

        return (None, f"RSI SHORT: RSI={rsi:.0f} | Stoch={stoch:.0f} | Wait for overbought")

    # Mean Reversion SHORT - Short excessive pumps
    if strategy.get('use_mean_rev_short'):
        std_dev_threshold = strategy.get('std_dev', 2.0)
        bb_pos = analysis.get('bb_position', 0.5)
        bb_width = analysis.get('bb_width', 0.02)
        mom_1h = analysis.get('momentum_1h', 0)
        mom_24h = analysis.get('momentum_24h', 0)
        stoch = analysis.get('stoch_rsi', 50)
        reversal = detect_reversal_pattern(analysis)

        has_short = symbol in portfolio.get('short_positions', {})

        if has_cash and not has_short:
            # Detect excessive pump: way above upper BB + big momentum
            is_pumped = bb_pos > 0.95 and mom_1h > 5  # Above upper band + strong 1h pump

            if is_pumped:
                confirmations = 1  # Pump detected
                reasons = [f"BB={bb_pos:.2f}", f"Mom1h={mom_1h:.1f}%"]

                if rsi > 70:
                    confirmations += 1
                    reasons.append(f"RSI={rsi:.0f}")
                if stoch > 80:
                    confirmations += 1
                    reasons.append(f"Stoch={stoch:.0f}")
                if mom_24h > 15:  # Extended 24h move
                    confirmations += 1
                    reasons.append(f"Mom24h={mom_24h:.1f}%")
                if reversal['bearish_score'] >= 15:
                    confirmations += 1
                    reasons.append("BearPattern")

                if confirmations >= 3:
                    return ('SHORT', f"MEAN REV SHORT ({confirmations}/5): {' | '.join(reasons)}")
                return (None, f"MEAN REV SHORT: Pump detected but only {confirmations}/3 confirms")

        elif has_short:
            # Cover when price returns to mean
            if bb_pos < 0.6 or rsi < 50:
                return ('COVER', f"MEAN REV EXIT: Price returning to mean BB={bb_pos:.2f}")

        return (None, f"MEAN REV SHORT: BB={bb_pos:.2f} | Mom1h={mom_1h:.1f}% | Wait for pump")

    # ============ EXTERNAL DATA STRATEGIES ============

    # Sniper Strategy - Uses external token scanning (handled by degen_scanner.py)
    if strategy.get('use_sniper'):
        max_risk = strategy.get('max_risk', 60)
        min_liq = strategy.get('min_liquidity', 1000)
        return (None, f"SNIPER: Scanning new tokens (risk<{max_risk}, liq>${min_liq}) - see degen_scanner")

    # Whale/Congress/Legend Strategy - Uses external wallet tracking
    if strategy.get('use_whale'):
        whale_ids = strategy.get('whale_ids', [])
        whale_names = ', '.join(whale_ids[:3])
        if 'congress' in whale_names:
            return (None, f"CONGRESS: Tracking {whale_names} trades - external data")
        elif 'legend' in whale_names:
            return (None, f"LEGEND: Following {whale_names} style - external data")
        else:
            return (None, f"WHALE: Tracking {whale_names} wallets - external data")

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

    # === AUTO-UPDATE CRYPTO LIST (once per day) ===
    if AUTO_UPDATE_ENABLED and should_update():
        try:
            update_result = run_auto_update()
            if update_result.get('updated'):
                log(f"[AUTO-UPDATE] Updated crypto list: {update_result['cryptos_count']} cryptos")
                # Reload portfolios to get new crypto lists
                portfolios = load_portfolios()['portfolios']
        except Exception as e:
            log(f"[AUTO-UPDATE] Error: {e}")

    # === ALPHA SIGNALS CHECK ===
    alpha_signal = None
    if ALPHA_ENABLED:
        try:
            alpha_signal = get_alpha_signal('BTC/USDT')
            if alpha_signal['action'] != 'HOLD':
                log(f"  [ALPHA] Signal: {alpha_signal['action']} (conf: {alpha_signal['confidence']:.0%})")
                for reason in alpha_signal.get('reasons', [])[:3]:
                    log(f"    - {reason}")
        except Exception as e:
            log(f"  [ALPHA] Error: {e}")

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

            # === ALPHA SIGNAL OVERRIDE ===
            # Block BUY if alpha says STRONG_SELL (whale dump incoming)
            if action == 'BUY' and alpha_signal and alpha_signal.get('action') == 'STRONG_SELL':
                action = None
                reason = f"BLOCKED by ALPHA: {alpha_signal.get('reasons', ['Market risk'])[0]}"
                log(f"  [ALPHA BLOCK] {portfolio['name']}/{crypto}: {reason}")

            # Log all decisions for this portfolio
            log_decision(portfolio, crypto, analysis, action or 'HOLD', reason)

            if action:
                # === PROFESSIONAL RISK CHECK ===
                if RISK_ENABLED and action == 'BUY':
                    allocation = portfolio['config'].get('allocation_percent', 10)
                    amount_usdt = portfolio['balance'].get('USDT', 0) * (allocation / 100)
                    risk_ok, risk_reason = check_trade_risk(portfolio, action, amount_usdt)
                    if not risk_ok:
                        log(f"  [RISK BLOCK] {portfolio['name']}/{crypto}: {risk_reason}")
                        action = None

                # === POSITION ROTATION ===
                # Check if this is a rotation (reason contains "Rotating")
                if action == 'BUY' and "Rotating" in reason:
                    try:
                        # Extract symbol to close from reason
                        # Format: "Rotating SYMBOL (...) for better opportunity..."
                        parts = reason.split()
                        if len(parts) >= 2:
                            close_symbol = parts[1]  # The symbol after "Rotating"
                            if close_symbol in portfolio['positions']:
                                close_pos = portfolio['positions'][close_symbol]
                                close_price = close_pos.get('current_price', close_pos.get('entry_price', 0))
                                if close_price > 0:
                                    close_result = execute_trade(portfolio, 'SELL', close_symbol, close_price, reason=f"🔄 ROTATION: Making room for {crypto}")
                                    if close_result['success']:
                                        log(f"  🔄 {portfolio['name']}: Closed {close_symbol} for rotation -> {crypto}")
                    except Exception as e:
                        log(f"  [ROTATION ERROR] {portfolio['name']}: {e}")

                if action:
                    try:
                        result = execute_trade(portfolio, action, crypto, analysis['price'], reason=reason)
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

                            # Record trade in risk manager
                            if RISK_ENABLED and action == 'SELL':
                                pnl = result.get('pnl', 0)
                                get_risk_manager().record_trade(pnl, {'symbol': crypto, 'action': action})

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
                record_trade(portfolio, trade)

                log(f"💀 RUG DETECTED: {symbol} | {rug_reason} | Lost ${entry_cost:.2f} | {portfolio['name']}")
                results.append({'portfolio': portfolio['name'], 'action': 'RUGGED', 'symbol': symbol, 'loss': entry_cost})

            # Check TP/SL and time exits for sniper positions
            elif current_price > 0 and entry_price > 0:
                pnl_pct = ((current_price / entry_price) - 1) * 100

                # Get strategy TP/SL/Time limits
                take_profit = strategy.get('take_profit', 20)
                stop_loss = strategy.get('stop_loss', 10)
                max_hold_hours = strategy.get('max_hold_hours', 2)

                # Check hold time
                entry_time_str = pos.get('entry_time', '')
                hours_held = 0
                if entry_time_str:
                    try:
                        entry_time = datetime.fromisoformat(entry_time_str)
                        hours_held = (datetime.now() - entry_time).total_seconds() / 3600
                    except:
                        pass

                should_sell = False
                sell_reason = ""

                # 1. TAKE PROFIT - Sell if up TP%
                if pnl_pct >= take_profit:
                    should_sell = True
                    sell_reason = f"TP HIT: +{pnl_pct:.1f}% >= {take_profit}%"

                # 2. STOP LOSS - Sell if down SL% (skip if stop_loss=0)
                elif stop_loss > 0 and pnl_pct <= -stop_loss:
                    should_sell = True
                    sell_reason = f"SL HIT: {pnl_pct:.1f}% <= -{stop_loss}%"

                # 3. TIME EXIT - Sell if held too long
                elif max_hold_hours > 0 and hours_held >= max_hold_hours:
                    should_sell = True
                    sell_reason = f"TIME EXIT: Held {hours_held:.1f}h >= {max_hold_hours}h"

                # 4. EMERGENCY EXIT - Down 90%+ (effective rug)
                elif pnl_pct <= -90:
                    should_sell = True
                    sell_reason = f"DUMPED {pnl_pct:.0f}% - Emergency exit"

                if should_sell:
                    chain = pos.get('chain', 'ethereum')
                    fees = calculate_dex_fees(chain, current_price * qty)

                    net_value = (current_price * qty) - fees['total']
                    net_value = max(0, net_value)

                    asset = symbol.replace('/USDT', '')
                    portfolio['balance']['USDT'] += net_value
                    portfolio['balance'][asset] = 0
                    del portfolio['positions'][symbol]

                    entry_cost = entry_price * qty + pos.get('fees_paid', 0)
                    real_pnl = net_value - entry_cost

                    action = 'TP_SOLD' if pnl_pct > 0 else ('SL_SOLD' if pnl_pct > -90 else 'DUMP_SOLD')

                    trade = {
                        'timestamp': datetime.now().isoformat(),
                        'action': action,
                        'symbol': symbol,
                        'price': current_price,
                        'quantity': qty,
                        'amount_usdt': net_value,
                        'pnl': real_pnl,
                        'reason': sell_reason
                    }
                    record_trade(portfolio, trade)

                    emoji = "💰" if pnl_pct > 0 else "📉"
                    log(f"{emoji} SNIPER {action}: {symbol} | {pnl_pct:+.1f}% | ${real_pnl:+.2f} | {portfolio['name']}")
                    results.append({'portfolio': portfolio['name'], 'action': action, 'symbol': symbol, 'pnl': real_pnl})

    return results


def update_all_position_prices(portfolios: dict) -> int:
    """Update current_price and pnl_percent for ALL positions (Binance + DEX)"""
    updated = 0

    # 1. Get all Binance prices
    binance_prices = {}
    try:
        response = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=5)
        if response.status_code == 200:
            for p in response.json():
                if p['symbol'].endswith('USDT'):
                    sym = p['symbol'].replace('USDT', '/USDT')
                    binance_prices[sym] = float(p['price'])
    except:
        pass

    # 2. Collect all DEX token addresses
    dex_addresses = set()
    for portfolio in portfolios.values():
        for pos in portfolio.get('positions', {}).values():
            addr = pos.get('address', '')
            if addr:
                dex_addresses.add(addr)

    # 3. Get DEX prices from DexScreener
    dex_prices = {}
    if dex_addresses:
        try:
            addrs = list(dex_addresses)
            for i in range(0, len(addrs), 30):
                batch = addrs[i:i+30]
                addr_str = ','.join(batch)
                url = f"https://api.dexscreener.com/latest/dex/tokens/{addr_str}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    for pair in response.json().get('pairs', []):
                        addr = pair.get('baseToken', {}).get('address', '')
                        price = float(pair.get('priceUsd', 0) or 0)
                        if addr and price > 0:
                            dex_prices[addr.lower()] = price
        except:
            pass

    # 4. Update all positions
    for portfolio in portfolios.values():
        for symbol, pos in portfolio.get('positions', {}).items():
            entry_price = pos.get('entry_price', 0)
            if entry_price <= 0:
                continue

            addr = pos.get('address', '')

            # Get current price
            if addr:
                current_price = dex_prices.get(addr.lower(), 0)
            else:
                current_price = binance_prices.get(symbol, 0)

            if current_price > 0:
                # Update position
                pos['current_price'] = current_price
                pos['pnl_percent'] = ((current_price / entry_price) - 1) * 100
                updated += 1

    return updated


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
                        'chain': chain,
                        'token_address': pos.get('address', ''),
                        'reason': f"RUG PULL | Lost 100% | Risk was {risk_score}/100"
                    }
                    record_trade(portfolio, trade)
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

                    # Stop loss trigger (skip if stop_loss=0)
                    elif stop_loss > 0 and gross_pnl_pct <= -stop_loss:
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
                                'chain': chain,
                                'token_address': pos.get('address', ''),
                                'reason': " | ".join(reason_parts)
                            }
                            record_trade(portfolio, trade)

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
                        record_trade(portfolio, trade)
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
            record_trade(portfolio, trade)

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
                        result = execute_trade(portfolio, 'SELL', symbol, current_price, reason=f"WHALE TP {pnl_pct:+.1f}%")
                        if result['success']:
                            log(f"🐋 WHALE TP: {symbol} +{pnl_pct:.1f}% [{portfolio['name']}]")
                            results.append({'portfolio': portfolio['name'], 'action': 'WHALE_SELL_TP', 'symbol': symbol})

                    elif stop_loss > 0 and pnl_pct <= -stop_loss:
                        result = execute_trade(portfolio, 'SELL', symbol, current_price, reason=f"WHALE SL {pnl_pct:.1f}%")
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
            record_trade(portfolio, trade)

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

            # 4. Update ALL position prices (Binance + DEX)
            try:
                prices_updated = update_all_position_prices(portfolios)
                if prices_updated > 0:
                    log(f"💰 Updated {prices_updated} position prices")
            except Exception as e:
                log(f"Warning: Price update failed: {e}")

            # Save portfolios (always save to keep prices updated)
            save_portfolios(portfolios, counter)
            if total_results:
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
