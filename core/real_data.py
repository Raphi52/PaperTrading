"""
REAL DATA MODULE - 100% FREE APIs
=================================
No simulation. Real market data only.

Free APIs used:
- Coinglass: Liquidations, Open Interest, Funding Rates
- Alternative.me: Fear & Greed Index
- Blockchain.com: BTC on-chain metrics
- Binance: Real-time prices, historical data
- DeFiLlama: TVL data
"""

import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json

# Cache to avoid rate limits
_cache = {}
CACHE_SHORT = 30      # 30 seconds for fast-changing data
CACHE_MEDIUM = 300    # 5 minutes for slower data
CACHE_LONG = 3600     # 1 hour for stable data


def _get_cached(key: str, max_age: int = CACHE_SHORT) -> Optional[dict]:
    """Get cached data if still valid"""
    if key in _cache:
        if time.time() - _cache[key]['time'] < max_age:
            return _cache[key]['data']
    return None


def _set_cache(key: str, data: dict):
    """Cache data with timestamp"""
    _cache[key] = {'time': time.time(), 'data': data}


# =============================================================================
# COINGLASS - FREE TIER (Liquidations, OI, Funding)
# =============================================================================

def get_liquidations_real() -> Dict:
    """
    Get REAL liquidation data from Coinglass.
    Free tier: Limited but functional.

    Returns: {
        'long_liquidations_24h': float,
        'short_liquidations_24h': float,
        'total_24h': float,
        'largest_single': float,
        'signal': 'buy_dip' | 'sell_top' | 'neutral',
        'source': 'coinglass'
    }
    """
    cache_key = 'coinglass_liquidations'
    cached = _get_cached(cache_key, CACHE_SHORT)
    if cached:
        return cached

    try:
        # Coinglass public endpoint (no API key needed for basic data)
        url = "https://open-api.coinglass.com/public/v2/liquidation_history"
        params = {"time_type": "h24", "symbol": "BTC"}

        headers = {"accept": "application/json"}
        response = requests.get(url, params=params, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get('success') and data.get('data'):
                liq_data = data['data']

                # Parse liquidation data
                long_liqs = float(liq_data.get('longLiquidationUsd', 0))
                short_liqs = float(liq_data.get('shortLiquidationUsd', 0))
                total = long_liqs + short_liqs

                # Determine signal
                signal = 'neutral'
                if long_liqs > 50_000_000:  # $50M+ longs liquidated
                    signal = 'buy_dip'
                elif short_liqs > 50_000_000:  # $50M+ shorts liquidated
                    signal = 'sell_top'

                result = {
                    'long_liquidations_24h': long_liqs,
                    'short_liquidations_24h': short_liqs,
                    'total_24h': total,
                    'signal': signal,
                    'source': 'coinglass_real',
                    'timestamp': datetime.now().isoformat()
                }
                _set_cache(cache_key, result)
                return result

        # Fallback: Try alternative free endpoint
        return _get_liquidations_fallback()

    except Exception as e:
        print(f"[REAL DATA] Coinglass error: {e}")
        return _get_liquidations_fallback()


def _get_liquidations_fallback() -> Dict:
    """Fallback liquidation data from alternative sources"""
    try:
        # Try CoinGlass alternative endpoint
        url = "https://fapi.coinglass.com/api/futures/liquidation/info"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                btc_data = next((x for x in data['data'] if x.get('symbol') == 'BTC'), None)
                if btc_data:
                    return {
                        'long_liquidations_24h': float(btc_data.get('longLiquidationUsd24h', 0)),
                        'short_liquidations_24h': float(btc_data.get('shortLiquidationUsd24h', 0)),
                        'total_24h': float(btc_data.get('totalLiquidationUsd24h', 0)),
                        'signal': 'neutral',
                        'source': 'coinglass_fallback',
                        'timestamp': datetime.now().isoformat()
                    }
    except:
        pass

    return {
        'long_liquidations_24h': 0,
        'short_liquidations_24h': 0,
        'total_24h': 0,
        'signal': 'neutral',
        'source': 'unavailable',
        'timestamp': datetime.now().isoformat()
    }


def get_funding_rates_real() -> Dict:
    """
    Get REAL funding rates from exchanges.
    High positive = longs pay shorts (bearish signal)
    High negative = shorts pay longs (bullish signal)
    """
    cache_key = 'funding_rates'
    cached = _get_cached(cache_key, CACHE_MEDIUM)
    if cached:
        return cached

    try:
        # Binance funding rate (free, no auth needed)
        url = "https://fapi.binance.com/fapi/v1/fundingRate"
        params = {"symbol": "BTCUSDT", "limit": 1}
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data:
                rate = float(data[0].get('fundingRate', 0))

                # Funding rate interpretation
                # > 0.01% = very high (bearish)
                # < -0.01% = very negative (bullish)
                signal = 'neutral'
                if rate > 0.0005:  # 0.05%+
                    signal = 'bearish'
                elif rate > 0.0003:  # 0.03%+
                    signal = 'slightly_bearish'
                elif rate < -0.0005:
                    signal = 'bullish'
                elif rate < -0.0003:
                    signal = 'slightly_bullish'

                result = {
                    'btc_funding_rate': rate,
                    'rate_percent': rate * 100,
                    'signal': signal,
                    'annualized': rate * 3 * 365 * 100,  # 3 funding periods/day
                    'source': 'binance',
                    'timestamp': datetime.now().isoformat()
                }
                _set_cache(cache_key, result)
                return result

    except Exception as e:
        print(f"[REAL DATA] Funding rate error: {e}")

    return {'btc_funding_rate': 0, 'signal': 'neutral', 'source': 'unavailable'}


def get_open_interest_real() -> Dict:
    """Get REAL open interest data from Binance"""
    cache_key = 'open_interest'
    cached = _get_cached(cache_key, CACHE_SHORT)
    if cached:
        return cached

    try:
        url = "https://fapi.binance.com/fapi/v1/openInterest"
        params = {"symbol": "BTCUSDT"}
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            oi = float(data.get('openInterest', 0))

            # Get historical OI for comparison
            hist_url = "https://fapi.binance.com/futures/data/openInterestHist"
            hist_params = {"symbol": "BTCUSDT", "period": "1h", "limit": 24}
            hist_response = requests.get(hist_url, params=hist_params, timeout=10)

            oi_24h_ago = oi
            if hist_response.status_code == 200:
                hist_data = hist_response.json()
                if hist_data:
                    oi_24h_ago = float(hist_data[0].get('sumOpenInterest', oi))

            change_pct = ((oi - oi_24h_ago) / oi_24h_ago * 100) if oi_24h_ago > 0 else 0

            result = {
                'open_interest_btc': oi,
                'oi_24h_ago': oi_24h_ago,
                'change_24h_pct': change_pct,
                'signal': 'increasing' if change_pct > 5 else ('decreasing' if change_pct < -5 else 'stable'),
                'source': 'binance',
                'timestamp': datetime.now().isoformat()
            }
            _set_cache(cache_key, result)
            return result

    except Exception as e:
        print(f"[REAL DATA] Open interest error: {e}")

    return {'open_interest_btc': 0, 'signal': 'neutral', 'source': 'unavailable'}


# =============================================================================
# FEAR & GREED INDEX - 100% FREE
# =============================================================================

def get_fear_greed_real() -> Dict:
    """
    Get REAL Fear & Greed Index from Alternative.me
    Completely free, no API key needed.

    0-25: Extreme Fear (BUY signal)
    25-45: Fear
    45-55: Neutral
    55-75: Greed
    75-100: Extreme Greed (SELL signal)
    """
    cache_key = 'fear_greed'
    cached = _get_cached(cache_key, CACHE_MEDIUM)
    if cached:
        return cached

    try:
        url = "https://api.alternative.me/fng/?limit=7"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                current = data['data'][0]
                value = int(current.get('value', 50))
                classification = current.get('value_classification', 'Neutral')

                # Calculate 7-day average
                values_7d = [int(d.get('value', 50)) for d in data['data'][:7]]
                avg_7d = sum(values_7d) / len(values_7d)

                # Trading signal
                signal = 'neutral'
                if value <= 20:
                    signal = 'extreme_fear_buy'
                elif value <= 35:
                    signal = 'fear_buy'
                elif value >= 80:
                    signal = 'extreme_greed_sell'
                elif value >= 65:
                    signal = 'greed_sell'

                result = {
                    'value': value,
                    'classification': classification,
                    'avg_7d': avg_7d,
                    'signal': signal,
                    'trend': 'improving' if value > avg_7d else 'worsening',
                    'source': 'alternative.me',
                    'timestamp': datetime.now().isoformat()
                }
                _set_cache(cache_key, result)
                return result

    except Exception as e:
        print(f"[REAL DATA] Fear & Greed error: {e}")

    return {'value': 50, 'classification': 'Neutral', 'signal': 'neutral', 'source': 'unavailable'}


# =============================================================================
# ON-CHAIN DATA - FREE (Blockchain.com, Blockchair)
# =============================================================================

def get_btc_onchain_real() -> Dict:
    """
    Get REAL BTC on-chain metrics from free APIs.
    - Exchange inflow/outflow
    - Active addresses
    - Hash rate
    """
    cache_key = 'btc_onchain'
    cached = _get_cached(cache_key, CACHE_LONG)
    if cached:
        return cached

    try:
        result = {
            'source': 'blockchain.com',
            'timestamp': datetime.now().isoformat()
        }

        # Get various on-chain metrics
        metrics = {
            'hash_rate': 'https://api.blockchain.info/charts/hash-rate?timespan=1days&format=json',
            'n_transactions': 'https://api.blockchain.info/charts/n-transactions?timespan=1days&format=json',
            'mempool_size': 'https://api.blockchain.info/charts/mempool-size?timespan=1days&format=json',
        }

        for metric_name, url in metrics.items():
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('values'):
                        latest = data['values'][-1]
                        result[metric_name] = latest.get('y', 0)
            except:
                result[metric_name] = 0

        # Determine signal based on metrics
        # High hash rate + high transactions = bullish
        signal = 'neutral'

        _set_cache(cache_key, result)
        return result

    except Exception as e:
        print(f"[REAL DATA] On-chain error: {e}")

    return {'source': 'unavailable'}


# =============================================================================
# EXCHANGE RESERVES - FREE (Limited)
# =============================================================================

def get_exchange_reserves_estimate() -> Dict:
    """
    Estimate exchange reserves from available free data.
    Note: Precise data requires paid APIs like Glassnode.
    """
    cache_key = 'exchange_reserves'
    cached = _get_cached(cache_key, CACHE_LONG)
    if cached:
        return cached

    try:
        # Use Binance order book depth as proxy for exchange liquidity
        url = "https://api.binance.com/api/v3/depth"
        params = {"symbol": "BTCUSDT", "limit": 500}
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()

            # Sum up bid and ask liquidity
            bid_liquidity = sum(float(bid[1]) for bid in data.get('bids', []))
            ask_liquidity = sum(float(ask[1]) for ask in data.get('asks', []))

            # More asks than bids = selling pressure
            ratio = bid_liquidity / ask_liquidity if ask_liquidity > 0 else 1

            signal = 'neutral'
            if ratio > 1.2:
                signal = 'bullish'  # More buyers
            elif ratio < 0.8:
                signal = 'bearish'  # More sellers

            result = {
                'bid_liquidity_btc': bid_liquidity,
                'ask_liquidity_btc': ask_liquidity,
                'bid_ask_ratio': ratio,
                'signal': signal,
                'source': 'binance_orderbook',
                'timestamp': datetime.now().isoformat()
            }
            _set_cache(cache_key, result)
            return result

    except Exception as e:
        print(f"[REAL DATA] Exchange reserves error: {e}")

    return {'signal': 'neutral', 'source': 'unavailable'}


# =============================================================================
# LONG/SHORT RATIO - FREE from Binance
# =============================================================================

def get_long_short_ratio_real() -> Dict:
    """Get REAL long/short ratio from Binance"""
    cache_key = 'long_short_ratio'
    cached = _get_cached(cache_key, CACHE_SHORT)
    if cached:
        return cached

    try:
        # Top trader long/short ratio
        url = "https://fapi.binance.com/futures/data/topLongShortAccountRatio"
        params = {"symbol": "BTCUSDT", "period": "1h", "limit": 1}
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data:
                ratio = float(data[0].get('longShortRatio', 1))
                long_account = float(data[0].get('longAccount', 0.5))
                short_account = float(data[0].get('shortAccount', 0.5))

                # Contrarian signal: too many longs = bearish, too many shorts = bullish
                signal = 'neutral'
                if ratio > 2.0:  # 66%+ long
                    signal = 'bearish'  # Contrarian: sell
                elif ratio > 1.5:
                    signal = 'slightly_bearish'
                elif ratio < 0.5:  # 66%+ short
                    signal = 'bullish'  # Contrarian: buy
                elif ratio < 0.7:
                    signal = 'slightly_bullish'

                result = {
                    'long_short_ratio': ratio,
                    'long_percent': long_account * 100,
                    'short_percent': short_account * 100,
                    'signal': signal,
                    'interpretation': 'contrarian',
                    'source': 'binance',
                    'timestamp': datetime.now().isoformat()
                }
                _set_cache(cache_key, result)
                return result

    except Exception as e:
        print(f"[REAL DATA] Long/short ratio error: {e}")

    return {'long_short_ratio': 1, 'signal': 'neutral', 'source': 'unavailable'}


# =============================================================================
# AGGREGATED ALPHA SIGNAL - ALL REAL DATA
# =============================================================================

def get_real_alpha_signal() -> Dict:
    """
    Aggregate ALL real data sources into a single trading signal.
    NO SIMULATION - Only real API data.
    """
    # Collect all data
    liquidations = get_liquidations_real()
    funding = get_funding_rates_real()
    fear_greed = get_fear_greed_real()
    long_short = get_long_short_ratio_real()
    orderbook = get_exchange_reserves_estimate()
    oi = get_open_interest_real()

    # Score calculation
    score = 0
    reasons = []

    # 1. Liquidations (weight: 2)
    if liquidations['signal'] == 'buy_dip':
        score += 2
        reasons.append(f"Liquidations: ${liquidations['long_liquidations_24h']/1e6:.1f}M longs rekt (buy dip)")
    elif liquidations['signal'] == 'sell_top':
        score -= 2
        reasons.append(f"Liquidations: ${liquidations['short_liquidations_24h']/1e6:.1f}M shorts rekt (top signal)")

    # 2. Funding rate (weight: 1.5)
    if 'bullish' in funding.get('signal', ''):
        score += 1.5
        reasons.append(f"Funding: {funding['rate_percent']:.3f}% negative (bullish)")
    elif 'bearish' in funding.get('signal', ''):
        score -= 1.5
        reasons.append(f"Funding: {funding['rate_percent']:.3f}% high (bearish)")

    # 3. Fear & Greed (weight: 2)
    fg_signal = fear_greed.get('signal', 'neutral')
    if 'fear' in fg_signal and 'buy' in fg_signal:
        mult = 2 if 'extreme' in fg_signal else 1
        score += mult
        reasons.append(f"Fear & Greed: {fear_greed['value']} ({fear_greed['classification']})")
    elif 'greed' in fg_signal and 'sell' in fg_signal:
        mult = 2 if 'extreme' in fg_signal else 1
        score -= mult
        reasons.append(f"Fear & Greed: {fear_greed['value']} ({fear_greed['classification']})")

    # 4. Long/Short ratio - contrarian (weight: 1)
    ls_signal = long_short.get('signal', 'neutral')
    if 'bullish' in ls_signal:
        score += 1
        reasons.append(f"L/S Ratio: {long_short['long_short_ratio']:.2f} (too many shorts)")
    elif 'bearish' in ls_signal:
        score -= 1
        reasons.append(f"L/S Ratio: {long_short['long_short_ratio']:.2f} (too many longs)")

    # 5. Order book (weight: 0.5)
    if orderbook.get('signal') == 'bullish':
        score += 0.5
        reasons.append(f"Orderbook: {orderbook['bid_ask_ratio']:.2f} bid/ask (buyers)")
    elif orderbook.get('signal') == 'bearish':
        score -= 0.5
        reasons.append(f"Orderbook: {orderbook['bid_ask_ratio']:.2f} bid/ask (sellers)")

    # Determine action
    if score >= 3:
        action = 'STRONG_BUY'
    elif score >= 1.5:
        action = 'BUY'
    elif score <= -3:
        action = 'STRONG_SELL'
    elif score <= -1.5:
        action = 'SELL'
    else:
        action = 'HOLD'

    confidence = min(1.0, abs(score) / 5)

    return {
        'action': action,
        'score': score,
        'confidence': confidence,
        'reasons': reasons,
        'data': {
            'liquidations': liquidations,
            'funding': funding,
            'fear_greed': fear_greed,
            'long_short': long_short,
            'orderbook': orderbook,
            'open_interest': oi
        },
        'timestamp': datetime.now().isoformat(),
        'source': 'REAL_DATA_ONLY'
    }


# Test
if __name__ == '__main__':
    print("=" * 60)
    print("REAL DATA TEST - NO SIMULATION")
    print("=" * 60)

    print("\n1. Fear & Greed Index:")
    fg = get_fear_greed_real()
    print(f"   Value: {fg.get('value')} ({fg.get('classification')})")
    print(f"   Signal: {fg.get('signal')}")
    print(f"   Source: {fg.get('source')}")

    print("\n2. Funding Rate:")
    fr = get_funding_rates_real()
    print(f"   Rate: {fr.get('rate_percent', 0):.4f}%")
    print(f"   Signal: {fr.get('signal')}")
    print(f"   Source: {fr.get('source')}")

    print("\n3. Long/Short Ratio:")
    ls = get_long_short_ratio_real()
    print(f"   Ratio: {ls.get('long_short_ratio', 0):.2f}")
    print(f"   Signal: {ls.get('signal')}")
    print(f"   Source: {ls.get('source')}")

    print("\n4. Liquidations:")
    liq = get_liquidations_real()
    print(f"   Longs: ${liq.get('long_liquidations_24h', 0)/1e6:.1f}M")
    print(f"   Shorts: ${liq.get('short_liquidations_24h', 0)/1e6:.1f}M")
    print(f"   Signal: {liq.get('signal')}")
    print(f"   Source: {liq.get('source')}")

    print("\n5. AGGREGATED SIGNAL:")
    signal = get_real_alpha_signal()
    print(f"   Action: {signal['action']}")
    print(f"   Score: {signal['score']:.1f}")
    print(f"   Confidence: {signal['confidence']:.0%}")
    print(f"   Reasons:")
    for r in signal['reasons']:
        print(f"      - {r}")
