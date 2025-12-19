"""
Logging utility avec couleurs et formatage
"""
import logging
import sys
from datetime import datetime
from colorama import init, Fore, Style
from typing import Optional

init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """Formatter avec couleurs pour le terminal"""

    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
    }

    ICONS = {
        'DEBUG': '🔍',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '💀',
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, '')
        icon = self.ICONS.get(record.levelname, '')

        timestamp = datetime.now().strftime('%H:%M:%S')

        # Format spécial pour les signaux de trading
        if hasattr(record, 'signal_type'):
            if record.signal_type == 'BUY':
                return f"{Fore.GREEN}🟢 [{timestamp}] BUY SIGNAL: {record.getMessage()}{Style.RESET_ALL}"
            elif record.signal_type == 'SELL':
                return f"{Fore.RED}🔴 [{timestamp}] SELL SIGNAL: {record.getMessage()}{Style.RESET_ALL}"
            elif record.signal_type == 'CONFLUENCE':
                return f"{Fore.MAGENTA}🎯 [{timestamp}] CONFLUENCE: {record.getMessage()}{Style.RESET_ALL}"

        return f"{color}{icon} [{timestamp}] {record.levelname}: {record.getMessage()}{Style.RESET_ALL}"


class TradingLogger:
    """Logger principal pour le trading bot"""

    def __init__(self, name: str = "TradingBot", level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.handlers = []

        # Console handler avec couleurs
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredFormatter())
        self.logger.addHandler(console_handler)

        # File handler pour historique
        file_handler = logging.FileHandler(
            f'data/trading_{datetime.now().strftime("%Y%m%d")}.log',
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s'
        ))
        self.logger.addHandler(file_handler)

    def info(self, msg: str):
        self.logger.info(msg)

    def debug(self, msg: str):
        self.logger.debug(msg)

    def warning(self, msg: str):
        self.logger.warning(msg)

    def error(self, msg: str):
        self.logger.error(msg)

    def critical(self, msg: str):
        self.logger.critical(msg)

    def buy_signal(self, msg: str):
        """Log un signal d'achat"""
        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, msg, (), None
        )
        record.signal_type = 'BUY'
        self.logger.handle(record)

    def sell_signal(self, msg: str):
        """Log un signal de vente"""
        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, msg, (), None
        )
        record.signal_type = 'SELL'
        self.logger.handle(record)

    def confluence(self, msg: str):
        """Log un signal de confluence"""
        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, msg, (), None
        )
        record.signal_type = 'CONFLUENCE'
        self.logger.handle(record)

    def trade_executed(self, side: str, symbol: str, amount: float, price: float):
        """Log une exécution de trade"""
        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        self.info(f"{emoji} TRADE EXECUTED: {side.upper()} {amount} {symbol} @ ${price:,.2f}")

    def balance_update(self, usdt: float, btc: float = 0):
        """Log mise à jour du solde"""
        self.info(f"💰 Balance: ${usdt:,.2f} USDT | {btc:.6f} BTC")

    def signal_summary(self, technical: int, sentiment: int, onchain: int):
        """Log résumé des signaux"""
        total = technical + sentiment + onchain
        signals = []
        if technical != 0:
            signals.append(f"Technical: {'+' if technical > 0 else ''}{technical}")
        if sentiment != 0:
            signals.append(f"Sentiment: {'+' if sentiment > 0 else ''}{sentiment}")
        if onchain != 0:
            signals.append(f"OnChain: {'+' if onchain > 0 else ''}{onchain}")

        self.confluence(f"{' | '.join(signals)} | Total: {total}/3")


# Instance globale
logger = TradingLogger()
