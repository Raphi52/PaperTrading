"""
Module d'analyse de sentiment - Signal 2/3
Analyse le sentiment du marché via Twitter, Reddit, Fear & Greed Index
"""
import requests
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum
from textblob import TextBlob
import re

from config.settings import sentiment_config
from utils.logger import logger


class SentimentLevel(Enum):
    EXTREME_FEAR = -2
    FEAR = -1
    NEUTRAL = 0
    GREED = 1
    EXTREME_GREED = 2


@dataclass
class SentimentSignal:
    """Résultat de l'analyse de sentiment"""
    signal: int  # -1, 0, +1
    score: int  # 0-100 (fear/greed)
    fear_greed_index: int
    social_score: int
    news_sentiment: float
    details: Dict


class SentimentAnalyzer:
    """Analyseur de sentiment multi-sources"""

    def __init__(self, config=None):
        self.config = config or sentiment_config
        self._cache = {}
        self._cache_duration = 300  # 5 minutes

    async def analyze(self, symbol: str = "BTC") -> SentimentSignal:
        """
        Analyse de sentiment complète

        Args:
            symbol: Symbole à analyser (BTC, ETH, etc.)

        Returns:
            SentimentSignal avec score global
        """
        # Récupérer toutes les sources en parallèle
        tasks = [
            self._get_fear_greed_index(),
            self._get_social_sentiment(symbol),
            self._get_lunarcrush_data(symbol),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        fear_greed = results[0] if not isinstance(results[0], Exception) else 50
        social_score = results[1] if not isinstance(results[1], Exception) else 50
        lunar_data = results[2] if not isinstance(results[2], Exception) else {}

        # Calculer le score global
        global_score = self._calculate_global_score(fear_greed, social_score, lunar_data)

        # Déterminer le signal
        signal = self._determine_signal(global_score, fear_greed)

        return SentimentSignal(
            signal=signal,
            score=global_score,
            fear_greed_index=fear_greed,
            social_score=social_score,
            news_sentiment=lunar_data.get('news_sentiment', 0),
            details={
                'fear_greed': fear_greed,
                'social': social_score,
                'lunar_galaxy_score': lunar_data.get('galaxy_score', 0),
                'lunar_social_volume': lunar_data.get('social_volume', 0),
                'timestamp': datetime.now().isoformat()
            }
        )

    async def _get_fear_greed_index(self) -> int:
        """
        Récupère le Fear & Greed Index (alternative.me)
        0 = Extreme Fear, 100 = Extreme Greed

        STRATÉGIE: Fear = BUY opportunity, Greed = SELL opportunity
        """
        cache_key = 'fear_greed'
        if self._is_cached(cache_key):
            return self._cache[cache_key]['value']

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.alternative.me/fng/',
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        value = int(data['data'][0]['value'])
                        self._set_cache(cache_key, value)
                        logger.debug(f"Fear & Greed Index: {value}")
                        return value

        except Exception as e:
            logger.warning(f"Failed to fetch Fear & Greed: {e}")

        return 50  # Default neutral

    async def _get_social_sentiment(self, symbol: str) -> int:
        """
        Analyse le sentiment social (simulation si pas de clés API)
        Retourne un score de 0-100
        """
        cache_key = f'social_{symbol}'
        if self._is_cached(cache_key):
            return self._cache[cache_key]['value']

        try:
            # Si on a les clés Twitter, utiliser l'API
            if self.config.twitter_bearer:
                score = await self._analyze_twitter(symbol)
            else:
                # Fallback: utiliser un endpoint gratuit ou score neutre
                score = await self._get_crypto_social_score(symbol)

            self._set_cache(cache_key, score)
            return score

        except Exception as e:
            logger.warning(f"Failed to get social sentiment: {e}")
            return 50

    async def _get_crypto_social_score(self, symbol: str) -> int:
        """Score social via API gratuite"""
        try:
            # CoinGecko a des données sociales gratuites
            async with aiohttp.ClientSession() as session:
                url = f'https://api.coingecko.com/api/v3/coins/{symbol.lower()}'
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Utiliser le sentiment score de CoinGecko
                        sentiment = data.get('sentiment_votes_up_percentage', 50)
                        return int(sentiment)
        except:
            pass
        return 50

    async def _analyze_twitter(self, symbol: str) -> int:
        """Analyse Twitter avec l'API officielle"""
        if not self.config.twitter_bearer:
            return 50

        try:
            headers = {'Authorization': f'Bearer {self.config.twitter_bearer}'}
            query = f'${symbol} OR #{symbol} -is:retweet lang:en'

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.twitter.com/2/tweets/search/recent',
                    headers=headers,
                    params={'query': query, 'max_results': 100},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        tweets = data.get('data', [])
                        return self._analyze_text_sentiment(tweets)

        except Exception as e:
            logger.warning(f"Twitter API error: {e}")

        return 50

    async def _get_lunarcrush_data(self, symbol: str) -> Dict:
        """Récupère les données LunarCrush (si clé disponible)"""
        if not self.config.lunarcrush_key:
            return {}

        cache_key = f'lunar_{symbol}'
        if self._is_cached(cache_key):
            return self._cache[cache_key]['value']

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'https://lunarcrush.com/api4/public/coins/{symbol}/v1',
                    headers={'Authorization': f'Bearer {self.config.lunarcrush_key}'},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = {
                            'galaxy_score': data.get('galaxy_score', 0),
                            'social_volume': data.get('social_volume', 0),
                            'social_score': data.get('social_score', 0),
                            'news_sentiment': data.get('news_sentiment', 0),
                        }
                        self._set_cache(cache_key, result)
                        return result

        except Exception as e:
            logger.warning(f"LunarCrush API error: {e}")

        return {}

    def _analyze_text_sentiment(self, texts: List) -> int:
        """
        Analyse le sentiment d'une liste de textes
        Retourne un score de 0-100
        """
        if not texts:
            return 50

        sentiments = []
        for item in texts:
            text = item.get('text', '') if isinstance(item, dict) else str(item)
            # Nettoyer le texte
            text = self._clean_text(text)

            # Analyse avec TextBlob
            blob = TextBlob(text)
            sentiments.append(blob.sentiment.polarity)

            # Bonus pour mots-clés bullish/bearish
            text_lower = text.lower()
            for keyword in self.config.bullish_keywords:
                if keyword in text_lower:
                    sentiments.append(0.3)
            for keyword in self.config.bearish_keywords:
                if keyword in text_lower:
                    sentiments.append(-0.3)

        if not sentiments:
            return 50

        # Moyenne des sentiments (-1 à +1) convertie en 0-100
        avg_sentiment = sum(sentiments) / len(sentiments)
        score = int((avg_sentiment + 1) * 50)  # -1 -> 0, +1 -> 100
        return max(0, min(100, score))

    def _clean_text(self, text: str) -> str:
        """Nettoie le texte pour l'analyse"""
        # Supprimer URLs
        text = re.sub(r'http\S+', '', text)
        # Supprimer mentions
        text = re.sub(r'@\w+', '', text)
        # Supprimer caractères spéciaux excessifs
        text = re.sub(r'[^\w\s#$]', ' ', text)
        return text.strip()

    def _calculate_global_score(self, fear_greed: int, social: int, lunar: Dict) -> int:
        """
        Calcule un score global de sentiment (0-100)

        Pondération:
        - Fear & Greed Index: 40%
        - Social Sentiment: 30%
        - LunarCrush: 30%
        """
        lunar_score = lunar.get('social_score', social) or social

        weighted = (
            fear_greed * 0.4 +
            social * 0.3 +
            lunar_score * 0.3
        )

        return int(weighted)

    def _determine_signal(self, score: int, fear_greed: int) -> int:
        """
        Détermine le signal de trading basé sur le sentiment

        LOGIQUE CONTRARIAN:
        - Extreme Fear (< 25) = BUY signal (+1)
        - Extreme Greed (> 75) = SELL signal (-1)
        - Neutral = 0
        """
        # Utiliser principalement le Fear & Greed pour le signal
        if fear_greed < self.config.fear_greed_bullish:
            logger.debug(f"Extreme Fear detected ({fear_greed}) -> BUY signal")
            return 1  # BUY when others are fearful
        elif fear_greed > self.config.fear_greed_bearish:
            logger.debug(f"Extreme Greed detected ({fear_greed}) -> SELL signal")
            return -1  # SELL when others are greedy
        else:
            return 0

    def _is_cached(self, key: str) -> bool:
        """Vérifie si une valeur est en cache et valide"""
        if key not in self._cache:
            return False
        cache_time = self._cache[key]['time']
        return (datetime.now() - cache_time).seconds < self._cache_duration

    def _set_cache(self, key: str, value):
        """Met une valeur en cache"""
        self._cache[key] = {
            'value': value,
            'time': datetime.now()
        }


# Pour utilisation synchrone
def analyze_sentiment_sync(symbol: str = "BTC") -> SentimentSignal:
    """Wrapper synchrone pour l'analyse de sentiment"""
    analyzer = SentimentAnalyzer()
    return asyncio.run(analyzer.analyze(symbol))
