#!/usr/bin/env python
"""
Strategy Optimizer CLI
======================
Analyzes strategy performance and suggests optimizations.

Usage:
    python optimize_strategies.py              # Generate suggestions
    python optimize_strategies.py --days 14   # Analyze last 14 days
    python optimize_strategies.py --apply     # Apply suggestions (dry run)
"""

import sys
import argparse

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from core.strategy_optimizer import StrategyOptimizer


def main():
    parser = argparse.ArgumentParser(description='Optimize trading strategies')
    parser.add_argument('--days', type=int, default=7, help='Days to analyze (default: 7)')
    parser.add_argument('--apply', action='store_true', help='Apply suggestions (dry run)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Only output filename')
    args = parser.parse_args()

    print("=" * 60)
    print("  STRATEGY OPTIMIZER")
    print("=" * 60)
    print()

    try:
        optimizer = StrategyOptimizer(days=args.days)

        if not args.quiet:
            print(f"Analyzing last {args.days} day(s)...")
            print()

        suggestions = optimizer.get_all_suggestions()

        if suggestions:
            if not args.quiet:
                print(f"Found {len(suggestions)} optimization suggestions:")
                print()
                print(optimizer.format_suggestions_report())

            # Save report
            filepath = optimizer.save_suggestions()

            if args.quiet:
                print(filepath)
            else:
                print(f"\nReport saved to: {filepath}")

            # Apply if requested
            if args.apply:
                print("\n" + "=" * 60)
                print("  APPLYING SUGGESTIONS (DRY RUN)")
                print("=" * 60)
                for s in suggestions:
                    optimizer.apply_suggestion(s, dry_run=True)
        else:
            print("No optimization suggestions at this time.")
            print("This could mean:")
            print("  - Not enough trade data (need at least 5 trades per strategy)")
            print("  - Strategies are performing within acceptable parameters")
            print("  - Analysis period is too short")

        optimizer.close()
        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
