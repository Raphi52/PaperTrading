"""
Analyseur Degen/Scalping - Signaux ultra-rapides pour trading 1 minute
======================================================================

Combine plusieurs indicateurs rapides:
- RSI 7 periodes (reactions rapides)
- EMA 9/21 (trend court terme)
- Volume spikes (detection de momentum)
- Breakout detection (cassures de resistance)
"""
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from config.degen_config import degen_config


class DegenSignal(Enum):
    """Signaux specifiques au mode Degen"""
    PUMP_DETECTED = 5      # Pump en cours - entry immediate
    DEGEN_BUY = 4          # Signal d'achat fort
    SCALP_BUY = 3          # Scalp opportunity
    BUY = 2                # Achat normal
    NEUTRAL = 0            # Pas de signal
    SELL = -2              # Vente
    SCALP_SELL = -3        # Scalp exit
    DEGEN_SELL = -4        # Exit fort
    DUMP_DETECTED = -5     # Dump en cours - exit immediate


@dataclass
class DegenAnalysis:
    """Resultat de l'analyse Degen"""
    signal: DegenSignal
    score: int  # -100 a +100
    confidence: int  # 0-100

    # Indicateurs
    rsi: float
    ema_fast: float
    ema_slow: float
    volume_ratio: float
    price_change_1m: float
    price_change_5m: float

    # Flags
    is_pump: bool
    is_dump: bool
    is_breakout: bool
    is_volume_spike: bool
    ema_bullish: bool

    # Details
    reasons: List[str]
    entry_price: float
    stop_loss: float
    take_profit: float

    # Timing
    timestamp: datetime


class DegenAnalyzer:
    """Analyseur pour le trading Degen/Scalping"""

    def __init__(self, config=None):
        self.config = config or degen_config

    def analyze(self, df: pd.DataFrame, symbol: str = "") -> DegenAnalysis:
        """
        Analyse complete pour le mode Degen

        Args:
            df: DataFrame OHLCV (minimum 50 bougies 1m)
            symbol: Nom du token

        Returns:
            DegenAnalysis avec signal et details
        """
        if df.empty or len(df) < 30:
            return self._empty_analysis()

        # Calculer les indicateurs
        df = self._calculate_indicators(df)

        # Analyser chaque composant
        rsi_signal, rsi_value = self._analyze_rsi(df)
        ema_signal, ema_bullish = self._analyze_ema(df)
        volume_signal, volume_ratio, is_spike = self._analyze_volume(df)
        momentum_signal, price_change_1m, price_change_5m = self._analyze_momentum(df)
        breakout_signal, is_breakout = self._analyze_breakout(df)

        # Detecter pump/dump
        is_pump = self._detect_pump(df, volume_ratio, price_change_1m)
        is_dump = self._detect_dump(df, volume_ratio, price_change_1m)

        # Calculer le score global
        score = self._calculate_score(
            rsi_signal, ema_signal, volume_signal,
            momentum_signal, breakout_signal,
            is_pump, is_dump
        )

        # Determiner le signal final
        signal, reasons = self._determine_signal(
            score, is_pump, is_dump, is_breakout,
            is_spike, ema_bullish, rsi_value
        )

        # Calculer les niveaux
        current_price = df['close'].iloc[-1]
        stop_loss, take_profit = self._calculate_levels(current_price, signal)

        # Confidence basee sur l'alignement des signaux
        confidence = self._calculate_confidence(
            rsi_signal, ema_signal, volume_signal,
            momentum_signal, is_pump, is_dump
        )

        return DegenAnalysis(
            signal=signal,
            score=score,
            confidence=confidence,
            rsi=rsi_value,
            ema_fast=df['ema_fast'].iloc[-1],
            ema_slow=df['ema_slow'].iloc[-1],
            volume_ratio=volume_ratio,
            price_change_1m=price_change_1m,
            price_change_5m=price_change_5m,
            is_pump=is_pump,
            is_dump=is_dump,
            is_breakout=is_breakout,
            is_volume_spike=is_spike,
            ema_bullish=ema_bullish,
            reasons=reasons,
            entry_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=datetime.now()
        )

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcule tous les indicateurs rapides"""
        df = df.copy()

        # RSI rapide (7 periodes)
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.config.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.config.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # EMAs rapides
        df['ema_fast'] = df['close'].ewm(span=self.config.ema_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.config.ema_slow, adjust=False).mean()
        df['ema_trend'] = df['close'].ewm(span=self.config.ema_trend, adjust=False).mean()

        # Volume SMA
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']

        # Price changes
        df['price_change_1'] = df['close'].pct_change(1) * 100
        df['price_change_5'] = df['close'].pct_change(5) * 100

        # Highs/Lows pour breakout
        df['high_20'] = df['high'].rolling(window=20).max()
        df['low_20'] = df['low'].rolling(window=20).min()

        # Momentum
        df['momentum'] = df['close'] - df['close'].shift(5)
        df['momentum_pct'] = df['momentum'] / df['close'].shift(5) * 100

        return df

    def _analyze_rsi(self, df: pd.DataFrame) -> Tuple[int, float]:
        """Analyse RSI rapide"""
        rsi = df['rsi'].iloc[-1]

        if pd.isna(rsi):
            return 0, 50.0

        if rsi < self.config.rsi_extreme_oversold:
            return 2, rsi  # Tres survenu = signal fort
        elif rsi < self.config.rsi_oversold:
            return 1, rsi
        elif rsi > self.config.rsi_extreme_overbought:
            return -2, rsi  # Tres suracheté = signal fort
        elif rsi > self.config.rsi_overbought:
            return -1, rsi

        return 0, rsi

    def _analyze_ema(self, df: pd.DataFrame) -> Tuple[int, bool]:
        """Analyse EMA crossover"""
        ema_fast = df['ema_fast'].iloc[-1]
        ema_slow = df['ema_slow'].iloc[-1]
        ema_fast_prev = df['ema_fast'].iloc[-2]
        ema_slow_prev = df['ema_slow'].iloc[-2]
        price = df['close'].iloc[-1]

        if pd.isna(ema_fast) or pd.isna(ema_slow):
            return 0, False

        # EMA bullish alignment
        ema_bullish = price > ema_fast > ema_slow

        # Crossover detection
        bullish_cross = ema_fast_prev < ema_slow_prev and ema_fast > ema_slow
        bearish_cross = ema_fast_prev > ema_slow_prev and ema_fast < ema_slow

        if bullish_cross:
            return 2, True
        elif bearish_cross:
            return -2, False
        elif ema_bullish:
            return 1, True
        elif price < ema_fast < ema_slow:
            return -1, False

        return 0, ema_fast > ema_slow

    def _analyze_volume(self, df: pd.DataFrame) -> Tuple[int, float, bool]:
        """Analyse volume spike"""
        volume_ratio = df['volume_ratio'].iloc[-1]
        price_change = df['price_change_1'].iloc[-1]

        if pd.isna(volume_ratio):
            return 0, 1.0, False

        is_spike = volume_ratio >= self.config.volume_spike_threshold
        is_pump_volume = volume_ratio >= self.config.volume_pump_threshold

        if is_pump_volume and price_change > 0:
            return 2, volume_ratio, True
        elif is_spike and price_change > 0:
            return 1, volume_ratio, True
        elif is_pump_volume and price_change < 0:
            return -2, volume_ratio, True
        elif is_spike and price_change < 0:
            return -1, volume_ratio, True

        return 0, volume_ratio, is_spike

    def _analyze_momentum(self, df: pd.DataFrame) -> Tuple[int, float, float]:
        """Analyse momentum"""
        price_change_1m = df['price_change_1'].iloc[-1]
        price_change_5m = df['price_change_5'].iloc[-1]

        if pd.isna(price_change_1m):
            return 0, 0.0, 0.0

        # Strong momentum up
        if price_change_1m >= self.config.price_pump_threshold:
            return 2, price_change_1m, price_change_5m
        elif price_change_1m >= self.config.price_spike_threshold:
            return 1, price_change_1m, price_change_5m
        # Strong momentum down
        elif price_change_1m <= -self.config.price_pump_threshold:
            return -2, price_change_1m, price_change_5m
        elif price_change_1m <= -self.config.price_spike_threshold:
            return -1, price_change_1m, price_change_5m

        return 0, price_change_1m, price_change_5m

    def _analyze_breakout(self, df: pd.DataFrame) -> Tuple[int, bool]:
        """Detecte les breakouts"""
        price = df['close'].iloc[-1]
        high_20 = df['high_20'].iloc[-2]  # Previous high (excluding current)
        low_20 = df['low_20'].iloc[-2]

        if pd.isna(high_20) or pd.isna(low_20):
            return 0, False

        # Breakout au dessus de la resistance
        breakout_up = price > high_20 * (1 + self.config.breakout_threshold / 100)
        # Breakdown en dessous du support
        breakout_down = price < low_20 * (1 - self.config.breakout_threshold / 100)

        if breakout_up:
            return 2, True
        elif breakout_down:
            return -2, True

        return 0, False

    def _detect_pump(self, df: pd.DataFrame, volume_ratio: float, price_change: float) -> bool:
        """Detecte un pump en cours"""
        return (
            volume_ratio >= self.config.volume_pump_threshold and
            price_change >= self.config.price_spike_threshold
        )

    def _detect_dump(self, df: pd.DataFrame, volume_ratio: float, price_change: float) -> bool:
        """Detecte un dump en cours"""
        return (
            volume_ratio >= self.config.volume_pump_threshold and
            price_change <= -self.config.price_spike_threshold
        )

    def _calculate_score(self, rsi: int, ema: int, volume: int,
                         momentum: int, breakout: int,
                         is_pump: bool, is_dump: bool) -> int:
        """Calcule le score global (-100 a +100)"""
        # Poids normalises
        weights = {
            'rsi': self.config.weight_rsi,
            'ema': self.config.weight_ema,
            'volume': self.config.weight_volume,
            'momentum': self.config.weight_momentum,
        }

        # Score de base (chaque signal va de -2 a +2)
        base_score = (
            rsi * weights['rsi'] +
            ema * weights['ema'] +
            volume * weights['volume'] +
            momentum * weights['momentum']
        )

        # Normaliser sur -100 a +100
        max_raw = 2 * sum(weights.values())
        score = int((base_score / max_raw) * 100)

        # Boost pour pump/dump
        if is_pump:
            score = min(100, score + 30)
        elif is_dump:
            score = max(-100, score - 30)

        # Boost pour breakout
        if breakout > 0:
            score = min(100, score + 15)
        elif breakout < 0:
            score = max(-100, score - 15)

        return max(-100, min(100, score))

    def _determine_signal(self, score: int, is_pump: bool, is_dump: bool,
                          is_breakout: bool, is_volume_spike: bool,
                          ema_bullish: bool, rsi: float) -> Tuple[DegenSignal, List[str]]:
        """Determine le signal final et les raisons"""
        reasons = []

        # Pump/Dump ont priorite
        if is_pump:
            reasons.append(f"PUMP DETECTED - Volume spike + price surge")
            return DegenSignal.PUMP_DETECTED, reasons

        if is_dump:
            reasons.append(f"DUMP DETECTED - Volume spike + price crash")
            return DegenSignal.DUMP_DETECTED, reasons

        # Breakout signals
        if is_breakout and score >= 60:
            reasons.append("Breakout above resistance")
            if is_volume_spike:
                reasons.append("Confirmed by volume")
                return DegenSignal.DEGEN_BUY, reasons
            return DegenSignal.SCALP_BUY, reasons

        # Score-based signals
        if score >= self.config.strong_buy_threshold:
            reasons.append(f"Strong momentum score: {score}")
            if rsi < self.config.rsi_oversold:
                reasons.append(f"RSI oversold: {rsi:.0f}")
            if ema_bullish:
                reasons.append("EMA bullish alignment")
            return DegenSignal.DEGEN_BUY, reasons

        elif score >= self.config.buy_threshold:
            reasons.append(f"Buy signal score: {score}")
            if is_volume_spike:
                reasons.append("Volume confirmation")
                return DegenSignal.SCALP_BUY, reasons
            return DegenSignal.BUY, reasons

        elif score <= -self.config.strong_buy_threshold:
            reasons.append(f"Strong sell score: {score}")
            return DegenSignal.DEGEN_SELL, reasons

        elif score <= -self.config.buy_threshold:
            reasons.append(f"Sell signal score: {score}")
            return DegenSignal.SCALP_SELL, reasons

        reasons.append(f"Neutral score: {score}")
        return DegenSignal.NEUTRAL, reasons

    def _calculate_levels(self, price: float, signal: DegenSignal) -> Tuple[float, float]:
        """Calcule SL et TP"""
        if signal.value > 0:  # Buy signals
            stop_loss = price * (1 - self.config.stop_loss_percent / 100)
            take_profit = price * (1 + self.config.take_profit_percent / 100)
        elif signal.value < 0:  # Sell signals
            stop_loss = price * (1 + self.config.stop_loss_percent / 100)
            take_profit = price * (1 - self.config.take_profit_percent / 100)
        else:
            stop_loss = price
            take_profit = price

        return stop_loss, take_profit

    def _calculate_confidence(self, rsi: int, ema: int, volume: int,
                              momentum: int, is_pump: bool, is_dump: bool) -> int:
        """Calcule la confiance du signal"""
        # Compter les signaux alignes
        signals = [rsi, ema, volume, momentum]
        positive = sum(1 for s in signals if s > 0)
        negative = sum(1 for s in signals if s < 0)

        if is_pump or is_dump:
            return 95  # Tres haute confiance sur pump/dump

        if positive >= 3 or negative >= 3:
            return 85  # 3/4 alignes
        elif positive >= 2 or negative >= 2:
            return 70  # 2/4 alignes
        else:
            return 50  # Faible alignement

    def _empty_analysis(self) -> DegenAnalysis:
        """Retourne une analyse vide"""
        return DegenAnalysis(
            signal=DegenSignal.NEUTRAL,
            score=0,
            confidence=0,
            rsi=50.0,
            ema_fast=0,
            ema_slow=0,
            volume_ratio=1.0,
            price_change_1m=0,
            price_change_5m=0,
            is_pump=False,
            is_dump=False,
            is_breakout=False,
            is_volume_spike=False,
            ema_bullish=False,
            reasons=["Insufficient data"],
            entry_price=0,
            stop_loss=0,
            take_profit=0,
            timestamp=datetime.now()
        )

    def get_quick_score(self, df: pd.DataFrame) -> Tuple[int, str]:
        """
        Score rapide pour le scanner (moins de calculs)

        Returns:
            (score, signal_type)
        """
        if df.empty or len(df) < 10:
            return 0, "NO_DATA"

        # Calculs rapides
        closes = df['close'].values
        volumes = df['volume'].values

        # RSI simplifie
        delta = np.diff(closes)
        gain = np.mean(np.maximum(delta[-7:], 0))
        loss = np.mean(np.abs(np.minimum(delta[-7:], 0)))
        rsi = 100 - (100 / (1 + gain / (loss + 1e-10)))

        # Volume ratio
        vol_avg = np.mean(volumes[-20:])
        vol_current = volumes[-1]
        vol_ratio = vol_current / (vol_avg + 1e-10)

        # Price change
        price_change = (closes[-1] - closes[-2]) / closes[-2] * 100

        # Score rapide
        score = 0

        if rsi < 30:
            score += 25
        elif rsi > 70:
            score -= 25

        if vol_ratio > 3 and price_change > 0:
            score += 30
        elif vol_ratio > 3 and price_change < 0:
            score -= 30

        if price_change > 1.5:
            score += 20
        elif price_change < -1.5:
            score -= 20

        # Signal type
        if score >= 60:
            return score, "STRONG_BUY"
        elif score >= 30:
            return score, "BUY"
        elif score <= -60:
            return score, "STRONG_SELL"
        elif score <= -30:
            return score, "SELL"
        else:
            return score, "NEUTRAL"
