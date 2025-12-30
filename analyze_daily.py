#!/usr/bin/env python
"""
Daily Strategy Analysis Script
==============================
Generates a comprehensive analysis report for Claude to suggest improvements.

Usage:
    python analyze_daily.py              # Generate and display report
    python analyze_daily.py --save       # Save to file only
    python analyze_daily.py --days 7     # Analyze last 7 days
"""

import sys
import argparse
from datetime import datetime

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from core.strategy_analyzer import StrategyAnalyzer


def main():
    parser = argparse.ArgumentParser(description='Generate daily trading analysis report')
    parser.add_argument('--save', action='store_true', help='Save report to file')
    parser.add_argument('--days', type=int, default=1, help='Days to analyze (default: 1)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Only output filename')
    args = parser.parse_args()

    print("=" * 60)
    print("  STRATEGY ANALYZER - Daily Report Generator")
    print("=" * 60)
    print()

    try:
        analyzer = StrategyAnalyzer()

        if not args.quiet:
            print(f"Analyzing last {args.days} day(s)...")
            print()

        report = analyzer.generate_report(days=args.days)

        # Save report
        filename = analyzer.save_report(report)

        if args.quiet:
            print(filename)
        else:
            print(f"Report saved to: {filename}")
            print()

            if not args.save:
                print("=" * 60)
                print("  REPORT CONTENT")
                print("=" * 60)
                print()
                print(report)

        analyzer.close()

        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
