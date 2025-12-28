"""
PROFESSIONAL RISK MANAGER
=========================
Institutional-grade risk management for serious trading.

Features:
- Maximum drawdown protection
- Kelly Criterion position sizing
- Daily/Weekly loss limits
- Volatility-adjusted sizing
- Emergency stop system
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Tuple

RISK_CONFIG_FILE = "data/risk_config.json"
RISK_STATE_FILE = "data/risk_state.json"


def load_risk_config() -> Dict:
    """Load risk configuration"""
    default_config = {
        'max_drawdown_percent': 25,
        'daily_loss_limit_percent': 10,
        'weekly_loss_limit_percent': 20,
        'max_position_percent': 10,
        'max_portfolio_positions': 50,
        'kelly_fraction': 0.25,
        'min_win_rate_required': 0.40,
        'high_volatility_reduction': 0.5,
        'emergency_stop_loss_percent': 30,
        'max_trades_per_day': 9999,           # Pas de limite
        'min_time_between_trades_seconds': 0,  # Pas de délai
        'pause_on_3_losses': False,
        'bear_market_reduction': 1.0,         # Pas de réduction
    }
    try:
        if os.path.exists(RISK_CONFIG_FILE):
            with open(RISK_CONFIG_FILE, 'r') as f:
                user_config = json.load(f)
                default_config.update(user_config)
    except:
        pass
    return default_config


def load_risk_state() -> Dict:
    """Load current risk state"""
    default_state = {
        'daily_pnl': 0,
        'weekly_pnl': 0,
        'peak_equity': 0,
        'current_drawdown': 0,
        'trades_today': 0,
        'last_trade_time': None,
        'emergency_stop_triggered': False,
        'daily_reset_date': datetime.now().strftime('%Y-%m-%d'),
        'weekly_reset_date': datetime.now().strftime('%Y-%m-%d'),
        'trade_history': []
    }
    try:
        if os.path.exists(RISK_STATE_FILE):
            with open(RISK_STATE_FILE, 'r') as f:
                state = json.load(f)
                default_state.update(state)
    except:
        pass
    return default_state


def save_risk_state(state: Dict):
    """Save current risk state"""
    try:
        os.makedirs(os.path.dirname(RISK_STATE_FILE), exist_ok=True)
        with open(RISK_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        print(f"[RISK] State save error: {e}")


class RiskManager:
    """Professional risk management system"""

    def __init__(self):
        self.config = load_risk_config()
        self.state = load_risk_state()
        self._check_daily_reset()
        self._check_weekly_reset()

    def _check_daily_reset(self):
        today = datetime.now().strftime('%Y-%m-%d')
        if self.state.get('daily_reset_date') != today:
            self.state['daily_pnl'] = 0
            self.state['trades_today'] = 0
            self.state['daily_reset_date'] = today
            save_risk_state(self.state)

    def _check_weekly_reset(self):
        today = datetime.now()
        week_start = (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')
        if self.state.get('weekly_reset_date') != week_start:
            self.state['weekly_pnl'] = 0
            self.state['weekly_reset_date'] = week_start
            save_risk_state(self.state)

    def can_trade(self, portfolio: Dict, action: str, amount_usdt: float) -> Tuple[bool, str]:
        """Check if a trade is allowed - MINIMAL RESTRICTIONS, rely on confluence instead."""

        # Only block on emergency stop (manual trigger)
        if self.state.get('emergency_stop_triggered'):
            return False, "EMERGENCY STOP ACTIVE"

        # Track stats but don't block
        self.state['trades_today'] = self.state.get('trades_today', 0)

        # Max open positions (prevent overexposure)
        open_positions = len(portfolio.get('positions', {}))
        if open_positions >= self.config['max_portfolio_positions'] and action == 'BUY':
            return False, f"Max positions: {open_positions}"

        # Drawdown check
        equity = self._calculate_equity(portfolio)
        if equity > self.state.get('peak_equity', 0):
            self.state['peak_equity'] = equity

        if self.state['peak_equity'] > 0:
            drawdown = ((self.state['peak_equity'] - equity) / self.state['peak_equity']) * 100
            self.state['current_drawdown'] = drawdown

            if drawdown > self.config['max_drawdown_percent']:
                return False, f"Max drawdown: {drawdown:.1f}%"

            if drawdown > self.config['emergency_stop_loss_percent']:
                self.state['emergency_stop_triggered'] = True
                save_risk_state(self.state)
                return False, f"EMERGENCY STOP: {drawdown:.1f}%"

        return True, "OK"

    def _calculate_equity(self, portfolio: Dict) -> float:
        """Calculate current portfolio equity"""
        equity = portfolio.get('balance', {}).get('USDT', 0)
        for symbol, pos in portfolio.get('positions', {}).items():
            qty = pos.get('quantity', 0)
            price = pos.get('entry_price', 0)
            equity += qty * price
        return equity

    def is_bear_market(self, analysis: Dict = None) -> bool:
        """Detect bear market conditions"""
        if not analysis:
            return False

        # Bear market indicators:
        # 1. RSI < 35 on BTC
        # 2. Price below EMA21
        # 3. Negative 24h change > 3%
        rsi = analysis.get('rsi', 50)
        trend = analysis.get('trend', 'neutral')
        change_24h = analysis.get('change_24h', 0)

        bear_signals = 0
        if rsi < 35:
            bear_signals += 1
        if trend == 'bearish':
            bear_signals += 1
        if change_24h < -3:
            bear_signals += 1

        return bear_signals >= 2

    def get_market_adjusted_size(self, base_size: float, analysis: Dict = None) -> float:
        """Reduce position size in bear market"""
        if self.is_bear_market(analysis):
            reduction = self.config.get('bear_market_reduction', 0.5)
            return base_size * reduction
        return base_size

    def calculate_kelly_size(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Kelly Criterion position sizing"""
        if win_rate < self.config['min_win_rate_required']:
            return 0
        if avg_loss == 0:
            return 0

        win_loss_ratio = abs(avg_win / avg_loss)
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
        kelly *= self.config['kelly_fraction']
        kelly = min(kelly, self.config['max_position_percent'] / 100)
        return max(kelly, 0)

    def get_volatility_adjusted_size(self, base_size: float, atr_percent: float) -> float:
        """Adjust size for volatility"""
        if atr_percent > 5:
            return base_size * self.config['high_volatility_reduction']
        elif atr_percent > 4:
            return base_size * 0.7
        elif atr_percent < 1.5:
            return base_size * 1.2
        return base_size

    def record_trade(self, pnl: float, trade_info: Dict = None):
        """Record trade result"""
        self.state['daily_pnl'] += pnl
        self.state['weekly_pnl'] += pnl
        self.state['trades_today'] += 1
        self.state['last_trade_time'] = datetime.now().isoformat()

        if trade_info:
            self.state['trade_history'].append({
                'pnl': pnl,
                'timestamp': datetime.now().isoformat(),
                **trade_info
            })
            self.state['trade_history'] = self.state['trade_history'][-100:]

        save_risk_state(self.state)

    def get_win_rate(self, lookback: int = 100) -> Tuple[float, float, float]:
        """Calculate win rate from history"""
        trades = self.state.get('trade_history', [])[-lookback:]
        if not trades:
            return 0.5, 0, 0

        wins = [t['pnl'] for t in trades if t.get('pnl', 0) > 0]
        losses = [t['pnl'] for t in trades if t.get('pnl', 0) < 0]

        win_rate = len(wins) / len(trades) if trades else 0.5
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        return win_rate, avg_win, avg_loss

    def get_optimal_position_size(self, portfolio: Dict, analysis: Dict) -> float:
        """Calculate optimal position size"""
        base_pct = self.config['max_position_percent']

        # Kelly adjustment
        win_rate, avg_win, avg_loss = self.get_win_rate()
        kelly_pct = self.calculate_kelly_size(win_rate, avg_win, avg_loss) * 100
        if kelly_pct > 0:
            base_pct = min(base_pct, kelly_pct)

        # Volatility adjustment
        atr_pct = analysis.get('atr_percent', 2.5)
        base_pct = self.get_volatility_adjusted_size(base_pct, atr_pct)

        # Drawdown adjustment
        current_dd = self.state.get('current_drawdown', 0)
        if current_dd > 10:
            base_pct *= 0.5
        elif current_dd > 5:
            base_pct *= 0.7

        return max(1, min(base_pct, self.config['max_position_percent']))

    def get_risk_status(self) -> Dict:
        """Get risk status summary"""
        return {
            'daily_pnl': self.state['daily_pnl'],
            'weekly_pnl': self.state['weekly_pnl'],
            'current_drawdown': self.state.get('current_drawdown', 0),
            'peak_equity': self.state.get('peak_equity', 0),
            'trades_today': self.state['trades_today'],
            'emergency_stop': self.state.get('emergency_stop_triggered', False),
            'win_rate': self.get_win_rate()[0],
        }

    def reset_emergency_stop(self):
        """Reset emergency stop"""
        self.state['emergency_stop_triggered'] = False
        save_risk_state(self.state)


# Global instance
_risk_manager = None


def get_risk_manager() -> RiskManager:
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager


def check_trade_risk(portfolio: Dict, action: str, amount_usdt: float) -> Tuple[bool, str]:
    return get_risk_manager().can_trade(portfolio, action, amount_usdt)


def get_optimal_size(portfolio: Dict, analysis: Dict) -> float:
    return get_risk_manager().get_optimal_position_size(portfolio, analysis)
