"""
Risk Guard - Trading Limits Enforcement
========================================

Enforces:
- Daily loss limits per portfolio
- Maximum trade size limits
- Global emergency stop
- Trade logging
"""

import json
import os
from datetime import datetime, date
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass


@dataclass
class TradeValidation:
    """Result of trade validation"""
    allowed: bool
    reason: str
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class RiskGuard:
    """Enforces trading limits and risk management rules"""

    def __init__(self, portfolio: dict, global_settings: dict = None):
        """
        Initialize RiskGuard for a portfolio.

        Args:
            portfolio: The portfolio dict containing risk_config
            global_settings: Global settings from data/settings.json
        """
        self.portfolio = portfolio
        self.global_settings = global_settings or {}
        self.risk_config = portfolio.get('risk_config', {})
        self.real_trading_stats = portfolio.get('real_trading_stats', {})

    # ==================== TRADE VALIDATION ====================

    def can_execute_trade(self, trade_size_usd: float, is_buy: bool = True) -> TradeValidation:
        """
        Check if a trade can be executed based on all risk rules.

        Args:
            trade_size_usd: The size of the trade in USD
            is_buy: True for buy, False for sell

        Returns:
            TradeValidation with allowed flag and reason
        """
        warnings = []

        # 1. Check if risk management is enabled
        if not self.risk_config.get('enabled', True):
            return TradeValidation(False, "Risk management disabled for this portfolio")

        # 2. Check global emergency stop
        global_real_trading = self.global_settings.get('real_trading', {})
        if global_real_trading.get('emergency_stop_triggered', False):
            return TradeValidation(False, "EMERGENCY STOP - All real trading halted")

        # 3. Check if global real trading is enabled
        if not global_real_trading.get('enabled', False):
            return TradeValidation(False, "Real trading not enabled globally")

        # 4. Check daily loss limit lock
        if self.real_trading_stats.get('daily_loss_locked', False):
            return TradeValidation(False, "Daily loss limit reached - trading locked until tomorrow")

        # 5. Check trade size limit
        max_trade_size = self.risk_config.get('max_trade_size_usd', 500)
        if trade_size_usd > max_trade_size:
            return TradeValidation(
                False,
                f"Trade size ${trade_size_usd:.2f} exceeds limit ${max_trade_size:.2f}"
            )

        # 6. Check portfolio percentage limit
        max_trade_pct = self.risk_config.get('max_trade_size_pct', 10)
        portfolio_value = self._get_portfolio_value()
        if portfolio_value > 0:
            trade_pct = (trade_size_usd / portfolio_value) * 100
            if trade_pct > max_trade_pct:
                return TradeValidation(
                    False,
                    f"Trade is {trade_pct:.1f}% of portfolio (limit: {max_trade_pct}%)"
                )

        # 7. Check daily loss approaching limit (warning only)
        daily_pnl = self.real_trading_stats.get('daily_pnl', 0)
        max_daily_loss = self.risk_config.get('max_daily_loss_usd', 100)

        if daily_pnl < 0:
            remaining_loss_budget = max_daily_loss + daily_pnl  # daily_pnl is negative
            if remaining_loss_budget < trade_size_usd * 0.1:  # Less than 10% of trade size
                warnings.append(f"Close to daily loss limit (${remaining_loss_budget:.2f} remaining)")

        # 8. Check global daily loss limit
        global_daily_limit = global_real_trading.get('global_daily_loss_limit', 500)
        global_daily_pnl = self._get_global_daily_pnl()
        if global_daily_pnl < -global_daily_limit:
            return TradeValidation(False, f"Global daily loss limit reached (${global_daily_limit})")

        return TradeValidation(True, "Trade approved", warnings)

    def check_daily_loss_limit(self) -> Tuple[bool, str]:
        """
        Check if daily loss limit has been reached.

        Returns:
            (limit_reached: bool, message: str)
        """
        daily_pnl = self.real_trading_stats.get('daily_pnl', 0)
        max_daily_loss = self.risk_config.get('max_daily_loss_usd', 100)
        max_daily_loss_pct = self.risk_config.get('max_daily_loss_pct', 5)

        # Check absolute loss
        if daily_pnl <= -max_daily_loss:
            return True, f"Daily loss limit reached: ${abs(daily_pnl):.2f} >= ${max_daily_loss:.2f}"

        # Check percentage loss
        portfolio_value = self._get_portfolio_value()
        if portfolio_value > 0:
            loss_pct = (abs(daily_pnl) / portfolio_value) * 100
            if loss_pct >= max_daily_loss_pct:
                return True, f"Daily loss {loss_pct:.1f}% >= limit {max_daily_loss_pct}%"

        return False, f"Within limits: PnL ${daily_pnl:+.2f}"

    def check_trade_size(self, amount_usd: float) -> Tuple[bool, str]:
        """
        Check if trade size is within limits.

        Returns:
            (within_limits: bool, message: str)
        """
        max_size = self.risk_config.get('max_trade_size_usd', 500)

        if amount_usd > max_size:
            return False, f"Trade ${amount_usd:.2f} exceeds max ${max_size:.2f}"

        return True, f"Trade size OK (${amount_usd:.2f} <= ${max_size:.2f})"

    # ==================== TRADE RECORDING ====================

    def record_trade_result(self, pnl: float, trade_info: dict = None) -> dict:
        """
        Record the result of a trade and update daily stats.

        Args:
            pnl: Profit/loss in USD (negative for losses)
            trade_info: Optional dict with trade details

        Returns:
            Updated real_trading_stats dict
        """
        # Ensure stats exist
        if 'real_trading_stats' not in self.portfolio:
            self.portfolio['real_trading_stats'] = {
                'daily_pnl': 0,
                'daily_trades_count': 0,
                'daily_loss_locked': False,
                'last_reset_date': date.today().isoformat()
            }

        stats = self.portfolio['real_trading_stats']

        # Check if we need to reset (new day)
        self._check_daily_reset()

        # Update stats
        stats['daily_pnl'] = stats.get('daily_pnl', 0) + pnl
        stats['daily_trades_count'] = stats.get('daily_trades_count', 0) + 1

        # Check if we hit the daily loss limit
        limit_reached, _ = self.check_daily_loss_limit()
        if limit_reached:
            stats['daily_loss_locked'] = True

        # Log to execution_log
        if trade_info:
            if 'execution_log' not in self.portfolio:
                self.portfolio['execution_log'] = []

            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'pnl': pnl,
                'daily_pnl_after': stats['daily_pnl'],
                **trade_info
            }
            self.portfolio['execution_log'].append(log_entry)

        self.real_trading_stats = stats
        return stats

    def reset_daily_stats(self) -> dict:
        """
        Reset daily statistics (called at midnight or manually).

        Returns:
            Updated stats dict
        """
        stats = {
            'daily_pnl': 0,
            'daily_trades_count': 0,
            'daily_loss_locked': False,
            'last_reset_date': date.today().isoformat()
        }
        self.portfolio['real_trading_stats'] = stats
        self.real_trading_stats = stats
        return stats

    # ==================== EMERGENCY STOP ====================

    def emergency_stop(self, reason: str, settings_path: str = "data/settings.json") -> bool:
        """
        Trigger emergency stop for ALL real trading.

        Args:
            reason: Reason for emergency stop
            settings_path: Path to settings file

        Returns:
            True if successful
        """
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)

            if 'real_trading' not in settings:
                settings['real_trading'] = {}

            settings['real_trading']['emergency_stop_triggered'] = True
            settings['real_trading']['emergency_stop_reason'] = reason
            settings['real_trading']['emergency_stop_time'] = datetime.now().isoformat()

            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=2)

            print(f"[EMERGENCY STOP] Triggered: {reason}")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to trigger emergency stop: {e}")
            return False

    def clear_emergency_stop(self, settings_path: str = "data/settings.json") -> bool:
        """
        Clear emergency stop flag.

        Args:
            settings_path: Path to settings file

        Returns:
            True if successful
        """
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)

            if 'real_trading' in settings:
                settings['real_trading']['emergency_stop_triggered'] = False
                settings['real_trading'].pop('emergency_stop_reason', None)
                settings['real_trading'].pop('emergency_stop_time', None)

            with open(settings_path, 'w') as f:
                json.dump(settings, f, indent=2)

            print("[EMERGENCY STOP] Cleared")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to clear emergency stop: {e}")
            return False

    # ==================== HELPERS ====================

    def _get_portfolio_value(self) -> float:
        """Get current portfolio value in USD"""
        balance = self.portfolio.get('balance', {})
        # For simplicity, just return USDT balance + initial capital estimate
        usdt = balance.get('USDT', 0)
        initial = self.portfolio.get('initial_capital', 10000)
        return max(usdt, initial)

    def _get_global_daily_pnl(self) -> float:
        """Get combined daily PnL across all real portfolios"""
        # This would need to load all portfolios - simplified here
        return self.real_trading_stats.get('daily_pnl', 0)

    def _check_daily_reset(self):
        """Check if we need to reset daily stats (new day)"""
        last_reset = self.real_trading_stats.get('last_reset_date', '')
        today = date.today().isoformat()

        if last_reset != today:
            self.reset_daily_stats()

    def get_risk_summary(self) -> dict:
        """Get a summary of current risk status"""
        daily_pnl = self.real_trading_stats.get('daily_pnl', 0)
        max_daily_loss = self.risk_config.get('max_daily_loss_usd', 100)
        max_trade_size = self.risk_config.get('max_trade_size_usd', 500)
        trades_today = self.real_trading_stats.get('daily_trades_count', 0)
        is_locked = self.real_trading_stats.get('daily_loss_locked', False)

        return {
            'daily_pnl': daily_pnl,
            'daily_pnl_pct': (daily_pnl / self._get_portfolio_value()) * 100 if self._get_portfolio_value() > 0 else 0,
            'max_daily_loss': max_daily_loss,
            'remaining_loss_budget': max_daily_loss + daily_pnl if daily_pnl < 0 else max_daily_loss,
            'max_trade_size': max_trade_size,
            'trades_today': trades_today,
            'is_locked': is_locked,
            'status': 'LOCKED' if is_locked else 'ACTIVE'
        }


# ==================== UTILITY FUNCTIONS ====================

def check_all_portfolios_daily_reset(portfolios: dict) -> int:
    """
    Check and reset daily stats for all portfolios if needed.
    Call this at the start of each bot cycle.

    Returns:
        Number of portfolios reset
    """
    reset_count = 0
    today = date.today().isoformat()

    for portfolio in portfolios.values():
        if portfolio.get('trading_mode') != 'real':
            continue

        stats = portfolio.get('real_trading_stats', {})
        last_reset = stats.get('last_reset_date', '')

        if last_reset != today:
            portfolio['real_trading_stats'] = {
                'daily_pnl': 0,
                'daily_trades_count': 0,
                'daily_loss_locked': False,
                'last_reset_date': today
            }
            reset_count += 1

    return reset_count


def get_global_daily_pnl(portfolios: dict) -> float:
    """Calculate combined daily PnL across all real portfolios"""
    total_pnl = 0
    for portfolio in portfolios.values():
        if portfolio.get('trading_mode') == 'real':
            stats = portfolio.get('real_trading_stats', {})
            total_pnl += stats.get('daily_pnl', 0)
    return total_pnl


def is_any_portfolio_locked(portfolios: dict) -> List[str]:
    """Return list of portfolio names that are daily-loss locked"""
    locked = []
    for portfolio in portfolios.values():
        if portfolio.get('trading_mode') == 'real':
            stats = portfolio.get('real_trading_stats', {})
            if stats.get('daily_loss_locked', False):
                locked.append(portfolio.get('name', portfolio.get('id', 'Unknown')))
    return locked
