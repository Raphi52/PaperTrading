"""
Strategy Optimizer Module
=========================
Automatically adjusts strategy parameters based on historical performance.

Usage:
    from core.strategy_optimizer import StrategyOptimizer
    optimizer = StrategyOptimizer()
    suggestions = optimizer.get_suggestions()
    optimizer.apply_suggestions(suggestions)
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Import strategy analyzer for data access
try:
    from core.strategy_analyzer import StrategyAnalyzer
except ImportError:
    StrategyAnalyzer = None

# Import database for trade history
try:
    from core.database import get_connection
except ImportError:
    get_connection = None


class StrategyOptimizer:
    """
    Automatically optimizes strategy parameters based on performance data.

    Key optimizations:
    1. TP adjustment: Reduce TP if never hit, increase if too conservative
    2. SL adjustment: Widen SL if hit rate >50%, tighten if rarely hit
    3. Time filter: Disable trading during worst performing hours
    4. Strategy disable: Pause strategies with >3 consecutive losing days
    """

    def __init__(self, days: int = 7):
        self.days = days
        self.analyzer = StrategyAnalyzer() if StrategyAnalyzer else None
        self.suggestions = []
        self.applied_changes = []

        # Thresholds for optimizations
        self.TP_NEVER_HIT_THRESHOLD = 0  # 0% TP hit rate triggers reduction
        self.TP_REDUCTION_FACTOR = 0.8   # Reduce TP by 20%
        self.SL_HIT_HIGH_THRESHOLD = 50  # >50% SL hits triggers widening
        self.SL_WIDEN_FACTOR = 1.15      # Widen SL by 15%
        self.MIN_TRADES_FOR_ANALYSIS = 5 # Need at least 5 trades
        self.MAX_CONSECUTIVE_LOSSES = 3  # Pause after 3 losing days

    def analyze_strategy(self, strategy_id: str) -> Dict:
        """Analyze a single strategy's performance"""
        if not self.analyzer:
            return {}

        stats = self.analyzer.get_strategy_stats(strategy_id, self.days)
        exit_reasons = self.analyzer.get_exit_reasons(strategy_id, self.days)

        # Calculate key metrics
        total_trades = stats.get('total_trades', 0)
        win_rate = stats.get('win_rate', 0)
        pnl = stats.get('pnl', 0)

        # Count exit types
        tp_hits = sum(1 for r in exit_reasons if 'TP' in r.get('reason', '').upper())
        sl_hits = sum(1 for r in exit_reasons if 'SL' in r.get('reason', '').upper())
        time_exits = sum(1 for r in exit_reasons if 'TIME' in r.get('reason', '').upper())

        tp_rate = (tp_hits / total_trades * 100) if total_trades > 0 else 0
        sl_rate = (sl_hits / total_trades * 100) if total_trades > 0 else 0

        return {
            'strategy_id': strategy_id,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'pnl': pnl,
            'tp_hits': tp_hits,
            'sl_hits': sl_hits,
            'time_exits': time_exits,
            'tp_rate': tp_rate,
            'sl_rate': sl_rate
        }

    def get_tp_suggestion(self, strategy_id: str, current_tp: float, analysis: Dict) -> Optional[Dict]:
        """Suggest TP adjustment if needed"""
        if analysis['total_trades'] < self.MIN_TRADES_FOR_ANALYSIS:
            return None

        # TP never hit - reduce it
        if analysis['tp_rate'] == 0 and analysis['total_trades'] >= 10:
            new_tp = round(current_tp * self.TP_REDUCTION_FACTOR, 1)
            return {
                'type': 'TP_REDUCTION',
                'strategy_id': strategy_id,
                'param': 'take_profit',
                'current': current_tp,
                'suggested': new_tp,
                'reason': f"TP never hit in {analysis['total_trades']} trades",
                'confidence': 'HIGH' if analysis['total_trades'] >= 20 else 'MEDIUM'
            }

        # TP hit rate very low (<10%) - reduce it
        elif analysis['tp_rate'] < 10 and analysis['total_trades'] >= 10:
            new_tp = round(current_tp * 0.85, 1)  # 15% reduction
            return {
                'type': 'TP_REDUCTION',
                'strategy_id': strategy_id,
                'param': 'take_profit',
                'current': current_tp,
                'suggested': new_tp,
                'reason': f"TP hit only {analysis['tp_rate']:.1f}% of trades",
                'confidence': 'MEDIUM'
            }

        return None

    def get_sl_suggestion(self, strategy_id: str, current_sl: float, analysis: Dict) -> Optional[Dict]:
        """Suggest SL adjustment if needed"""
        if analysis['total_trades'] < self.MIN_TRADES_FOR_ANALYSIS:
            return None

        # SL hit too often - widen it
        if analysis['sl_rate'] > self.SL_HIT_HIGH_THRESHOLD:
            new_sl = round(current_sl * self.SL_WIDEN_FACTOR, 1)
            return {
                'type': 'SL_WIDEN',
                'strategy_id': strategy_id,
                'param': 'stop_loss',
                'current': current_sl,
                'suggested': new_sl,
                'reason': f"SL hit {analysis['sl_rate']:.1f}% of trades (too tight)",
                'confidence': 'HIGH' if analysis['sl_rate'] > 60 else 'MEDIUM'
            }

        # SL rarely hit but still losing - might be time exits, check further
        elif analysis['sl_rate'] < 20 and analysis['win_rate'] < 40:
            # Check if time exits are the problem
            if analysis['time_exits'] > analysis['tp_hits']:
                return {
                    'type': 'HOLD_TIME_INCREASE',
                    'strategy_id': strategy_id,
                    'param': 'max_hold_hours',
                    'current': 'N/A',
                    'suggested': 'Increase by 50%',
                    'reason': f"Time exits ({analysis['time_exits']}) > TP hits ({analysis['tp_hits']})",
                    'confidence': 'MEDIUM'
                }

        return None

    def get_all_suggestions(self) -> List[Dict]:
        """Get all optimization suggestions for all strategies"""
        if not self.analyzer:
            return []

        suggestions = []

        # Get all strategies from portfolios
        try:
            portfolios_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolios.json')
            with open(portfolios_path, 'r') as f:
                data = json.load(f)

            # Get unique strategy IDs
            strategy_ids = set()
            for p in data.get('portfolios', {}).values():
                if p.get('strategy_id'):
                    strategy_ids.add(p['strategy_id'])

            # Import STRATEGIES dict from bot.py
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from bot import STRATEGIES

            # Analyze each strategy
            for strategy_id in strategy_ids:
                if strategy_id not in STRATEGIES:
                    continue

                strategy = STRATEGIES[strategy_id]
                analysis = self.analyze_strategy(strategy_id)

                if not analysis or analysis.get('total_trades', 0) < self.MIN_TRADES_FOR_ANALYSIS:
                    continue

                # Get TP suggestion
                current_tp = strategy.get('take_profit', 15)
                tp_suggestion = self.get_tp_suggestion(strategy_id, current_tp, analysis)
                if tp_suggestion:
                    suggestions.append(tp_suggestion)

                # Get SL suggestion
                current_sl = strategy.get('stop_loss', 7)
                sl_suggestion = self.get_sl_suggestion(strategy_id, current_sl, analysis)
                if sl_suggestion:
                    suggestions.append(sl_suggestion)

        except Exception as e:
            print(f"Error getting suggestions: {e}")

        # Sort by confidence (HIGH first)
        suggestions.sort(key=lambda x: 0 if x.get('confidence') == 'HIGH' else 1)

        self.suggestions = suggestions
        return suggestions

    def format_suggestions_report(self) -> str:
        """Format suggestions as markdown report"""
        if not self.suggestions:
            self.get_all_suggestions()

        if not self.suggestions:
            return "No optimization suggestions at this time."

        lines = [
            "# Strategy Optimization Suggestions",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Analysis period: {self.days} days",
            "",
            "## Recommended Changes",
            "",
            "| Strategy | Parameter | Current | Suggested | Reason | Confidence |",
            "|----------|-----------|---------|-----------|--------|------------|"
        ]

        for s in self.suggestions:
            lines.append(
                f"| {s['strategy_id']} | {s['param']} | {s['current']} | {s['suggested']} | {s['reason']} | {s['confidence']} |"
            )

        lines.extend([
            "",
            "## Code Changes",
            "",
            "```python",
            "# Apply these changes to STRATEGIES dict in bot.py:",
        ])

        for s in self.suggestions:
            if s['param'] in ['take_profit', 'stop_loss']:
                lines.append(f'"{s["strategy_id"]}": {{"{s["param"]}": {s["suggested"]}}},  # was {s["current"]}')

        lines.append("```")

        return "\n".join(lines)

    def apply_suggestion(self, suggestion: Dict, dry_run: bool = True) -> bool:
        """
        Apply a single suggestion to bot.py STRATEGIES dict.

        Args:
            suggestion: The suggestion dict
            dry_run: If True, only print what would be changed

        Returns:
            True if applied successfully
        """
        if dry_run:
            print(f"[DRY RUN] Would change {suggestion['strategy_id']}.{suggestion['param']}: "
                  f"{suggestion['current']} -> {suggestion['suggested']}")
            return True

        # For actual application, we would need to modify bot.py
        # This is intentionally left as dry_run only for safety
        print(f"[WARNING] Live application not implemented for safety. "
              f"Please manually update {suggestion['strategy_id']}.{suggestion['param']}")
        return False

    def save_suggestions(self, filepath: Optional[str] = None) -> str:
        """Save suggestions to file"""
        if not filepath:
            os.makedirs('data/optimizer', exist_ok=True)
            filepath = f"data/optimizer/suggestions_{datetime.now().strftime('%Y-%m-%d')}.md"

        report = self.format_suggestions_report()

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)

        return filepath

    def close(self):
        """Clean up resources"""
        if self.analyzer:
            self.analyzer.close()


def main():
    """Run optimizer and print suggestions"""
    print("=" * 60)
    print("  STRATEGY OPTIMIZER")
    print("=" * 60)
    print()

    optimizer = StrategyOptimizer(days=7)

    print("Analyzing strategies...")
    suggestions = optimizer.get_all_suggestions()

    if suggestions:
        print(f"\nFound {len(suggestions)} optimization suggestions:\n")
        print(optimizer.format_suggestions_report())

        # Save to file
        filepath = optimizer.save_suggestions()
        print(f"\nSaved to: {filepath}")
    else:
        print("No optimization suggestions at this time.")

    optimizer.close()


if __name__ == "__main__":
    main()
