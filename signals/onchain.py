"""
Module d'analyse On-Chain - Signal 3/3
Analyse les métriques blockchain: whale movements, exchange flows, etc.
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass

from config.settings import onchain_config
from utils.logger import logger


@dataclass
class OnChainSignal:
    """Résultat de l'analyse on-chain"""
    signal: int  # -1, 0, +1
    score: int  # 0-100
    whale_activity: str  # 'accumulating', 'distributing', 'neutral'
    exchange_flow: str  # 'inflow', 'outflow', 'neutral'
    details: Dict


class OnChainAnalyzer:
    """Analyseur de métriques on-chain"""

    def __init__(self, config=None):
        self.config = config or onchain_config
        self._cache = {}
        self._cache_duration = 600  # 10 minutes

    async def analyze(self, symbol: str = "BTC") -> OnChainSignal:
        """
        Analyse on-chain complète

        Métriques analysées:
        1. Whale wallet movements
        2. Exchange inflow/outflow
        3. Active addresses
        4. Network hash rate (for BTC)
        """
        tasks = [
            self._get_whale_activity(symbol),
            self._get_exchange_flow(symbol),
            self._get_network_metrics(symbol),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        whale_data = results[0] if not isinstance(results[0], Exception) else {}
        exchange_data = results[1] if not isinstance(results[1], Exception) else {}
        network_data = results[2] if not isinstance(results[2], Exception) else {}

        # Analyser les données
        whale_signal = self._analyze_whale_activity(whale_data)
        exchange_signal = self._analyze_exchange_flow(exchange_data)
        network_signal = self._analyze_network(network_data)

        # Calculer le signal global
        signals = [whale_signal, exchange_signal, network_signal]
        final_signal = self._calculate_final_signal(signals)
        score = self._calculate_score(signals)

        return OnChainSignal(
            signal=final_signal,
            score=score,
            whale_activity=whale_data.get('trend', 'neutral'),
            exchange_flow=exchange_data.get('trend', 'neutral'),
            details={
                'whale': whale_data,
                'exchange': exchange_data,
                'network': network_data,
                'timestamp': datetime.now().isoformat()
            }
        )

    async def _get_whale_activity(self, symbol: str) -> Dict:
        """
        Récupère l'activité des whales

        Sources:
        - Glassnode (payant)
        - Whale Alert API (gratuit limité)
        - Blockchain.com API (gratuit)
        """
        cache_key = f'whale_{symbol}'
        if self._is_cached(cache_key):
            return self._cache[cache_key]['value']

        result = {
            'large_txs_24h': 0,
            'accumulation_score': 50,
            'trend': 'neutral'
        }

        # Essayer Glassnode si clé disponible
        if self.config.glassnode_key:
            glassnode_data = await self._fetch_glassnode_whale_data(symbol)
            if glassnode_data:
                result.update(glassnode_data)
                self._set_cache(cache_key, result)
                return result

        # Fallback: Blockchain.com pour BTC
        if symbol.upper() == 'BTC':
            blockchain_data = await self._fetch_blockchain_whale_data()
            if blockchain_data:
                result.update(blockchain_data)

        self._set_cache(cache_key, result)
        return result

    async def _fetch_glassnode_whale_data(self, symbol: str) -> Optional[Dict]:
        """Fetch whale data from Glassnode"""
        try:
            async with aiohttp.ClientSession() as session:
                # Whale entity count
                url = f'https://api.glassnode.com/v1/metrics/entities/whale_count'
                params = {
                    'a': symbol.upper(),
                    'api_key': self.config.glassnode_key,
                    'i': '24h'
                }
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data:
                            latest = data[-1]
                            prev = data[-2] if len(data) > 1 else latest

                            change = (latest['v'] - prev['v']) / prev['v'] * 100 if prev['v'] > 0 else 0

                            return {
                                'whale_count': latest['v'],
                                'whale_change_24h': change,
                                'trend': 'accumulating' if change > 1 else ('distributing' if change < -1 else 'neutral'),
                                'accumulation_score': 50 + int(change * 10)
                            }
        except Exception as e:
            logger.debug(f"Glassnode whale data error: {e}")
        return None

    async def _fetch_blockchain_whale_data(self) -> Optional[Dict]:
        """Fetch BTC whale data from Blockchain.com (gratuit)"""
        try:
            async with aiohttp.ClientSession() as session:
                # Large transactions (> 100 BTC)
                url = 'https://blockchain.info/q/24hrbtcsent'
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        btc_sent = int(await response.text()) / 100000000  # Satoshi to BTC

                        # Estimation basée sur le volume
                        if btc_sent > 500000:  # High volume
                            return {
                                'btc_sent_24h': btc_sent,
                                'trend': 'high_activity',
                                'accumulation_score': 50  # Neutral car on sait pas la direction
                            }
        except Exception as e:
            logger.debug(f"Blockchain.com error: {e}")
        return None

    async def _get_exchange_flow(self, symbol: str) -> Dict:
        """
        Récupère les flux entrants/sortants des exchanges

        LOGIQUE:
        - Inflow (vers exchanges) = intention de vendre = BEARISH
        - Outflow (hors exchanges) = intention de hold = BULLISH
        """
        cache_key = f'exchange_flow_{symbol}'
        if self._is_cached(cache_key):
            return self._cache[cache_key]['value']

        result = {
            'net_flow': 0,
            'inflow': 0,
            'outflow': 0,
            'trend': 'neutral'
        }

        if self.config.glassnode_key:
            flow_data = await self._fetch_glassnode_exchange_flow(symbol)
            if flow_data:
                result.update(flow_data)

        self._set_cache(cache_key, result)
        return result

    async def _fetch_glassnode_exchange_flow(self, symbol: str) -> Optional[Dict]:
        """Fetch exchange flow from Glassnode"""
        try:
            async with aiohttp.ClientSession() as session:
                url = 'https://api.glassnode.com/v1/metrics/transactions/transfers_to_exchanges_count'
                params = {
                    'a': symbol.upper(),
                    'api_key': self.config.glassnode_key,
                    'i': '24h'
                }

                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data and len(data) >= 7:
                            # Comparer les dernières 24h à la moyenne 7 jours
                            latest = data[-1]['v']
                            avg_7d = sum(d['v'] for d in data[-7:]) / 7

                            ratio = latest / avg_7d if avg_7d > 0 else 1

                            if ratio > self.config.exchange_inflow_bearish:
                                trend = 'inflow'
                            elif ratio < (1 / self.config.exchange_outflow_bullish):
                                trend = 'outflow'
                            else:
                                trend = 'neutral'

                            return {
                                'inflow_count': latest,
                                'inflow_avg_7d': avg_7d,
                                'ratio': ratio,
                                'trend': trend
                            }
        except Exception as e:
            logger.debug(f"Glassnode exchange flow error: {e}")
        return None

    async def _get_network_metrics(self, symbol: str) -> Dict:
        """Récupère les métriques réseau (hash rate, difficulty, etc.)"""
        cache_key = f'network_{symbol}'
        if self._is_cached(cache_key):
            return self._cache[cache_key]['value']

        result = {
            'hash_rate_trend': 'neutral',
            'active_addresses_trend': 'neutral'
        }

        if symbol.upper() == 'BTC':
            # Utiliser Blockchain.com gratuit pour BTC
            try:
                async with aiohttp.ClientSession() as session:
                    url = 'https://blockchain.info/q/hashrate'
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            hash_rate = float(await response.text())
                            result['hash_rate'] = hash_rate
                            result['hash_rate_trend'] = 'healthy'  # Simplified
            except:
                pass

        self._set_cache(cache_key, result)
        return result

    def _analyze_whale_activity(self, data: Dict) -> int:
        """
        Analyse l'activité whale et retourne un signal

        LOGIQUE:
        - Whales accumulent = +1 (BUY)
        - Whales distribuent = -1 (SELL)
        - Neutral = 0
        """
        trend = data.get('trend', 'neutral')
        score = data.get('accumulation_score', 50)

        if trend == 'accumulating' or score > 60:
            return 1
        elif trend == 'distributing' or score < 40:
            return -1
        return 0

    def _analyze_exchange_flow(self, data: Dict) -> int:
        """
        Analyse les flux exchange

        LOGIQUE:
        - Outflow (sortie des exchanges) = +1 (BULLISH - holders)
        - Inflow (entrée dans exchanges) = -1 (BEARISH - sellers)
        """
        trend = data.get('trend', 'neutral')

        if trend == 'outflow':
            return 1  # Bullish
        elif trend == 'inflow':
            return -1  # Bearish
        return 0

    def _analyze_network(self, data: Dict) -> int:
        """Analyse les métriques réseau"""
        hash_trend = data.get('hash_rate_trend', 'neutral')
        addr_trend = data.get('active_addresses_trend', 'neutral')

        # Hash rate en hausse = réseau sain = légèrement bullish
        if hash_trend == 'healthy' or hash_trend == 'increasing':
            return 1
        elif hash_trend == 'decreasing':
            return -1
        return 0

    def _calculate_final_signal(self, signals: List[int]) -> int:
        """
        Calcule le signal final

        Majorité simple: 2/3 signaux dans une direction = signal
        """
        total = sum(signals)

        if total >= 2:
            return 1  # BUY
        elif total <= -2:
            return -1  # SELL
        return 0

    def _calculate_score(self, signals: List[int]) -> int:
        """Calcule un score de 0-100"""
        # Convertir de [-3, +3] à [0, 100]
        total = sum(signals)
        return int(((total + 3) / 6) * 100)

    def _is_cached(self, key: str) -> bool:
        if key not in self._cache:
            return False
        cache_time = self._cache[key]['time']
        return (datetime.now() - cache_time).seconds < self._cache_duration

    def _set_cache(self, key: str, value):
        self._cache[key] = {
            'value': value,
            'time': datetime.now()
        }


# Wrapper synchrone
def analyze_onchain_sync(symbol: str = "BTC") -> OnChainSignal:
    """Wrapper synchrone pour l'analyse on-chain"""
    analyzer = OnChainAnalyzer()
    return asyncio.run(analyzer.analyze(symbol))
