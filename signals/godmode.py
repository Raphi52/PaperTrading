"""
God Mode Detector - Détection des conditions de cycle bottom
============================================================

Détecte les moments RARES où toutes les conditions sont alignées
pour un potentiel x5-x10 sur 12-18 mois.

Ces conditions arrivent ~1-2 fois par cycle crypto (tous les 3-4 ans).
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from config.settings import sentiment_config, onchain_config
from utils.logger import logger


class GodModeLevel(Enum):
    """Niveaux de God Mode"""
    INACTIVE = 0        # Conditions normales
    WARMING_UP = 1      # 2-3 conditions réunies
    ACTIVATED = 2       # 4-5 conditions réunies
    EXTREME = 3         # 6+ conditions = CYCLE BOTTOM


@dataclass
class GodModeCondition:
    """Une condition du God Mode"""
    name: str
    description: str
    is_met: bool
    value: float
    threshold: float
    weight: int  # Importance de 1 à 3


@dataclass
class GodModeSignal:
    """Résultat du God Mode Detector"""
    level: GodModeLevel
    score: int  # 0-100
    conditions_met: int
    total_conditions: int
    conditions: List[GodModeCondition]
    recommended_allocation: float  # % du portfolio à investir
    recommended_assets: List[str]
    message: str
    timestamp: datetime


class GodModeDetector:
    """
    Détecteur de conditions exceptionnelles de marché

    QUAND UTILISER:
    - God Mode ACTIVATED → Augmenter exposition à 30-50%
    - God Mode EXTREME → All-in progressif sur 2-4 semaines

    ATTENTION:
    - Ces conditions sont RARES (1-2x par cycle)
    - Toujours DCA, jamais all-in en une fois
    - Timeframe: 12-18 mois pour les gains
    """

    def __init__(self):
        self._cache = {}
        self._cache_duration = 3600  # 1 heure (ces métriques changent lentement)

    async def detect(self, current_price: float, ath_price: float = None) -> GodModeSignal:
        """
        Détecte si les conditions God Mode sont réunies

        Args:
            current_price: Prix actuel du BTC
            ath_price: All-Time High du BTC (si None, fetch automatique)
        """
        logger.info("🔮 Running God Mode detection...")

        # Récupérer toutes les métriques en parallèle
        tasks = [
            self._check_fear_greed(),
            self._check_drawdown_from_ath(current_price, ath_price),
            self._check_rsi_weekly(),
            self._check_whale_accumulation(),
            self._check_exchange_reserves(),
            self._check_funding_rates(),
            self._check_mvrv_ratio(),
            self._check_puell_multiple(),
            self._check_pi_cycle(),
            self._check_200w_sma(current_price),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filtrer les erreurs
        conditions = [r for r in results if isinstance(r, GodModeCondition)]

        # Calculer le score
        conditions_met = sum(1 for c in conditions if c.is_met)
        weighted_score = sum(c.weight for c in conditions if c.is_met)
        max_weighted_score = sum(c.weight for c in conditions)

        score = int((weighted_score / max_weighted_score) * 100) if max_weighted_score > 0 else 0

        # Déterminer le niveau
        level = self._determine_level(conditions_met, score)

        # Recommandations
        allocation, assets, message = self._get_recommendations(level, score, conditions)

        signal = GodModeSignal(
            level=level,
            score=score,
            conditions_met=conditions_met,
            total_conditions=len(conditions),
            conditions=conditions,
            recommended_allocation=allocation,
            recommended_assets=assets,
            message=message,
            timestamp=datetime.now()
        )

        # Log le résultat
        self._log_signal(signal)

        return signal

    # ==================== CONDITIONS ====================

    async def _check_fear_greed(self) -> GodModeCondition:
        """Fear & Greed Index < 15 = Extreme Fear"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.alternative.me/fng/',
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        value = int(data['data'][0]['value'])

                        return GodModeCondition(
                            name="Fear & Greed Index",
                            description="Extreme Fear < 15",
                            is_met=value < 15,
                            value=value,
                            threshold=15,
                            weight=3  # Très important
                        )
        except Exception as e:
            logger.debug(f"Fear & Greed error: {e}")

        return GodModeCondition(
            name="Fear & Greed Index",
            description="Extreme Fear < 15",
            is_met=False,
            value=50,
            threshold=15,
            weight=3
        )

    async def _check_drawdown_from_ath(self, current_price: float,
                                        ath_price: float = None) -> GodModeCondition:
        """Drawdown > 60% depuis ATH"""
        if ath_price is None:
            # Fetch ATH depuis CoinGecko
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        'https://api.coingecko.com/api/v3/coins/bitcoin',
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            ath_price = data['market_data']['ath']['usd']
            except:
                ath_price = 73000  # Fallback ATH approximatif

        drawdown = ((ath_price - current_price) / ath_price) * 100

        return GodModeCondition(
            name="Drawdown from ATH",
            description="Prix -60% ou plus depuis ATH",
            is_met=drawdown >= 60,
            value=drawdown,
            threshold=60,
            weight=3
        )

    async def _check_rsi_weekly(self) -> GodModeCondition:
        """RSI Weekly < 30"""
        # Simulé - en production, calculer depuis les données weekly
        # Pour l'instant, utiliser une API ou calculer
        try:
            async with aiohttp.ClientSession() as session:
                # Utiliser TradingView ou autre source
                # Pour la démo, on simule
                value = 45  # Placeholder

                return GodModeCondition(
                    name="RSI Weekly",
                    description="RSI Weekly < 30 (oversold)",
                    is_met=value < 30,
                    value=value,
                    threshold=30,
                    weight=2
                )
        except:
            pass

        return GodModeCondition(
            name="RSI Weekly",
            description="RSI Weekly < 30",
            is_met=False,
            value=50,
            threshold=30,
            weight=2
        )

    async def _check_whale_accumulation(self) -> GodModeCondition:
        """Whales en accumulation forte"""
        try:
            # Glassnode ou alternative
            # Métrique: nombre de wallets > 1000 BTC en augmentation
            value = 50  # Placeholder (0-100, 100 = accumulation max)

            return GodModeCondition(
                name="Whale Accumulation",
                description="Whales accumulent massivement",
                is_met=value > 70,
                value=value,
                threshold=70,
                weight=3
            )
        except:
            pass

        return GodModeCondition(
            name="Whale Accumulation",
            description="Whales accumulent",
            is_met=False,
            value=50,
            threshold=70,
            weight=3
        )

    async def _check_exchange_reserves(self) -> GodModeCondition:
        """Réserves d'exchange en baisse = bullish"""
        try:
            # Les coins quittent les exchanges = moins de selling pressure
            value = 50  # Placeholder (% de baisse sur 30j)

            return GodModeCondition(
                name="Exchange Reserves",
                description="Réserves exchange en baisse >5%",
                is_met=value > 5,
                value=value,
                threshold=5,
                weight=2
            )
        except:
            pass

        return GodModeCondition(
            name="Exchange Reserves",
            description="Réserves en baisse",
            is_met=False,
            value=0,
            threshold=5,
            weight=2
        )

    async def _check_funding_rates(self) -> GodModeCondition:
        """Funding rates très négatifs = trop de shorts"""
        try:
            async with aiohttp.ClientSession() as session:
                # Binance funding rate
                async with session.get(
                    'https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1',
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data:
                            rate = float(data[0]['fundingRate']) * 100

                            return GodModeCondition(
                                name="Funding Rate",
                                description="Funding très négatif < -0.1%",
                                is_met=rate < -0.1,
                                value=rate,
                                threshold=-0.1,
                                weight=2
                            )
        except Exception as e:
            logger.debug(f"Funding rate error: {e}")

        return GodModeCondition(
            name="Funding Rate",
            description="Funding négatif",
            is_met=False,
            value=0,
            threshold=-0.1,
            weight=2
        )

    async def _check_mvrv_ratio(self) -> GodModeCondition:
        """MVRV Z-Score < 0 = undervalued"""
        try:
            # MVRV = Market Value / Realized Value
            # Z-Score < 0 = historiquement undervalued
            value = 0.5  # Placeholder

            return GodModeCondition(
                name="MVRV Z-Score",
                description="MVRV Z-Score < 0 (undervalued)",
                is_met=value < 0,
                value=value,
                threshold=0,
                weight=3
            )
        except:
            pass

        return GodModeCondition(
            name="MVRV Z-Score",
            description="MVRV < 0",
            is_met=False,
            value=0.5,
            threshold=0,
            weight=3
        )

    async def _check_puell_multiple(self) -> GodModeCondition:
        """Puell Multiple < 0.5 = miners en stress = bottom"""
        try:
            value = 0.8  # Placeholder

            return GodModeCondition(
                name="Puell Multiple",
                description="Puell Multiple < 0.5",
                is_met=value < 0.5,
                value=value,
                threshold=0.5,
                weight=2
            )
        except:
            pass

        return GodModeCondition(
            name="Puell Multiple",
            description="Puell < 0.5",
            is_met=False,
            value=0.8,
            threshold=0.5,
            weight=2
        )

    async def _check_pi_cycle(self) -> GodModeCondition:
        """Pi Cycle Bottom indicator"""
        try:
            # 111 DMA crosses under 350 DMA x 2 = bottom signal
            value = False  # Placeholder

            return GodModeCondition(
                name="Pi Cycle Bottom",
                description="Pi Cycle bottom signal",
                is_met=value,
                value=1 if value else 0,
                threshold=1,
                weight=2
            )
        except:
            pass

        return GodModeCondition(
            name="Pi Cycle Bottom",
            description="Pi Cycle signal",
            is_met=False,
            value=0,
            threshold=1,
            weight=2
        )

    async def _check_200w_sma(self, current_price: float) -> GodModeCondition:
        """Prix sous la 200 Week SMA = historiquement rare et bullish"""
        try:
            # 200 Week SMA approximatif pour BTC
            # En production: calculer depuis les données historiques
            sma_200w = 35000  # Placeholder approximatif

            below_sma = current_price < sma_200w
            percent_below = ((sma_200w - current_price) / sma_200w) * 100 if below_sma else 0

            return GodModeCondition(
                name="200 Week SMA",
                description="Prix sous 200W SMA",
                is_met=below_sma,
                value=percent_below,
                threshold=0,
                weight=3
            )
        except:
            pass

        return GodModeCondition(
            name="200 Week SMA",
            description="Sous 200W SMA",
            is_met=False,
            value=0,
            threshold=0,
            weight=3
        )

    # ==================== ANALYSIS ====================

    def _determine_level(self, conditions_met: int, score: int) -> GodModeLevel:
        """Détermine le niveau de God Mode"""
        if score >= 70 or conditions_met >= 7:
            return GodModeLevel.EXTREME
        elif score >= 50 or conditions_met >= 5:
            return GodModeLevel.ACTIVATED
        elif score >= 30 or conditions_met >= 3:
            return GodModeLevel.WARMING_UP
        else:
            return GodModeLevel.INACTIVE

    def _get_recommendations(self, level: GodModeLevel, score: int,
                            conditions: List[GodModeCondition]) -> Tuple[float, List[str], str]:
        """Génère les recommandations basées sur le niveau"""

        if level == GodModeLevel.EXTREME:
            return (
                50.0,  # 50% du portfolio
                ["BTC", "ETH", "SOL", "LINK"],
                "🚨 CYCLE BOTTOM DETECTED! Accumulation maximale recommandée. "
                "DCA sur 2-4 semaines. Ceci est RARE (1-2x par cycle)."
            )

        elif level == GodModeLevel.ACTIVATED:
            return (
                30.0,  # 30% du portfolio
                ["BTC", "ETH"],
                "🟢 GOD MODE ACTIVATED! Conditions très favorables. "
                "Augmenter l'exposition progressivement."
            )

        elif level == GodModeLevel.WARMING_UP:
            return (
                15.0,  # 15% du portfolio
                ["BTC"],
                "🟡 Conditions intéressantes. Surveiller de près. "
                "Commencer à accumuler BTC."
            )

        else:
            return (
                5.0,  # Position normale
                ["BTC"],
                "⚪ Conditions normales. Trading standard avec confluence."
            )

    def _log_signal(self, signal: GodModeSignal):
        """Log le signal God Mode"""
        level_emoji = {
            GodModeLevel.INACTIVE: "⚪",
            GodModeLevel.WARMING_UP: "🟡",
            GodModeLevel.ACTIVATED: "🟢",
            GodModeLevel.EXTREME: "🚨"
        }

        emoji = level_emoji.get(signal.level, "⚪")

        logger.info(f"\n{'='*60}")
        logger.info(f"{emoji} GOD MODE: {signal.level.name}")
        logger.info(f"{'='*60}")
        logger.info(f"Score: {signal.score}/100")
        logger.info(f"Conditions: {signal.conditions_met}/{signal.total_conditions}")
        logger.info(f"")

        for c in signal.conditions:
            status = "✅" if c.is_met else "❌"
            logger.info(f"  {status} {c.name}: {c.value:.2f} (threshold: {c.threshold})")

        logger.info(f"")
        logger.info(f"📊 Allocation recommandée: {signal.recommended_allocation}%")
        logger.info(f"🪙 Assets: {', '.join(signal.recommended_assets)}")
        logger.info(f"💬 {signal.message}")
        logger.info(f"{'='*60}\n")


# Fonction utilitaire
async def check_god_mode(current_price: float) -> GodModeSignal:
    """Vérifie rapidement le God Mode"""
    detector = GodModeDetector()
    return await detector.detect(current_price)
