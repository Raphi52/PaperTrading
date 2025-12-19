"""
Demo du Trading Bot - Sans API keys
===================================

Ce script montre comment fonctionne le systeme de confluence
en utilisant des donnees simulees.
"""
import sys
import os

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from signals.technical import TechnicalAnalyzer, Signal
from signals.sentiment import SentimentAnalyzer
from signals.onchain import OnChainAnalyzer
from signals.godmode import GodModeDetector, GodModeLevel
from core.confluence import ConfluenceEngine, TradeAction
from utils.logger import logger


def generate_sample_ohlcv(days: int = 30, trend: str = 'bullish') -> pd.DataFrame:
    """Génère des données OHLCV simulées"""
    np.random.seed(42)

    dates = pd.date_range(end=datetime.now(), periods=days * 24, freq='H')

    # Prix de base
    if trend == 'bullish':
        base_price = 40000 + np.cumsum(np.random.randn(len(dates)) * 100 + 20)
    elif trend == 'bearish':
        base_price = 50000 + np.cumsum(np.random.randn(len(dates)) * 100 - 20)
    else:
        base_price = 45000 + np.cumsum(np.random.randn(len(dates)) * 100)

    # OHLCV
    data = {
        'open': base_price + np.random.randn(len(dates)) * 50,
        'high': base_price + abs(np.random.randn(len(dates)) * 100),
        'low': base_price - abs(np.random.randn(len(dates)) * 100),
        'close': base_price + np.random.randn(len(dates)) * 50,
        'volume': np.random.uniform(1000, 5000, len(dates))
    }

    df = pd.DataFrame(data, index=dates)
    df['high'] = df[['open', 'close', 'high']].max(axis=1)
    df['low'] = df[['open', 'close', 'low']].min(axis=1)

    return df


async def demo_technical_analysis():
    """Démo de l'analyse technique"""
    print("\n" + "=" * 60)
    print("📊 DEMO: ANALYSE TECHNIQUE")
    print("=" * 60)

    analyzer = TechnicalAnalyzer()

    # Test avec différentes tendances
    for trend in ['bullish', 'bearish', 'neutral']:
        print(f"\n--- Tendance: {trend.upper()} ---")
        df = generate_sample_ohlcv(30, trend)

        result = analyzer.analyze(df)

        print(f"Signal: {result.signal.name}")
        print(f"Score: {result.score}/100")
        print(f"RSI: {result.rsi:.1f} ({result.rsi_signal.name})")
        print(f"MACD: {result.macd_signal.name}")
        print(f"Bollinger: {result.bb_signal.name}")
        print(f"EMA: {result.ema_signal.name}")
        print(f"Volume: {result.volume_signal.name}")


async def demo_sentiment_analysis():
    """Démo de l'analyse de sentiment"""
    print("\n" + "=" * 60)
    print("😊 DEMO: ANALYSE DE SENTIMENT")
    print("=" * 60)

    analyzer = SentimentAnalyzer()

    print("\nFetching Fear & Greed Index...")
    result = await analyzer.analyze("BTC")

    print(f"Fear & Greed Index: {result.fear_greed_index}")
    print(f"Social Score: {result.social_score}")
    print(f"Global Score: {result.score}")
    print(f"Signal: {'+1 (BUY)' if result.signal > 0 else ('-1 (SELL)' if result.signal < 0 else '0 (NEUTRAL)')}")

    if result.fear_greed_index < 25:
        print("💡 Extreme Fear = BUY opportunity (contrarian)")
    elif result.fear_greed_index > 75:
        print("💡 Extreme Greed = SELL signal (contrarian)")


async def demo_onchain_analysis():
    """Démo de l'analyse on-chain"""
    print("\n" + "=" * 60)
    print("⛓️ DEMO: ANALYSE ON-CHAIN")
    print("=" * 60)

    analyzer = OnChainAnalyzer()

    print("\nFetching on-chain metrics...")
    result = await analyzer.analyze("BTC")

    print(f"Whale Activity: {result.whale_activity}")
    print(f"Exchange Flow: {result.exchange_flow}")
    print(f"Score: {result.score}")
    print(f"Signal: {'+1 (BUY)' if result.signal > 0 else ('-1 (SELL)' if result.signal < 0 else '0 (NEUTRAL)')}")


async def demo_godmode():
    """Démo du détecteur God Mode"""
    print("\n" + "=" * 60)
    print("🚨 DEMO: GOD MODE DETECTOR")
    print("=" * 60)

    detector = GodModeDetector()

    # Simuler différents scénarios de prix
    scenarios = [
        {"price": 95000, "description": "Prix près de l'ATH"},
        {"price": 45000, "description": "Prix modéré (-50% de l'ATH)"},
        {"price": 25000, "description": "Crash sévère (-70% de l'ATH)"},
    ]

    for scenario in scenarios:
        print(f"\n--- {scenario['description']} (${scenario['price']:,}) ---")

        result = await detector.detect(scenario['price'])

        level_emoji = {
            GodModeLevel.INACTIVE: "⚪",
            GodModeLevel.WARMING_UP: "🟡",
            GodModeLevel.ACTIVATED: "🟢",
            GodModeLevel.EXTREME: "🚨"
        }

        emoji = level_emoji.get(result.level, "⚪")
        print(f"{emoji} Level: {result.level.name}")
        print(f"Score: {result.score}/100")
        print(f"Conditions: {result.conditions_met}/{result.total_conditions}")
        print(f"Recommended Allocation: {result.recommended_allocation}%")
        print(f"Assets: {', '.join(result.recommended_assets)}")

        # Afficher les conditions
        print("\nConditions check:")
        for c in result.conditions[:5]:  # Afficher les 5 premières
            status = "✅" if c.is_met else "❌"
            print(f"  {status} {c.name}: {c.value:.2f} (threshold: {c.threshold})")

    print("\n💡 God Mode EXTREME = Cycle bottom détecté = Accumulation maximale")
    print("💡 Ces conditions sont RARES (1-2x par cycle crypto de 4 ans)")


async def demo_confluence():
    """Démo complète de confluence"""
    print("\n" + "=" * 60)
    print("🎯 DEMO: CONFLUENCE ENGINE")
    print("=" * 60)

    engine = ConfluenceEngine()

    # Générer des données
    df = generate_sample_ohlcv(30, 'bullish')

    print("\nRunning full confluence analysis...")
    result = await engine.analyze(df, "BTC")

    print(f"\n{'=' * 40}")
    print(f"CONFLUENCE RESULT")
    print(f"{'=' * 40}")

    action_emoji = {
        TradeAction.STRONG_BUY: "🟢🟢",
        TradeAction.BUY: "🟢",
        TradeAction.HOLD: "⚪",
        TradeAction.SELL: "🔴",
        TradeAction.STRONG_SELL: "🔴🔴",
        TradeAction.GOD_MODE_BUY: "🚨🚨🚨"
    }

    print(f"Action: {action_emoji.get(result.action, '')} {result.action.value}")
    print(f"Confidence: {result.confidence}%")
    print(f"Signals Aligned: {result.signals_aligned}/3")
    print(f"")
    print(f"Technical: {'+1' if result.technical_signal > 0 else ('-1' if result.technical_signal < 0 else '0')}")
    print(f"Sentiment: {'+1' if result.sentiment_signal > 0 else ('-1' if result.sentiment_signal < 0 else '0')}")
    print(f"On-Chain:  {'+1' if result.onchain_signal > 0 else ('-1' if result.onchain_signal < 0 else '0')}")
    print(f"")

    # God Mode info
    if result.god_mode:
        print(f"God Mode: {result.god_mode.level.name} ({result.god_mode.score}/100)")
    if result.god_mode_active:
        print(f"🚨 GOD MODE ACTIVE! Recommended allocation: {result.recommended_allocation}%")
    print(f"")
    print(f"Reasoning: {result.reasoning}")


async def demo_trade_decision():
    """Simule plusieurs décisions de trading"""
    print("\n" + "=" * 60)
    print("💹 DEMO: SIMULATION DE DECISIONS")
    print("=" * 60)

    scenarios = [
        {"technical": 1, "sentiment": 1, "onchain": 1, "expected": "STRONG_BUY"},
        {"technical": 1, "sentiment": 1, "onchain": 0, "expected": "BUY"},
        {"technical": 1, "sentiment": 0, "onchain": 0, "expected": "HOLD"},
        {"technical": -1, "sentiment": -1, "onchain": -1, "expected": "STRONG_SELL"},
        {"technical": -1, "sentiment": -1, "onchain": 0, "expected": "SELL"},
        {"technical": 1, "sentiment": -1, "onchain": 0, "expected": "HOLD"},
    ]

    print("\n| Technical | Sentiment | On-Chain | Total | Decision |")
    print("|-----------|-----------|----------|-------|----------|")

    for s in scenarios:
        total = s['technical'] + s['sentiment'] + s['onchain']
        decision = s['expected']

        tech = f"+1" if s['technical'] > 0 else (f"-1" if s['technical'] < 0 else " 0")
        sent = f"+1" if s['sentiment'] > 0 else (f"-1" if s['sentiment'] < 0 else " 0")
        chain = f"+1" if s['onchain'] > 0 else (f"-1" if s['onchain'] < 0 else " 0")

        print(f"|    {tech}     |    {sent}     |    {chain}    |  {total:+d}   | {decision:^8} |")


async def main():
    """Run all demos"""
    print("""
    ============================================================
    |          TRADING BOT - DEMONSTRATION MODE                |
    |                                                          |
    |     Ce demo montre le fonctionnement du systeme          |
    |     sans necessiter de cles API                          |
    ============================================================
    """)

    # Créer le dossier data s'il n'existe pas
    import os
    os.makedirs('data', exist_ok=True)

    # Run demos
    await demo_technical_analysis()
    await demo_sentiment_analysis()
    await demo_onchain_analysis()
    await demo_godmode()
    await demo_confluence()
    await demo_trade_decision()

    print("\n" + "=" * 60)
    print("✅ DEMO COMPLETE!")
    print("=" * 60)
    print("\nProchaines étapes:")
    print("1. Copie .env.example vers .env")
    print("2. Ajoute tes clés API (Binance testnet)")
    print("3. Lance: python main.py")


if __name__ == "__main__":
    asyncio.run(main())
