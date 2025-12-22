"""
Pretty Logger Module
=====================

Enhanced logging with:
- Color-coded output
- Structured formatting
- Performance tracking
- Trade summaries
"""

import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class LogLevel(Enum):
    DEBUG = 0
    INFO = 1
    SUCCESS = 2
    WARNING = 3
    ERROR = 4
    CRITICAL = 5
    TRADE = 6
    SIGNAL = 7


class Colors:
    """ANSI color codes for terminal output"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Foreground
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Bright
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'

    # Background
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'


# Check if we're in a terminal that supports colors
def supports_color():
    """Check if terminal supports ANSI colors"""
    if os.getenv('NO_COLOR'):
        return False
    if os.getenv('FORCE_COLOR'):
        return True
    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


COLORS_ENABLED = supports_color()


def colorize(text: str, color: str) -> str:
    """Add color to text if supported"""
    if COLORS_ENABLED:
        return f"{color}{text}{Colors.RESET}"
    return text


class PrettyLogger:
    """Enhanced logger with colors and formatting"""

    LEVEL_STYLES = {
        LogLevel.DEBUG: (Colors.DIM, '🔍'),
        LogLevel.INFO: (Colors.CYAN, 'ℹ️'),
        LogLevel.SUCCESS: (Colors.BRIGHT_GREEN, '✅'),
        LogLevel.WARNING: (Colors.YELLOW, '⚠️'),
        LogLevel.ERROR: (Colors.RED, '❌'),
        LogLevel.CRITICAL: (Colors.BRIGHT_RED + Colors.BOLD, '🚨'),
        LogLevel.TRADE: (Colors.BRIGHT_MAGENTA, '💹'),
        LogLevel.SIGNAL: (Colors.BRIGHT_CYAN, '📡'),
    }

    def __init__(self, name: str = "Bot", log_file: str = None):
        self.name = name
        self.log_file = log_file or "data/bot_log.txt"
        self.session_start = datetime.now()
        self.trade_count = 0
        self.signal_count = 0

    def _format_time(self) -> str:
        """Format current time"""
        return datetime.now().strftime("%H:%M:%S")

    def _write_to_file(self, message: str):
        """Write to log file (without colors)"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                # Strip ANSI codes for file
                clean_msg = message
                for color in dir(Colors):
                    if not color.startswith('_'):
                        clean_msg = clean_msg.replace(getattr(Colors, color), '')
                f.write(f"{clean_msg}\n")
        except:
            pass

    def log(self, level: LogLevel, message: str, extra: Dict = None):
        """Log a message with level"""
        color, icon = self.LEVEL_STYLES.get(level, (Colors.WHITE, '•'))
        time_str = colorize(self._format_time(), Colors.DIM)
        level_str = colorize(f"[{level.name:8}]", color)

        output = f"{time_str} {icon} {level_str} {message}"

        if extra:
            extra_str = " | ".join([f"{k}={v}" for k, v in extra.items()])
            output += colorize(f" ({extra_str})", Colors.DIM)

        print(output)
        self._write_to_file(output)

    # Convenience methods
    def debug(self, msg: str, **kwargs):
        self.log(LogLevel.DEBUG, msg, kwargs if kwargs else None)

    def info(self, msg: str, **kwargs):
        self.log(LogLevel.INFO, msg, kwargs if kwargs else None)

    def success(self, msg: str, **kwargs):
        self.log(LogLevel.SUCCESS, msg, kwargs if kwargs else None)

    def warning(self, msg: str, **kwargs):
        self.log(LogLevel.WARNING, msg, kwargs if kwargs else None)

    def error(self, msg: str, **kwargs):
        self.log(LogLevel.ERROR, msg, kwargs if kwargs else None)

    def critical(self, msg: str, **kwargs):
        self.log(LogLevel.CRITICAL, msg, kwargs if kwargs else None)

    # Trading-specific methods
    def trade(self, action: str, symbol: str, price: float, qty: float = 0,
              pnl: float = None, portfolio: str = None):
        """Log a trade"""
        self.trade_count += 1

        if action.upper() == 'BUY':
            action_str = colorize('BUY ', Colors.BRIGHT_GREEN + Colors.BOLD)
            icon = '🟢'
        elif action.upper() == 'SELL':
            action_str = colorize('SELL', Colors.BRIGHT_RED + Colors.BOLD)
            icon = '🔴'
        else:
            action_str = colorize(action, Colors.YELLOW)
            icon = '💹'

        msg = f"{icon} {action_str} {colorize(symbol, Colors.BOLD)} @ ${price:,.4f}"

        if qty > 0:
            msg += colorize(f" (qty: {qty:.6f})", Colors.DIM)

        if pnl is not None:
            pnl_color = Colors.BRIGHT_GREEN if pnl >= 0 else Colors.BRIGHT_RED
            msg += colorize(f" PnL: ${pnl:+,.2f}", pnl_color)

        if portfolio:
            msg += colorize(f" [{portfolio}]", Colors.CYAN)

        print(f"{colorize(self._format_time(), Colors.DIM)} {msg}")
        self._write_to_file(msg)

    def signal(self, signal_type: str, symbol: str, strength: int = 0,
               reason: str = None):
        """Log a trading signal"""
        self.signal_count += 1

        strength_bar = self._strength_bar(strength)
        signal_color = Colors.BRIGHT_GREEN if 'BUY' in signal_type.upper() else Colors.BRIGHT_RED

        msg = f"📡 {colorize(signal_type, signal_color + Colors.BOLD)} {symbol} {strength_bar}"

        if reason:
            msg += colorize(f" - {reason}", Colors.DIM)

        print(f"{colorize(self._format_time(), Colors.DIM)} {msg}")
        self._write_to_file(msg)

    def _strength_bar(self, strength: int, max_bars: int = 5) -> str:
        """Create a visual strength bar"""
        filled = min(strength // 20, max_bars)
        empty = max_bars - filled

        if strength >= 80:
            bar_color = Colors.BRIGHT_GREEN
        elif strength >= 60:
            bar_color = Colors.GREEN
        elif strength >= 40:
            bar_color = Colors.YELLOW
        else:
            bar_color = Colors.RED

        bar = colorize('█' * filled, bar_color) + colorize('░' * empty, Colors.DIM)
        return f"[{bar}] {strength}%"

    def portfolio_summary(self, portfolios: Dict):
        """Log a portfolio summary"""
        total_value = 0
        total_pnl = 0
        active_count = 0
        position_count = 0

        for p in portfolios.values():
            if p.get('active', True):
                active_count += 1
                initial = p.get('initial_capital', 10000)
                balance = p.get('balance', {}).get('USDT', 0)

                # Calculate position value
                for pos in p.get('positions', {}).values():
                    qty = pos.get('quantity', 0)
                    price = pos.get('current_price', pos.get('entry_price', 0))
                    balance += qty * price
                    position_count += 1

                total_value += balance
                total_pnl += balance - initial

        pnl_color = Colors.BRIGHT_GREEN if total_pnl >= 0 else Colors.BRIGHT_RED

        print()
        print(colorize("═" * 50, Colors.CYAN))
        print(colorize("  📊 PORTFOLIO SUMMARY", Colors.BOLD + Colors.CYAN))
        print(colorize("═" * 50, Colors.CYAN))
        print(f"  Active Portfolios: {colorize(str(active_count), Colors.BOLD)}")
        print(f"  Open Positions:    {colorize(str(position_count), Colors.BOLD)}")
        print(f"  Total Value:       {colorize(f'${total_value:,.2f}', Colors.BOLD)}")
        print(f"  Total PnL:         {colorize(f'${total_pnl:+,.2f}', pnl_color + Colors.BOLD)}")
        print(colorize("═" * 50, Colors.CYAN))
        print()

    def scan_start(self, scan_number: int):
        """Log scan cycle start"""
        print()
        print(colorize(f"{'─' * 20} Scan #{scan_number} {'─' * 20}", Colors.BLUE))

    def scan_end(self, duration: float, trades: int = 0, signals: int = 0):
        """Log scan cycle end"""
        print(colorize(f"Scan complete in {duration:.1f}s | Trades: {trades} | Signals: {signals}", Colors.DIM))
        print()

    def section(self, title: str):
        """Log a section header"""
        print()
        print(colorize(f"▶ {title}", Colors.BOLD + Colors.CYAN))
        print(colorize("─" * (len(title) + 2), Colors.DIM))

    def table(self, headers: list, rows: list, title: str = None):
        """Print a formatted table"""
        if title:
            print(colorize(f"\n{title}", Colors.BOLD))

        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))

        # Header
        header_str = " │ ".join([h.ljust(col_widths[i]) for i, h in enumerate(headers)])
        print(colorize(f" {header_str}", Colors.BOLD))
        print(colorize("─" * (sum(col_widths) + 3 * (len(headers) - 1) + 2), Colors.DIM))

        # Rows
        for row in rows:
            row_str = " │ ".join([str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)])
            print(f" {row_str}")


# Global logger instance
logger = PrettyLogger()


# ==================== CONVENIENCE FUNCTIONS ====================

def log_trade(action: str, symbol: str, price: float, qty: float = 0,
              pnl: float = None, portfolio: str = None):
    """Quick trade logging"""
    logger.trade(action, symbol, price, qty, pnl, portfolio)


def log_signal(signal_type: str, symbol: str, strength: int = 0, reason: str = None):
    """Quick signal logging"""
    logger.signal(signal_type, symbol, strength, reason)


def log_info(msg: str, **kwargs):
    """Quick info logging"""
    logger.info(msg, **kwargs)


def log_success(msg: str, **kwargs):
    """Quick success logging"""
    logger.success(msg, **kwargs)


def log_warning(msg: str, **kwargs):
    """Quick warning logging"""
    logger.warning(msg, **kwargs)


def log_error(msg: str, **kwargs):
    """Quick error logging"""
    logger.error(msg, **kwargs)


def log_section(title: str):
    """Quick section logging"""
    logger.section(title)


def log_summary(portfolios: Dict):
    """Quick portfolio summary"""
    logger.portfolio_summary(portfolios)
