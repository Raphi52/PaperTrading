"""
Smart Position Sizing Module
=============================

Implements intelligent position sizing based on:
- ATR (Average True Range) for volatility adjustment
- Kelly Criterion for optimal bet sizing
- Risk-per-trade limits
- Portfolio heat management
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import requests


@dataclass
class SizeRecommendation:
    """Position size recommendation"""
    recommended_size_usd: float
    recommended_size_pct: float
    max_size_usd: float
    reasoning: str
    risk_level: str  # LOW, MEDIUM, HIGH
    atr_pct: float
    kelly_fraction: float


class SmartPositionSizer:
    """Calculates optimal position sizes"""

    def __init__(self, portfolio: dict, settings: dict = None):
        self.portfolio = portfolio
        self.settings = settings or {}
        self.balance = portfolio.get('balance', {}).get('USDT', 0)
        self.initial_capital = portfolio.get('initial_capital', 10000)
        self.current_positions = portfolio.get('positions', {})

    def calculate_position_size(self, symbol: str, side: str = 'BUY',
                                 risk_per_trade_pct: float = 2.0) -> SizeRecommendation:
        """
        Calculate optimal position size for a trade.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'BUY' or 'SELL'
            risk_per_trade_pct: Maximum risk per trade as % of portfolio

        Returns:
            SizeRecommendation with optimal sizing
        """
        # Get ATR data
        atr_pct = self._get_atr_percentage(symbol)

        # Calculate base size from risk
        if atr_pct > 0:
            # Risk-based sizing: position_size = (risk_amount) / (stop_distance)
            # Using 2x ATR as typical stop distance
            stop_distance_pct = atr_pct * 2
            risk_amount = self.balance * (risk_per_trade_pct / 100)
            volatility_adjusted_size = risk_amount / (stop_distance_pct / 100)
        else:
            volatility_adjusted_size = self.balance * 0.10  # Default 10%

        # Kelly Criterion sizing
        kelly_size = self._calculate_kelly_size()

        # Portfolio heat check
        current_exposure = self._get_current_exposure()
        max_exposure = 0.80  # Max 80% of portfolio in positions
        remaining_capacity = max(0, (max_exposure - current_exposure)) * self.balance

        # Maximum size limits
        max_single_position = self.balance * 0.20  # Max 20% per position
        max_size = min(max_single_position, remaining_capacity, self.balance * 0.5)

        # Combine sizing methods (conservative approach)
        recommended_size = min(
            volatility_adjusted_size,
            kelly_size if kelly_size > 0 else float('inf'),
            max_size
        )

        # Ensure minimum viable size
        recommended_size = max(recommended_size, 10)  # At least $10

        # Cap at available balance
        recommended_size = min(recommended_size, self.balance * 0.95)

        # Determine risk level
        size_pct = (recommended_size / self.balance) * 100 if self.balance > 0 else 0
        if size_pct > 15 or atr_pct > 5:
            risk_level = 'HIGH'
        elif size_pct > 8 or atr_pct > 3:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'

        # Build reasoning
        reasons = []
        if atr_pct > 0:
            reasons.append(f"ATR: {atr_pct:.1f}%")
        if current_exposure > 0.5:
            reasons.append(f"Portfolio {current_exposure*100:.0f}% invested")
        if kelly_size > 0 and kelly_size < volatility_adjusted_size:
            reasons.append("Kelly-adjusted")

        return SizeRecommendation(
            recommended_size_usd=round(recommended_size, 2),
            recommended_size_pct=round(size_pct, 1),
            max_size_usd=round(max_size, 2),
            reasoning=" | ".join(reasons) if reasons else "Standard sizing",
            risk_level=risk_level,
            atr_pct=round(atr_pct, 2),
            kelly_fraction=round(kelly_size / self.balance, 2) if self.balance > 0 else 0
        )

    def _get_atr_percentage(self, symbol: str, period: int = 14) -> float:
        """Get ATR as percentage of price"""
        try:
            binance_symbol = symbol.replace('/', '')
            response = requests.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": binance_symbol, "interval": "1h", "limit": period + 1},
                timeout=5
            )

            if response.status_code != 200:
                return 3.0  # Default 3%

            klines = response.json()
            if len(klines) < period:
                return 3.0

            # Calculate ATR
            trs = []
            for i in range(1, len(klines)):
                high = float(klines[i][2])
                low = float(klines[i][3])
                prev_close = float(klines[i-1][4])

                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                trs.append(tr)

            atr = np.mean(trs[-period:])
            current_price = float(klines[-1][4])

            return (atr / current_price) * 100

        except Exception:
            return 3.0  # Default

    def _calculate_kelly_size(self) -> float:
        """Calculate Kelly Criterion position size"""
        trades = self.portfolio.get('trades', [])

        # Need at least 20 trades for reliable Kelly
        sell_trades = [t for t in trades if 'SELL' in t.get('action', '')]
        if len(sell_trades) < 20:
            return self.balance * 0.10  # Default 10%

        wins = [t['pnl'] for t in sell_trades if t.get('pnl', 0) > 0]
        losses = [abs(t['pnl']) for t in sell_trades if t.get('pnl', 0) < 0]

        if not wins or not losses:
            return self.balance * 0.10

        win_rate = len(wins) / len(sell_trades)
        avg_win = np.mean(wins)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return self.balance * 0.10

        # Kelly formula: f* = (bp - q) / b
        # where b = avg_win/avg_loss, p = win_rate, q = 1-p
        b = avg_win / avg_loss
        kelly_fraction = (b * win_rate - (1 - win_rate)) / b

        # Use half-Kelly for safety
        kelly_fraction = max(0, kelly_fraction * 0.5)

        # Cap at 25%
        kelly_fraction = min(kelly_fraction, 0.25)

        return self.balance * kelly_fraction

    def _get_current_exposure(self) -> float:
        """Get current portfolio exposure (invested / total)"""
        total_invested = 0

        for pos in self.current_positions.values():
            qty = pos.get('quantity', 0)
            price = pos.get('current_price', pos.get('entry_price', 0))
            total_invested += qty * price

        total_value = self.balance + total_invested
        return total_invested / total_value if total_value > 0 else 0

    def get_stop_loss_price(self, symbol: str, entry_price: float,
                            atr_multiplier: float = 2.0) -> Tuple[float, float]:
        """
        Calculate stop loss price based on ATR.

        Returns:
            (stop_price, stop_percentage)
        """
        atr_pct = self._get_atr_percentage(symbol)
        stop_distance_pct = atr_pct * atr_multiplier

        stop_price = entry_price * (1 - stop_distance_pct / 100)
        return round(stop_price, 6), round(stop_distance_pct, 2)

    def get_take_profit_price(self, symbol: str, entry_price: float,
                               risk_reward: float = 2.0) -> Tuple[float, float]:
        """
        Calculate take profit price based on ATR and risk/reward.

        Returns:
            (tp_price, tp_percentage)
        """
        atr_pct = self._get_atr_percentage(symbol)
        stop_distance_pct = atr_pct * 2  # 2x ATR stop
        tp_distance_pct = stop_distance_pct * risk_reward

        tp_price = entry_price * (1 + tp_distance_pct / 100)
        return round(tp_price, 6), round(tp_distance_pct, 2)


class PortfolioHeatManager:
    """Manages overall portfolio risk/heat"""

    def __init__(self, portfolios: dict):
        self.portfolios = portfolios

    def get_total_heat(self) -> Dict:
        """Calculate total portfolio heat across all portfolios"""
        total_capital = 0
        total_invested = 0
        total_unrealized_pnl = 0
        position_count = 0

        for portfolio in self.portfolios.values():
            if not portfolio.get('active', True):
                continue

            capital = portfolio.get('initial_capital', 0)
            total_capital += capital

            for pos in portfolio.get('positions', {}).values():
                qty = pos.get('quantity', 0)
                entry = pos.get('entry_price', 0)
                current = pos.get('current_price', entry)

                value = qty * entry
                total_invested += value
                total_unrealized_pnl += (current - entry) * qty
                position_count += 1

        heat_pct = (total_invested / total_capital) * 100 if total_capital > 0 else 0

        # Heat levels
        if heat_pct > 80:
            heat_level = 'CRITICAL'
            action = 'Consider closing some positions'
        elif heat_pct > 60:
            heat_level = 'HIGH'
            action = 'Avoid new large positions'
        elif heat_pct > 40:
            heat_level = 'MEDIUM'
            action = 'Normal operations'
        else:
            heat_level = 'LOW'
            action = 'Room for more positions'

        return {
            'heat_pct': round(heat_pct, 1),
            'heat_level': heat_level,
            'total_capital': total_capital,
            'total_invested': round(total_invested, 2),
            'available_capital': round(total_capital - total_invested, 2),
            'unrealized_pnl': round(total_unrealized_pnl, 2),
            'position_count': position_count,
            'action': action
        }

    def get_portfolio_heat(self, portfolio: dict) -> Dict:
        """Calculate heat for a single portfolio"""
        capital = portfolio.get('initial_capital', 10000)
        balance = portfolio.get('balance', {}).get('USDT', 0)
        positions = portfolio.get('positions', {})

        invested = 0
        unrealized = 0

        for pos in positions.values():
            qty = pos.get('quantity', 0)
            entry = pos.get('entry_price', 0)
            current = pos.get('current_price', entry)
            invested += qty * entry
            unrealized += (current - entry) * qty

        heat_pct = (invested / capital) * 100 if capital > 0 else 0

        return {
            'heat_pct': round(heat_pct, 1),
            'invested': round(invested, 2),
            'available': round(balance, 2),
            'unrealized': round(unrealized, 2),
            'positions': len(positions)
        }


# ==================== UTILITY FUNCTIONS ====================

def get_smart_size(portfolio: dict, symbol: str, risk_pct: float = 2.0) -> SizeRecommendation:
    """Convenience function for smart sizing"""
    sizer = SmartPositionSizer(portfolio)
    return sizer.calculate_position_size(symbol, risk_per_trade_pct=risk_pct)


def get_atr_stops(symbol: str, entry_price: float, atr_mult: float = 2.0) -> Dict:
    """Get ATR-based stop loss and take profit"""
    sizer = SmartPositionSizer({'balance': {'USDT': 10000}})

    sl_price, sl_pct = sizer.get_stop_loss_price(symbol, entry_price, atr_mult)
    tp_price, tp_pct = sizer.get_take_profit_price(symbol, entry_price, risk_reward=2.0)

    return {
        'stop_loss': sl_price,
        'stop_loss_pct': sl_pct,
        'take_profit': tp_price,
        'take_profit_pct': tp_pct,
        'risk_reward': round(tp_pct / sl_pct, 1) if sl_pct > 0 else 0
    }
