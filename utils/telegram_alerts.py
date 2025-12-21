"""
Telegram Alerts - Notifications en temps reel
==============================================

Envoie des alertes Telegram pour:
- Signaux de trading (PUMP, BUY, SELL)
- Ouverture/fermeture de positions
- PnL updates
- Alertes de securite

Configuration:
    1. Creer un bot Telegram avec @BotFather
    2. Obtenir le token du bot
    3. Obtenir votre chat_id (envoyer /start au bot puis utiliser @userinfobot)
    4. Ajouter dans .env:
        TELEGRAM_BOT_TOKEN=your_token
        TELEGRAM_CHAT_ID=your_chat_id
"""
import os
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum
import json

from dotenv import load_dotenv

load_dotenv()


class AlertType(Enum):
    """Types d'alertes"""
    PUMP = "pump"
    DUMP = "dump"
    BUY_SIGNAL = "buy_signal"
    SELL_SIGNAL = "sell_signal"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    WHALE_ALERT = "whale_alert"
    NEW_LISTING = "new_listing"
    ERROR = "error"
    INFO = "info"


@dataclass
class Alert:
    """Structure d'une alerte"""
    type: AlertType
    symbol: str
    message: str
    price: float = 0
    pnl: float = 0
    pnl_percent: float = 0
    extra_data: Dict = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.extra_data is None:
            self.extra_data = {}


class TelegramAlerts:
    """Gestionnaire d'alertes Telegram"""

    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.bot_token and self.chat_id)
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

        # Rate limiting
        self.last_message_time = 0
        self.min_interval = 1  # 1 seconde entre les messages
        self.message_queue: List[Alert] = []

        # Emojis par type
        self.emojis = {
            AlertType.PUMP: "🚀🚀🚀",
            AlertType.DUMP: "📉📉📉",
            AlertType.BUY_SIGNAL: "🟢",
            AlertType.SELL_SIGNAL: "🔴",
            AlertType.POSITION_OPENED: "📈",
            AlertType.POSITION_CLOSED: "📊",
            AlertType.TAKE_PROFIT: "💰",
            AlertType.STOP_LOSS: "🛑",
            AlertType.TRAILING_STOP: "🔒",
            AlertType.WHALE_ALERT: "🐋",
            AlertType.NEW_LISTING: "🆕",
            AlertType.ERROR: "⚠️",
            AlertType.INFO: "ℹ️",
        }

        if self.enabled:
            print(f"[OK] Telegram alerts enabled (chat_id: {self.chat_id[:4]}...)")
        else:
            print("[WARN] Telegram alerts disabled (missing token or chat_id)")

    async def send_message(self, text: str, parse_mode: str = "HTML",
                           disable_notification: bool = False) -> bool:
        """Envoie un message Telegram"""
        if not self.enabled:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_notification": disable_notification
                }

                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        return True
                    else:
                        error = await response.text()
                        print(f"Telegram error: {error}")
                        return False

        except Exception as e:
            print(f"Telegram send error: {e}")
            return False

    def send_message_sync(self, text: str, parse_mode: str = "HTML") -> bool:
        """Version synchrone de send_message"""
        import requests

        if not self.enabled:
            return False

        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode
            }

            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200

        except Exception as e:
            print(f"Telegram send error: {e}")
            return False

    def format_alert(self, alert: Alert) -> str:
        """Formate une alerte pour Telegram"""
        emoji = self.emojis.get(alert.type, "📢")
        time_str = alert.timestamp.strftime("%H:%M:%S")

        # Header
        header = f"{emoji} <b>{alert.type.value.upper()}</b> | {alert.symbol}\n"

        # Message principal
        body = f"{alert.message}\n"

        # Prix
        if alert.price > 0:
            body += f"💵 Price: <code>${alert.price:.4f}</code>\n"

        # PnL
        if alert.pnl != 0:
            pnl_emoji = "✅" if alert.pnl > 0 else "❌"
            body += f"{pnl_emoji} PnL: <code>${alert.pnl:+.2f}</code> ({alert.pnl_percent:+.1f}%)\n"

        # Extra data
        if alert.extra_data:
            for key, value in alert.extra_data.items():
                body += f"• {key}: <code>{value}</code>\n"

        # Footer
        footer = f"\n⏰ {time_str}"

        return header + body + footer

    async def send_alert(self, alert: Alert) -> bool:
        """Envoie une alerte formatee"""
        text = self.format_alert(alert)
        return await self.send_message(text)

    def send_alert_sync(self, alert: Alert) -> bool:
        """Version synchrone de send_alert"""
        text = self.format_alert(alert)
        return self.send_message_sync(text)

    # ==================== ALERTES SPECIFIQUES ====================

    async def pump_detected(self, symbol: str, price: float, change_pct: float,
                            volume_ratio: float):
        """Alerte pump detecte"""
        alert = Alert(
            type=AlertType.PUMP,
            symbol=symbol,
            message=f"PUMP DETECTED! +{change_pct:.1f}% in 1 minute",
            price=price,
            extra_data={
                "Change": f"+{change_pct:.1f}%",
                "Volume": f"{volume_ratio:.1f}x average"
            }
        )
        return await self.send_alert(alert)

    async def dump_detected(self, symbol: str, price: float, change_pct: float,
                            volume_ratio: float):
        """Alerte dump detecte"""
        alert = Alert(
            type=AlertType.DUMP,
            symbol=symbol,
            message=f"DUMP DETECTED! {change_pct:.1f}% in 1 minute",
            price=price,
            extra_data={
                "Change": f"{change_pct:.1f}%",
                "Volume": f"{volume_ratio:.1f}x average"
            }
        )
        return await self.send_alert(alert)

    async def buy_signal(self, symbol: str, price: float, signal_type: str,
                         score: int, reasons: List[str] = None):
        """Alerte signal d'achat"""
        alert = Alert(
            type=AlertType.BUY_SIGNAL,
            symbol=symbol,
            message=f"Buy signal: {signal_type}",
            price=price,
            extra_data={
                "Signal": signal_type,
                "Score": f"{score}/100",
                "Reasons": ", ".join(reasons[:2]) if reasons else "N/A"
            }
        )
        return await self.send_alert(alert)

    async def position_opened(self, symbol: str, price: float, amount_usdt: float,
                              stop_loss: float, take_profit: float, signal_type: str):
        """Alerte position ouverte"""
        alert = Alert(
            type=AlertType.POSITION_OPENED,
            symbol=symbol,
            message=f"Position opened: ${amount_usdt:.2f}",
            price=price,
            extra_data={
                "Size": f"${amount_usdt:.2f}",
                "Stop Loss": f"${stop_loss:.4f}",
                "Take Profit": f"${take_profit:.4f}",
                "Signal": signal_type
            }
        )
        return await self.send_alert(alert)

    async def position_closed(self, symbol: str, entry_price: float, exit_price: float,
                              pnl: float, pnl_percent: float, reason: str):
        """Alerte position fermee"""
        alert_type = AlertType.TAKE_PROFIT if pnl > 0 else AlertType.STOP_LOSS
        if reason == "trailing_stop":
            alert_type = AlertType.TRAILING_STOP

        alert = Alert(
            type=alert_type,
            symbol=symbol,
            message=f"Position closed: {reason}",
            price=exit_price,
            pnl=pnl,
            pnl_percent=pnl_percent,
            extra_data={
                "Entry": f"${entry_price:.4f}",
                "Exit": f"${exit_price:.4f}",
                "Reason": reason
            }
        )
        return await self.send_alert(alert)

    async def whale_alert(self, symbol: str, wallet: str, action: str,
                          amount: float, price: float):
        """Alerte whale"""
        alert = Alert(
            type=AlertType.WHALE_ALERT,
            symbol=symbol,
            message=f"Whale {action}: {amount:.2f} {symbol}",
            price=price,
            extra_data={
                "Wallet": f"{wallet[:8]}...{wallet[-6:]}",
                "Action": action.upper(),
                "Amount": f"{amount:.2f} {symbol}",
                "Value": f"${amount * price:,.2f}"
            }
        )
        return await self.send_alert(alert)

    async def new_listing(self, symbol: str, exchange: str, price: float = 0):
        """Alerte nouveau listing"""
        alert = Alert(
            type=AlertType.NEW_LISTING,
            symbol=symbol,
            message=f"New listing detected on {exchange}!",
            price=price,
            extra_data={
                "Exchange": exchange,
                "Token": symbol
            }
        )
        return await self.send_alert(alert)

    async def daily_summary(self, total_pnl: float, trades_count: int,
                            win_rate: float, capital: float):
        """Resume quotidien"""
        emoji = "📈" if total_pnl >= 0 else "📉"
        pnl_emoji = "✅" if total_pnl >= 0 else "❌"

        text = f"""
{emoji} <b>DAILY SUMMARY</b>

{pnl_emoji} Total PnL: <code>${total_pnl:+.2f}</code>
📊 Trades: <code>{trades_count}</code>
🎯 Win Rate: <code>{win_rate:.1f}%</code>
💰 Capital: <code>${capital:,.2f}</code>

⏰ {datetime.now().strftime("%Y-%m-%d %H:%M")}
"""
        return await self.send_message(text)

    # ==================== QUICK ALERTS ====================

    def quick_pump(self, symbol: str, change: float, volume: float):
        """Alerte pump rapide (sync)"""
        text = f"🚀🚀🚀 <b>PUMP</b> | {symbol}\n+{change:.1f}% | Vol: {volume:.1f}x"
        return self.send_message_sync(text)

    def quick_dump(self, symbol: str, change: float, volume: float):
        """Alerte dump rapide (sync)"""
        text = f"📉📉📉 <b>DUMP</b> | {symbol}\n{change:.1f}% | Vol: {volume:.1f}x"
        return self.send_message_sync(text)

    def quick_trade(self, symbol: str, action: str, price: float, pnl: float = 0):
        """Alerte trade rapide (sync)"""
        emoji = "🟢" if action == "BUY" else "🔴"
        pnl_str = f" | PnL: ${pnl:+.2f}" if pnl != 0 else ""
        text = f"{emoji} <b>{action}</b> | {symbol} @ ${price:.4f}{pnl_str}"
        return self.send_message_sync(text)


# Instance globale
telegram = TelegramAlerts()


# ==================== FONCTIONS UTILITAIRES ====================

def send_pump_alert(symbol: str, change: float, volume: float):
    """Wrapper pour alerte pump"""
    return telegram.quick_pump(symbol, change, volume)


def send_trade_alert(symbol: str, action: str, price: float, pnl: float = 0):
    """Wrapper pour alerte trade"""
    return telegram.quick_trade(symbol, action, price, pnl)


async def send_position_update(symbol: str, entry: float, current: float,
                               pnl: float, pnl_pct: float):
    """Envoie une mise a jour de position"""
    alert = Alert(
        type=AlertType.INFO,
        symbol=symbol,
        message="Position update",
        price=current,
        pnl=pnl,
        pnl_percent=pnl_pct,
        extra_data={"Entry": f"${entry:.4f}"}
    )
    return await telegram.send_alert(alert)
