"""
Multi-Timeframe Pattern Scoring System
======================================
Analyzes patterns across M1, M5, M15, M30, H1, H4, D1 timeframes
and calculates clarity/confidence scores for trade entries.
"""

import requests
import pandas as pd
import time as time_module

# ============ CONFIGURATION ============

# Cache for multi-timeframe data
_mtf_cache = {}  # {symbol: {timeframe: {'data': df, 'last_update': time}}}

# All available timeframes
TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']

# Cache TTL per timeframe (in seconds)
TIMEFRAME_TTL = {
    '1m': 30,      # 30 seconds
    '5m': 120,     # 2 minutes
    '15m': 300,    # 5 minutes
    '30m': 600,    # 10 minutes
    '1h': 1800,    # 30 minutes
    '4h': 7200,    # 2 hours
    '1d': 21600    # 6 hours
}

# Timeframe weight for pattern scoring (higher TF = more reliable)
TIMEFRAME_WEIGHT = {
    '1m': 0.3,
    '5m': 0.5,
    '15m': 0.7,
    '30m': 0.85,
    '1h': 1.0,
    '4h': 1.2,
    '1d': 1.5
}

# Minimum pattern score to enter trade
MIN_PATTERN_SCORE = 75


# ============ DATA FETCHING ============

def fetch_multi_timeframe_data(symbol: str, timeframes: list = None) -> dict:
    """
    Fetch OHLCV data for multiple timeframes with smart caching.
    Returns: {timeframe: pd.DataFrame}
    """
    global _mtf_cache

    if timeframes is None:
        timeframes = ['5m', '15m', '1h', '4h']  # Default: key timeframes for swing trading

    if symbol not in _mtf_cache:
        _mtf_cache[symbol] = {}

    result = {}
    now = time_module.time()

    for tf in timeframes:
        # Check cache
        cache_entry = _mtf_cache[symbol].get(tf, {})
        ttl = TIMEFRAME_TTL.get(tf, 300)

        if cache_entry and now - cache_entry.get('last_update', 0) < ttl:
            result[tf] = cache_entry['data']
            continue

        # Fetch fresh data from Binance
        try:
            binance_symbol = symbol.replace('/', '')
            url = f"https://api.binance.com/api/v3/klines?symbol={binance_symbol}&interval={tf}&limit=100"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data and len(data) >= 20:
                    df = pd.DataFrame(data, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                        'taker_buy_quote', 'ignore'
                    ])
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

                    # Cache the data
                    _mtf_cache[symbol][tf] = {
                        'data': df,
                        'last_update': now
                    }
                    result[tf] = df
        except Exception:
            pass  # Silently fail, will use cached data if available

    return result


# ============ CANDLESTICK PATTERN DETECTION ============

def detect_candlestick_patterns(df: pd.DataFrame) -> list:
    """
    Detect candlestick patterns in OHLCV data.
    Returns list of detected patterns with direction and score.
    """
    patterns = []
    if df is None or len(df) < 5:
        return patterns

    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values

    # Last few candles
    o1, o2, o3 = opens[-1], opens[-2], opens[-3]
    h1, h2, h3 = highs[-1], highs[-2], highs[-3]
    l1, l2, l3 = lows[-1], lows[-2], lows[-3]
    c1, c2, c3 = closes[-1], closes[-2], closes[-3]

    body1 = abs(c1 - o1)
    body2 = abs(c2 - o2)
    range1 = h1 - l1 if h1 > l1 else 0.0001

    is_bullish1 = c1 > o1
    is_bullish2 = c2 > o2
    is_bullish3 = c3 > o3

    # 1. HAMMER (bullish reversal at bottom)
    if range1 > 0:
        lower_wick1 = min(o1, c1) - l1
        upper_wick1 = h1 - max(o1, c1)
        if body1 > 0 and lower_wick1 > body1 * 2 and upper_wick1 < body1 * 0.5 and body1 < range1 * 0.4:
            patterns.append({
                'name': 'Hammer',
                'direction': 'bullish',
                'score': 15,
                'confidence': min(100, int(lower_wick1 / body1 * 20))
            })

    # 2. INVERTED HAMMER (bullish reversal)
    if range1 > 0:
        lower_wick1 = min(o1, c1) - l1
        upper_wick1 = h1 - max(o1, c1)
        if body1 > 0 and upper_wick1 > body1 * 2 and lower_wick1 < body1 * 0.5 and body1 < range1 * 0.4:
            patterns.append({
                'name': 'Inverted Hammer',
                'direction': 'bullish',
                'score': 12,
                'confidence': min(100, int(upper_wick1 / body1 * 20))
            })

    # 3. BULLISH ENGULFING
    if not is_bullish2 and is_bullish1 and o1 <= c2 and c1 >= o2 and body2 > 0:
        engulf_ratio = body1 / body2
        patterns.append({
            'name': 'Bullish Engulfing',
            'direction': 'bullish',
            'score': 20,
            'confidence': min(100, int(engulf_ratio * 40))
        })

    # 4. BEARISH ENGULFING
    if is_bullish2 and not is_bullish1 and o1 >= c2 and c1 <= o2 and body2 > 0:
        engulf_ratio = body1 / body2
        patterns.append({
            'name': 'Bearish Engulfing',
            'direction': 'bearish',
            'score': 20,
            'confidence': min(100, int(engulf_ratio * 40))
        })

    # 5. MORNING STAR (3-candle bullish reversal)
    body3 = abs(c3 - o3)
    if body3 > 0 and body1 > 0:
        if not is_bullish3 and is_bullish1 and body2 < body3 * 0.3 and body2 < body1 * 0.3:
            if c1 > (o3 + c3) / 2:
                patterns.append({
                    'name': 'Morning Star',
                    'direction': 'bullish',
                    'score': 25,
                    'confidence': 75
                })

    # 6. EVENING STAR (3-candle bearish reversal)
    if body3 > 0 and body1 > 0:
        if is_bullish3 and not is_bullish1 and body2 < body3 * 0.3 and body2 < body1 * 0.3:
            if c1 < (o3 + c3) / 2:
                patterns.append({
                    'name': 'Evening Star',
                    'direction': 'bearish',
                    'score': 25,
                    'confidence': 75
                })

    # 7. DOJI (indecision)
    if body1 < range1 * 0.1:
        patterns.append({
            'name': 'Doji',
            'direction': 'neutral',
            'score': 8,
            'confidence': 60
        })

    # 8. THREE WHITE SOLDIERS (strong bullish)
    if len(df) >= 4:
        o4, c4 = opens[-4], closes[-4]
        is_bullish4 = c4 > o4
        if is_bullish1 and is_bullish2 and is_bullish3 and not is_bullish4:
            if c1 > c2 > c3 and o1 > o2 > o3:
                patterns.append({
                    'name': 'Three White Soldiers',
                    'direction': 'bullish',
                    'score': 25,
                    'confidence': 85
                })

    # 9. SHOOTING STAR (bearish at top)
    if range1 > 0:
        lower_wick1 = min(o1, c1) - l1
        upper_wick1 = h1 - max(o1, c1)
        if body1 > 0 and upper_wick1 > body1 * 2 and lower_wick1 < body1 * 0.3 and not is_bullish1:
            patterns.append({
                'name': 'Shooting Star',
                'direction': 'bearish',
                'score': 15,
                'confidence': min(100, int(upper_wick1 / body1 * 20))
            })

    return patterns


# ============ INDICATOR PATTERN DETECTION ============

def detect_indicator_patterns(df: pd.DataFrame) -> list:
    """
    Detect patterns based on technical indicators.
    Returns list of patterns with direction and score.
    """
    patterns = []
    if df is None or len(df) < 30:
        return patterns

    closes = df['close']
    volumes = df['volume']

    # RSI Calculation
    delta = closes.diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    loss_safe = loss.replace(0, 0.0001)
    rs = gain / loss_safe
    rsi = 100 - (100 / (1 + rs))
    rsi_now = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

    # MACD Calculation
    ema_12 = closes.ewm(span=12).mean()
    ema_26 = closes.ewm(span=26).mean()
    macd = ema_12 - ema_26
    macd_signal = macd.ewm(span=9).mean()

    # Bollinger Bands
    sma_20 = closes.rolling(window=20).mean()
    std_20 = closes.rolling(window=20).std()
    bb_upper = sma_20 + (2 * std_20)
    bb_lower = sma_20 - (2 * std_20)
    bb_width = (bb_upper - bb_lower) / sma_20

    # Volume
    vol_avg = volumes.rolling(window=20).mean()
    vol_now = volumes.iloc[-1]
    vol_avg_now = vol_avg.iloc[-1]
    vol_ratio = vol_now / vol_avg_now if vol_avg_now > 0 else 1

    # 1. RSI DIVERGENCE
    if len(rsi) >= 10:
        price_low_now = closes.iloc[-5:].min()
        price_low_prev = closes.iloc[-10:-5].min()
        rsi_low_now = rsi.iloc[-5:].min()
        rsi_low_prev = rsi.iloc[-10:-5].min()

        # Bullish divergence: price lower low, RSI higher low
        if price_low_now < price_low_prev and rsi_low_now > rsi_low_prev:
            patterns.append({
                'name': 'Bullish RSI Divergence',
                'direction': 'bullish',
                'score': 25,
                'confidence': 70
            })

        # Bearish divergence: price higher high, RSI lower high
        price_high_now = closes.iloc[-5:].max()
        price_high_prev = closes.iloc[-10:-5].max()
        rsi_high_now = rsi.iloc[-5:].max()
        rsi_high_prev = rsi.iloc[-10:-5].max()

        if price_high_now > price_high_prev and rsi_high_now < rsi_high_prev:
            patterns.append({
                'name': 'Bearish RSI Divergence',
                'direction': 'bearish',
                'score': 25,
                'confidence': 70
            })

    # 2. MACD CROSSOVER
    if len(macd) >= 2:
        macd_now = macd.iloc[-1]
        macd_signal_now = macd_signal.iloc[-1]
        macd_prev = macd.iloc[-2]
        macd_signal_prev = macd_signal.iloc[-2]

        if macd_prev < macd_signal_prev and macd_now > macd_signal_now:
            patterns.append({
                'name': 'MACD Bullish Cross',
                'direction': 'bullish',
                'score': 15,
                'confidence': 65
            })
        elif macd_prev > macd_signal_prev and macd_now < macd_signal_now:
            patterns.append({
                'name': 'MACD Bearish Cross',
                'direction': 'bearish',
                'score': 15,
                'confidence': 65
            })

    # 3. BOLLINGER SQUEEZE BREAKOUT
    bb_width_now = bb_width.iloc[-1]
    bb_width_avg = bb_width.iloc[-20:].mean()

    if bb_width_now < bb_width_avg * 0.6:  # Squeeze detected
        if closes.iloc[-1] > bb_upper.iloc[-1]:
            patterns.append({
                'name': 'BB Squeeze Breakout UP',
                'direction': 'bullish',
                'score': 20,
                'confidence': 75
            })
        elif closes.iloc[-1] < bb_lower.iloc[-1]:
            patterns.append({
                'name': 'BB Squeeze Breakout DOWN',
                'direction': 'bearish',
                'score': 20,
                'confidence': 75
            })

    # 4. VOLUME SPIKE with price move
    if vol_ratio > 2.0:
        price_change = (closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100
        if price_change > 1:
            patterns.append({
                'name': 'Volume Spike UP',
                'direction': 'bullish',
                'score': 15,
                'confidence': int(min(100, vol_ratio * 30))
            })
        elif price_change < -1:
            patterns.append({
                'name': 'Volume Spike DOWN',
                'direction': 'bearish',
                'score': 15,
                'confidence': int(min(100, vol_ratio * 30))
            })

    # 5. RSI EXTREME
    if rsi_now < 25:
        patterns.append({
            'name': 'RSI Oversold',
            'direction': 'bullish',
            'score': 12,
            'confidence': int(100 - rsi_now * 2)
        })
    elif rsi_now > 75:
        patterns.append({
            'name': 'RSI Overbought',
            'direction': 'bearish',
            'score': 12,
            'confidence': int(rsi_now - 25)
        })

    return patterns


# ============ STRUCTURE PATTERN DETECTION ============

def detect_structure_patterns(df: pd.DataFrame) -> list:
    """
    Detect price structure patterns (double top/bottom, triangles, trends).
    """
    patterns = []
    if df is None or len(df) < 30:
        return patterns

    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values

    # Find swing highs and lows
    swing_highs = []
    swing_lows = []

    for i in range(2, len(df) - 2):
        # Swing high: higher than 2 candles before and after
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append((i, highs[i]))
        # Swing low
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append((i, lows[i]))

    # 1. DOUBLE BOTTOM (bullish reversal)
    if len(swing_lows) >= 2:
        last_two_lows = swing_lows[-2:]
        low1_price = last_two_lows[0][1]
        low2_price = last_two_lows[1][1]
        diff_pct = abs(low1_price - low2_price) / low1_price * 100

        if diff_pct < 2:  # Two lows within 2%
            if closes[-1] > low1_price * 1.02:  # Price above lows
                patterns.append({
                    'name': 'Double Bottom',
                    'direction': 'bullish',
                    'score': 30,
                    'confidence': int(100 - diff_pct * 20)
                })

    # 2. DOUBLE TOP (bearish reversal)
    if len(swing_highs) >= 2:
        last_two_highs = swing_highs[-2:]
        high1_price = last_two_highs[0][1]
        high2_price = last_two_highs[1][1]
        diff_pct = abs(high1_price - high2_price) / high1_price * 100

        if diff_pct < 2:
            if closes[-1] < high1_price * 0.98:
                patterns.append({
                    'name': 'Double Top',
                    'direction': 'bearish',
                    'score': 30,
                    'confidence': int(100 - diff_pct * 20)
                })

    # 3. ASCENDING TRIANGLE (bullish)
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        highs_flat = abs(swing_highs[-1][1] - swing_highs[-2][1]) / swing_highs[-1][1] < 0.015
        lows_rising = swing_lows[-1][1] > swing_lows[-2][1] * 1.01

        if highs_flat and lows_rising:
            patterns.append({
                'name': 'Ascending Triangle',
                'direction': 'bullish',
                'score': 20,
                'confidence': 70
            })

    # 4. DESCENDING TRIANGLE (bearish)
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        lows_flat = abs(swing_lows[-1][1] - swing_lows[-2][1]) / swing_lows[-1][1] < 0.015
        highs_falling = swing_highs[-1][1] < swing_highs[-2][1] * 0.99

        if lows_flat and highs_falling:
            patterns.append({
                'name': 'Descending Triangle',
                'direction': 'bearish',
                'score': 20,
                'confidence': 70
            })

    # 5. HH-HL UPTREND
    if len(swing_highs) >= 3 and len(swing_lows) >= 3:
        hh = swing_highs[-1][1] > swing_highs[-2][1] > swing_highs[-3][1]
        hl = swing_lows[-1][1] > swing_lows[-2][1] > swing_lows[-3][1]

        if hh and hl:
            patterns.append({
                'name': 'HH-HL Uptrend',
                'direction': 'bullish',
                'score': 18,
                'confidence': 80
            })

    # 6. LH-LL DOWNTREND
    if len(swing_highs) >= 3 and len(swing_lows) >= 3:
        lh = swing_highs[-1][1] < swing_highs[-2][1] < swing_highs[-3][1]
        ll = swing_lows[-1][1] < swing_lows[-2][1] < swing_lows[-3][1]

        if lh and ll:
            patterns.append({
                'name': 'LH-LL Downtrend',
                'direction': 'bearish',
                'score': 18,
                'confidence': 80
            })

    # 7. RANGE BREAKOUT
    range_high = max(highs[-20:])
    range_low = min(lows[-20:])

    if closes[-1] > range_high:
        patterns.append({
            'name': 'Range Breakout UP',
            'direction': 'bullish',
            'score': 22,
            'confidence': 75
        })
    elif closes[-1] < range_low:
        patterns.append({
            'name': 'Range Breakout DOWN',
            'direction': 'bearish',
            'score': 22,
            'confidence': 75
        })

    return patterns


# ============ MAIN SCORING FUNCTION ============

def calculate_pattern_clarity_score(symbol: str, timeframes: list = None) -> dict:
    """
    Calculate pattern clarity score across multiple timeframes.

    Args:
        symbol: Trading pair (e.g., 'BTC/USDT')
        timeframes: List of timeframes to analyze (default: ['5m', '15m', '1h', '4h'])

    Returns:
        dict with:
        - score: 0-100 pattern clarity score
        - direction: 'bullish' or 'bearish'
        - confidence: 'VERY_HIGH', 'HIGH', 'MEDIUM', 'LOW'
        - recommendation: 'STRONG_BUY', 'BUY', 'WEAK_BUY', 'WAIT', etc.
        - patterns: Top 5 patterns detected
        - reasons: List of scoring reasons
    """
    mtf_data = fetch_multi_timeframe_data(symbol, timeframes)

    if not mtf_data:
        return {
            'score': 0,
            'direction': 'neutral',
            'confidence': 'NONE',
            'recommendation': 'WAIT',
            'patterns': [],
            'reasons': ['No data available']
        }

    # Detect patterns on each timeframe
    all_patterns = []
    bullish_score = 0
    bearish_score = 0
    bullish_tfs = 0
    bearish_tfs = 0
    patterns_by_tf = {}

    for tf, df in mtf_data.items():
        if df is None or len(df) < 20:
            continue

        # Detect all pattern types
        tf_patterns = []
        tf_patterns.extend(detect_candlestick_patterns(df))
        tf_patterns.extend(detect_indicator_patterns(df))
        tf_patterns.extend(detect_structure_patterns(df))

        patterns_by_tf[tf] = tf_patterns

        # Apply timeframe weight
        weight = TIMEFRAME_WEIGHT.get(tf, 1.0)
        tf_bullish = 0
        tf_bearish = 0

        for p in tf_patterns:
            p['timeframe'] = tf
            p['weighted_score'] = p['score'] * weight
            all_patterns.append(p)

            if p['direction'] == 'bullish':
                tf_bullish += p['weighted_score']
            elif p['direction'] == 'bearish':
                tf_bearish += p['weighted_score']

        # Count TF direction
        if tf_bullish > tf_bearish and tf_bullish > 10:
            bullish_tfs += 1
            bullish_score += tf_bullish
        elif tf_bearish > tf_bullish and tf_bearish > 10:
            bearish_tfs += 1
            bearish_score += tf_bearish

    # Calculate final score
    total_tfs = len(mtf_data)
    reasons = []

    # Determine direction
    if bullish_score > bearish_score:
        direction = 'bullish'
        raw_score = bullish_score
        aligned_tfs = bullish_tfs
    else:
        direction = 'bearish'
        raw_score = bearish_score
        aligned_tfs = bearish_tfs

    direction_alignment = aligned_tfs / total_tfs if total_tfs > 0 else 0

    # Base score (max 60)
    base_score = min(60, raw_score / 2.5)

    # Multi-timeframe alignment bonus (max 30)
    mtf_bonus = 0
    if direction_alignment >= 0.75:
        mtf_bonus = 30
        reasons.append(f"Strong MTF alignment: {aligned_tfs}/{total_tfs} TFs")
    elif direction_alignment >= 0.5:
        mtf_bonus = 15
        reasons.append(f"Moderate MTF alignment: {aligned_tfs}/{total_tfs} TFs")

    # High confidence patterns bonus (max 10)
    high_conf = [p for p in all_patterns if p.get('confidence', 0) >= 75]
    conf_bonus = min(10, len(high_conf) * 3)
    if high_conf:
        reasons.append(f"{len(high_conf)} high-confidence patterns")

    # Final score
    final_score = min(100, int(base_score + mtf_bonus + conf_bonus))

    # Determine recommendation
    if final_score >= 85:
        confidence = 'VERY_HIGH'
        recommendation = 'STRONG_BUY' if direction == 'bullish' else 'STRONG_SELL'
    elif final_score >= 75:
        confidence = 'HIGH'
        recommendation = 'BUY' if direction == 'bullish' else 'SELL'
    elif final_score >= 60:
        confidence = 'MEDIUM'
        recommendation = 'WEAK_BUY' if direction == 'bullish' else 'WEAK_SELL'
    else:
        confidence = 'LOW'
        recommendation = 'WAIT'

    # Get best patterns for display
    best_patterns = sorted(all_patterns, key=lambda x: x.get('weighted_score', 0), reverse=True)[:5]

    return {
        'score': final_score,
        'direction': direction,
        'confidence': confidence,
        'recommendation': recommendation,
        'patterns': best_patterns,
        'patterns_by_tf': patterns_by_tf,
        'reasons': reasons,
        'bullish_score': bullish_score,
        'bearish_score': bearish_score,
        'bullish_tfs': bullish_tfs,
        'bearish_tfs': bearish_tfs,
        'total_tfs': total_tfs
    }


# ============ ROTATION LOGIC ============

def should_rotate_for_better_pattern(
    portfolio: dict,
    current_symbol: str,
    new_symbol: str,
    new_pattern_score: int
) -> tuple:
    """
    Determine if we should exit current position for a better pattern.

    Args:
        portfolio: Portfolio dict with positions
        current_symbol: Symbol of current position
        new_symbol: Symbol of potential new position
        new_pattern_score: Pattern clarity score of new opportunity

    Returns:
        (should_rotate: bool, reason: str)
    """
    if current_symbol not in portfolio.get('positions', {}):
        return (False, "No current position")

    pos = portfolio['positions'][current_symbol]
    entry_price = pos.get('entry_price', 0)
    current_price = pos.get('current_price', entry_price)

    if entry_price <= 0:
        return (False, "Invalid entry price")

    current_pnl_pct = ((current_price - entry_price) / entry_price) * 100
    current_pattern_score = pos.get('pattern_score', 50)
    score_diff = new_pattern_score - current_pattern_score

    # Rule 1: New pattern significantly better (30+ points) and excellent score
    if score_diff >= 30 and new_pattern_score >= 85:
        return (True, f"Much better pattern: {new_pattern_score} vs {current_pattern_score}")

    # Rule 2: Position stagnant (<2% gain) + much better opportunity
    if current_pnl_pct < 2 and score_diff >= 25 and new_pattern_score >= 80:
        return (True, f"Stagnant ({current_pnl_pct:.1f}%) -> better pattern ({new_pattern_score})")

    # Rule 3: Position in loss + excellent new opportunity
    if current_pnl_pct < 0 and new_pattern_score >= 90:
        return (True, f"Cutting loss ({current_pnl_pct:.1f}%) for excellent pattern ({new_pattern_score})")

    # Rule 4: Position losing + significantly better
    if current_pnl_pct < -2 and score_diff >= 20 and new_pattern_score >= 80:
        return (True, f"Rotating loss ({current_pnl_pct:.1f}%) to better ({new_pattern_score})")

    return (False, f"Keep position (diff: {score_diff}, pnl: {current_pnl_pct:.1f}%)")


def find_best_opportunity(symbols: list, min_score: int = 75) -> dict:
    """
    Find the best trading opportunity among multiple symbols.

    Args:
        symbols: List of trading pairs to analyze
        min_score: Minimum pattern score to consider (default: 75)

    Returns:
        dict with best symbol and its analysis, or None if no good opportunity
    """
    best = None
    best_score = 0

    for symbol in symbols:
        try:
            analysis = calculate_pattern_clarity_score(symbol)
            if analysis['score'] >= min_score and analysis['score'] > best_score:
                best_score = analysis['score']
                best = {
                    'symbol': symbol,
                    'analysis': analysis
                }
        except Exception:
            continue

    return best


# ============ HELPER FUNCTIONS ============

def get_pattern_summary(symbol: str) -> str:
    """Get a human-readable summary of patterns for a symbol."""
    analysis = calculate_pattern_clarity_score(symbol)

    summary = f"{symbol}: Score {analysis['score']}/100 ({analysis['confidence']})\n"
    summary += f"Direction: {analysis['direction'].upper()}\n"
    summary += f"Recommendation: {analysis['recommendation']}\n"

    if analysis['patterns']:
        summary += "Top patterns:\n"
        for p in analysis['patterns'][:3]:
            summary += f"  - {p['name']} ({p['timeframe']}): {p['direction']} [{p['confidence']}%]\n"

    return summary


def clear_cache():
    """Clear the multi-timeframe data cache."""
    global _mtf_cache
    _mtf_cache = {}


# ============ CASCADE CONFLUENCE SYSTEM ============

# Cascade configuration
CASCADE_CONFIG = {
    # Phase 1: Trend direction (must align)
    'trend_timeframes': ['1d', '4h'],
    'min_trend_alignment': 2,

    # Phase 2: Setup patterns
    'setup_timeframes': ['1h', '30m'],
    'min_setup_score': 15,

    # Phase 3: Entry trigger
    'entry_timeframes': ['15m', '5m'],
    'min_entry_score': 20,

    # Thresholds
    'min_cascade_score': 70,
    'strong_cascade_score': 85,
}


def calculate_cascade_score(symbol: str, config: dict = None) -> dict:
    """
    Calculate Cascade Confluence score.

    Cascade = D1/H4 confirm direction -> H1/M30 show setup -> M15/M5 give entry

    Returns:
        dict with cascade phases, alignment, and final score
    """
    cfg = config or CASCADE_CONFIG

    # Fetch all needed timeframes
    all_tfs = cfg['trend_timeframes'] + cfg['setup_timeframes'] + cfg['entry_timeframes']
    all_tfs = list(set(all_tfs))  # Remove duplicates

    mtf_data = fetch_multi_timeframe_data(symbol, all_tfs)

    if not mtf_data:
        return {
            'score': 0,
            'cascade_complete': False,
            'phase': 'NO_DATA',
            'direction': 'neutral',
            'phases': {},
            'recommendation': 'WAIT'
        }

    # Analyze each phase
    phases = {
        'trend': {'aligned': False, 'direction': 'neutral', 'score': 0, 'patterns': []},
        'setup': {'ready': False, 'direction': 'neutral', 'score': 0, 'patterns': []},
        'entry': {'triggered': False, 'direction': 'neutral', 'score': 0, 'patterns': []}
    }

    # ===== PHASE 1: TREND (D1, H4) =====
    trend_bullish = 0
    trend_bearish = 0
    trend_patterns = []

    for tf in cfg['trend_timeframes']:
        if tf not in mtf_data:
            continue
        df = mtf_data[tf]

        patterns = []
        patterns.extend(detect_candlestick_patterns(df))
        patterns.extend(detect_indicator_patterns(df))
        patterns.extend(detect_structure_patterns(df))

        tf_bullish = sum(p['score'] for p in patterns if p['direction'] == 'bullish')
        tf_bearish = sum(p['score'] for p in patterns if p['direction'] == 'bearish')

        for p in patterns:
            p['timeframe'] = tf
        trend_patterns.extend(patterns)

        if tf_bullish > tf_bearish and tf_bullish > 10:
            trend_bullish += 1
        elif tf_bearish > tf_bullish and tf_bearish > 10:
            trend_bearish += 1

    trend_dir = 'bullish' if trend_bullish > trend_bearish else 'bearish' if trend_bearish > trend_bullish else 'neutral'
    trend_aligned = max(trend_bullish, trend_bearish) >= cfg['min_trend_alignment']
    trend_score = max(trend_bullish, trend_bearish) * 15

    phases['trend'] = {
        'aligned': trend_aligned,
        'direction': trend_dir,
        'score': trend_score,
        'bullish_count': trend_bullish,
        'bearish_count': trend_bearish,
        'patterns': sorted(trend_patterns, key=lambda x: x['score'], reverse=True)[:3]
    }

    # ===== PHASE 2: SETUP (H1, M30) =====
    setup_bullish_score = 0
    setup_bearish_score = 0
    setup_patterns = []

    for tf in cfg['setup_timeframes']:
        if tf not in mtf_data:
            continue
        df = mtf_data[tf]

        patterns = []
        patterns.extend(detect_candlestick_patterns(df))
        patterns.extend(detect_indicator_patterns(df))
        patterns.extend(detect_structure_patterns(df))

        for p in patterns:
            p['timeframe'] = tf
            if p['direction'] == 'bullish':
                setup_bullish_score += p['score']
            elif p['direction'] == 'bearish':
                setup_bearish_score += p['score']

        setup_patterns.extend(patterns)

    # Setup must align with trend direction
    setup_score = setup_bullish_score if trend_dir == 'bullish' else setup_bearish_score
    setup_ready = setup_score >= cfg['min_setup_score'] and trend_aligned

    phases['setup'] = {
        'ready': setup_ready,
        'direction': trend_dir if setup_ready else 'neutral',
        'score': setup_score,
        'bullish_score': setup_bullish_score,
        'bearish_score': setup_bearish_score,
        'patterns': sorted(setup_patterns, key=lambda x: x['score'], reverse=True)[:3]
    }

    # ===== PHASE 3: ENTRY TRIGGER (M15, M5) =====
    entry_bullish_score = 0
    entry_bearish_score = 0
    entry_patterns = []

    for tf in cfg['entry_timeframes']:
        if tf not in mtf_data:
            continue
        df = mtf_data[tf]

        patterns = []
        patterns.extend(detect_candlestick_patterns(df))
        patterns.extend(detect_indicator_patterns(df))
        patterns.extend(detect_structure_patterns(df))

        for p in patterns:
            p['timeframe'] = tf
            if p['direction'] == 'bullish':
                entry_bullish_score += p['score']
            elif p['direction'] == 'bearish':
                entry_bearish_score += p['score']

        entry_patterns.extend(patterns)

    # Entry must align with trend direction
    entry_score = entry_bullish_score if trend_dir == 'bullish' else entry_bearish_score
    entry_triggered = entry_score >= cfg['min_entry_score'] and setup_ready

    phases['entry'] = {
        'triggered': entry_triggered,
        'direction': trend_dir if entry_triggered else 'neutral',
        'score': entry_score,
        'bullish_score': entry_bullish_score,
        'bearish_score': entry_bearish_score,
        'patterns': sorted(entry_patterns, key=lambda x: x['score'], reverse=True)[:3]
    }

    # ===== FINAL CASCADE SCORE =====
    cascade_complete = trend_aligned and setup_ready and entry_triggered

    # Score calculation
    final_score = 0

    if trend_aligned:
        final_score += 35  # Trend alignment is crucial
    if setup_ready:
        final_score += 25  # Setup adds confidence
    if entry_triggered:
        final_score += 25  # Entry timing

    # Bonus for strong patterns
    all_patterns = trend_patterns + setup_patterns + entry_patterns
    high_conf = [p for p in all_patterns if p.get('confidence', 0) >= 75]
    final_score += min(15, len(high_conf) * 3)

    final_score = min(100, final_score)

    # Determine current phase
    if not trend_aligned:
        current_phase = 'WAITING_TREND'
    elif not setup_ready:
        current_phase = 'WAITING_SETUP'
    elif not entry_triggered:
        current_phase = 'WAITING_ENTRY'
    else:
        current_phase = 'CASCADE_COMPLETE'

    # Recommendation
    if cascade_complete and final_score >= 85:
        recommendation = 'STRONG_BUY' if trend_dir == 'bullish' else 'STRONG_SELL'
        confidence = 'VERY_HIGH'
    elif cascade_complete and final_score >= 70:
        recommendation = 'BUY' if trend_dir == 'bullish' else 'SELL'
        confidence = 'HIGH'
    elif trend_aligned and setup_ready:
        recommendation = 'PREPARE'
        confidence = 'MEDIUM'
    else:
        recommendation = 'WAIT'
        confidence = 'LOW'

    return {
        'score': final_score,
        'cascade_complete': cascade_complete,
        'phase': current_phase,
        'direction': trend_dir,
        'confidence': confidence,
        'recommendation': recommendation,
        'phases': phases,
        'all_patterns_count': len(all_patterns),
        'high_conf_patterns': len(high_conf)
    }


def find_best_cascade_opportunity(symbols: list, min_score: int = 70) -> dict:
    """
    Find the best cascade opportunity among symbols.
    Only returns opportunities with complete cascade.
    """
    best = None
    best_score = 0

    for symbol in symbols:
        try:
            analysis = calculate_cascade_score(symbol)
            if analysis['cascade_complete'] and analysis['score'] >= min_score:
                if analysis['score'] > best_score:
                    best_score = analysis['score']
                    best = {
                        'symbol': symbol,
                        'analysis': analysis
                    }
        except Exception:
            continue

    return best


# ============ CASCADE VARIANTS ============

# Aggressive: Lower thresholds, faster entry
CASCADE_AGGRESSIVE = {
    'trend_timeframes': ['4h', '1h'],
    'min_trend_alignment': 1,
    'setup_timeframes': ['30m', '15m'],
    'min_setup_score': 12,
    'entry_timeframes': ['5m', '1m'],
    'min_entry_score': 15,
    'min_cascade_score': 60,
    'strong_cascade_score': 75,
}

# Conservative: Higher thresholds, safer entry
CASCADE_CONSERVATIVE = {
    'trend_timeframes': ['1d', '4h'],
    'min_trend_alignment': 2,
    'setup_timeframes': ['4h', '1h'],
    'min_setup_score': 25,
    'entry_timeframes': ['1h', '30m'],
    'min_entry_score': 25,
    'min_cascade_score': 80,
    'strong_cascade_score': 90,
}

# Scalp: Very fast, small timeframes
CASCADE_SCALP = {
    'trend_timeframes': ['1h', '30m'],
    'min_trend_alignment': 1,
    'setup_timeframes': ['15m', '5m'],
    'min_setup_score': 10,
    'entry_timeframes': ['5m', '1m'],
    'min_entry_score': 12,
    'min_cascade_score': 55,
    'strong_cascade_score': 70,
}

# Swing: Larger timeframes for multi-day holds
CASCADE_SWING = {
    'trend_timeframes': ['1d', '4h'],
    'min_trend_alignment': 2,
    'setup_timeframes': ['4h', '1h'],
    'min_setup_score': 20,
    'entry_timeframes': ['1h', '30m'],
    'min_entry_score': 18,
    'min_cascade_score': 75,
    'strong_cascade_score': 88,
}

# Intraday: Focus on H1-M5 range
CASCADE_INTRADAY = {
    'trend_timeframes': ['4h', '1h'],
    'min_trend_alignment': 2,
    'setup_timeframes': ['1h', '30m'],
    'min_setup_score': 15,
    'entry_timeframes': ['15m', '5m'],
    'min_entry_score': 15,
    'min_cascade_score': 65,
    'strong_cascade_score': 80,
}

# Momentum: Faster reaction to strong moves
CASCADE_MOMENTUM = {
    'trend_timeframes': ['1h', '30m'],
    'min_trend_alignment': 2,
    'setup_timeframes': ['30m', '15m'],
    'min_setup_score': 18,
    'entry_timeframes': ['15m', '5m'],
    'min_entry_score': 20,
    'min_cascade_score': 65,
    'strong_cascade_score': 82,
}

# All cascade configs
CASCADE_CONFIGS = {
    'default': CASCADE_CONFIG,
    'aggressive': CASCADE_AGGRESSIVE,
    'conservative': CASCADE_CONSERVATIVE,
    'scalp': CASCADE_SCALP,
    'swing': CASCADE_SWING,
    'intraday': CASCADE_INTRADAY,
    'momentum': CASCADE_MOMENTUM,
}
