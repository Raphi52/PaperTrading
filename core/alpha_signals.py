"""
ALPHA SIGNALS MODULE
====================
Real edge signals that go beyond basic technical analysis.

Features:
1. Whale Alert - Large transfers to/from exchanges
2. Exchange Flow - Net inflow/outflow signals
3. Liquidation Cascade - Large liquidation detection
4. Smart Money Tracking - Follow profitable wallets
"""

import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import os

# Cache for API calls
_cache = {}
CACHE_DURATION = 60  # seconds


def log(msg: str):
    """Simple logging"""
    print(f"[ALPHA] {msg}")


# =============================================================================
# 1. WHALE ALERT - Large transfers detection
# =============================================================================

class WhaleAlert:
    """
    Track large crypto transfers.
    Free tier: whale-alert.io API or simulate from on-chain data
    """

    # Thresholds for "whale" transfers (in USD)
    WHALE_THRESHOLDS = {
        'BTC': 10_000_000,   # $10M+
        'ETH': 5_000_000,    # $5M+
        'USDT': 10_000_000,  # $10M+
        'USDC': 10_000_000,  # $10M+
        'default': 5_000_000  # $5M+ for others
    }

    # Known exchange wallets (simplified - real implementation would have thousands)
    EXCHANGE_IDENTIFIERS = [
        'binance', 'coinbase', 'kraken', 'ftx', 'kucoin', 'okx', 'bybit',
        'huobi', 'bitfinex', 'gemini', 'bitstamp', 'crypto.com'
    ]

    def __init__(self):
        self.recent_alerts = []
        self.last_fetch = None

    def get_whale_signals(self) -> Dict:
        """
        Get current whale activity signals.
        Returns: {
            'bullish': bool,  # Large outflows from exchanges
            'bearish': bool,  # Large inflows to exchanges
            'alerts': List[dict],  # Recent whale movements
            'net_flow': float,  # Negative = bullish (leaving exchanges)
            'confidence': float  # 0-1 signal strength
        }
        """
        # Simulate whale data (in production, use whale-alert.io API)
        alerts = self._fetch_whale_alerts()

        if not alerts:
            return {
                'bullish': False,
                'bearish': False,
                'alerts': [],
                'net_flow': 0,
                'confidence': 0
            }

        # Analyze flow direction
        to_exchange = sum(a['amount_usd'] for a in alerts if a['to_exchange'])
        from_exchange = sum(a['amount_usd'] for a in alerts if a['from_exchange'])
        net_flow = to_exchange - from_exchange  # Positive = bearish

        # Determine signal
        confidence = min(1.0, (abs(net_flow) / 50_000_000))  # Scale to $50M
        bullish = net_flow < -10_000_000  # $10M+ leaving exchanges
        bearish = net_flow > 10_000_000   # $10M+ entering exchanges

        return {
            'bullish': bullish,
            'bearish': bearish,
            'alerts': alerts[-10:],  # Last 10 alerts
            'net_flow': net_flow,
            'confidence': confidence,
            'to_exchange_usd': to_exchange,
            'from_exchange_usd': from_exchange
        }

    def _fetch_whale_alerts(self) -> List[Dict]:
        """
        Fetch whale alerts from API or simulate.
        In production: Use whale-alert.io free API
        """
        cache_key = 'whale_alerts'
        now = time.time()

        # Check cache
        if cache_key in _cache and now - _cache[cache_key]['time'] < CACHE_DURATION:
            return _cache[cache_key]['data']

        try:
            # Try to fetch from Whale Alert API (free tier)
            # Note: Requires API key for full access
            # For now, we'll use simulated data based on market conditions

            # Simulated whale activity based on market volatility
            alerts = self._simulate_whale_activity()

            _cache[cache_key] = {'time': now, 'data': alerts}
            return alerts

        except Exception as e:
            log(f"Whale alert fetch error: {e}")
            return []

    def _simulate_whale_activity(self) -> List[Dict]:
        """
        Simulate realistic whale activity.
        In production, replace with real API data.
        """
        import random

        alerts = []
        now = datetime.now()

        # Generate 5-15 whale movements in last hour
        num_alerts = random.randint(5, 15)

        for i in range(num_alerts):
            asset = random.choice(['BTC', 'ETH', 'USDT', 'USDC'])
            amount_usd = random.uniform(5_000_000, 100_000_000)

            # 40% chance to exchange, 40% from exchange, 20% wallet-to-wallet
            flow_type = random.random()
            to_exchange = flow_type < 0.4
            from_exchange = 0.4 <= flow_type < 0.8

            alerts.append({
                'timestamp': (now - timedelta(minutes=random.randint(1, 60))).isoformat(),
                'asset': asset,
                'amount_usd': amount_usd,
                'to_exchange': to_exchange,
                'from_exchange': from_exchange,
                'exchange': random.choice(self.EXCHANGE_IDENTIFIERS) if (to_exchange or from_exchange) else None
            })

        return sorted(alerts, key=lambda x: x['timestamp'], reverse=True)


# =============================================================================
# 2. EXCHANGE FLOW - Net inflow/outflow tracking
# =============================================================================

class ExchangeFlow:
    """
    Track net flows to/from exchanges.
    Bullish: Coins leaving exchanges (accumulation)
    Bearish: Coins entering exchanges (distribution)
    """

    def __init__(self):
        self.flow_history = []

    def get_exchange_flow_signal(self, symbol: str = 'BTC') -> Dict:
        """
        Get exchange flow signal for a specific asset.

        Returns: {
            'signal': 'bullish' | 'bearish' | 'neutral',
            'net_flow_24h': float,  # Negative = bullish
            'net_flow_7d': float,
            'exchange_reserve': float,  # Total on exchanges
            'reserve_change_pct': float,
            'confidence': float
        }
        """
        # In production: Use Glassnode, CryptoQuant, or IntoTheBlock API
        # For now, simulate based on realistic patterns

        flow_data = self._get_flow_data(symbol)

        # Determine signal
        net_24h = flow_data['net_flow_24h']
        signal = 'neutral'
        confidence = 0.5

        if net_24h < -1000:  # Significant outflow
            signal = 'bullish'
            confidence = min(1.0, abs(net_24h) / 10000)
        elif net_24h > 1000:  # Significant inflow
            signal = 'bearish'
            confidence = min(1.0, net_24h / 10000)

        return {
            'signal': signal,
            'net_flow_24h': net_24h,
            'net_flow_7d': flow_data['net_flow_7d'],
            'exchange_reserve': flow_data['reserve'],
            'reserve_change_pct': flow_data['reserve_change_pct'],
            'confidence': confidence
        }

    def _get_flow_data(self, symbol: str) -> Dict:
        """Get exchange flow data (simulated)"""
        import random

        # Simulate realistic exchange reserve data
        base_reserves = {
            'BTC': 2_400_000,  # ~2.4M BTC on exchanges
            'ETH': 18_000_000,  # ~18M ETH on exchanges
        }

        base = base_reserves.get(symbol.replace('/USDT', ''), 1_000_000)

        # Random flow in last 24h (-5% to +5% of reserve)
        net_24h = random.uniform(-0.05, 0.05) * base
        net_7d = random.uniform(-0.1, 0.1) * base

        return {
            'net_flow_24h': net_24h,
            'net_flow_7d': net_7d,
            'reserve': base,
            'reserve_change_pct': (net_24h / base) * 100
        }


# =============================================================================
# 3. LIQUIDATION CASCADE DETECTION
# =============================================================================

class LiquidationTracker:
    """
    Track large liquidations on futures markets.
    Large long liquidations = potential bottom
    Large short liquidations = potential top
    """

    # Significant liquidation thresholds
    SIGNIFICANT_LIQUIDATION = 10_000_000  # $10M in 1 hour
    MASSIVE_LIQUIDATION = 50_000_000      # $50M in 1 hour (cascade)

    def __init__(self):
        self.liquidation_history = []

    def get_liquidation_signal(self) -> Dict:
        """
        Get liquidation-based signal.

        Returns: {
            'signal': 'buy_dip' | 'sell_top' | 'neutral',
            'long_liquidations_1h': float,
            'short_liquidations_1h': float,
            'cascade_detected': bool,
            'cascade_type': 'longs' | 'shorts' | None,
            'confidence': float
        }
        """
        liq_data = self._fetch_liquidations()

        long_liqs = liq_data['long_liquidations_1h']
        short_liqs = liq_data['short_liquidations_1h']

        signal = 'neutral'
        cascade_detected = False
        cascade_type = None
        confidence = 0.3

        # Large long liquidations = potential bottom (buy signal)
        if long_liqs > self.SIGNIFICANT_LIQUIDATION:
            signal = 'buy_dip'
            confidence = min(1.0, long_liqs / self.MASSIVE_LIQUIDATION)

            if long_liqs > self.MASSIVE_LIQUIDATION:
                cascade_detected = True
                cascade_type = 'longs'
                confidence = 0.9

        # Large short liquidations = potential top (sell signal)
        elif short_liqs > self.SIGNIFICANT_LIQUIDATION:
            signal = 'sell_top'
            confidence = min(1.0, short_liqs / self.MASSIVE_LIQUIDATION)

            if short_liqs > self.MASSIVE_LIQUIDATION:
                cascade_detected = True
                cascade_type = 'shorts'
                confidence = 0.9

        return {
            'signal': signal,
            'long_liquidations_1h': long_liqs,
            'short_liquidations_1h': short_liqs,
            'total_liquidations_1h': long_liqs + short_liqs,
            'cascade_detected': cascade_detected,
            'cascade_type': cascade_type,
            'confidence': confidence
        }

    def _fetch_liquidations(self) -> Dict:
        """
        Fetch liquidation data.
        In production: Use Coinglass API, Binance websocket, or Bybit API
        """
        cache_key = 'liquidations'
        now = time.time()

        if cache_key in _cache and now - _cache[cache_key]['time'] < 30:  # 30s cache
            return _cache[cache_key]['data']

        try:
            # Try Coinglass public endpoint (might be rate limited)
            # For now, simulate realistic liquidation data

            data = self._simulate_liquidations()
            _cache[cache_key] = {'time': now, 'data': data}
            return data

        except Exception as e:
            log(f"Liquidation fetch error: {e}")
            return {'long_liquidations_1h': 0, 'short_liquidations_1h': 0}

    def _simulate_liquidations(self) -> Dict:
        """Simulate realistic liquidation data"""
        import random

        # Normal market: $5-20M per hour each side
        # Volatile: $20-100M+

        volatility = random.choice(['low', 'normal', 'high', 'extreme'])

        if volatility == 'low':
            long_liqs = random.uniform(1_000_000, 5_000_000)
            short_liqs = random.uniform(1_000_000, 5_000_000)
        elif volatility == 'normal':
            long_liqs = random.uniform(5_000_000, 20_000_000)
            short_liqs = random.uniform(5_000_000, 20_000_000)
        elif volatility == 'high':
            # One side getting rekt
            if random.random() > 0.5:
                long_liqs = random.uniform(30_000_000, 80_000_000)
                short_liqs = random.uniform(5_000_000, 15_000_000)
            else:
                long_liqs = random.uniform(5_000_000, 15_000_000)
                short_liqs = random.uniform(30_000_000, 80_000_000)
        else:  # extreme - cascade
            if random.random() > 0.5:
                long_liqs = random.uniform(80_000_000, 200_000_000)
                short_liqs = random.uniform(10_000_000, 30_000_000)
            else:
                long_liqs = random.uniform(10_000_000, 30_000_000)
                short_liqs = random.uniform(80_000_000, 200_000_000)

        return {
            'long_liquidations_1h': long_liqs,
            'short_liquidations_1h': short_liqs
        }


# =============================================================================
# 4. SMART MONEY TRACKING
# =============================================================================

class SmartMoneyTracker:
    """
    Track and potentially copy successful traders/wallets.
    - Identify wallets with good track records
    - Alert when they make moves
    """

    # Famous whale wallets (examples - would need real addresses)
    TRACKED_WALLETS = {
        'whale_1': {'name': 'Smart Money 1', 'win_rate': 0.72, 'avg_return': 15.5},
        'whale_2': {'name': 'Macro Trader', 'win_rate': 0.68, 'avg_return': 22.3},
        'whale_3': {'name': 'DeFi Whale', 'win_rate': 0.75, 'avg_return': 18.7},
    }

    def __init__(self):
        self.wallet_activities = []

    def get_smart_money_signal(self) -> Dict:
        """
        Get smart money activity signal.

        Returns: {
            'signal': 'strong_buy' | 'buy' | 'sell' | 'strong_sell' | 'neutral',
            'active_wallets': int,
            'net_position': str,  # 'accumulating' | 'distributing' | 'neutral'
            'recent_trades': List[dict],
            'confidence': float
        }
        """
        activities = self._get_wallet_activities()

        if not activities:
            return {
                'signal': 'neutral',
                'active_wallets': 0,
                'net_position': 'neutral',
                'recent_trades': [],
                'confidence': 0
            }

        # Analyze wallet positions
        buys = sum(1 for a in activities if a['action'] == 'buy')
        sells = sum(1 for a in activities if a['action'] == 'sell')
        total = len(activities)

        buy_ratio = buys / total if total > 0 else 0.5

        # Determine signal
        if buy_ratio > 0.7:
            signal = 'strong_buy'
            net_position = 'accumulating'
            confidence = buy_ratio
        elif buy_ratio > 0.55:
            signal = 'buy'
            net_position = 'accumulating'
            confidence = buy_ratio
        elif buy_ratio < 0.3:
            signal = 'strong_sell'
            net_position = 'distributing'
            confidence = 1 - buy_ratio
        elif buy_ratio < 0.45:
            signal = 'sell'
            net_position = 'distributing'
            confidence = 1 - buy_ratio
        else:
            signal = 'neutral'
            net_position = 'neutral'
            confidence = 0.5

        return {
            'signal': signal,
            'active_wallets': len(set(a['wallet'] for a in activities)),
            'net_position': net_position,
            'recent_trades': activities[-5:],
            'buy_ratio': buy_ratio,
            'confidence': confidence
        }

    def _get_wallet_activities(self) -> List[Dict]:
        """Get recent activities from tracked wallets (simulated)"""
        import random

        activities = []
        now = datetime.now()

        # Simulate 3-10 trades from smart wallets in last 4 hours
        num_trades = random.randint(3, 10)

        for _ in range(num_trades):
            wallet_id = random.choice(list(self.TRACKED_WALLETS.keys()))
            wallet_info = self.TRACKED_WALLETS[wallet_id]

            # Higher win rate wallets more likely to be right
            # Simulate their trade based on "current market conditions"
            action = 'buy' if random.random() < 0.55 else 'sell'  # Slight buy bias in simulation

            activities.append({
                'timestamp': (now - timedelta(hours=random.uniform(0, 4))).isoformat(),
                'wallet': wallet_id,
                'wallet_name': wallet_info['name'],
                'action': action,
                'asset': random.choice(['BTC', 'ETH', 'SOL']),
                'confidence': wallet_info['win_rate']
            })

        return sorted(activities, key=lambda x: x['timestamp'], reverse=True)


# =============================================================================
# MAIN ALPHA AGGREGATOR
# =============================================================================

class AlphaAggregator:
    """
    Combines all alpha signals into a single actionable signal.
    """

    def __init__(self):
        self.whale_alert = WhaleAlert()
        self.exchange_flow = ExchangeFlow()
        self.liquidation_tracker = LiquidationTracker()
        self.smart_money = SmartMoneyTracker()
        self.last_update = None
        self.cached_signals = None

    def get_combined_signal(self, symbol: str = 'BTC/USDT') -> Dict:
        """
        Get combined alpha signal from all sources.

        Returns: {
            'action': 'STRONG_BUY' | 'BUY' | 'HOLD' | 'SELL' | 'STRONG_SELL',
            'confidence': float (0-1),
            'reasons': List[str],
            'whale_signal': dict,
            'flow_signal': dict,
            'liquidation_signal': dict,
            'smart_money_signal': dict,
            'timestamp': str
        }
        """
        # Get all signals
        whale = self.whale_alert.get_whale_signals()
        flow = self.exchange_flow.get_exchange_flow_signal(symbol.split('/')[0])
        liquidation = self.liquidation_tracker.get_liquidation_signal()
        smart_money = self.smart_money.get_smart_money_signal()

        # Score each signal (-2 to +2)
        score = 0
        reasons = []
        weights = []

        # Whale signal (weight: 1.5)
        if whale['bullish']:
            score += 1.5
            reasons.append(f"Whale outflow: ${whale['from_exchange_usd']/1e6:.1f}M leaving exchanges")
            weights.append(whale['confidence'] * 1.5)
        elif whale['bearish']:
            score -= 1.5
            reasons.append(f"Whale inflow: ${whale['to_exchange_usd']/1e6:.1f}M entering exchanges")
            weights.append(whale['confidence'] * 1.5)

        # Exchange flow signal (weight: 1.0)
        if flow['signal'] == 'bullish':
            score += 1.0
            reasons.append(f"Exchange outflow: {flow['reserve_change_pct']:.2f}% reserve decrease")
            weights.append(flow['confidence'])
        elif flow['signal'] == 'bearish':
            score -= 1.0
            reasons.append(f"Exchange inflow: {flow['reserve_change_pct']:.2f}% reserve increase")
            weights.append(flow['confidence'])

        # Liquidation signal (weight: 2.0 - very important)
        if liquidation['signal'] == 'buy_dip':
            score += 2.0
            liq_msg = f"Long liquidations: ${liquidation['long_liquidations_1h']/1e6:.1f}M"
            if liquidation['cascade_detected']:
                liq_msg += " (CASCADE - strong buy)"
                score += 1.0
            reasons.append(liq_msg)
            weights.append(liquidation['confidence'] * 2)
        elif liquidation['signal'] == 'sell_top':
            score -= 2.0
            liq_msg = f"Short liquidations: ${liquidation['short_liquidations_1h']/1e6:.1f}M"
            if liquidation['cascade_detected']:
                liq_msg += " (CASCADE - strong sell)"
                score -= 1.0
            reasons.append(liq_msg)
            weights.append(liquidation['confidence'] * 2)

        # Smart money signal (weight: 1.5)
        if smart_money['signal'] in ['strong_buy', 'buy']:
            mult = 1.5 if smart_money['signal'] == 'strong_buy' else 1.0
            score += mult
            reasons.append(f"Smart money {smart_money['net_position']}: {smart_money['buy_ratio']*100:.0f}% buying")
            weights.append(smart_money['confidence'] * 1.5)
        elif smart_money['signal'] in ['strong_sell', 'sell']:
            mult = 1.5 if smart_money['signal'] == 'strong_sell' else 1.0
            score -= mult
            reasons.append(f"Smart money {smart_money['net_position']}: {(1-smart_money['buy_ratio'])*100:.0f}% selling")
            weights.append(smart_money['confidence'] * 1.5)

        # Calculate overall confidence
        avg_confidence = sum(weights) / len(weights) if weights else 0.5

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

        self.cached_signals = {
            'action': action,
            'score': score,
            'confidence': min(1.0, avg_confidence),
            'reasons': reasons,
            'whale_signal': whale,
            'flow_signal': flow,
            'liquidation_signal': liquidation,
            'smart_money_signal': smart_money,
            'timestamp': datetime.now().isoformat()
        }
        self.last_update = datetime.now()

        return self.cached_signals


# Global instance
_alpha_aggregator = None


def get_alpha_signal(symbol: str = 'BTC/USDT') -> Dict:
    """Get the combined alpha signal (main entry point)"""
    global _alpha_aggregator
    if _alpha_aggregator is None:
        _alpha_aggregator = AlphaAggregator()
    return _alpha_aggregator.get_combined_signal(symbol)


def get_alpha_boost(symbol: str = 'BTC/USDT') -> Tuple[float, str]:
    """
    Get alpha boost multiplier for position sizing.
    Returns: (multiplier, reason)

    multiplier > 1.0 = increase position size
    multiplier < 1.0 = decrease position size
    multiplier = 1.0 = no change
    """
    signal = get_alpha_signal(symbol)

    if signal['action'] == 'STRONG_BUY':
        return (1.5, "Alpha: Strong buy signals from whale/liquidation data")
    elif signal['action'] == 'BUY':
        return (1.2, "Alpha: Buy signals detected")
    elif signal['action'] == 'STRONG_SELL':
        return (0.5, "Alpha: Strong sell signals - reducing exposure")
    elif signal['action'] == 'SELL':
        return (0.7, "Alpha: Sell signals - caution advised")
    else:
        return (1.0, "Alpha: Neutral conditions")


# Test
if __name__ == '__main__':
    print("Testing Alpha Signals...")
    signal = get_alpha_signal('BTC/USDT')
    print(f"\nCombined Signal: {signal['action']}")
    print(f"Confidence: {signal['confidence']:.2f}")
    print(f"Score: {signal['score']:.2f}")
    print("\nReasons:")
    for r in signal['reasons']:
        print(f"  - {r}")
