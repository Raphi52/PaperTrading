"""
Strategy Analyzer Module
========================
Generates daily analysis reports optimized for Claude to suggest improvements.

Usage:
    from core.strategy_analyzer import StrategyAnalyzer
    analyzer = StrategyAnalyzer()
    report = analyzer.generate_report()
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

DB_PATH = "data/trading.db"
PORTFOLIOS_PATH = "data/portfolios.json"
REPORTS_DIR = "data/daily_reports"


class StrategyAnalyzer:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.portfolios = self._load_portfolios()
        self.strategies = self._get_strategy_configs()

    def _load_portfolios(self) -> Dict:
        """Load portfolios from JSON"""
        try:
            with open(PORTFOLIOS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f).get('portfolios', {})
        except:
            return {}

    def _get_strategy_configs(self) -> Dict:
        """Get strategy configs from portfolios"""
        configs = {}
        for pid, p in self.portfolios.items():
            sid = p.get('strategy_id', '')
            if sid and sid not in configs:
                configs[sid] = {
                    'take_profit': 20,  # Default
                    'stop_loss': 10,    # Default
                }
        return configs

    def get_trades(self, days: int = 7, strategy_id: str = None) -> List[Dict]:
        """Get trades from last N days"""
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        if strategy_id:
            cursor.execute("""
                SELECT * FROM trades
                WHERE timestamp >= ? AND strategy_id = ?
                ORDER BY timestamp DESC
            """, (since, strategy_id))
        else:
            cursor.execute("""
                SELECT * FROM trades
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            """, (since,))

        return [dict(row) for row in cursor.fetchall()]

    def get_strategy_stats(self, days: int = 7) -> Dict[str, Dict]:
        """Get performance stats grouped by strategy"""
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                strategy_id,
                COUNT(*) as total_trades,
                SUM(CASE WHEN action = 'SELL' THEN 1 ELSE 0 END) as sells,
                SUM(CASE WHEN action = 'SELL' AND pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN action = 'SELL' AND pnl < 0 THEN 1 ELSE 0 END) as losses,
                ROUND(SUM(CASE WHEN action = 'SELL' THEN pnl ELSE 0 END), 2) as total_pnl,
                ROUND(AVG(CASE WHEN action = 'SELL' THEN pnl END), 2) as avg_pnl,
                ROUND(SUM(fee), 2) as total_fees,
                MIN(timestamp) as first_trade,
                MAX(timestamp) as last_trade
            FROM trades
            WHERE timestamp >= ?
            GROUP BY strategy_id
            ORDER BY total_pnl ASC
        """, (since,))

        stats = {}
        for row in cursor.fetchall():
            row = dict(row)
            sid = row['strategy_id']
            sells = row['sells'] or 0
            wins = row['wins'] or 0
            stats[sid] = {
                **row,
                'win_rate': round((wins / sells * 100) if sells > 0 else 0, 1)
            }
        return stats

    def get_exit_reasons(self, days: int = 7) -> Dict[str, Dict]:
        """Analyze exit reasons distribution"""
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                strategy_id,
                reason,
                COUNT(*) as count,
                ROUND(SUM(pnl), 2) as total_pnl
            FROM trades
            WHERE timestamp >= ? AND action = 'SELL' AND reason IS NOT NULL
            GROUP BY strategy_id, reason
            ORDER BY strategy_id, count DESC
        """, (since,))

        results = defaultdict(list)
        for row in cursor.fetchall():
            row = dict(row)
            results[row['strategy_id']].append({
                'reason': row['reason'],
                'count': row['count'],
                'pnl': row['total_pnl'] or 0
            })
        return dict(results)

    def get_hourly_performance(self, days: int = 7) -> List[Dict]:
        """Get P&L by hour of day"""
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                CAST(strftime('%H', timestamp) AS INTEGER) as hour,
                COUNT(*) as trades,
                ROUND(SUM(pnl), 2) as pnl
            FROM trades
            WHERE timestamp >= ? AND action = 'SELL'
            GROUP BY hour
            ORDER BY hour
        """, (since,))

        return [dict(row) for row in cursor.fetchall()]

    def get_symbol_performance(self, days: int = 7) -> List[Dict]:
        """Get P&L by trading pair"""
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                symbol,
                COUNT(*) as trades,
                ROUND(SUM(pnl), 2) as pnl,
                ROUND(AVG(pnl), 2) as avg_pnl
            FROM trades
            WHERE timestamp >= ? AND action = 'SELL'
            GROUP BY symbol
            ORDER BY pnl ASC
            LIMIT 20
        """, (since,))

        return [dict(row) for row in cursor.fetchall()]

    def get_worst_trades(self, days: int = 1, limit: int = 20) -> List[Dict]:
        """Get worst performing trades"""
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                timestamp, portfolio_name, strategy_id, symbol,
                price, pnl, pnl_pct, reason
            FROM trades
            WHERE timestamp >= ? AND action = 'SELL' AND pnl < 0
            ORDER BY pnl ASC
            LIMIT ?
        """, (since, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_inactive_strategies(self, days: int = 3) -> List[Dict]:
        """Find strategies with no trades recently"""
        # Get all strategy IDs from portfolios
        all_strategies = set()
        for p in self.portfolios.values():
            if p.get('active') and p.get('config', {}).get('auto_trade'):
                all_strategies.add(p.get('strategy_id'))

        # Get strategies that traded recently
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute("""
            SELECT DISTINCT strategy_id FROM trades WHERE timestamp >= ?
        """, (since,))
        active = {row[0] for row in cursor.fetchall()}

        # Find inactive
        inactive = []
        for sid in all_strategies - active:
            # Get last trade
            cursor.execute("""
                SELECT MAX(timestamp) as last_trade FROM trades WHERE strategy_id = ?
            """, (sid,))
            row = cursor.fetchone()
            inactive.append({
                'strategy_id': sid,
                'last_trade': row[0] if row else 'Never'
            })

        return inactive

    def detect_anomalies(self) -> List[str]:
        """Detect trading anomalies"""
        anomalies = []

        # Check for strategies with too many positions
        for pid, p in self.portfolios.items():
            positions = len(p.get('positions', {}))
            if positions > 10:
                anomalies.append(f"[!] {p['name']} has {positions} open positions (high risk)")

        # Check for overtrading (>30 trades/day)
        cursor = self.conn.cursor()
        today = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
        cursor.execute("""
            SELECT strategy_id, COUNT(*) as count
            FROM trades WHERE timestamp >= ?
            GROUP BY strategy_id
            HAVING count > 30
        """, (today,))
        for row in cursor.fetchall():
            anomalies.append(f"[!] {row[0]} traded {row[1]}x today (overtrading)")

        # Check for strategies with 100% loss rate today
        cursor.execute("""
            SELECT strategy_id,
                   SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                   COUNT(*) as total
            FROM trades
            WHERE timestamp >= ? AND action = 'SELL'
            GROUP BY strategy_id
            HAVING losses = total AND total >= 3
        """, (today,))
        for row in cursor.fetchall():
            anomalies.append(f"[!] {row[0]} has 100% loss rate today ({row[1]} losses)")

        return anomalies

    def generate_suggestions(self, strategy_stats: Dict, exit_reasons: Dict) -> List[Dict]:
        """Generate improvement suggestions based on data"""
        suggestions = []

        for sid, stats in strategy_stats.items():
            if stats['total_pnl'] is None or stats['sells'] is None:
                continue

            pnl = stats['total_pnl'] or 0
            sells = stats['sells'] or 0
            win_rate = stats['win_rate'] or 0

            # Skip strategies with few trades
            if sells < 3:
                continue

            reasons = exit_reasons.get(sid, [])
            reason_map = {r['reason']: r for r in reasons}

            # Check SL hit rate
            sl_reasons = [r for r in reasons if 'SL' in (r.get('reason') or '')]
            sl_count = sum(r['count'] for r in sl_reasons)
            sl_rate = (sl_count / sells * 100) if sells > 0 else 0

            if sl_rate > 50 and pnl < 0:
                suggestions.append({
                    'strategy': sid,
                    'priority': 'URGENT' if pnl < -100 else 'IMPORTANT',
                    'problem': f'SL hit rate {sl_rate:.0f}% (too tight)',
                    'suggestion': 'Increase stop_loss by 2-3%',
                    'impact': f'Could improve win rate from {win_rate:.0f}%'
                })

            # Check TIME EXIT rate
            time_reasons = [r for r in reasons if 'TIME' in (r.get('reason') or '')]
            time_count = sum(r['count'] for r in time_reasons)
            time_rate = (time_count / sells * 100) if sells > 0 else 0

            if time_rate > 40 and pnl < 0:
                suggestions.append({
                    'strategy': sid,
                    'priority': 'IMPORTANT',
                    'problem': f'TIME EXIT rate {time_rate:.0f}% (exits too early)',
                    'suggestion': 'Increase max_hold_hours',
                    'impact': f'Trades not reaching TP'
                })

            # Check if TP is never hit
            tp_reasons = [r for r in reasons if 'TP' in (r.get('reason') or '')]
            tp_count = sum(r['count'] for r in tp_reasons)

            if tp_count == 0 and sells >= 5 and pnl < 0:
                suggestions.append({
                    'strategy': sid,
                    'priority': 'IMPORTANT',
                    'problem': f'TP never hit in {sells} trades',
                    'suggestion': 'Reduce take_profit by 20-30%',
                    'impact': 'More trades will close in profit'
                })

            # Check very low win rate
            if win_rate < 30 and sells >= 5:
                suggestions.append({
                    'strategy': sid,
                    'priority': 'URGENT' if pnl < -200 else 'REVIEW',
                    'problem': f'Win rate only {win_rate:.0f}%',
                    'suggestion': 'Review entry conditions or disable',
                    'impact': f'Losing ${abs(pnl):.0f}'
                })

        # Sort by priority
        priority_order = {'URGENT': 0, 'IMPORTANT': 1, 'REVIEW': 2, 'OPTIMIZATION': 3}
        suggestions.sort(key=lambda x: priority_order.get(x['priority'], 99))

        return suggestions

    def analyze_by_market_regime(self, days: int = 7) -> Dict[str, Dict]:
        """
        Analyze performance by market regime (TRENDING, RANGING, VOLATILE).
        Uses price change and volatility to classify each trade's market context.
        """
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        # Get trades with price context
        cursor.execute("""
            SELECT strategy_id, symbol, pnl, timestamp, price
            FROM trades
            WHERE timestamp >= ? AND action = 'SELL'
        """, (since,))

        # Initialize regime stats per strategy
        regime_stats = defaultdict(lambda: {
            'TRENDING': {'trades': 0, 'wins': 0, 'pnl': 0},
            'RANGING': {'trades': 0, 'wins': 0, 'pnl': 0},
            'VOLATILE': {'trades': 0, 'wins': 0, 'pnl': 0}
        })

        # Get 24h price changes for regime classification
        for row in cursor.fetchall():
            row = dict(row)
            sid = row['strategy_id']
            pnl = row['pnl'] or 0

            # Classify based on trade reason patterns (simplified)
            # In production, this would use actual market data
            # For now, use time-based heuristics
            hour = int(row['timestamp'][11:13]) if row['timestamp'] else 12

            # Simplified regime classification by hour patterns
            if hour >= 14 and hour <= 21:  # US market hours - more trending
                regime = 'TRENDING'
            elif hour >= 0 and hour <= 8:  # Asian session - more ranging
                regime = 'RANGING'
            else:  # European overlap - more volatile
                regime = 'VOLATILE'

            regime_stats[sid][regime]['trades'] += 1
            regime_stats[sid][regime]['pnl'] += pnl
            if pnl > 0:
                regime_stats[sid][regime]['wins'] += 1

        # Calculate win rates per regime
        result = {}
        for sid, regimes in regime_stats.items():
            result[sid] = {}
            for regime, data in regimes.items():
                trades = data['trades']
                result[sid][regime] = {
                    'trades': trades,
                    'wins': data['wins'],
                    'pnl': round(data['pnl'], 2),
                    'win_rate': round((data['wins'] / trades * 100) if trades > 0 else 0, 1)
                }

        return result

    def calculate_optimal_trading_hours(self, days: int = 7) -> Dict[str, Dict]:
        """
        Calculate optimal trading hours per strategy.
        Returns best and worst hours based on P&L.
        """
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                strategy_id,
                CAST(strftime('%H', timestamp) AS INTEGER) as hour,
                COUNT(*) as trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                ROUND(SUM(pnl), 2) as pnl
            FROM trades
            WHERE timestamp >= ? AND action = 'SELL'
            GROUP BY strategy_id, hour
            ORDER BY strategy_id, hour
        """, (since,))

        hourly_data = defaultdict(list)
        for row in cursor.fetchall():
            row = dict(row)
            hourly_data[row['strategy_id']].append({
                'hour': row['hour'],
                'trades': row['trades'],
                'wins': row['wins'],
                'pnl': row['pnl'] or 0
            })

        result = {}
        for sid, hours in hourly_data.items():
            if not hours:
                continue

            # Sort by P&L
            sorted_hours = sorted(hours, key=lambda x: x['pnl'], reverse=True)
            best = sorted_hours[:3]
            worst = sorted_hours[-3:]

            # Calculate recommended hours (positive P&L only)
            profitable_hours = [h['hour'] for h in hours if h['pnl'] > 0]

            result[sid] = {
                'best_hours': [{'hour': h['hour'], 'pnl': h['pnl'], 'trades': h['trades']} for h in best],
                'worst_hours': [{'hour': h['hour'], 'pnl': h['pnl'], 'trades': h['trades']} for h in worst],
                'recommended_hours': sorted(profitable_hours),
                'avoid_hours': [h['hour'] for h in worst if h['pnl'] < 0]
            }

        return result

    def analyze_entry_quality(self, days: int = 7) -> Dict[str, Dict]:
        """
        Analyze entry quality based on trade outcomes.
        Higher quality entries have better risk/reward ratios.
        """
        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT
                strategy_id,
                pnl,
                pnl_pct,
                reason
            FROM trades
            WHERE timestamp >= ? AND action = 'SELL'
        """, (since,))

        strategy_entries = defaultdict(list)
        for row in cursor.fetchall():
            row = dict(row)
            pnl = row['pnl'] or 0
            pnl_pct = row['pnl_pct'] or 0
            reason = row['reason'] or ''

            # Score entry quality based on outcome
            if 'TP' in reason:
                quality = 100  # Perfect entry
            elif pnl > 0:
                quality = 70 + min(30, pnl_pct * 3)  # Good entry
            elif 'SL' in reason:
                quality = 20 + max(0, 30 + pnl_pct)  # Poor entry hit SL
            elif 'TIME' in reason:
                quality = 40 + pnl_pct * 2  # Mediocre - time exit
            else:
                quality = 50 + pnl_pct * 2  # Other

            quality = max(0, min(100, quality))  # Clamp 0-100
            strategy_entries[row['strategy_id']].append(quality)

        result = {}
        for sid, qualities in strategy_entries.items():
            if not qualities:
                continue

            avg_quality = sum(qualities) / len(qualities)
            high_quality = len([q for q in qualities if q >= 70])
            low_quality = len([q for q in qualities if q < 40])

            result[sid] = {
                'avg_entry_quality': round(avg_quality, 1),
                'total_entries': len(qualities),
                'high_quality_count': high_quality,
                'low_quality_count': low_quality,
                'quality_ratio': round(high_quality / len(qualities) * 100, 1) if qualities else 0,
                'rating': 'Excellent' if avg_quality >= 70 else 'Good' if avg_quality >= 55 else 'Fair' if avg_quality >= 40 else 'Poor'
            }

        return result

    def calculate_sharpe_ratio(self, days: int = 30) -> Dict[str, float]:
        """
        Calculate Sharpe ratio per strategy.
        Sharpe = (Mean Return - Risk Free Rate) / Std Dev of Returns
        Assumes risk-free rate of 0 for simplicity.
        """
        import math

        cursor = self.conn.cursor()
        since = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT strategy_id, pnl_pct
            FROM trades
            WHERE timestamp >= ? AND action = 'SELL' AND pnl_pct IS NOT NULL
            ORDER BY strategy_id
        """, (since,))

        strategy_returns = defaultdict(list)
        for row in cursor.fetchall():
            row = dict(row)
            strategy_returns[row['strategy_id']].append(row['pnl_pct'])

        result = {}
        for sid, returns in strategy_returns.items():
            if len(returns) < 5:  # Need minimum trades for meaningful Sharpe
                result[sid] = None
                continue

            mean_return = sum(returns) / len(returns)

            # Calculate standard deviation
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std_dev = math.sqrt(variance) if variance > 0 else 0.0001

            # Sharpe ratio (annualized assuming ~365 trading days)
            # Daily Sharpe * sqrt(365) for annualization
            daily_sharpe = mean_return / std_dev if std_dev > 0 else 0
            annual_sharpe = daily_sharpe * math.sqrt(365)

            result[sid] = round(annual_sharpe, 2)

        return result

    def get_strategy_summary(self, days: int = 7) -> Dict[str, Dict]:
        """
        Get comprehensive summary including new metrics for each strategy.
        """
        basic_stats = self.get_strategy_stats(days)
        regimes = self.analyze_by_market_regime(days)
        optimal_hours = self.calculate_optimal_trading_hours(days)
        entry_quality = self.analyze_entry_quality(days)
        sharpe = self.calculate_sharpe_ratio(days)

        result = {}
        all_strategies = set(basic_stats.keys()) | set(regimes.keys()) | set(sharpe.keys())

        for sid in all_strategies:
            result[sid] = {
                'basic': basic_stats.get(sid, {}),
                'regimes': regimes.get(sid, {}),
                'optimal_hours': optimal_hours.get(sid, {}),
                'entry_quality': entry_quality.get(sid, {}),
                'sharpe_ratio': sharpe.get(sid)
            }

        return result

    def generate_report(self, days: int = 1) -> str:
        """Generate the full analysis report"""
        now = datetime.now()

        # Gather all data
        stats_1d = self.get_strategy_stats(days=1)
        stats_7d = self.get_strategy_stats(days=7)
        stats_30d = self.get_strategy_stats(days=30)
        exit_reasons = self.get_exit_reasons(days=7)
        hourly = self.get_hourly_performance(days=7)
        symbols = self.get_symbol_performance(days=7)
        worst_trades = self.get_worst_trades(days=1, limit=20)
        inactive = self.get_inactive_strategies(days=3)
        anomalies = self.detect_anomalies()
        suggestions = self.generate_suggestions(stats_7d, exit_reasons)

        # Calculate totals
        total_pnl_1d = sum((s.get('total_pnl') or 0) for s in stats_1d.values())
        total_trades_1d = sum((s.get('sells') or 0) for s in stats_1d.values())
        total_wins_1d = sum((s.get('wins') or 0) for s in stats_1d.values())
        win_rate_1d = (total_wins_1d / total_trades_1d * 100) if total_trades_1d > 0 else 0

        # Find best/worst strategies
        sorted_1d = sorted(stats_1d.items(), key=lambda x: x[1].get('total_pnl') or 0)
        worst_strategy = sorted_1d[0] if sorted_1d else (None, {})
        best_strategy = sorted_1d[-1] if sorted_1d else (None, {})

        # Build report
        lines = []
        lines.append(f"# Daily Trading Analysis - {now.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        # Executive Summary
        lines.append("## 1. RESUME EXECUTIF")
        lines.append(f"- **P&L du jour**: {'+'if total_pnl_1d >= 0 else ''}${total_pnl_1d:.2f}")
        lines.append(f"- **Win Rate**: {win_rate_1d:.1f}%")
        lines.append(f"- **Trades**: {total_trades_1d} ({total_wins_1d} wins, {total_trades_1d - total_wins_1d} losses)")
        if best_strategy[0]:
            lines.append(f"- **Meilleure strategie**: {best_strategy[0]} (+${best_strategy[1].get('total_pnl', 0):.2f})")
        if worst_strategy[0]:
            lines.append(f"- **Pire strategie**: {worst_strategy[0]} (${worst_strategy[1].get('total_pnl', 0):.2f})")
        lines.append("")

        # Struggling Strategies
        lines.append("## 2. STRATEGIES EN DIFFICULTE (Top 10 pires)")
        struggling = [s for s in sorted_1d[:10] if (s[1].get('total_pnl') or 0) < 0]

        if struggling:
            lines.append("| Strategy | P&L 24h | P&L 7j | Win Rate | Trades | Probleme |")
            lines.append("|----------|---------|--------|----------|--------|----------|")
            for sid, s in struggling:
                pnl_7d = stats_7d.get(sid, {}).get('total_pnl', 0) or 0
                wr = s.get('win_rate', 0) or 0
                trades = s.get('sells', 0) or 0

                # Identify main problem
                reasons = exit_reasons.get(sid, [])
                problem = "Low win rate"
                for r in reasons:
                    if 'SL' in (r.get('reason') or '') and r['count'] > trades * 0.5:
                        problem = "SL trop serre"
                        break
                    elif 'TIME' in (r.get('reason') or '') and r['count'] > trades * 0.4:
                        problem = "TIME EXIT"
                        break

                lines.append(f"| {sid} | ${s.get('total_pnl', 0):.0f} | ${pnl_7d:.0f} | {wr:.0f}% | {trades} | {problem} |")
        else:
            lines.append("*Aucune strategie en difficulte aujourd'hui*")
        lines.append("")

        # Loss Patterns
        lines.append("## 3. PATTERNS DE PERTES (7 jours)")
        lines.append("")
        lines.append("### Par raison de sortie:")

        # Aggregate exit reasons
        reason_totals = defaultdict(lambda: {'count': 0, 'pnl': 0})
        for sid, reasons in exit_reasons.items():
            for r in reasons:
                # Simplify reason
                reason = r.get('reason', 'Unknown') or 'Unknown'
                if 'SL' in reason:
                    key = 'SL HIT'
                elif 'TP' in reason:
                    key = 'TP HIT'
                elif 'TIME' in reason:
                    key = 'TIME EXIT'
                elif 'TRAIL' in reason:
                    key = 'TRAILING STOP'
                elif 'EMA' in reason:
                    key = 'EMA SIGNAL'
                else:
                    key = reason[:30]

                reason_totals[key]['count'] += r['count']
                reason_totals[key]['pnl'] += r.get('pnl', 0) or 0

        for reason, data in sorted(reason_totals.items(), key=lambda x: x[1]['pnl']):
            pnl = data['pnl']
            sign = '+' if pnl >= 0 else ''
            lines.append(f"- **{reason}**: {data['count']} trades, {sign}${pnl:.0f}")
        lines.append("")

        # Hourly performance
        lines.append("### Par heure du jour:")
        if hourly:
            worst_hours = sorted(hourly, key=lambda x: x.get('pnl') or 0)[:3]
            best_hours = sorted(hourly, key=lambda x: x.get('pnl') or 0, reverse=True)[:3]

            worst_str = ", ".join([f"{h['hour']}h (${h['pnl']:.0f})" for h in worst_hours if (h.get('pnl') or 0) < 0])
            best_str = ", ".join([f"{h['hour']}h (+${h['pnl']:.0f})" for h in best_hours if (h.get('pnl') or 0) > 0])

            if worst_str:
                lines.append(f"- Pires heures: {worst_str}")
            if best_str:
                lines.append(f"- Meilleures heures: {best_str}")
        lines.append("")

        # Symbol performance
        lines.append("### Par crypto (pires):")
        worst_symbols = [s for s in symbols if (s.get('pnl') or 0) < 0][:5]
        for s in worst_symbols:
            lines.append(f"- {s['symbol']}: ${s['pnl']:.0f} ({s['trades']} trades)")
        lines.append("")

        # Inactive strategies
        lines.append("## 4. STRATEGIES INACTIVES")
        if inactive:
            lines.append("| Strategy | Derniere trade |")
            lines.append("|----------|----------------|")
            for s in inactive[:10]:
                lines.append(f"| {s['strategy_id']} | {s['last_trade']} |")
        else:
            lines.append("*Toutes les strategies sont actives*")
        lines.append("")

        # Anomalies
        lines.append("## 5. ANOMALIES DETECTEES")
        if anomalies:
            for a in anomalies:
                lines.append(f"- {a}")
        else:
            lines.append("*Aucune anomalie detectee*")
        lines.append("")

        # Recommendations
        lines.append("## 6. RECOMMANDATIONS PRIORISEES")
        if suggestions:
            for i, s in enumerate(suggestions[:10], 1):
                lines.append(f"{i}. **{s['priority']}**: {s['strategy']} - {s['problem']}")
                lines.append(f"   - Suggestion: {s['suggestion']}")
                lines.append(f"   - Impact: {s['impact']}")
        else:
            lines.append("*Pas de recommandations urgentes*")
        lines.append("")

        # Code suggestions
        lines.append("## 7. CODE CHANGES SUGGERES")
        lines.append("```python")
        lines.append("# Modifications suggérées pour STRATEGIES dict dans bot.py:")
        for s in suggestions[:5]:
            if 'stop_loss' in s['suggestion'].lower():
                lines.append(f'# {s["strategy"]}: augmenter stop_loss de 2-3%')
            elif 'take_profit' in s['suggestion'].lower():
                lines.append(f'# {s["strategy"]}: reduire take_profit de 20%')
            elif 'max_hold' in s['suggestion'].lower():
                lines.append(f'# {s["strategy"]}: augmenter max_hold_hours')
        lines.append("```")
        lines.append("")

        # Worst trades detail
        lines.append("## 8. PIRES TRADES DU JOUR")
        if worst_trades:
            lines.append("| Time | Portfolio | Strategy | Symbol | P&L | Reason |")
            lines.append("|------|-----------|----------|--------|-----|--------|")
            for t in worst_trades[:15]:
                time_str = t['timestamp'][11:16] if t['timestamp'] else ''
                lines.append(f"| {time_str} | {t['portfolio_name'][:15]} | {t['strategy_id']} | {t['symbol']} | ${t['pnl']:.0f} | {(t['reason'] or '')[:25]} |")
        else:
            lines.append("*Pas de trades perdants aujourd'hui*")
        lines.append("")

        # Advanced Metrics Section
        lines.append("## 9. METRIQUES AVANCEES")
        lines.append("")

        # Calculate advanced metrics
        sharpe_ratios = self.calculate_sharpe_ratio(30)
        entry_quality = self.analyze_entry_quality(7)
        optimal_hours = self.calculate_optimal_trading_hours(7)

        # Top Sharpe Ratios
        valid_sharpe = [(sid, sr) for sid, sr in sharpe_ratios.items() if sr is not None]
        sorted_sharpe = sorted(valid_sharpe, key=lambda x: x[1], reverse=True)

        if sorted_sharpe:
            lines.append("### Meilleurs Sharpe Ratios (30j):")
            for sid, sr in sorted_sharpe[:5]:
                rating = "Excellent" if sr > 2 else "Bon" if sr > 1 else "Moyen" if sr > 0 else "Negatif"
                lines.append(f"- **{sid}**: {sr:.2f} ({rating})")
            lines.append("")

        # Entry Quality Rankings
        sorted_quality = sorted(entry_quality.items(), key=lambda x: x[1].get('avg_entry_quality', 0), reverse=True)

        if sorted_quality:
            lines.append("### Qualite des Entrees (7j):")
            lines.append("| Strategy | Score | Rating | High/Low |")
            lines.append("|----------|-------|--------|----------|")
            for sid, eq in sorted_quality[:10]:
                lines.append(f"| {sid} | {eq['avg_entry_quality']:.0f}/100 | {eq['rating']} | {eq['high_quality_count']}/{eq['low_quality_count']} |")
            lines.append("")

        # Optimal Trading Hours Summary
        lines.append("### Heures Optimales par Strategie:")
        for sid, hours_data in list(optimal_hours.items())[:5]:
            if hours_data.get('best_hours'):
                best = hours_data['best_hours'][0]
                avoid = hours_data.get('avoid_hours', [])
                avoid_str = ', '.join([f"{h}h" for h in avoid[:3]]) if avoid else 'aucune'
                lines.append(f"- **{sid}**: Meilleure heure {best['hour']}h (+${best['pnl']:.0f}), Eviter: {avoid_str}")
        lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"*Rapport genere le {now.strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("*Pour appliquer les corrections, copiez ce rapport a Claude et demandez l'implementation.*")

        return "\n".join(lines)

    def save_report(self, report: str = None) -> str:
        """Save report to file"""
        os.makedirs(REPORTS_DIR, exist_ok=True)

        if report is None:
            report = self.generate_report()

        filename = os.path.join(
            REPORTS_DIR,
            f"report_{datetime.now().strftime('%Y-%m-%d')}.md"
        )

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)

        return filename

    def close(self):
        """Close database connection"""
        self.conn.close()


# Quick test
if __name__ == "__main__":
    analyzer = StrategyAnalyzer()
    report = analyzer.generate_report()
    filename = analyzer.save_report(report)
    print(f"Report saved to: {filename}")
    print("\n" + "="*50 + "\n")
    print(report)
    analyzer.close()
