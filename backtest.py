"""
Backtesting Module
==================

Teste la stratégie de confluence sur des données historiques.
"""
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict
from dataclasses import dataclass

from signals.technical import TechnicalAnalyzer
from config.settings import trading_config
from utils.logger import logger


@dataclass
class BacktestTrade:
    """Représente un trade dans le backtest"""
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    side: str
    pnl_percent: float
    pnl_usdt: float
    reason: str


@dataclass
class BacktestResult:
    """Résultats du backtest"""
    initial_capital: float
    final_capital: float
    total_return_percent: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    profit_factor: float
    trades: List[BacktestTrade]


class Backtester:
    """Backtester pour la stratégie de confluence"""

    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.technical = TechnicalAnalyzer()

    def run(self, df: pd.DataFrame, use_confluence: bool = True) -> BacktestResult:
        """
        Lance le backtest

        Args:
            df: DataFrame avec OHLCV data
            use_confluence: Si True, attend 2/3 signaux. Si False, trade sur technique seule.
        """
        logger.info(f"Starting backtest on {len(df)} candles...")

        capital = self.initial_capital
        position = None
        trades = []
        equity_curve = [capital]

        # Simuler les signaux de sentiment/onchain (random pour backtest)
        np.random.seed(42)
        sentiment_signals = np.random.choice([-1, 0, 1], size=len(df), p=[0.2, 0.6, 0.2])
        onchain_signals = np.random.choice([-1, 0, 1], size=len(df), p=[0.2, 0.6, 0.2])

        # Parcourir les données
        for i in range(50, len(df)):  # Commencer à 50 pour avoir assez de données
            current_data = df.iloc[:i+1]
            current_price = df.iloc[i]['close']
            current_date = df.index[i]

            # Analyse technique
            tech_result = self.technical.analyze(current_data)
            tech_signal = self.technical.get_signal_value(tech_result)

            # Signaux simulés
            sent_signal = sentiment_signals[i]
            chain_signal = onchain_signals[i]

            # Confluence
            total_signal = tech_signal + sent_signal + chain_signal
            signals_aligned = max(
                sum(1 for s in [tech_signal, sent_signal, chain_signal] if s > 0),
                sum(1 for s in [tech_signal, sent_signal, chain_signal] if s < 0)
            )

            # Décision
            if use_confluence:
                should_buy = signals_aligned >= 2 and total_signal > 0
                should_sell = signals_aligned >= 2 and total_signal < 0
            else:
                should_buy = tech_signal > 0
                should_sell = tech_signal < 0

            # Gérer la position
            if position is None and should_buy:
                # Ouvrir position
                position = {
                    'entry_date': current_date,
                    'entry_price': current_price,
                    'stop_loss': current_price * 0.98,  # -2%
                    'take_profit': current_price * 1.03,  # +3%
                }

            elif position is not None:
                # Vérifier stop loss / take profit
                if current_price <= position['stop_loss']:
                    # Stop loss hit
                    pnl_percent = (current_price - position['entry_price']) / position['entry_price'] * 100
                    pnl_usdt = capital * (pnl_percent / 100) * 0.1  # 10% du capital par trade

                    trade = BacktestTrade(
                        entry_date=position['entry_date'],
                        exit_date=current_date,
                        entry_price=position['entry_price'],
                        exit_price=current_price,
                        side='long',
                        pnl_percent=pnl_percent,
                        pnl_usdt=pnl_usdt,
                        reason='stop_loss'
                    )
                    trades.append(trade)
                    capital += pnl_usdt
                    position = None

                elif current_price >= position['take_profit']:
                    # Take profit hit
                    pnl_percent = (current_price - position['entry_price']) / position['entry_price'] * 100
                    pnl_usdt = capital * (pnl_percent / 100) * 0.1

                    trade = BacktestTrade(
                        entry_date=position['entry_date'],
                        exit_date=current_date,
                        entry_price=position['entry_price'],
                        exit_price=current_price,
                        side='long',
                        pnl_percent=pnl_percent,
                        pnl_usdt=pnl_usdt,
                        reason='take_profit'
                    )
                    trades.append(trade)
                    capital += pnl_usdt
                    position = None

                elif should_sell:
                    # Signal de vente
                    pnl_percent = (current_price - position['entry_price']) / position['entry_price'] * 100
                    pnl_usdt = capital * (pnl_percent / 100) * 0.1

                    trade = BacktestTrade(
                        entry_date=position['entry_date'],
                        exit_date=current_date,
                        entry_price=position['entry_price'],
                        exit_price=current_price,
                        side='long',
                        pnl_percent=pnl_percent,
                        pnl_usdt=pnl_usdt,
                        reason='signal'
                    )
                    trades.append(trade)
                    capital += pnl_usdt
                    position = None

            equity_curve.append(capital)

        # Calculer les métriques
        return self._calculate_metrics(trades, equity_curve)

    def _calculate_metrics(self, trades: List[BacktestTrade],
                           equity_curve: List[float]) -> BacktestResult:
        """Calcule les métriques de performance"""

        if not trades:
            return BacktestResult(
                initial_capital=self.initial_capital,
                final_capital=equity_curve[-1],
                total_return_percent=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0,
                max_drawdown=0,
                sharpe_ratio=0,
                profit_factor=0,
                trades=[]
            )

        winning = [t for t in trades if t.pnl_usdt > 0]
        losing = [t for t in trades if t.pnl_usdt <= 0]

        total_profit = sum(t.pnl_usdt for t in winning)
        total_loss = abs(sum(t.pnl_usdt for t in losing))

        # Max drawdown
        peak = equity_curve[0]
        max_dd = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio (simplifié)
        returns = pd.Series(equity_curve).pct_change().dropna()
        sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

        return BacktestResult(
            initial_capital=self.initial_capital,
            final_capital=equity_curve[-1],
            total_return_percent=(equity_curve[-1] - self.initial_capital) / self.initial_capital * 100,
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=len(winning) / len(trades) * 100 if trades else 0,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            profit_factor=total_profit / total_loss if total_loss > 0 else float('inf'),
            trades=trades
        )


def generate_historical_data(days: int = 365) -> pd.DataFrame:
    """Génère des données historiques simulées pour le backtest"""
    np.random.seed(42)

    dates = pd.date_range(end=datetime.now(), periods=days * 24, freq='H')

    # Simuler un marché avec tendances et corrections
    trend = np.zeros(len(dates))
    price = 30000  # Prix de départ

    for i in range(len(dates)):
        # Changement de tendance aléatoire
        if i % (24 * 30) == 0:  # Tous les mois
            trend[i:] = np.random.choice([-1, 0, 1], p=[0.3, 0.4, 0.3])

        # Mouvement de prix
        drift = trend[i] * 10  # Tendance
        volatility = np.random.randn() * 50  # Bruit
        price = max(price + drift + volatility, 1000)  # Min 1000
        trend[i] = price

    prices = trend

    # Créer OHLCV
    data = {
        'open': prices + np.random.randn(len(prices)) * 50,
        'high': prices + abs(np.random.randn(len(prices)) * 100),
        'low': prices - abs(np.random.randn(len(prices)) * 100),
        'close': prices,
        'volume': np.random.uniform(1000, 10000, len(prices))
    }

    df = pd.DataFrame(data, index=dates)
    df['high'] = df[['open', 'close', 'high']].max(axis=1)
    df['low'] = df[['open', 'close', 'low']].min(axis=1)

    return df


def print_results(result: BacktestResult, strategy_name: str):
    """Affiche les résultats du backtest"""
    print(f"\n{'=' * 50}")
    print(f"📊 BACKTEST RESULTS: {strategy_name}")
    print(f"{'=' * 50}")
    print(f"Initial Capital:    ${result.initial_capital:,.2f}")
    print(f"Final Capital:      ${result.final_capital:,.2f}")
    print(f"Total Return:       {result.total_return_percent:+.2f}%")
    print(f"")
    print(f"Total Trades:       {result.total_trades}")
    print(f"Winning Trades:     {result.winning_trades}")
    print(f"Losing Trades:      {result.losing_trades}")
    print(f"Win Rate:           {result.win_rate:.1f}%")
    print(f"")
    print(f"Max Drawdown:       {result.max_drawdown:.2f}%")
    print(f"Sharpe Ratio:       {result.sharpe_ratio:.2f}")
    print(f"Profit Factor:      {result.profit_factor:.2f}")
    print(f"{'=' * 50}")


async def main():
    """Run backtest comparison"""
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║              BACKTEST - CONFLUENCE vs TECHNICAL           ║
    ║                                                           ║
    ║     Compare la stratégie confluence (2/3 signaux)         ║
    ║     vs technique seule                                    ║
    ╚═══════════════════════════════════════════════════════════╝
    """)

    # Créer le dossier data
    import os
    os.makedirs('data', exist_ok=True)

    # Générer des données
    print("Generating 1 year of historical data...")
    df = generate_historical_data(365)
    print(f"Data range: {df.index[0]} to {df.index[-1]}")
    print(f"Price range: ${df['close'].min():,.0f} - ${df['close'].max():,.0f}")

    # Backtest avec confluence
    print("\nRunning backtest with CONFLUENCE strategy...")
    backtester = Backtester(initial_capital=10000)
    result_confluence = backtester.run(df, use_confluence=True)
    print_results(result_confluence, "CONFLUENCE (2/3 signals)")

    # Backtest technique seule
    print("\nRunning backtest with TECHNICAL ONLY strategy...")
    result_technical = backtester.run(df, use_confluence=False)
    print_results(result_technical, "TECHNICAL ONLY")

    # Comparaison
    print("\n" + "=" * 50)
    print("📈 COMPARISON")
    print("=" * 50)

    confluence_better = result_confluence.total_return_percent > result_technical.total_return_percent

    print(f"Confluence Return:  {result_confluence.total_return_percent:+.2f}%")
    print(f"Technical Return:   {result_technical.total_return_percent:+.2f}%")
    print(f"")
    print(f"Confluence Win Rate: {result_confluence.win_rate:.1f}%")
    print(f"Technical Win Rate:  {result_technical.win_rate:.1f}%")
    print(f"")
    print(f"Winner: {'CONFLUENCE' if confluence_better else 'TECHNICAL'} 🏆")


if __name__ == "__main__":
    asyncio.run(main())
