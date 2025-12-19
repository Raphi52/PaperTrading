"""
Configuration Degen Trading - Mode Ultra-Agressif Style MoonDev
================================================================

Trading haute frequence sur timeframe 1 minute avec:
- Indicateurs rapides (RSI 7, EMA 9/21)
- Detection de momentum et breakouts
- Position sizing agressif (10-20%)
"""
import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class DegenConfig:
    """Configuration pour le mode Degen/Scalping"""

    # ========== TIMEFRAME ==========
    timeframe: str = "1m"  # Scalping 1 minute
    secondary_timeframe: str = "5m"  # Confirmation

    # ========== INDICATEURS RAPIDES ==========
    # RSI ultra-court pour reactions rapides
    rsi_period: int = 7
    rsi_oversold: int = 25  # Plus agressif que 30
    rsi_overbought: int = 75  # Plus agressif que 70
    rsi_extreme_oversold: int = 15  # Signal fort
    rsi_extreme_overbought: int = 85  # Signal fort

    # EMAs rapides pour le scalping
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 50  # Trend court terme

    # ========== RISK MANAGEMENT (FULL DEGEN) ==========
    risk_per_trade: float = float(os.getenv("DEGEN_RISK_PERCENT", "15"))  # 15% par trade
    max_positions: int = int(os.getenv("DEGEN_MAX_POSITIONS", "5"))
    max_capital_deployed: float = 75.0  # Max 75% du capital total

    # Stop Loss / Take Profit serres
    stop_loss_percent: float = 1.0  # -1% SL serre
    take_profit_percent: float = 2.0  # +2% TP rapide
    trailing_stop_percent: float = 0.5  # Trailing serre
    trailing_activation: float = 1.0  # Active trailing a +1%

    # ========== MOMENTUM DETECTION ==========
    volume_spike_threshold: float = 3.0  # 3x volume moyen = spike
    volume_pump_threshold: float = 5.0  # 5x volume = pump probable
    price_spike_threshold: float = 1.5  # +1.5% en 1 bougie = mouvement
    price_pump_threshold: float = 3.0  # +3% en 1 bougie = pump

    # Breakout detection
    breakout_lookback: int = 20  # Cherche resistance sur 20 bougies
    breakout_threshold: float = 0.5  # +0.5% au dessus de la resistance

    # ========== SCANNER CONFIGURATION ==========
    scan_interval: int = 10  # Scan toutes les 10 secondes
    min_volume_24h: float = float(os.getenv("DEGEN_MIN_VOLUME", "5000000"))  # $5M min
    max_symbols: int = int(os.getenv("DEGEN_MAX_SYMBOLS", "50"))  # Top 50

    # Filtres scanner
    min_price_change_1h: float = -10.0  # Pas de tokens en chute libre
    max_price_change_1h: float = 50.0  # Pas de tokens deja pumpes
    min_market_cap: float = 1_000_000  # $1M market cap min

    # ========== SIGNAUX ==========
    # Poids des signaux pour le score
    weight_rsi: float = 0.25
    weight_ema: float = 0.20
    weight_volume: float = 0.30
    weight_momentum: float = 0.25

    # Seuils de decision
    buy_threshold: int = 60  # Score >= 60 = BUY
    strong_buy_threshold: int = 80  # Score >= 80 = STRONG BUY
    sell_threshold: int = 40  # Score <= 40 = SELL

    # ========== MODES DE TRADING ==========
    # scalping: entrees/sorties rapides
    # momentum: ride les pumps
    # hybrid: combine les deux
    trading_mode: str = os.getenv("DEGEN_MODE", "hybrid")

    # ========== ALERTES ==========
    enable_sound_alerts: bool = True
    telegram_alerts: bool = False
    alert_on_pump: bool = True
    alert_on_signal: bool = True

    # ========== BLACKLIST ==========
    # Tokens a eviter (stablecoins, leveraged tokens)
    blacklist: List[str] = field(default_factory=lambda: [
        "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP",  # Stablecoins
        "UPUSDT", "DOWNUSDT",  # Leveraged
        "BTCUP", "BTCDOWN", "ETHUP", "ETHDOWN",
        "BNBUP", "BNBDOWN",
    ])

    # ========== FAVORIS ==========
    # Tokens avec plus de volatilite (memecoins, altcoins populaires)
    favorites: List[str] = field(default_factory=lambda: [
        "PEPE", "DOGE", "SHIB", "FLOKI", "BONK",  # Memecoins
        "SOL", "AVAX", "MATIC", "ARB", "OP",  # L1/L2
        "INJ", "SUI", "SEI", "TIA", "JTO",  # Nouveaux
        "WIF", "BOME", "MEW", "POPCAT",  # Memecoins Solana
    ])


@dataclass
class DegenRiskConfig:
    """Configuration specifique au risk management degen"""

    # Circuit breakers
    max_daily_loss_percent: float = 20.0  # Stop trading si -20% sur la journee
    max_consecutive_losses: int = 5  # Pause apres 5 pertes consecutives
    cooldown_after_loss_streak: int = 300  # 5 minutes de pause

    # Position limits
    max_position_size_usd: float = 1000.0  # Max $1000 par position
    min_position_size_usd: float = 20.0  # Min $20 par position

    # Time-based rules
    avoid_low_volume_hours: bool = True  # Evite les heures creuses
    low_volume_start_utc: int = 2  # 2h UTC
    low_volume_end_utc: int = 6  # 6h UTC


# Instances globales
degen_config = DegenConfig()
degen_risk_config = DegenRiskConfig()
