"""
Module de connexion aux exchanges via CCXT
"""
import ccxt
import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import asyncio

from config.settings import exchange_config, trading_config
from utils.logger import logger


class Exchange:
    """Gestionnaire de connexion exchange"""

    def __init__(self, name: str = None, testnet: bool = None):
        self.name = name or exchange_config.name
        self.testnet = testnet if testnet is not None else exchange_config.testnet

        # Configuration exchange
        exchange_class = getattr(ccxt, self.name)
        self.exchange = exchange_class({
            'apiKey': exchange_config.api_key,
            'secret': exchange_config.secret,
            'sandbox': self.testnet,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })

        # Cache
        self._balance_cache = None
        self._balance_cache_time = None
        self._cache_duration = 5  # seconds

        logger.info(f"Exchange initialized: {self.name} (testnet={self.testnet})")

    # ==================== Market Data ====================

    def get_ticker(self, symbol: str = None) -> Dict:
        """Récupère le ticker actuel"""
        symbol = symbol or trading_config.symbol
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'symbol': symbol,
                'price': ticker['last'],
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'volume': ticker['baseVolume'],
                'change_24h': ticker.get('percentage', 0),
                'high_24h': ticker['high'],
                'low_24h': ticker['low'],
                'timestamp': datetime.now()
            }
        except Exception as e:
            logger.error(f"Error fetching ticker: {e}")
            return None

    def get_price(self, symbol: str = None) -> float:
        """Récupère le prix actuel"""
        ticker = self.get_ticker(symbol)
        return ticker['price'] if ticker else 0

    def get_ohlcv(self, symbol: str = None, timeframe: str = '1h',
                   limit: int = 500, since: int = None) -> pd.DataFrame:
        """
        Récupère les données OHLCV (candlesticks)

        Returns:
            DataFrame avec colonnes: timestamp, open, high, low, close, volume
        """
        symbol = symbol or trading_config.symbol
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            return df

        except Exception as e:
            logger.error(f"Error fetching OHLCV: {e}")
            return pd.DataFrame()

    def get_orderbook(self, symbol: str = None, limit: int = 20) -> Dict:
        """Récupère le carnet d'ordres"""
        symbol = symbol or trading_config.symbol
        try:
            orderbook = self.exchange.fetch_order_book(symbol, limit)
            return {
                'bids': orderbook['bids'][:limit],
                'asks': orderbook['asks'][:limit],
                'spread': orderbook['asks'][0][0] - orderbook['bids'][0][0] if orderbook['bids'] and orderbook['asks'] else 0
            }
        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return None

    # ==================== Account ====================

    def get_balance(self, force_refresh: bool = False) -> Dict:
        """Récupère le solde du compte (avec cache)"""
        now = datetime.now()

        if not force_refresh and self._balance_cache and self._balance_cache_time:
            if (now - self._balance_cache_time).seconds < self._cache_duration:
                return self._balance_cache

        try:
            balance = self.exchange.fetch_balance()

            self._balance_cache = {
                'USDT': {
                    'free': balance['USDT']['free'] if 'USDT' in balance else 0,
                    'used': balance['USDT']['used'] if 'USDT' in balance else 0,
                    'total': balance['USDT']['total'] if 'USDT' in balance else 0,
                },
                'BTC': {
                    'free': balance['BTC']['free'] if 'BTC' in balance else 0,
                    'used': balance['BTC']['used'] if 'BTC' in balance else 0,
                    'total': balance['BTC']['total'] if 'BTC' in balance else 0,
                },
                'total_usdt': self._calculate_total_in_usdt(balance)
            }
            self._balance_cache_time = now

            return self._balance_cache

        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return None

    def _calculate_total_in_usdt(self, balance: Dict) -> float:
        """Calcule la valeur totale en USDT"""
        total = 0

        # USDT direct
        if 'USDT' in balance:
            total += balance['USDT']['total']

        # BTC converti
        if 'BTC' in balance and balance['BTC']['total'] > 0:
            btc_price = self.get_price('BTC/USDT')
            total += balance['BTC']['total'] * btc_price

        return total

    # ==================== Trading ====================

    def create_market_buy(self, symbol: str = None, amount_usdt: float = None) -> Dict:
        """
        Crée un ordre d'achat market

        Args:
            symbol: Paire de trading (ex: BTC/USDT)
            amount_usdt: Montant en USDT à dépenser
        """
        symbol = symbol or trading_config.symbol
        amount_usdt = amount_usdt or trading_config.trade_amount_usdt

        try:
            # Calculer la quantité
            price = self.get_price(symbol)
            quantity = amount_usdt / price

            # Arrondir selon les règles de l'exchange
            market = self.exchange.market(symbol)
            quantity = self.exchange.amount_to_precision(symbol, quantity)

            logger.info(f"Creating market buy: {quantity} {symbol} (~${amount_usdt})")

            order = self.exchange.create_market_buy_order(symbol, float(quantity))

            logger.trade_executed('BUY', symbol, float(quantity), price)

            return {
                'success': True,
                'order_id': order['id'],
                'symbol': symbol,
                'side': 'buy',
                'quantity': float(quantity),
                'price': price,
                'cost': amount_usdt,
                'timestamp': datetime.now()
            }

        except Exception as e:
            logger.error(f"Error creating buy order: {e}")
            return {'success': False, 'error': str(e)}

    def create_market_sell(self, symbol: str = None, quantity: float = None,
                           sell_percent: float = 100) -> Dict:
        """
        Crée un ordre de vente market

        Args:
            symbol: Paire de trading
            quantity: Quantité à vendre (si None, vend un pourcentage du solde)
            sell_percent: Pourcentage du solde à vendre si quantity est None
        """
        symbol = symbol or trading_config.symbol
        base_currency = symbol.split('/')[0]

        try:
            if quantity is None:
                balance = self.get_balance(force_refresh=True)
                if base_currency in balance:
                    quantity = balance[base_currency]['free'] * (sell_percent / 100)
                else:
                    logger.error(f"No {base_currency} balance to sell")
                    return {'success': False, 'error': 'No balance'}

            quantity = self.exchange.amount_to_precision(symbol, quantity)
            price = self.get_price(symbol)

            logger.info(f"Creating market sell: {quantity} {symbol}")

            order = self.exchange.create_market_sell_order(symbol, float(quantity))

            logger.trade_executed('SELL', symbol, float(quantity), price)

            return {
                'success': True,
                'order_id': order['id'],
                'symbol': symbol,
                'side': 'sell',
                'quantity': float(quantity),
                'price': price,
                'revenue': float(quantity) * price,
                'timestamp': datetime.now()
            }

        except Exception as e:
            logger.error(f"Error creating sell order: {e}")
            return {'success': False, 'error': str(e)}

    def create_limit_buy(self, symbol: str, quantity: float, price: float) -> Dict:
        """Crée un ordre d'achat limit"""
        try:
            order = self.exchange.create_limit_buy_order(symbol, quantity, price)
            logger.info(f"Limit buy created: {quantity} {symbol} @ ${price}")
            return {'success': True, 'order': order}
        except Exception as e:
            logger.error(f"Error creating limit buy: {e}")
            return {'success': False, 'error': str(e)}

    def create_limit_sell(self, symbol: str, quantity: float, price: float) -> Dict:
        """Crée un ordre de vente limit"""
        try:
            order = self.exchange.create_limit_sell_order(symbol, quantity, price)
            logger.info(f"Limit sell created: {quantity} {symbol} @ ${price}")
            return {'success': True, 'order': order}
        except Exception as e:
            logger.error(f"Error creating limit sell: {e}")
            return {'success': False, 'error': str(e)}

    def cancel_order(self, order_id: str, symbol: str = None) -> bool:
        """Annule un ordre"""
        symbol = symbol or trading_config.symbol
        try:
            self.exchange.cancel_order(order_id, symbol)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """Récupère les ordres ouverts"""
        symbol = symbol or trading_config.symbol
        try:
            return self.exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return []

    # ==================== Helpers ====================

    def get_min_order_size(self, symbol: str = None) -> float:
        """Récupère la taille minimum d'ordre"""
        symbol = symbol or trading_config.symbol
        try:
            market = self.exchange.market(symbol)
            return market['limits']['amount']['min']
        except:
            return 0.0001  # Default for BTC

    def is_tradeable(self, symbol: str = None) -> bool:
        """Vérifie si la paire est tradeable"""
        symbol = symbol or trading_config.symbol
        try:
            market = self.exchange.market(symbol)
            return market['active']
        except:
            return False
