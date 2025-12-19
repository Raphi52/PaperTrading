"""
Degen Trading Bot - Trading Ultra-Agressif Style MoonDev
=========================================================

Bot de trading automatique avec:
- Scalping sur timeframe 1 minute
- Detection de momentum et pumps
- Multi-asset (jusqu'a 5 positions)
- Position sizing 10-20%

Usage:
    python degen_bot.py                    # Paper trading
    python degen_bot.py --live             # Live trading (DANGER!)
    python degen_bot.py --symbols BTC,ETH  # Tokens specifiques

ATTENTION: Trading tres risque! Utilisez en paper trading d'abord.
"""
import sys
import os
import time
import json
import argparse
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor
import threading

# Fix encoding Windows
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from config.degen_config import degen_config, degen_risk_config, DegenConfig
from signals.degen import DegenAnalyzer, DegenSignal, DegenAnalysis
from degen_scanner import DegenScanner, ScanResult


# Couleurs console
class C:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"


@dataclass
class DegenPosition:
    """Position ouverte"""
    symbol: str
    side: str  # 'long'
    entry_price: float
    quantity: float
    amount_usdt: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    trailing_stop: Optional[float] = None
    highest_price: float = 0
    current_price: float = 0
    pnl: float = 0
    pnl_percent: float = 0
    signal_type: str = ""
    reasons: List[str] = field(default_factory=list)


@dataclass
class DegenTrade:
    """Historique d'un trade"""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    amount_usdt: float
    pnl: float
    pnl_percent: float
    entry_time: datetime
    exit_time: datetime
    reason: str  # 'take_profit', 'stop_loss', 'trailing_stop', 'signal', 'manual'
    signal_type: str


class DegenBot:
    """Bot de trading Degen"""

    def __init__(self, config: DegenConfig = None, live: bool = False,
                 initial_capital: float = 1000.0):
        self.config = config or degen_config
        self.live = live
        self.initial_capital = initial_capital
        self.current_capital = initial_capital

        # Components
        self.scanner = DegenScanner(self.config)
        self.analyzer = DegenAnalyzer(self.config)

        # State
        self.positions: Dict[str, DegenPosition] = {}
        self.trades: List[DegenTrade] = []
        self.running = False

        # Stats
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0
        self.max_drawdown = 0
        self.consecutive_losses = 0

        # Data files
        self.data_dir = "data/degen"
        os.makedirs(self.data_dir, exist_ok=True)

        # Load state
        self._load_state()

        # Log
        mode = "LIVE" if live else "PAPER"
        print(f"\n{C.BOLD}{C.MAGENTA}{'='*60}{C.RESET}")
        print(f"{C.BOLD}{C.MAGENTA}  DEGEN BOT - {mode} MODE{C.RESET}")
        print(f"{C.BOLD}{C.MAGENTA}{'='*60}{C.RESET}")
        print(f"  Capital: ${self.current_capital:,.2f}")
        print(f"  Risk per trade: {self.config.risk_per_trade}%")
        print(f"  Max positions: {self.config.max_positions}")
        print(f"  Trading mode: {self.config.trading_mode}")
        print(f"  Timeframe: {self.config.timeframe}")
        print(f"{C.MAGENTA}{'='*60}{C.RESET}\n")

    def _log(self, message: str, level: str = "INFO"):
        """Log avec timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        colors = {
            "INFO": C.WHITE,
            "BUY": C.GREEN,
            "SELL": C.RED,
            "WARN": C.YELLOW,
            "ERROR": C.RED,
            "PUMP": C.GREEN + C.BOLD,
            "DUMP": C.RED + C.BOLD,
        }
        color = colors.get(level, C.WHITE)
        print(f"[{timestamp}] {color}{message}{C.RESET}")

    def can_open_position(self, symbol: str) -> Tuple[bool, str]:
        """Verifie si on peut ouvrir une position"""
        # Check max positions
        if len(self.positions) >= self.config.max_positions:
            return False, f"Max positions ({self.config.max_positions}) reached"

        # Check if already in position
        if symbol in self.positions:
            return False, f"Already in position on {symbol}"

        # Check capital deployed
        total_deployed = sum(p.amount_usdt for p in self.positions.values())
        max_deploy = self.current_capital * (self.config.max_capital_deployed / 100)
        if total_deployed >= max_deploy:
            return False, f"Max capital deployed ({self.config.max_capital_deployed}%)"

        # Check daily loss limit
        today_pnl = self._get_daily_pnl()
        if today_pnl <= -degen_risk_config.max_daily_loss_percent:
            return False, f"Daily loss limit reached ({today_pnl:.1f}%)"

        # Check consecutive losses
        if self.consecutive_losses >= degen_risk_config.max_consecutive_losses:
            return False, f"Consecutive loss limit ({self.consecutive_losses})"

        return True, "OK"

    def calculate_position_size(self, confidence: int = 70) -> float:
        """Calcule la taille de position"""
        base_size = self.current_capital * (self.config.risk_per_trade / 100)

        # Ajuster selon confiance
        confidence_mult = 0.5 + (confidence / 100) * 0.5
        size = base_size * confidence_mult

        # Limites
        size = max(size, degen_risk_config.min_position_size_usd)
        size = min(size, degen_risk_config.max_position_size_usd)
        size = min(size, self.current_capital * 0.2)  # Max 20% par position

        return size

    def open_position(self, symbol: str, price: float, analysis: DegenAnalysis) -> bool:
        """Ouvre une position"""
        can_open, reason = self.can_open_position(symbol)
        if not can_open:
            self._log(f"Cannot open {symbol}: {reason}", "WARN")
            return False

        # Calculate size
        size_usdt = self.calculate_position_size(analysis.confidence)
        quantity = size_usdt / price

        # Create position
        position = DegenPosition(
            symbol=symbol,
            side='long',
            entry_price=price,
            quantity=quantity,
            amount_usdt=size_usdt,
            entry_time=datetime.now(),
            stop_loss=analysis.stop_loss,
            take_profit=analysis.take_profit,
            highest_price=price,
            current_price=price,
            signal_type=analysis.signal.name,
            reasons=analysis.reasons
        )

        self.positions[symbol] = position
        self.current_capital -= size_usdt

        # Log
        signal_color = C.GREEN if analysis.signal.value >= 4 else C.CYAN
        self._log(
            f"{signal_color}BUY {symbol}{C.RESET} | "
            f"${size_usdt:.2f} @ ${price:.4f} | "
            f"SL: ${analysis.stop_loss:.4f} | "
            f"TP: ${analysis.take_profit:.4f} | "
            f"{analysis.signal.name}",
            "BUY"
        )

        self._save_state()
        return True

    def close_position(self, symbol: str, price: float, reason: str) -> Optional[DegenTrade]:
        """Ferme une position"""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Calculate PnL
        pnl = (price - pos.entry_price) * pos.quantity
        pnl_percent = (price - pos.entry_price) / pos.entry_price * 100

        # Create trade record
        trade = DegenTrade(
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=price,
            quantity=pos.quantity,
            amount_usdt=pos.amount_usdt,
            pnl=pnl,
            pnl_percent=pnl_percent,
            entry_time=pos.entry_time,
            exit_time=datetime.now(),
            reason=reason,
            signal_type=pos.signal_type
        )

        # Update stats
        self.trades.append(trade)
        self.total_trades += 1
        self.total_pnl += pnl
        self.current_capital += pos.amount_usdt + pnl

        if pnl > 0:
            self.winning_trades += 1
            self.consecutive_losses = 0
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1

        # Update max drawdown
        drawdown = (self.initial_capital - self.current_capital) / self.initial_capital * 100
        self.max_drawdown = max(self.max_drawdown, drawdown)

        # Remove position
        del self.positions[symbol]

        # Log
        emoji = "✅" if pnl > 0 else "❌"
        color = C.GREEN if pnl > 0 else C.RED
        self._log(
            f"{emoji} CLOSE {symbol} | "
            f"${pnl:+.2f} ({pnl_percent:+.1f}%) | "
            f"Reason: {reason}",
            "SELL"
        )

        self._save_state()
        return trade

    def update_positions(self):
        """Met a jour toutes les positions"""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]

            # Fetch current price
            try:
                url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
                response = requests.get(url, timeout=5)
                data = response.json()
                current_price = float(data['price'])
            except:
                continue

            pos.current_price = current_price

            # Update PnL
            pos.pnl = (current_price - pos.entry_price) * pos.quantity
            pos.pnl_percent = (current_price - pos.entry_price) / pos.entry_price * 100

            # Update highest price
            if current_price > pos.highest_price:
                pos.highest_price = current_price

                # Activate trailing stop if in profit
                if pos.pnl_percent >= self.config.trailing_activation and pos.trailing_stop is None:
                    pos.trailing_stop = current_price * (1 - self.config.trailing_stop_percent / 100)
                    self._log(f"Trailing stop activated for {symbol} at ${pos.trailing_stop:.4f}", "INFO")

                # Update trailing stop
                elif pos.trailing_stop:
                    new_trail = current_price * (1 - self.config.trailing_stop_percent / 100)
                    if new_trail > pos.trailing_stop:
                        pos.trailing_stop = new_trail

            # Check exits
            close_reason = None

            # Take profit
            if current_price >= pos.take_profit:
                close_reason = "take_profit"

            # Stop loss
            elif current_price <= pos.stop_loss:
                close_reason = "stop_loss"

            # Trailing stop
            elif pos.trailing_stop and current_price <= pos.trailing_stop:
                close_reason = "trailing_stop"

            if close_reason:
                self.close_position(symbol, current_price, close_reason)

    def process_signal(self, result: ScanResult, analysis: DegenAnalysis):
        """Traite un signal du scanner"""
        symbol = result.symbol

        # Determiner l'action
        signal = analysis.signal

        # PUMP - Entry immediate
        if signal == DegenSignal.PUMP_DETECTED:
            self._log(f"🚀 PUMP DETECTED: {symbol} +{result.change_1m:.1f}% | Vol: {result.volume_ratio:.1f}x", "PUMP")
            self.open_position(symbol, result.price, analysis)

        # DEGEN BUY - Signal fort
        elif signal == DegenSignal.DEGEN_BUY:
            self._log(f"🔥 DEGEN BUY: {symbol} | Score: {analysis.score}", "BUY")
            self.open_position(symbol, result.price, analysis)

        # SCALP BUY - Signal rapide
        elif signal == DegenSignal.SCALP_BUY:
            if self.config.trading_mode in ['scalping', 'hybrid']:
                self._log(f"⚡ SCALP BUY: {symbol} | Score: {analysis.score}", "BUY")
                self.open_position(symbol, result.price, analysis)

        # BUY - Signal normal
        elif signal == DegenSignal.BUY:
            if self.config.trading_mode in ['momentum', 'hybrid']:
                self.open_position(symbol, result.price, analysis)

        # DUMP - Exit toutes positions sur ce token
        elif signal == DegenSignal.DUMP_DETECTED:
            if symbol in self.positions:
                self._log(f"📉 DUMP DETECTED: {symbol} | Exiting position", "DUMP")
                self.close_position(symbol, result.price, "dump_detected")

        # SELL signals - Exit position
        elif signal.value < 0 and symbol in self.positions:
            self.close_position(symbol, result.price, "signal")

    def print_status(self):
        """Affiche le statut"""
        os.system('cls' if os.name == 'nt' else 'clear')

        print(f"\n{C.BOLD}{C.CYAN}{'='*70}{C.RESET}")
        print(f"{C.BOLD}{C.CYAN}  DEGEN BOT - {'LIVE' if self.live else 'PAPER'} | {datetime.now().strftime('%H:%M:%S')}{C.RESET}")
        print(f"{C.BOLD}{C.CYAN}{'='*70}{C.RESET}")

        # Capital
        pnl_color = C.GREEN if self.total_pnl >= 0 else C.RED
        print(f"\n  Capital: ${self.current_capital:,.2f} | "
              f"PnL: {pnl_color}${self.total_pnl:+,.2f}{C.RESET} | "
              f"Drawdown: {self.max_drawdown:.1f}%")

        # Stats
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        print(f"  Trades: {self.total_trades} | "
              f"Win: {self.winning_trades} | "
              f"Loss: {self.losing_trades} | "
              f"Rate: {win_rate:.1f}%")

        # Positions
        print(f"\n  {C.BOLD}OPEN POSITIONS ({len(self.positions)}/{self.config.max_positions}){C.RESET}")
        print(f"  {'-'*66}")

        if self.positions:
            print(f"  {'Symbol':>10} | {'Entry':>10} | {'Current':>10} | {'PnL':>12} | {'SL':>10} | {'TP':>10}")
            print(f"  {'-'*66}")

            for symbol, pos in self.positions.items():
                pnl_str = f"${pos.pnl:+.2f} ({pos.pnl_percent:+.1f}%)"
                pnl_color = C.GREEN if pos.pnl >= 0 else C.RED

                print(f"  {symbol:>10} | "
                      f"${pos.entry_price:>9.4f} | "
                      f"${pos.current_price:>9.4f} | "
                      f"{pnl_color}{pnl_str:>12}{C.RESET} | "
                      f"${pos.stop_loss:>9.4f} | "
                      f"${pos.take_profit:>9.4f}")
        else:
            print(f"  {C.YELLOW}No open positions{C.RESET}")

        # Recent trades
        print(f"\n  {C.BOLD}RECENT TRADES{C.RESET}")
        print(f"  {'-'*66}")

        recent = self.trades[-5:] if self.trades else []
        for trade in reversed(recent):
            emoji = "✅" if trade.pnl > 0 else "❌"
            pnl_color = C.GREEN if trade.pnl > 0 else C.RED
            print(f"  {emoji} {trade.symbol:>8} | "
                  f"{pnl_color}${trade.pnl:+.2f} ({trade.pnl_percent:+.1f}%){C.RESET} | "
                  f"{trade.reason} | "
                  f"{trade.exit_time.strftime('%H:%M:%S')}")

        if not recent:
            print(f"  {C.YELLOW}No trades yet{C.RESET}")

        print(f"\n  {C.CYAN}Scanning every {self.config.scan_interval}s | Ctrl+C to stop{C.RESET}\n")

    def run(self, symbols: List[str] = None):
        """Lance le bot"""
        self.running = True
        self._log("Bot started", "INFO")

        try:
            while self.running:
                start = time.time()

                # 1. Update positions
                self.update_positions()

                # 2. Scan for opportunities
                if symbols:
                    # Scan specific symbols
                    for symbol in symbols:
                        self._scan_symbol(symbol)
                else:
                    # Scan top tokens
                    results = self.scanner.scan_all()
                    for result in results[:20]:  # Top 20
                        if result.score >= self.config.buy_threshold:
                            df = self.scanner.fetch_klines(f"{result.symbol}USDT")
                            if not df.empty:
                                analysis = self.analyzer.analyze(df, result.symbol)
                                self.process_signal(result, analysis)

                # 3. Display status
                self.print_status()

                # 4. Wait
                elapsed = time.time() - start
                sleep_time = max(1, self.config.scan_interval - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            self._log("Stopping bot...", "WARN")
            self.running = False
            self._save_state()
            self._print_final_stats()

    def _scan_symbol(self, symbol: str):
        """Scan un symbole specifique"""
        try:
            df = self.scanner.fetch_klines(f"{symbol}USDT")
            if df.empty:
                return

            analysis = self.analyzer.analyze(df, symbol)

            # Create mock ScanResult
            result = ScanResult(
                symbol=symbol,
                price=df['close'].iloc[-1],
                change_1m=analysis.price_change_1m,
                change_5m=analysis.price_change_5m,
                change_1h=0,
                volume_24h=0,
                volume_ratio=analysis.volume_ratio,
                rsi=analysis.rsi,
                score=analysis.score,
                signal=analysis.signal.name,
                signal_type=analysis.signal,
                reasons=analysis.reasons,
                is_pump=analysis.is_pump,
                is_dump=analysis.is_dump,
                timestamp=datetime.now()
            )

            self.process_signal(result, analysis)

        except Exception as e:
            self._log(f"Error scanning {symbol}: {e}", "ERROR")

    def _get_daily_pnl(self) -> float:
        """Retourne le PnL du jour en %"""
        today = datetime.now().date()
        daily_pnl = sum(
            t.pnl for t in self.trades
            if t.exit_time.date() == today
        )
        return (daily_pnl / self.initial_capital * 100) if self.initial_capital > 0 else 0

    def _save_state(self):
        """Sauvegarde l'etat"""
        state = {
            'capital': self.current_capital,
            'total_pnl': self.total_pnl,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'max_drawdown': self.max_drawdown,
            'consecutive_losses': self.consecutive_losses,
            'positions': {k: asdict(v) for k, v in self.positions.items()},
            'updated_at': datetime.now().isoformat()
        }

        # Convert datetime objects
        for pos in state['positions'].values():
            if isinstance(pos.get('entry_time'), datetime):
                pos['entry_time'] = pos['entry_time'].isoformat()

        with open(f"{self.data_dir}/state.json", 'w') as f:
            json.dump(state, f, indent=2, default=str)

        # Save trades
        trades_data = [asdict(t) for t in self.trades[-1000:]]  # Last 1000
        for t in trades_data:
            t['entry_time'] = t['entry_time'].isoformat() if isinstance(t['entry_time'], datetime) else t['entry_time']
            t['exit_time'] = t['exit_time'].isoformat() if isinstance(t['exit_time'], datetime) else t['exit_time']

        with open(f"{self.data_dir}/trades.json", 'w') as f:
            json.dump(trades_data, f, indent=2, default=str)

    def _load_state(self):
        """Charge l'etat precedent"""
        try:
            if os.path.exists(f"{self.data_dir}/state.json"):
                with open(f"{self.data_dir}/state.json", 'r') as f:
                    state = json.load(f)

                self.current_capital = state.get('capital', self.initial_capital)
                self.total_pnl = state.get('total_pnl', 0)
                self.total_trades = state.get('total_trades', 0)
                self.winning_trades = state.get('winning_trades', 0)
                self.losing_trades = state.get('losing_trades', 0)
                self.max_drawdown = state.get('max_drawdown', 0)
                self.consecutive_losses = state.get('consecutive_losses', 0)

                self._log(f"Loaded state: ${self.current_capital:.2f} | PnL: ${self.total_pnl:+.2f}", "INFO")

        except Exception as e:
            self._log(f"Could not load state: {e}", "WARN")

    def _print_final_stats(self):
        """Affiche les stats finales"""
        print(f"\n{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")
        print(f"{C.BOLD}{C.CYAN}  FINAL STATISTICS{C.RESET}")
        print(f"{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")

        pnl_color = C.GREEN if self.total_pnl >= 0 else C.RED
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        print(f"\n  Initial Capital:  ${self.initial_capital:,.2f}")
        print(f"  Final Capital:    ${self.current_capital:,.2f}")
        print(f"  Total PnL:        {pnl_color}${self.total_pnl:+,.2f}{C.RESET}")
        print(f"  Return:           {pnl_color}{(self.total_pnl/self.initial_capital*100):+.1f}%{C.RESET}")
        print(f"  Max Drawdown:     {self.max_drawdown:.1f}%")
        print(f"\n  Total Trades:     {self.total_trades}")
        print(f"  Winning:          {self.winning_trades}")
        print(f"  Losing:           {self.losing_trades}")
        print(f"  Win Rate:         {win_rate:.1f}%")

        if self.trades:
            avg_win = sum(t.pnl for t in self.trades if t.pnl > 0) / max(1, self.winning_trades)
            avg_loss = sum(t.pnl for t in self.trades if t.pnl < 0) / max(1, self.losing_trades)
            print(f"\n  Avg Win:          ${avg_win:+.2f}")
            print(f"  Avg Loss:         ${avg_loss:+.2f}")

        print(f"\n{C.CYAN}{'='*60}{C.RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Degen Trading Bot")
    parser.add_argument('--live', action='store_true', help='Enable live trading (DANGER!)')
    parser.add_argument('--capital', type=float, default=1000, help='Initial capital in USDT')
    parser.add_argument('--symbols', type=str, help='Comma-separated symbols to trade (e.g., BTC,ETH,SOL)')
    parser.add_argument('--mode', type=str, choices=['scalping', 'momentum', 'hybrid'], default='hybrid')

    args = parser.parse_args()

    # Warning for live mode
    if args.live:
        print(f"\n{C.RED}{C.BOLD}{'='*60}")
        print("  WARNING: LIVE TRADING MODE")
        print("  This will use REAL money!")
        print("  Are you sure? (type 'yes' to continue)")
        print(f"{'='*60}{C.RESET}\n")

        confirm = input("> ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return

    # Parse symbols
    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',')]

    # Create bot
    config = degen_config
    config.trading_mode = args.mode

    bot = DegenBot(
        config=config,
        live=args.live,
        initial_capital=args.capital
    )

    # Run
    bot.run(symbols=symbols)


if __name__ == "__main__":
    main()
