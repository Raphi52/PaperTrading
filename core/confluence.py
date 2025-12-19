"""
Confluence Engine - Le coeur du système
Combine les 3 signaux pour décision finale + God Mode Detection
"""
import asyncio
from datetime import datetime
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from signals.technical import TechnicalAnalyzer, TechnicalSignal, Signal
from signals.sentiment import SentimentAnalyzer, SentimentSignal
from signals.onchain import OnChainAnalyzer, OnChainSignal
from signals.godmode import GodModeDetector, GodModeSignal, GodModeLevel
from config.settings import trading_config
from utils.logger import logger


class TradeAction(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    GOD_MODE_BUY = "GOD_MODE_BUY"  # 🚨 Accumulation maximale


@dataclass
class ConfluenceResult:
    """Résultat de l'analyse de confluence"""
    action: TradeAction
    confidence: int  # 0-100
    technical_signal: int  # -1, 0, +1
    sentiment_signal: int  # -1, 0, +1
    onchain_signal: int  # -1, 0, +1
    confluence_score: int  # -3 à +3
    signals_aligned: int  # Nombre de signaux alignés (0-3)
    technical_data: TechnicalSignal
    sentiment_data: SentimentSignal
    onchain_data: OnChainSignal
    timestamp: datetime
    reasoning: str
    # God Mode
    god_mode: Optional[GodModeSignal] = None
    god_mode_active: bool = False
    recommended_allocation: float = 5.0  # % du portfolio


class ConfluenceEngine:
    """
    Moteur de confluence - Combine 3 signaux indépendants + God Mode

    RÈGLE D'OR:
    - Trade UNIQUEMENT si au moins 2/3 signaux sont alignés
    - 3/3 signaux = position plus grande
    - 1/3 ou 0/3 = HOLD (pas de trade)
    - GOD MODE = Accumulation maximale (rare, cycle bottom)
    """

    def __init__(self):
        self.technical = TechnicalAnalyzer()
        self.sentiment = SentimentAnalyzer()
        self.onchain = OnChainAnalyzer()
        self.godmode = GodModeDetector()
        self.threshold = trading_config.confluence_threshold
        self._last_godmode_check = None
        self._godmode_cache = None
        self._godmode_cache_duration = 3600  # Check God Mode toutes les heures

    async def analyze(self, ohlcv_data, symbol: str = "BTC",
                      check_godmode: bool = True) -> ConfluenceResult:
        """
        Analyse de confluence complète + God Mode

        Args:
            ohlcv_data: DataFrame avec données OHLCV
            symbol: Symbole (BTC, ETH, etc.)
            check_godmode: Vérifier les conditions God Mode

        Returns:
            ConfluenceResult avec décision et détails
        """
        logger.info(f"Running confluence analysis for {symbol}...")

        # Récupérer le prix actuel
        current_price = float(ohlcv_data['close'].iloc[-1]) if not ohlcv_data.empty else 0

        # Lancer les analyses en parallèle
        technical_task = asyncio.create_task(
            asyncio.to_thread(self.technical.analyze, ohlcv_data)
        )
        sentiment_task = asyncio.create_task(
            self.sentiment.analyze(symbol)
        )
        onchain_task = asyncio.create_task(
            self.onchain.analyze(symbol)
        )

        # God Mode check (avec cache pour éviter trop d'appels API)
        godmode_signal = None
        if check_godmode:
            godmode_signal = await self._check_godmode_cached(current_price)

        # Attendre tous les résultats
        technical_result = await technical_task
        sentiment_result = await sentiment_task
        onchain_result = await onchain_task

        # Extraire les signaux (-1, 0, +1)
        tech_signal = self.technical.get_signal_value(technical_result)
        sent_signal = sentiment_result.signal
        chain_signal = onchain_result.signal

        # Log des signaux individuels
        logger.signal_summary(tech_signal, sent_signal, chain_signal)

        # Calculer la confluence
        confluence_score = tech_signal + sent_signal + chain_signal
        signals_aligned = self._count_aligned_signals(tech_signal, sent_signal, chain_signal)

        # Déterminer l'action
        action, confidence = self._determine_action(
            confluence_score, signals_aligned,
            tech_signal, sent_signal, chain_signal
        )

        # 🚨 GOD MODE OVERRIDE
        god_mode_active = False
        recommended_allocation = 5.0  # Default

        if godmode_signal:
            if godmode_signal.level in [GodModeLevel.ACTIVATED, GodModeLevel.EXTREME]:
                god_mode_active = True
                recommended_allocation = godmode_signal.recommended_allocation

                # Override action si God Mode EXTREME et pas de signal SELL fort
                if godmode_signal.level == GodModeLevel.EXTREME and action != TradeAction.STRONG_SELL:
                    action = TradeAction.GOD_MODE_BUY
                    confidence = 95
                    logger.info("🚨 GOD MODE EXTREME - Overriding to GOD_MODE_BUY")

                elif godmode_signal.level == GodModeLevel.ACTIVATED and action in [TradeAction.HOLD, TradeAction.BUY]:
                    action = TradeAction.STRONG_BUY
                    confidence = max(confidence, 85)
                    logger.info("🟢 GOD MODE ACTIVATED - Upgrading to STRONG_BUY")

            elif godmode_signal.level == GodModeLevel.WARMING_UP:
                recommended_allocation = godmode_signal.recommended_allocation
                # Juste augmenter la confiance sur les BUY
                if action in [TradeAction.BUY, TradeAction.STRONG_BUY]:
                    confidence = min(confidence + 10, 95)

        # Générer le raisonnement
        reasoning = self._generate_reasoning(
            action, tech_signal, sent_signal, chain_signal,
            technical_result, sentiment_result, onchain_result,
            godmode_signal
        )

        result = ConfluenceResult(
            action=action,
            confidence=confidence,
            technical_signal=tech_signal,
            sentiment_signal=sent_signal,
            onchain_signal=chain_signal,
            confluence_score=confluence_score,
            signals_aligned=signals_aligned,
            technical_data=technical_result,
            sentiment_data=sentiment_result,
            onchain_data=onchain_result,
            timestamp=datetime.now(),
            reasoning=reasoning,
            god_mode=godmode_signal,
            god_mode_active=god_mode_active,
            recommended_allocation=recommended_allocation
        )

        # Log du résultat
        self._log_result(result)

        return result

    async def _check_godmode_cached(self, current_price: float) -> Optional[GodModeSignal]:
        """Vérifie God Mode avec cache"""
        now = datetime.now()

        # Utiliser le cache si récent
        if self._godmode_cache and self._last_godmode_check:
            elapsed = (now - self._last_godmode_check).total_seconds()
            if elapsed < self._godmode_cache_duration:
                return self._godmode_cache

        # Nouveau check
        try:
            self._godmode_cache = await self.godmode.detect(current_price)
            self._last_godmode_check = now
            return self._godmode_cache
        except Exception as e:
            logger.warning(f"God Mode check failed: {e}")
            return None

    def _count_aligned_signals(self, tech: int, sent: int, chain: int) -> int:
        """Compte le nombre de signaux alignés dans la même direction"""
        signals = [tech, sent, chain]
        bullish = sum(1 for s in signals if s > 0)
        bearish = sum(1 for s in signals if s < 0)
        return max(bullish, bearish)

    def _determine_action(self, score: int, aligned: int,
                          tech: int, sent: int, chain: int) -> Tuple[TradeAction, int]:
        """
        Détermine l'action de trading

        LOGIQUE:
        - 3 signaux BUY (+3) = STRONG_BUY (90% confidence)
        - 2 signaux BUY (+2 ou +1) = BUY (70% confidence)
        - 3 signaux SELL (-3) = STRONG_SELL (90% confidence)
        - 2 signaux SELL (-2 ou -1) = SELL (70% confidence)
        - Sinon = HOLD
        """
        # STRONG_BUY: tous les signaux sont positifs
        if score >= 3 or (aligned >= 3 and score > 0):
            return TradeAction.STRONG_BUY, 90

        # STRONG_SELL: tous les signaux sont négatifs
        if score <= -3 or (aligned >= 3 and score < 0):
            return TradeAction.STRONG_SELL, 90

        # BUY: au moins 2 signaux positifs
        if aligned >= self.threshold and score > 0:
            confidence = 70 if aligned == 2 else 80
            return TradeAction.BUY, confidence

        # SELL: au moins 2 signaux négatifs
        if aligned >= self.threshold and score < 0:
            confidence = 70 if aligned == 2 else 80
            return TradeAction.SELL, confidence

        # HOLD: pas assez de confluence
        return TradeAction.HOLD, 50

    def _generate_reasoning(self, action: TradeAction,
                            tech: int, sent: int, chain: int,
                            tech_data: TechnicalSignal,
                            sent_data: SentimentSignal,
                            chain_data: OnChainSignal,
                            godmode: Optional[GodModeSignal] = None) -> str:
        """Génère une explication de la décision"""
        reasons = []

        # God Mode (si actif, c'est la priorité)
        if godmode and godmode.level in [GodModeLevel.ACTIVATED, GodModeLevel.EXTREME]:
            emoji = "🚨" if godmode.level == GodModeLevel.EXTREME else "🟢"
            reasons.append(f"{emoji} GOD MODE {godmode.level.name} ({godmode.conditions_met}/{godmode.total_conditions} conditions)")

        # Technical
        if tech > 0:
            reasons.append(f"Technical BULLISH (RSI: {tech_data.rsi:.1f}, Score: {tech_data.score})")
        elif tech < 0:
            reasons.append(f"Technical BEARISH (RSI: {tech_data.rsi:.1f}, Score: {tech_data.score})")
        else:
            reasons.append(f"Technical NEUTRAL (RSI: {tech_data.rsi:.1f})")

        # Sentiment
        if sent > 0:
            reasons.append(f"Sentiment BULLISH - Fear detected ({sent_data.fear_greed_index}) = Buy opportunity")
        elif sent < 0:
            reasons.append(f"Sentiment BEARISH - Greed detected ({sent_data.fear_greed_index}) = Sell signal")
        else:
            reasons.append(f"Sentiment NEUTRAL (F&G: {sent_data.fear_greed_index})")

        # On-Chain
        if chain > 0:
            reasons.append(f"On-Chain BULLISH - {chain_data.whale_activity}, {chain_data.exchange_flow}")
        elif chain < 0:
            reasons.append(f"On-Chain BEARISH - {chain_data.whale_activity}, {chain_data.exchange_flow}")
        else:
            reasons.append(f"On-Chain NEUTRAL")

        reasons.append(f"ACTION: {action.value}")

        return " | ".join(reasons)

    def _log_result(self, result: ConfluenceResult):
        """Log le résultat de l'analyse"""
        emoji_map = {
            TradeAction.STRONG_BUY: "🟢🟢",
            TradeAction.BUY: "🟢",
            TradeAction.HOLD: "⚪",
            TradeAction.SELL: "🔴",
            TradeAction.STRONG_SELL: "🔴🔴",
            TradeAction.GOD_MODE_BUY: "🚨🚨🚨"
        }

        emoji = emoji_map.get(result.action, "⚪")

        logger.info(f"{'='*50}")

        # God Mode alert
        if result.god_mode_active:
            logger.info(f"🚨 GOD MODE ACTIVE - Recommended allocation: {result.recommended_allocation}%")

        logger.confluence(f"{emoji} {result.action.value} | Confidence: {result.confidence}% | Aligned: {result.signals_aligned}/3")
        logger.info(f"Technical: {'+' if result.technical_signal > 0 else ''}{result.technical_signal} | "
                   f"Sentiment: {'+' if result.sentiment_signal > 0 else ''}{result.sentiment_signal} | "
                   f"OnChain: {'+' if result.onchain_signal > 0 else ''}{result.onchain_signal}")

        if result.god_mode and result.god_mode.level != GodModeLevel.INACTIVE:
            logger.info(f"God Mode: {result.god_mode.level.name} ({result.god_mode.score}/100)")

        logger.info(f"{'='*50}")


# Singleton
_engine = None

def get_confluence_engine() -> ConfluenceEngine:
    """Retourne l'instance singleton du moteur de confluence"""
    global _engine
    if _engine is None:
        _engine = ConfluenceEngine()
    return _engine
