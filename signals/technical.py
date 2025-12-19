"""
Module d'analyse technique - Signal 1/3
Calcule les indicateurs et génère des signaux basés sur l'analyse technique
"""
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

import ta
from ta.trend import EMAIndicator, SMAIndicator, MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange

from config.settings import technical_config
from utils.logger import logger


class Signal(Enum):
    STRONG_BUY = 2
    BUY = 1
    NEUTRAL = 0
    SELL = -1
    STRONG_SELL = -2


@dataclass
class TechnicalSignal:
    """Résultat de l'analyse technique"""
    signal: Signal
    score: int  # -100 à +100
    rsi: float
    rsi_signal: Signal
    macd_signal: Signal
    bb_signal: Signal
    ema_signal: Signal
    volume_signal: Signal
    details: Dict


class TechnicalAnalyzer:
    """Analyseur technique multi-indicateurs"""

    def __init__(self, config=None):
        self.config = config or technical_config

    def analyze(self, df: pd.DataFrame) -> TechnicalSignal:
        """
        Analyse technique complète

        Args:
            df: DataFrame avec colonnes OHLCV

        Returns:
            TechnicalSignal avec tous les indicateurs
        """
        if df.empty or len(df) < 50:
            logger.warning("Not enough data for technical analysis")
            return self._empty_signal()

        # Calculer tous les indicateurs
        df = self._calculate_indicators(df)

        # Analyser chaque indicateur
        rsi_signal, rsi_value = self._analyze_rsi(df)
        macd_signal = self._analyze_macd(df)
        bb_signal = self._analyze_bollinger(df)
        ema_signal = self._analyze_ema(df)
        volume_signal = self._analyze_volume(df)

        # Calculer le score global (-100 à +100)
        signals = [rsi_signal, macd_signal, bb_signal, ema_signal, volume_signal]
        score = self._calculate_score(signals)

        # Déterminer le signal final
        final_signal = self._determine_signal(score)

        return TechnicalSignal(
            signal=final_signal,
            score=score,
            rsi=rsi_value,
            rsi_signal=rsi_signal,
            macd_signal=macd_signal,
            bb_signal=bb_signal,
            ema_signal=ema_signal,
            volume_signal=volume_signal,
            details=self._get_details(df)
        )

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcule tous les indicateurs techniques"""
        df = df.copy()

        # RSI
        rsi = RSIIndicator(df['close'], window=self.config.rsi_period)
        df['rsi'] = rsi.rsi()

        # MACD
        macd = MACD(
            df['close'],
            window_fast=self.config.macd_fast,
            window_slow=self.config.macd_slow,
            window_sign=self.config.macd_signal
        )
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_histogram'] = macd.macd_diff()

        # Bollinger Bands
        bb = BollingerBands(
            df['close'],
            window=self.config.bb_period,
            window_dev=self.config.bb_std
        )
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

        # EMAs
        df['ema_fast'] = EMAIndicator(df['close'], window=self.config.ema_fast).ema_indicator()
        df['ema_slow'] = EMAIndicator(df['close'], window=self.config.ema_slow).ema_indicator()
        df['sma_200'] = SMAIndicator(df['close'], window=self.config.sma_trend).sma_indicator()

        # Volume SMA
        df['volume_sma'] = df['volume'].rolling(window=self.config.volume_sma_period).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']

        # ATR (pour volatilité)
        atr = AverageTrueRange(df['high'], df['low'], df['close'])
        df['atr'] = atr.average_true_range()

        # Stochastic
        stoch = StochasticOscillator(df['high'], df['low'], df['close'])
        df['stoch_k'] = stoch.stoch()
        df['stoch_d'] = stoch.stoch_signal()

        return df

    def _analyze_rsi(self, df: pd.DataFrame) -> Tuple[Signal, float]:
        """Analyse RSI"""
        rsi = df['rsi'].iloc[-1]

        if pd.isna(rsi):
            return Signal.NEUTRAL, 50

        if rsi < 20:
            return Signal.STRONG_BUY, rsi
        elif rsi < self.config.rsi_oversold:
            return Signal.BUY, rsi
        elif rsi > 80:
            return Signal.STRONG_SELL, rsi
        elif rsi > self.config.rsi_overbought:
            return Signal.SELL, rsi
        else:
            return Signal.NEUTRAL, rsi

    def _analyze_macd(self, df: pd.DataFrame) -> Signal:
        """Analyse MACD crossover"""
        if len(df) < 2:
            return Signal.NEUTRAL

        macd_now = df['macd'].iloc[-1]
        signal_now = df['macd_signal'].iloc[-1]
        macd_prev = df['macd'].iloc[-2]
        signal_prev = df['macd_signal'].iloc[-2]
        histogram = df['macd_histogram'].iloc[-1]

        if pd.isna(macd_now) or pd.isna(signal_now):
            return Signal.NEUTRAL

        # Crossover bullish
        if macd_prev < signal_prev and macd_now > signal_now:
            return Signal.STRONG_BUY if histogram > 0 else Signal.BUY

        # Crossover bearish
        if macd_prev > signal_prev and macd_now < signal_now:
            return Signal.STRONG_SELL if histogram < 0 else Signal.SELL

        # Tendance continue
        if macd_now > signal_now and histogram > 0:
            return Signal.BUY
        elif macd_now < signal_now and histogram < 0:
            return Signal.SELL

        return Signal.NEUTRAL

    def _analyze_bollinger(self, df: pd.DataFrame) -> Signal:
        """Analyse Bollinger Bands"""
        close = df['close'].iloc[-1]
        upper = df['bb_upper'].iloc[-1]
        lower = df['bb_lower'].iloc[-1]
        middle = df['bb_middle'].iloc[-1]

        if pd.isna(upper) or pd.isna(lower):
            return Signal.NEUTRAL

        # Position dans les bandes (0 = lower, 1 = upper)
        position = (close - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

        if position < 0.05:  # Sous la bande basse
            return Signal.STRONG_BUY
        elif position < 0.2:
            return Signal.BUY
        elif position > 0.95:  # Au-dessus de la bande haute
            return Signal.STRONG_SELL
        elif position > 0.8:
            return Signal.SELL
        else:
            return Signal.NEUTRAL

    def _analyze_ema(self, df: pd.DataFrame) -> Signal:
        """Analyse EMA crossover et tendance"""
        close = df['close'].iloc[-1]
        ema_fast = df['ema_fast'].iloc[-1]
        ema_slow = df['ema_slow'].iloc[-1]
        sma_200 = df['sma_200'].iloc[-1]

        if pd.isna(ema_fast) or pd.isna(ema_slow):
            return Signal.NEUTRAL

        # EMA crossover
        ema_fast_prev = df['ema_fast'].iloc[-2]
        ema_slow_prev = df['ema_slow'].iloc[-2]

        bullish_cross = ema_fast_prev < ema_slow_prev and ema_fast > ema_slow
        bearish_cross = ema_fast_prev > ema_slow_prev and ema_fast < ema_slow

        # Tendance long terme
        above_200 = close > sma_200 if not pd.isna(sma_200) else True

        if bullish_cross:
            return Signal.STRONG_BUY if above_200 else Signal.BUY
        elif bearish_cross:
            return Signal.STRONG_SELL if not above_200 else Signal.SELL
        elif ema_fast > ema_slow and above_200:
            return Signal.BUY
        elif ema_fast < ema_slow and not above_200:
            return Signal.SELL

        return Signal.NEUTRAL

    def _analyze_volume(self, df: pd.DataFrame) -> Signal:
        """Analyse du volume"""
        volume_ratio = df['volume_ratio'].iloc[-1]
        price_change = (df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]

        if pd.isna(volume_ratio):
            return Signal.NEUTRAL

        # Volume élevé + prix monte = bullish
        if volume_ratio > 2 and price_change > 0.01:
            return Signal.STRONG_BUY
        elif volume_ratio > 1.5 and price_change > 0:
            return Signal.BUY
        # Volume élevé + prix baisse = bearish
        elif volume_ratio > 2 and price_change < -0.01:
            return Signal.STRONG_SELL
        elif volume_ratio > 1.5 and price_change < 0:
            return Signal.SELL

        return Signal.NEUTRAL

    def _calculate_score(self, signals: list) -> int:
        """Calcule un score de -100 à +100"""
        weights = {
            Signal.STRONG_BUY: 40,
            Signal.BUY: 20,
            Signal.NEUTRAL: 0,
            Signal.SELL: -20,
            Signal.STRONG_SELL: -40
        }

        total = sum(weights[s] for s in signals)
        # Normaliser sur -100 à +100
        max_score = 40 * len(signals)
        return int((total / max_score) * 100)

    def _determine_signal(self, score: int) -> Signal:
        """Détermine le signal final basé sur le score"""
        if score >= 60:
            return Signal.STRONG_BUY
        elif score >= 30:
            return Signal.BUY
        elif score <= -60:
            return Signal.STRONG_SELL
        elif score <= -30:
            return Signal.SELL
        else:
            return Signal.NEUTRAL

    def _get_details(self, df: pd.DataFrame) -> Dict:
        """Retourne les détails des indicateurs"""
        return {
            'price': df['close'].iloc[-1],
            'rsi': df['rsi'].iloc[-1],
            'macd': df['macd'].iloc[-1],
            'macd_signal': df['macd_signal'].iloc[-1],
            'bb_upper': df['bb_upper'].iloc[-1],
            'bb_lower': df['bb_lower'].iloc[-1],
            'ema_fast': df['ema_fast'].iloc[-1],
            'ema_slow': df['ema_slow'].iloc[-1],
            'volume_ratio': df['volume_ratio'].iloc[-1],
            'atr': df['atr'].iloc[-1]
        }

    def _empty_signal(self) -> TechnicalSignal:
        """Retourne un signal vide"""
        return TechnicalSignal(
            signal=Signal.NEUTRAL,
            score=0,
            rsi=50,
            rsi_signal=Signal.NEUTRAL,
            macd_signal=Signal.NEUTRAL,
            bb_signal=Signal.NEUTRAL,
            ema_signal=Signal.NEUTRAL,
            volume_signal=Signal.NEUTRAL,
            details={}
        )

    def get_signal_value(self, signal: TechnicalSignal) -> int:
        """Convertit le signal en valeur pour la confluence (-1, 0, +1)"""
        if signal.signal in [Signal.STRONG_BUY, Signal.BUY]:
            return 1
        elif signal.signal in [Signal.STRONG_SELL, Signal.SELL]:
            return -1
        return 0
