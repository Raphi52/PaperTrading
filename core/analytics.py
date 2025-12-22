"""
Advanced Analytics Module
==========================

Calculates professional trading metrics:
- Sharpe Ratio
- Sortino Ratio
- Max Drawdown
- Win Rate & Profit Factor
- Calmar Ratio
- Risk-adjusted returns
- Strategy rankings
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import json


@dataclass
class PerformanceMetrics:
    """Complete performance metrics for a portfolio"""
    # Basic stats
    total_pnl: float = 0
    total_pnl_pct: float = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    # Win/Loss metrics
    win_rate: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    profit_factor: float = 0
    expectancy: float = 0

    # Risk metrics
    max_drawdown: float = 0
    max_drawdown_pct: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0

    # Streaks
    current_streak: int = 0
    max_win_streak: int = 0
    max_loss_streak: int = 0

    # Time-based
    avg_hold_time_hours: float = 0
    best_day_pnl: float = 0
    worst_day_pnl: float = 0

    # Risk-adjusted
    risk_reward_ratio: float = 0
    volatility: float = 0

    def to_dict(self) -> dict:
        return {
            'total_pnl': self.total_pnl,
            'total_pnl_pct': self.total_pnl_pct,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.win_rate,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'profit_factor': self.profit_factor,
            'expectancy': self.expectancy,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': self.max_drawdown_pct,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'current_streak': self.current_streak,
            'max_win_streak': self.max_win_streak,
            'max_loss_streak': self.max_loss_streak,
            'risk_reward_ratio': self.risk_reward_ratio,
            'volatility': self.volatility
        }


class PortfolioAnalytics:
    """Calculates advanced analytics for a portfolio"""

    def __init__(self, portfolio: dict):
        self.portfolio = portfolio
        self.trades = portfolio.get('trades', [])
        self.initial_capital = portfolio.get('initial_capital', 10000)

    def calculate_all_metrics(self) -> PerformanceMetrics:
        """Calculate all performance metrics"""
        metrics = PerformanceMetrics()

        if not self.trades:
            return metrics

        # Extract PnL from trades
        pnls = []
        wins = []
        losses = []
        hold_times = []

        for trade in self.trades:
            pnl = trade.get('pnl', 0)
            if trade.get('action') == 'SELL' or 'SELL' in trade.get('action', ''):
                pnls.append(pnl)
                if pnl > 0:
                    wins.append(pnl)
                elif pnl < 0:
                    losses.append(pnl)

        # Basic counts
        metrics.total_trades = len(pnls)
        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)

        if metrics.total_trades == 0:
            return metrics

        # Total PnL
        metrics.total_pnl = sum(pnls)
        metrics.total_pnl_pct = (metrics.total_pnl / self.initial_capital) * 100

        # Win rate
        metrics.win_rate = (metrics.winning_trades / metrics.total_trades) * 100

        # Average win/loss
        metrics.avg_win = np.mean(wins) if wins else 0
        metrics.avg_loss = np.mean(losses) if losses else 0

        # Profit factor
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0
        metrics.profit_factor = total_wins / total_losses if total_losses > 0 else float('inf') if total_wins > 0 else 0

        # Expectancy (average expected profit per trade)
        metrics.expectancy = np.mean(pnls) if pnls else 0

        # Risk/Reward ratio
        if metrics.avg_loss != 0:
            metrics.risk_reward_ratio = abs(metrics.avg_win / metrics.avg_loss)

        # Volatility (std of returns)
        if len(pnls) > 1:
            returns = [p / self.initial_capital for p in pnls]
            metrics.volatility = np.std(returns) * 100

        # Max Drawdown
        metrics.max_drawdown, metrics.max_drawdown_pct = self._calculate_max_drawdown(pnls)

        # Sharpe Ratio (assuming risk-free rate of 0 for simplicity)
        metrics.sharpe_ratio = self._calculate_sharpe_ratio(pnls)

        # Sortino Ratio
        metrics.sortino_ratio = self._calculate_sortino_ratio(pnls)

        # Calmar Ratio
        if metrics.max_drawdown_pct > 0:
            annualized_return = metrics.total_pnl_pct * (365 / max(self._get_trading_days(), 1))
            metrics.calmar_ratio = annualized_return / metrics.max_drawdown_pct

        # Streaks
        metrics.current_streak, metrics.max_win_streak, metrics.max_loss_streak = self._calculate_streaks(pnls)

        # Daily PnL
        daily_pnls = self._get_daily_pnls()
        if daily_pnls:
            metrics.best_day_pnl = max(daily_pnls)
            metrics.worst_day_pnl = min(daily_pnls)

        return metrics

    def _calculate_max_drawdown(self, pnls: List[float]) -> Tuple[float, float]:
        """Calculate maximum drawdown"""
        if not pnls:
            return 0, 0

        cumulative = np.cumsum(pnls)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = running_max - cumulative

        max_dd = np.max(drawdowns) if len(drawdowns) > 0 else 0
        max_dd_pct = (max_dd / self.initial_capital) * 100 if self.initial_capital > 0 else 0

        return max_dd, max_dd_pct

    def _calculate_sharpe_ratio(self, pnls: List[float], risk_free_rate: float = 0) -> float:
        """Calculate Sharpe ratio (annualized)"""
        if len(pnls) < 2:
            return 0

        returns = [p / self.initial_capital for p in pnls]
        excess_returns = np.array(returns) - risk_free_rate

        if np.std(excess_returns) == 0:
            return 0

        # Annualize (assuming ~252 trading days)
        sharpe = np.mean(excess_returns) / np.std(excess_returns)
        annualized_sharpe = sharpe * np.sqrt(252 / max(len(pnls), 1))

        return annualized_sharpe

    def _calculate_sortino_ratio(self, pnls: List[float], risk_free_rate: float = 0) -> float:
        """Calculate Sortino ratio (only penalizes downside volatility)"""
        if len(pnls) < 2:
            return 0

        returns = [p / self.initial_capital for p in pnls]
        excess_returns = np.array(returns) - risk_free_rate

        # Only negative returns for downside deviation
        negative_returns = excess_returns[excess_returns < 0]
        if len(negative_returns) == 0:
            return float('inf') if np.mean(excess_returns) > 0 else 0

        downside_std = np.std(negative_returns)
        if downside_std == 0:
            return 0

        sortino = np.mean(excess_returns) / downside_std
        return sortino * np.sqrt(252 / max(len(pnls), 1))

    def _calculate_streaks(self, pnls: List[float]) -> Tuple[int, int, int]:
        """Calculate current streak, max win streak, max loss streak"""
        if not pnls:
            return 0, 0, 0

        current_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        current_win = 0
        current_loss = 0

        for pnl in pnls:
            if pnl > 0:
                current_win += 1
                current_loss = 0
                max_win_streak = max(max_win_streak, current_win)
            elif pnl < 0:
                current_loss += 1
                current_win = 0
                max_loss_streak = max(max_loss_streak, current_loss)
            else:
                current_win = 0
                current_loss = 0

        # Current streak (positive = wins, negative = losses)
        if pnls:
            last_pnl = pnls[-1]
            if last_pnl > 0:
                current_streak = current_win
            elif last_pnl < 0:
                current_streak = -current_loss

        return current_streak, max_win_streak, max_loss_streak

    def _get_trading_days(self) -> int:
        """Get number of trading days"""
        if not self.trades:
            return 1

        try:
            first_trade = datetime.fromisoformat(self.trades[0].get('timestamp', ''))
            last_trade = datetime.fromisoformat(self.trades[-1].get('timestamp', ''))
            return max((last_trade - first_trade).days, 1)
        except:
            return 1

    def _get_daily_pnls(self) -> List[float]:
        """Get PnL grouped by day"""
        daily = defaultdict(float)

        for trade in self.trades:
            pnl = trade.get('pnl', 0)
            if pnl != 0:
                try:
                    ts = trade.get('timestamp', '')[:10]
                    daily[ts] += pnl
                except:
                    pass

        return list(daily.values())


class StrategyRanker:
    """Ranks strategies by performance across all portfolios"""

    def __init__(self, portfolios: dict):
        self.portfolios = portfolios

    def get_strategy_rankings(self) -> List[Dict]:
        """Get strategies ranked by performance"""
        strategy_stats = defaultdict(lambda: {
            'portfolios': 0,
            'total_pnl': 0,
            'total_trades': 0,
            'wins': 0,
            'total_capital': 0,
            'metrics': []
        })

        for pid, portfolio in self.portfolios.items():
            strategy = portfolio.get('strategy_id', 'unknown')
            initial = portfolio.get('initial_capital', 10000)

            analytics = PortfolioAnalytics(portfolio)
            metrics = analytics.calculate_all_metrics()

            stats = strategy_stats[strategy]
            stats['portfolios'] += 1
            stats['total_pnl'] += metrics.total_pnl
            stats['total_trades'] += metrics.total_trades
            stats['wins'] += metrics.winning_trades
            stats['total_capital'] += initial
            stats['metrics'].append(metrics)

        # Calculate aggregated metrics
        rankings = []
        for strategy, stats in strategy_stats.items():
            if stats['total_trades'] == 0:
                continue

            avg_win_rate = (stats['wins'] / stats['total_trades']) * 100 if stats['total_trades'] > 0 else 0
            avg_pnl_pct = (stats['total_pnl'] / stats['total_capital']) * 100 if stats['total_capital'] > 0 else 0

            # Calculate average Sharpe
            sharpes = [m.sharpe_ratio for m in stats['metrics'] if m.sharpe_ratio != 0]
            avg_sharpe = np.mean(sharpes) if sharpes else 0

            # Calculate average profit factor
            pfs = [m.profit_factor for m in stats['metrics'] if m.profit_factor > 0 and m.profit_factor < float('inf')]
            avg_pf = np.mean(pfs) if pfs else 0

            # Calculate score (weighted combination)
            score = (
                avg_win_rate * 0.25 +
                min(avg_pnl_pct, 100) * 0.30 +  # Cap at 100% for scoring
                min(avg_sharpe, 3) * 20 * 0.25 +  # Sharpe contribution
                min(avg_pf, 3) * 10 * 0.20  # Profit factor contribution
            )

            rankings.append({
                'strategy': strategy,
                'portfolios': stats['portfolios'],
                'total_pnl': stats['total_pnl'],
                'avg_pnl_pct': avg_pnl_pct,
                'total_trades': stats['total_trades'],
                'win_rate': avg_win_rate,
                'avg_sharpe': avg_sharpe,
                'avg_profit_factor': avg_pf,
                'score': score
            })

        # Sort by score
        rankings.sort(key=lambda x: x['score'], reverse=True)
        return rankings

    def get_top_strategies(self, n: int = 10) -> List[Dict]:
        """Get top N strategies"""
        return self.get_strategy_rankings()[:n]

    def get_worst_strategies(self, n: int = 5) -> List[Dict]:
        """Get worst N strategies"""
        rankings = self.get_strategy_rankings()
        return rankings[-n:] if len(rankings) >= n else rankings


class MarketRegimeDetector:
    """Detects market regime (Bull/Bear/Sideways)"""

    def __init__(self):
        self.cache = {}
        self.cache_time = None

    def detect_regime(self, btc_data: dict = None) -> Dict:
        """
        Detect current market regime based on BTC price action.

        Returns:
            {
                'regime': 'BULL' | 'BEAR' | 'SIDEWAYS',
                'strength': 0-100,
                'trend_direction': float (-1 to 1),
                'volatility': 'LOW' | 'MEDIUM' | 'HIGH',
                'recommendation': str
            }
        """
        import requests

        try:
            # Fetch BTC data if not provided
            if btc_data is None:
                response = requests.get(
                    "https://api.binance.com/api/v3/klines",
                    params={"symbol": "BTCUSDT", "interval": "4h", "limit": 50},
                    timeout=5
                )
                if response.status_code == 200:
                    klines = response.json()
                    closes = [float(k[4]) for k in klines]
                    highs = [float(k[2]) for k in klines]
                    lows = [float(k[3]) for k in klines]
                else:
                    return self._default_regime()
            else:
                closes = btc_data.get('closes', [])
                highs = btc_data.get('highs', [])
                lows = btc_data.get('lows', [])

            if len(closes) < 20:
                return self._default_regime()

            # Calculate indicators
            current_price = closes[-1]

            # EMAs
            ema_20 = self._ema(closes, 20)
            ema_50 = self._ema(closes, 50) if len(closes) >= 50 else ema_20

            # Price vs EMAs
            above_ema20 = current_price > ema_20
            above_ema50 = current_price > ema_50
            ema_trend = ema_20 > ema_50

            # Calculate trend strength
            price_change_20 = (current_price - closes[-20]) / closes[-20] * 100

            # Volatility (ATR-like)
            ranges = [highs[i] - lows[i] for i in range(-14, 0)]
            avg_range = np.mean(ranges)
            volatility_pct = (avg_range / current_price) * 100

            # Determine regime
            if above_ema20 and above_ema50 and ema_trend and price_change_20 > 5:
                regime = 'BULL'
                strength = min(80 + price_change_20, 100)
                trend_direction = 0.8
            elif not above_ema20 and not above_ema50 and not ema_trend and price_change_20 < -5:
                regime = 'BEAR'
                strength = min(80 + abs(price_change_20), 100)
                trend_direction = -0.8
            else:
                regime = 'SIDEWAYS'
                strength = 50 + abs(price_change_20)
                trend_direction = 0.1 if price_change_20 > 0 else -0.1

            # Volatility classification
            if volatility_pct < 2:
                vol_class = 'LOW'
            elif volatility_pct < 4:
                vol_class = 'MEDIUM'
            else:
                vol_class = 'HIGH'

            # Recommendations
            recommendations = {
                ('BULL', 'LOW'): "Strong uptrend, low volatility - Good for trend following",
                ('BULL', 'MEDIUM'): "Bullish with normal volatility - Standard long positions",
                ('BULL', 'HIGH'): "Volatile bull market - Use tighter stops, smaller positions",
                ('BEAR', 'LOW'): "Steady decline - Consider hedging or staying cash",
                ('BEAR', 'MEDIUM'): "Bear market - Reduce exposure, wait for reversal",
                ('BEAR', 'HIGH'): "Volatile crash - Stay cash or use very small positions",
                ('SIDEWAYS', 'LOW'): "Range-bound, low volatility - Mean reversion works",
                ('SIDEWAYS', 'MEDIUM'): "Choppy market - Grid trading or reduce activity",
                ('SIDEWAYS', 'HIGH'): "Whipsaws likely - Avoid trading or use wide stops",
            }

            return {
                'regime': regime,
                'strength': round(strength, 1),
                'trend_direction': round(trend_direction, 2),
                'volatility': vol_class,
                'volatility_pct': round(volatility_pct, 2),
                'price_change_20': round(price_change_20, 2),
                'recommendation': recommendations.get((regime, vol_class), "Monitor market conditions"),
                'btc_price': current_price,
                'ema_20': round(ema_20, 2),
                'ema_50': round(ema_50, 2)
            }

        except Exception as e:
            return self._default_regime()

    def _ema(self, data: List[float], period: int) -> float:
        """Calculate EMA"""
        if len(data) < period:
            return np.mean(data)

        multiplier = 2 / (period + 1)
        ema = np.mean(data[:period])

        for price in data[period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def _default_regime(self) -> Dict:
        return {
            'regime': 'UNKNOWN',
            'strength': 0,
            'trend_direction': 0,
            'volatility': 'UNKNOWN',
            'recommendation': "Unable to determine market regime"
        }


class CorrelationAnalyzer:
    """Analyzes correlation between positions"""

    def __init__(self, positions: Dict):
        self.positions = positions

    def get_correlation_risk(self) -> Dict:
        """
        Analyze portfolio concentration and correlation risk.

        Returns:
            {
                'concentration_score': 0-100 (higher = more concentrated),
                'largest_position_pct': float,
                'sector_exposure': dict,
                'risk_level': 'LOW' | 'MEDIUM' | 'HIGH',
                'recommendations': list
            }
        """
        if not self.positions:
            return {
                'concentration_score': 0,
                'largest_position_pct': 0,
                'sector_exposure': {},
                'risk_level': 'LOW',
                'recommendations': ['No open positions']
            }

        # Calculate position values
        position_values = {}
        total_value = 0

        for symbol, pos in self.positions.items():
            value = pos.get('quantity', 0) * pos.get('current_price', pos.get('entry_price', 0))
            position_values[symbol] = value
            total_value += value

        if total_value == 0:
            return self._default_result()

        # Calculate concentration
        weights = [v / total_value for v in position_values.values()]
        herfindahl_index = sum(w ** 2 for w in weights)  # 0 = diversified, 1 = concentrated

        # Largest position
        largest = max(weights) * 100 if weights else 0

        # Sector exposure (basic classification)
        sectors = self._classify_sectors(position_values.keys())

        # Risk level
        if herfindahl_index > 0.5 or largest > 40:
            risk_level = 'HIGH'
        elif herfindahl_index > 0.25 or largest > 25:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'

        # Recommendations
        recommendations = []
        if largest > 30:
            recommendations.append(f"Consider reducing largest position ({largest:.0f}% of portfolio)")
        if len(position_values) < 3:
            recommendations.append("Low diversification - consider adding more positions")
        if herfindahl_index > 0.4:
            recommendations.append("Portfolio is highly concentrated")

        dominant_sector = max(sectors.items(), key=lambda x: x[1])[0] if sectors else None
        if dominant_sector and sectors[dominant_sector] > 50:
            recommendations.append(f"Heavy exposure to {dominant_sector} sector ({sectors[dominant_sector]:.0f}%)")

        return {
            'concentration_score': round(herfindahl_index * 100, 1),
            'largest_position_pct': round(largest, 1),
            'position_count': len(position_values),
            'sector_exposure': sectors,
            'risk_level': risk_level,
            'recommendations': recommendations if recommendations else ['Portfolio looks well-balanced']
        }

    def _classify_sectors(self, symbols) -> Dict[str, float]:
        """Basic sector classification"""
        sector_map = {
            'BTC': 'Bitcoin', 'ETH': 'Ethereum', 'BNB': 'Exchange',
            'SOL': 'Layer1', 'ADA': 'Layer1', 'AVAX': 'Layer1', 'DOT': 'Layer1',
            'MATIC': 'Layer2', 'ARB': 'Layer2', 'OP': 'Layer2',
            'LINK': 'DeFi', 'UNI': 'DeFi', 'AAVE': 'DeFi', 'MKR': 'DeFi',
            'DOGE': 'Meme', 'SHIB': 'Meme', 'PEPE': 'Meme', 'FLOKI': 'Meme',
        }

        sectors = defaultdict(float)
        total = len(list(symbols))

        for symbol in symbols:
            base = symbol.split('/')[0] if '/' in symbol else symbol
            sector = sector_map.get(base, 'Other')
            sectors[sector] += 1

        # Convert to percentages
        return {k: (v / total) * 100 for k, v in sectors.items()}

    def _default_result(self) -> Dict:
        return {
            'concentration_score': 0,
            'largest_position_pct': 0,
            'sector_exposure': {},
            'risk_level': 'LOW',
            'recommendations': ['No position data available']
        }


# ==================== UTILITY FUNCTIONS ====================

def calculate_portfolio_metrics(portfolio: dict) -> PerformanceMetrics:
    """Convenience function to calculate metrics for a portfolio"""
    analytics = PortfolioAnalytics(portfolio)
    return analytics.calculate_all_metrics()


def get_strategy_leaderboard(portfolios: dict) -> List[Dict]:
    """Get strategy leaderboard"""
    ranker = StrategyRanker(portfolios)
    return ranker.get_strategy_rankings()


def detect_market_regime() -> Dict:
    """Detect current market regime"""
    detector = MarketRegimeDetector()
    return detector.detect_regime()


def analyze_portfolio_risk(positions: dict) -> Dict:
    """Analyze portfolio concentration risk"""
    analyzer = CorrelationAnalyzer(positions)
    return analyzer.get_correlation_risk()
