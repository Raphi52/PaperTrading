"""
Configuration centrale du Trading Bot
"""
import os
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import List

load_dotenv()


@dataclass
class ExchangeConfig:
    name: str = "binance"
    api_key: str = os.getenv("BINANCE_API_KEY", "")
    secret: str = os.getenv("BINANCE_SECRET", "")
    testnet: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"


@dataclass
class TradingConfig:
    symbol: str = os.getenv("DEFAULT_SYMBOL", "BTC/USDT")
    trade_amount_usdt: float = float(os.getenv("TRADE_AMOUNT_USDT", "100"))
    max_risk_percent: float = float(os.getenv("MAX_RISK_PERCENT", "2"))
    confluence_threshold: int = int(os.getenv("CONFLUENCE_THRESHOLD", "2"))

    # Take Profit / Stop Loss
    take_profit_percent: float = 3.0
    stop_loss_percent: float = 2.0
    trailing_stop_percent: float = 1.5

    # Timeframes
    primary_timeframe: str = "1h"
    secondary_timeframe: str = "4h"


@dataclass
class TechnicalConfig:
    """Configuration des indicateurs techniques"""
    # RSI
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70

    # Bollinger Bands
    bb_period: int = 20
    bb_std: float = 2.0

    # Moving Averages
    ema_fast: int = 12
    ema_slow: int = 26
    sma_trend: int = 200

    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # Volume
    volume_sma_period: int = 20


@dataclass
class SentimentConfig:
    """Configuration de l'analyse de sentiment"""
    twitter_bearer: str = os.getenv("TWITTER_BEARER_TOKEN", "")
    reddit_client_id: str = os.getenv("REDDIT_CLIENT_ID", "")
    reddit_secret: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    lunarcrush_key: str = os.getenv("LUNARCRUSH_API_KEY", "")

    # Thresholds
    fear_greed_bullish: int = 25  # En dessous = fear extreme = buy
    fear_greed_bearish: int = 75  # Au dessus = greed extreme = sell

    # Keywords pour analyse
    bullish_keywords: List[str] = None
    bearish_keywords: List[str] = None

    def __post_init__(self):
        self.bullish_keywords = [
            "moon", "pump", "bullish", "buy", "long", "hodl", "accumulate",
            "breakout", "support", "bottom", "undervalued", "gem"
        ]
        self.bearish_keywords = [
            "dump", "crash", "bearish", "sell", "short", "rekt", "scam",
            "resistance", "top", "overvalued", "bubble", "rugpull"
        ]


@dataclass
class OnChainConfig:
    """Configuration des métriques on-chain"""
    glassnode_key: str = os.getenv("GLASSNODE_API_KEY", "")
    etherscan_key: str = os.getenv("ETHERSCAN_API_KEY", "")

    # Whale thresholds
    whale_btc_threshold: float = 100  # BTC
    whale_eth_threshold: float = 1000  # ETH

    # Exchange flow
    exchange_inflow_bearish: float = 1.5  # x moyenne = bearish
    exchange_outflow_bullish: float = 1.5  # x moyenne = bullish


@dataclass
class NotificationConfig:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    discord_webhook: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    enabled: bool = True


# Import Degen config
from config.degen_config import degen_config, degen_risk_config

# Instances globales
exchange_config = ExchangeConfig()
trading_config = TradingConfig()
technical_config = TechnicalConfig()
sentiment_config = SentimentConfig()
onchain_config = OnChainConfig()
notification_config = NotificationConfig()

# Degen config already instantiated in degen_config.py
# Use: from config.degen_config import degen_config
