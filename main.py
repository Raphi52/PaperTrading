"""
Multi-Signal Confluence Trading Bot
===================================

Un bot de trading qui combine 3 signaux indépendants:
1. Analyse Technique (RSI, MACD, Bollinger, EMA)
2. Analyse de Sentiment (Fear & Greed, Social Media)
3. Analyse On-Chain (Whale movements, Exchange flows)

Trade UNIQUEMENT quand 2/3 ou 3/3 signaux sont alignés.
"""
import asyncio
import signal
import sys
from datetime import datetime
from typing import Optional

from core.exchange import Exchange
from core.confluence import ConfluenceEngine, TradeAction
from core.risk_manager import RiskManager
from config.settings import trading_config
from utils.logger import logger


class TradingBot:
    """Bot de trading principal"""

    def __init__(self, symbol: str = None, testnet: bool = True):
        self.symbol = symbol or trading_config.symbol
        self.base_currency = self.symbol.split('/')[0]  # BTC
        self.quote_currency = self.symbol.split('/')[1]  # USDT

        # Composants
        self.exchange = Exchange(testnet=testnet)
        self.confluence = ConfluenceEngine()
        self.risk_manager = RiskManager()

        # État
        self.running = False
        self.last_analysis_time = None
        self.analysis_interval = 300  # 5 minutes

        logger.info(f"Trading Bot initialized")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Testnet: {testnet}")

    async def start(self):
        """Démarre le bot"""
        self.running = True
        logger.info("=" * 60)
        logger.info("🚀 TRADING BOT STARTED")
        logger.info("=" * 60)

        # Afficher le solde initial
        balance = self.exchange.get_balance()
        if balance:
            self.risk_manager.initial_capital = balance['total_usdt']
            self.risk_manager.current_capital = balance['total_usdt']
            logger.balance_update(balance['USDT']['free'], balance['BTC']['free'])

        # Boucle principale
        while self.running:
            try:
                await self._trading_cycle()
                await asyncio.sleep(self.analysis_interval)
            except Exception as e:
                logger.error(f"Error in trading cycle: {e}")
                await asyncio.sleep(60)

    async def stop(self):
        """Arrête le bot"""
        self.running = False
        logger.info("Bot stopping...")

        # Afficher les stats finales
        stats = self.risk_manager.get_stats()
        logger.info("=" * 60)
        logger.info("📊 FINAL STATISTICS")
        logger.info(f"Total trades: {stats['total_trades']}")
        logger.info(f"Win rate: {stats['win_rate']:.1f}%")
        logger.info(f"Total PnL: ${stats['total_pnl']:.2f}")
        logger.info("=" * 60)

    async def _trading_cycle(self):
        """Un cycle d'analyse et trading"""
        logger.info("-" * 40)
        logger.info(f"Analysis cycle at {datetime.now().strftime('%H:%M:%S')}")

        # 1. Récupérer les données OHLCV
        ohlcv = self.exchange.get_ohlcv(
            self.symbol,
            timeframe=trading_config.primary_timeframe,
            limit=200
        )

        if ohlcv.empty:
            logger.warning("No OHLCV data available")
            return

        current_price = self.exchange.get_price(self.symbol)
        logger.info(f"Current {self.symbol} price: ${current_price:,.2f}")

        # 2. Vérifier les positions ouvertes
        await self._check_positions(current_price)

        # 3. Analyse de confluence
        result = await self.confluence.analyze(ohlcv, self.base_currency)

        # 4. Exécuter les trades si nécessaire
        await self._execute_signal(result, current_price)

        self.last_analysis_time = datetime.now()

    async def _check_positions(self, current_price: float):
        """Vérifie et met à jour les positions ouvertes"""
        for symbol in list(self.risk_manager.positions.keys()):
            action = self.risk_manager.update_position(symbol, current_price)

            if action:
                # Fermer la position
                pos = self.risk_manager.positions[symbol]
                logger.info(f"Closing position: {action}")

                # Vendre
                result = self.exchange.create_market_sell(
                    symbol=self.symbol,
                    quantity=pos.quantity
                )

                if result['success']:
                    self.risk_manager.close_position(symbol, current_price, action)

    async def _execute_signal(self, confluence_result, current_price: float):
        """Exécute un signal de trading"""
        action = confluence_result.action
        confidence = confluence_result.confidence

        # HOLD = ne rien faire
        if action == TradeAction.HOLD:
            logger.info("Signal: HOLD - No action")
            return

        # 🚨 GOD MODE BUY - Accumulation maximale
        if action == TradeAction.GOD_MODE_BUY:
            await self._execute_god_mode_buy(confluence_result, current_price)

        # BUY signals
        elif action in [TradeAction.BUY, TradeAction.STRONG_BUY]:
            await self._execute_buy(current_price, confidence, action == TradeAction.STRONG_BUY)

        # SELL signals
        elif action in [TradeAction.SELL, TradeAction.STRONG_SELL]:
            await self._execute_sell(current_price, confidence)

    async def _execute_buy(self, price: float, confidence: int, is_strong: bool):
        """Exécute un ordre d'achat"""
        # Vérifier si on peut ouvrir une position
        balance = self.exchange.get_balance()
        can_trade, reason = self.risk_manager.can_open_position(self.symbol, balance['USDT']['free'])

        if not can_trade:
            logger.warning(f"Cannot open position: {reason}")
            return

        # Calculer le stop loss
        stop_loss_price = price * (1 - trading_config.stop_loss_percent / 100)

        # Calculer la taille de position
        position_size = self.risk_manager.calculate_position_size(
            capital=balance['USDT']['free'],
            entry_price=price,
            stop_loss_price=stop_loss_price,
            confidence=confidence
        )

        # Ajuster si STRONG_BUY
        if is_strong:
            position_size *= 1.5
            logger.info("STRONG BUY - Position size increased by 50%")

        # Exécuter l'achat
        logger.buy_signal(f"{self.symbol} @ ${price:,.2f} | Size: ${position_size:.2f}")

        result = self.exchange.create_market_buy(
            symbol=self.symbol,
            amount_usdt=position_size
        )

        if result['success']:
            # Enregistrer la position
            self.risk_manager.open_position(
                symbol=self.symbol,
                side='long',
                entry_price=result['price'],
                quantity=result['quantity']
            )
        else:
            logger.error(f"Buy order failed: {result.get('error')}")

    async def _execute_sell(self, price: float, confidence: int):
        """Exécute un ordre de vente (ferme les positions)"""
        if self.symbol not in self.risk_manager.positions:
            logger.info("No position to sell")
            return

        pos = self.risk_manager.positions[self.symbol]

        logger.sell_signal(f"{self.symbol} @ ${price:,.2f}")

        result = self.exchange.create_market_sell(
            symbol=self.symbol,
            quantity=pos.quantity
        )

        if result['success']:
            self.risk_manager.close_position(self.symbol, price, 'signal')
        else:
            logger.error(f"Sell order failed: {result.get('error')}")

    async def _execute_god_mode_buy(self, confluence_result, price: float):
        """
        🚨 Exécute un achat en mode GOD MODE

        C'est un moment RARE (1-2x par cycle crypto) où toutes les conditions
        sont alignées pour une accumulation maximale.

        Utilise le recommended_allocation du God Mode Detector.
        """
        god_mode = confluence_result.god_mode
        recommended_alloc = confluence_result.recommended_allocation  # % du portfolio

        logger.info("=" * 60)
        logger.info("🚨🚨🚨 GOD MODE BUY ACTIVATED 🚨🚨🚨")
        logger.info("=" * 60)

        if god_mode:
            logger.info(f"Level: {god_mode.level.name}")
            logger.info(f"Score: {god_mode.score}/100")
            logger.info(f"Conditions: {god_mode.conditions_met}/{god_mode.total_conditions}")
            logger.info(f"Recommended allocation: {recommended_alloc}%")
            logger.info(f"Assets: {', '.join(god_mode.recommended_assets)}")
            logger.info(f"Message: {god_mode.message}")

        # Vérifier le solde
        balance = self.exchange.get_balance()
        available_usdt = balance['USDT']['free']

        can_trade, reason = self.risk_manager.can_open_position(self.symbol, available_usdt)
        if not can_trade:
            logger.warning(f"Cannot open God Mode position: {reason}")
            return

        # Calculer la taille de position basée sur le recommended_allocation
        # Mais on fait du DCA progressif, donc on divise par 4 (sur 4 semaines)
        # pour ne pas all-in d'un coup
        dca_fraction = 0.25  # 25% de l'allocation recommandée maintenant
        position_size = available_usdt * (recommended_alloc / 100) * dca_fraction

        # Limiter à max 50% du capital disponible par trade
        max_position = available_usdt * 0.5
        position_size = min(position_size, max_position)

        logger.info(f"God Mode position size: ${position_size:.2f} (DCA 1/4)")
        logger.buy_signal(f"🚨 GOD MODE: {self.symbol} @ ${price:,.2f} | Size: ${position_size:.2f}")

        # Exécuter l'achat
        result = self.exchange.create_market_buy(
            symbol=self.symbol,
            amount_usdt=position_size
        )

        if result['success']:
            # Stop loss plus large pour God Mode (on attend le cycle complet)
            stop_loss_price = price * 0.70  # -30% stop loss (cycles peuvent être volatils)

            self.risk_manager.open_position(
                symbol=self.symbol,
                side='long',
                entry_price=result['price'],
                quantity=result['quantity']
            )

            logger.info("=" * 60)
            logger.info("✅ GOD MODE POSITION OPENED")
            logger.info(f"Entry: ${result['price']:,.2f}")
            logger.info(f"Quantity: {result['quantity']:.8f} {self.base_currency}")
            logger.info(f"Stop Loss: ${stop_loss_price:,.2f} (-30%)")
            logger.info("⚠️ Remember: DCA over 2-4 weeks, never all-in at once!")
            logger.info("=" * 60)
        else:
            logger.error(f"God Mode buy failed: {result.get('error')}")


async def main():
    """Point d'entrée principal"""
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║     MULTI-SIGNAL CONFLUENCE TRADING BOT                   ║
    ║                                                           ║
    ║     Technical + Sentiment + On-Chain = Smart Trading      ║
    ╚═══════════════════════════════════════════════════════════╝
    """)

    # Créer le bot
    bot = TradingBot(
        symbol="BTC/USDT",
        testnet=True  # IMPORTANT: Commencer en testnet!
    )

    # Gérer l'arrêt propre
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        asyncio.create_task(bot.stop())
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Démarrer le bot
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
