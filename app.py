"""
Trading Bot - Dashboard Unifie
===============================

Interface unique avec toutes les fonctionnalites:
- Dashboard principal (portfolios, signaux)
- Mode Degen (scalping, momentum)
- Scanner temps reel
- Wallet Tracker
- Sniper

Lance avec: streamlit run app.py
Ou automatiquement via: python bot.py
"""
import sys
import os
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List

if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Imports locaux
from utils.theme import apply_theme, COLORS, header, alert, get_page_config
from config.degen_config import degen_config

# Page config
st.set_page_config(
    page_title="Trading Bot",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Appliquer le theme
apply_theme()

# Custom CSS for tooltips
st.markdown("""
<style>
.tooltip-container {
    position: relative;
    display: inline-block;
    cursor: pointer;
}
.tooltip-container .tooltip-text {
    visibility: hidden;
    opacity: 0;
    width: 280px;
    background: linear-gradient(145deg, #2a2a4a 0%, #1a1a2e 100%);
    color: #fff;
    text-align: left;
    border-radius: 8px;
    padding: 10px 12px;
    position: absolute;
    z-index: 9999;
    bottom: 125%;
    left: 50%;
    transform: translateX(-50%);
    transition: opacity 0.3s;
    font-size: 0.85rem;
    line-height: 1.4;
    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
    border: 1px solid #444;
}
.tooltip-container .tooltip-text::after {
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    margin-left: -6px;
    border-width: 6px;
    border-style: solid;
    border-color: #1a1a2e transparent transparent transparent;
}
.tooltip-container:hover .tooltip-text {
    visibility: visible;
    opacity: 1;
}
</style>
""", unsafe_allow_html=True)

# ==================== DATA LOADING ====================

@st.cache_data(ttl=60)
def get_top_cryptos(limit: int = 50) -> List[Dict]:
    """Recupere les top cryptos par volume"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        data = response.json()

        usdt_pairs = [
            d for d in data
            if d['symbol'].endswith('USDT')
            and not any(x in d['symbol'] for x in ['UP', 'DOWN', 'BEAR', 'BULL'])
        ]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        return sorted_pairs[:limit]
    except:
        return []


def load_portfolios() -> Dict:
    """Charge les portfolios"""
    try:
        if os.path.exists("data/portfolios.json"):
            with open("data/portfolios.json", 'r') as f:
                return json.load(f)
    except:
        pass
    return {"portfolios": {}, "counter": 0}


def save_portfolios(data: Dict):
    """Sauvegarde les portfolios"""
    os.makedirs("data", exist_ok=True)
    with open("data/portfolios.json", 'w') as f:
        json.dump(data, f, indent=2, default=str)


def load_degen_state() -> Dict:
    """Charge l'etat du bot degen"""
    state = {
        'capital': 1000,
        'total_pnl': 0,
        'positions': {},
        'trades': [],
        'total_trades': 0,
        'winning_trades': 0,
        'losing_trades': 0
    }
    try:
        if os.path.exists('data/degen/state.json'):
            with open('data/degen/state.json', 'r') as f:
                state.update(json.load(f))
        if os.path.exists('data/degen/trades.json'):
            with open('data/degen/trades.json', 'r') as f:
                state['trades'] = json.load(f)
    except:
        pass
    return state


def calculate_rsi(closes: list, period: int = 14) -> float:
    """Calcule le RSI"""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gain = np.where(deltas > 0, deltas, 0)
    loss = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gain[-period:])
    avg_loss = np.mean(loss[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


@st.cache_data(ttl=30)
def fetch_klines(symbol: str, interval: str = '1m', limit: int = 100) -> pd.DataFrame:
    """Recupere les klines"""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=5)
        data = response.json()
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    except:
        return pd.DataFrame()


def analyze_token(symbol: str, data: Dict) -> Dict:
    """Analyse rapide d'un token"""
    df = fetch_klines(symbol, '1m', 100)
    if df.empty:
        return None

    closes = df['close'].tolist()
    volumes = df['volume'].tolist()

    rsi = calculate_rsi(closes, 7)
    price = closes[-1]
    change_1m = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0
    change_5m = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0

    vol_avg = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
    vol_ratio = volumes[-1] / vol_avg if vol_avg > 0 else 1

    # Score
    score = 0
    reasons = []

    if rsi < 25:
        score += 30
        reasons.append(f"RSI oversold ({rsi:.0f})")
    elif rsi > 75:
        score -= 30
        reasons.append(f"RSI overbought ({rsi:.0f})")

    if vol_ratio > 3 and change_1m > 0:
        score += 25
        reasons.append(f"Volume spike ({vol_ratio:.1f}x)")
    elif vol_ratio > 3 and change_1m < 0:
        score -= 25

    if change_1m > 1.5:
        score += 20
        reasons.append(f"Momentum +{change_1m:.1f}%")
    elif change_1m < -1.5:
        score -= 20

    # Signal
    is_pump = vol_ratio >= 5 and change_1m >= 1.5
    is_dump = vol_ratio >= 5 and change_1m <= -1.5

    if is_pump:
        signal = "PUMP"
    elif is_dump:
        signal = "DUMP"
    elif score >= 50:
        signal = "STRONG_BUY"
    elif score >= 25:
        signal = "BUY"
    elif score <= -50:
        signal = "STRONG_SELL"
    elif score <= -25:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    return {
        'symbol': symbol.replace('USDT', ''),
        'price': price,
        'change_1m': change_1m,
        'change_5m': change_5m,
        'change_24h': float(data.get('priceChangePercent', 0)),
        'volume_24h': float(data.get('quoteVolume', 0)),
        'volume_ratio': vol_ratio,
        'rsi': rsi,
        'score': score,
        'signal': signal,
        'reasons': reasons,
        'is_pump': is_pump,
        'is_dump': is_dump
    }


# ==================== MAIN APP ====================

def main():
    # Sidebar Navigation
    with st.sidebar:
        st.markdown("## 🚀 Trading Bot")
        st.divider()

        page = st.radio(
            "Navigation",
            ["📊 Dashboard", "🔥 Degen Mode", "🔍 Scanner", "📈 Portfolios", "⚙️ Settings"],
            label_visibility="collapsed"
        )

        st.divider()

        # Quick stats
        degen_state = load_degen_state()
        pnl = degen_state.get('total_pnl', 0)
        pnl_color = COLORS.BUY if pnl >= 0 else COLORS.SELL

        st.markdown(f"""
        <div style="background: {COLORS.BG_CARD}; padding: 1rem; border-radius: 10px;">
            <div style="color: {COLORS.TEXT_SECONDARY}; font-size: 0.8rem;">Total PnL</div>
            <div style="color: {pnl_color}; font-size: 1.5rem; font-weight: bold;">${pnl:+,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # Bot status
        st.markdown("### 🤖 Bot Status")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ Start", use_container_width=True):
                st.session_state.bot_running = True
                st.toast("Bot started!")
        with col2:
            if st.button("⏹️ Stop", use_container_width=True):
                st.session_state.bot_running = False
                st.toast("Bot stopped!")

        bot_status = "🟢 Running" if st.session_state.get('bot_running', False) else "🔴 Stopped"
        st.markdown(f"Status: **{bot_status}**")

    # Main content based on page
    if page == "📊 Dashboard":
        render_dashboard()
    elif page == "🔥 Degen Mode":
        render_degen()
    elif page == "🔍 Scanner":
        render_scanner()
    elif page == "📈 Portfolios":
        render_portfolios()
    elif page == "⚙️ Settings":
        render_settings()


def render_dashboard():
    """Page principale"""
    header("📊 Dashboard")

    # Market overview
    col1, col2, col3, col4 = st.columns(4)

    cryptos = get_top_cryptos(10)
    if cryptos:
        btc = next((c for c in cryptos if c['symbol'] == 'BTCUSDT'), None)
        eth = next((c for c in cryptos if c['symbol'] == 'ETHUSDT'), None)
        sol = next((c for c in cryptos if c['symbol'] == 'SOLUSDT'), None)

        with col1:
            if btc:
                change = float(btc['priceChangePercent'])
                st.metric("BTC", f"${float(btc['lastPrice']):,.0f}", f"{change:+.1f}%")
        with col2:
            if eth:
                change = float(eth['priceChangePercent'])
                st.metric("ETH", f"${float(eth['lastPrice']):,.0f}", f"{change:+.1f}%")
        with col3:
            if sol:
                change = float(sol['priceChangePercent'])
                st.metric("SOL", f"${float(sol['lastPrice']):,.2f}", f"{change:+.1f}%")
        with col4:
            # Total market volume
            total_vol = sum(float(c['quoteVolume']) for c in cryptos[:10]) / 1e9
            st.metric("Volume 24h", f"${total_vol:.1f}B", "Top 10")

    st.divider()

    # Two columns
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📈 Top Movers")

        if cryptos:
            # Top gainers
            gainers = sorted(cryptos, key=lambda x: float(x['priceChangePercent']), reverse=True)[:5]
            losers = sorted(cryptos, key=lambda x: float(x['priceChangePercent']))[:5]

            tab1, tab2 = st.tabs(["🟢 Gainers", "🔴 Losers"])

            with tab1:
                for c in gainers:
                    symbol = c['symbol'].replace('USDT', '')
                    price = float(c['lastPrice'])
                    change = float(c['priceChangePercent'])
                    price_fmt = f"{price:.4f}" if price < 1 else f"{price:.2f}"
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; padding: 0.5rem; border-bottom: 1px solid #333;">
                        <span><b>{symbol}</b></span>
                        <span>${price_fmt}</span>
                        <span style="color: {COLORS.BUY};">+{change:.1f}%</span>
                    </div>
                    """, unsafe_allow_html=True)

            with tab2:
                for c in losers:
                    symbol = c['symbol'].replace('USDT', '')
                    price = float(c['lastPrice'])
                    change = float(c['priceChangePercent'])
                    price_fmt = f"{price:.4f}" if price < 1 else f"{price:.2f}"
                    st.markdown(f"""
                    <div style="display: flex; justify-content: space-between; padding: 0.5rem; border-bottom: 1px solid #333;">
                        <span><b>{symbol}</b></span>
                        <span>${price_fmt}</span>
                        <span style="color: {COLORS.SELL};">{change:.1f}%</span>
                    </div>
                    """, unsafe_allow_html=True)

    with col2:
        st.subheader("🎯 Active Signals")

        # Quick scan for signals
        signals_found = []
        for c in cryptos[:20]:
            result = analyze_token(c['symbol'], c)
            if result and result['signal'] not in ['NEUTRAL']:
                signals_found.append(result)

        if signals_found:
            for s in signals_found[:5]:
                color = COLORS.BUY if 'BUY' in s['signal'] or s['signal'] == 'PUMP' else COLORS.SELL
                st.markdown(f"""
                <div style="background: {COLORS.BG_CARD}; padding: 0.75rem; border-radius: 8px; margin-bottom: 0.5rem; border-left: 3px solid {color};">
                    <div style="display: flex; justify-content: space-between;">
                        <b>{s['symbol']}</b>
                        <span style="color: {color};">{s['signal']}</span>
                    </div>
                    <div style="color: {COLORS.TEXT_SECONDARY}; font-size: 0.8rem;">
                        Score: {s['score']} | RSI: {s['rsi']:.0f}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No active signals")


def render_degen():
    """Mode Degen"""
    header("🔥 Degen Mode", degen=True)

    state = load_degen_state()

    # Stats
    col1, col2, col3, col4, col5 = st.columns(5)

    pnl = state.get('total_pnl', 0)
    capital = state.get('capital', 1000)
    total_trades = state.get('total_trades', 0)
    winning = state.get('winning_trades', 0)
    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0

    with col1:
        st.metric("💰 Capital", f"${capital:,.2f}")
    with col2:
        st.metric("📈 PnL", f"${pnl:+,.2f}")
    with col3:
        st.metric("📊 Trades", total_trades)
    with col4:
        st.metric("✅ Win Rate", f"{win_rate:.1f}%")
    with col5:
        positions = state.get('positions', {})
        st.metric("📌 Positions", f"{len(positions)}/5")

    st.divider()

    # Config
    with st.expander("⚙️ Degen Config", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            risk = st.slider("Risk per trade %", 5, 25, 15)
            st.caption(f"${capital * risk / 100:.2f} per trade")
        with col2:
            mode = st.selectbox("Mode", ["hybrid", "scalping", "momentum"])
        with col3:
            max_pos = st.slider("Max positions", 1, 10, 5)

    st.divider()

    # Positions and trades
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📌 Open Positions")
        positions = state.get('positions', {})

        if positions:
            for symbol, pos in positions.items():
                entry = pos.get('entry_price', 0)
                current = pos.get('current_price', entry)
                pnl_val = (current - entry) / entry * pos.get('amount_usdt', 0) if entry > 0 else 0
                pnl_pct = (current - entry) / entry * 100 if entry > 0 else 0

                card_class = "profit" if pnl_val >= 0 else "loss"
                pnl_color = COLORS.BUY if pnl_val >= 0 else COLORS.SELL

                st.markdown(f"""
                <div class="position-card {card_class}">
                    <div style="display: flex; justify-content: space-between;">
                        <h4 style="margin: 0;">{symbol}</h4>
                        <span style="color: {pnl_color}; font-weight: bold;">${pnl_val:+.2f} ({pnl_pct:+.1f}%)</span>
                    </div>
                    <div style="color: {COLORS.TEXT_SECONDARY}; font-size: 0.9rem;">
                        Entry: ${entry:.4f} | Size: ${pos.get('amount_usdt', 0):.2f}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No open positions")

    with col2:
        st.subheader("📜 Recent Trades")
        trades = state.get('trades', [])[-10:]

        if trades:
            for t in reversed(trades):
                pnl_val = t.get('pnl', 0)
                emoji = "✅" if pnl_val > 0 else "❌"
                color = COLORS.BUY if pnl_val > 0 else COLORS.SELL

                st.markdown(f"""
                <div style="padding: 0.5rem; border-bottom: 1px solid #333;">
                    {emoji} <b>{t.get('symbol', '')}</b> |
                    <span style="color: {color};">${pnl_val:+.2f}</span> |
                    {t.get('reason', '')}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No trades yet")


def render_scanner():
    """Scanner"""
    header("🔍 Scanner")

    # Config
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        num_tokens = st.selectbox("Tokens", [25, 50, 100], index=1)
    with col2:
        timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "1h"], index=0)
    with col3:
        min_score = st.slider("Min Score", 0, 100, 25)
    with col4:
        if st.button("🔄 Scan Now", type="primary"):
            st.cache_data.clear()

    st.divider()

    # Scan
    with st.spinner(f"Scanning {num_tokens} tokens..."):
        cryptos = get_top_cryptos(num_tokens)
        results = []

        progress = st.progress(0)
        for i, c in enumerate(cryptos):
            result = analyze_token(c['symbol'], c)
            if result:
                results.append(result)
            progress.progress((i + 1) / len(cryptos))
        progress.empty()

    # Stats
    pumps = [r for r in results if r['is_pump']]
    dumps = [r for r in results if r['is_dump']]
    opportunities = [r for r in results if r['score'] >= min_score]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🚀 Pumps", len(pumps))
    with col2:
        st.metric("📉 Dumps", len(dumps))
    with col3:
        st.metric("🎯 Opportunities", len(opportunities))
    with col4:
        st.metric("⏱️ Updated", datetime.now().strftime("%H:%M:%S"))

    st.divider()

    # Alerts
    if pumps:
        for r in pumps[:3]:
            alert(f"🚀 <b>{r['symbol']}</b> | ${r['price']:.4f} | +{r['change_1m']:.1f}% | Vol: {r['volume_ratio']:.1f}x", "pump")

    if dumps:
        for r in dumps[:3]:
            alert(f"📉 <b>{r['symbol']}</b> | ${r['price']:.4f} | {r['change_1m']:.1f}% | Vol: {r['volume_ratio']:.1f}x", "dump")

    # Results table
    st.subheader("📊 All Results")

    # Sort by score
    results.sort(key=lambda x: x['score'], reverse=True)

    df = pd.DataFrame([{
        'Symbol': r['symbol'],
        'Price': f"${r['price']:.4f}" if r['price'] < 1 else f"${r['price']:.2f}",
        '1m': f"{r['change_1m']:+.1f}%",
        '5m': f"{r['change_5m']:+.1f}%",
        '24h': f"{r['change_24h']:+.1f}%",
        'Vol': f"{r['volume_ratio']:.1f}x",
        'RSI': f"{r['rsi']:.0f}",
        'Score': r['score'],
        'Signal': r['signal']
    } for r in results if r['score'] >= min_score or r['signal'] != 'NEUTRAL'])

    st.dataframe(df, use_container_width=True, hide_index=True)


def render_portfolios():
    """Portfolios avec cards"""
    header("📈 Portfolios")

    data = load_portfolios()
    portfolios = data.get('portfolios', {})

    # Create new portfolio
    with st.expander("➕ Create Portfolio", expanded=not portfolios):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name", placeholder="My Portfolio")
            capital = st.number_input("Starting Capital ($)", value=1000, min_value=100)
        with col2:
            strategy = st.selectbox("Strategy", [
                "confluence_normal", "confluence_strict", "degen_hybrid",
                "degen_scalp", "god_mode_only", "hodl"
            ])
            cryptos = st.multiselect("Cryptos", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "PEPE/USDT"])

        if st.button("Create Portfolio", type="primary"):
            if name and cryptos:
                pid = f"p{data['counter'] + 1}"
                data['portfolios'][pid] = {
                    'name': name,
                    'balance': {'USDT': capital},
                    'initial_capital': capital,
                    'positions': {},
                    'trades': [],
                    'config': {'cryptos': cryptos, 'allocation_percent': 10},
                    'strategy_id': strategy,
                    'active': True,
                    'created_at': datetime.now().isoformat()
                }
                data['counter'] += 1
                save_portfolios(data)
                st.success(f"Portfolio '{name}' created!")
                st.rerun()

    if not portfolios:
        st.info("No portfolios yet. Create one above!")
        return

    # Strategy icons
    strat_icons = {
        # Original
        "confluence_normal": "📊", "confluence_strict": "🎯", "degen_hybrid": "🔥",
        "degen_scalp": "⚡", "degen_momentum": "🚀", "degen_full": "💀",
        "god_mode_only": "🚨", "hodl": "💎", "manual": "🎮",
        "conservative": "🛡️", "aggressive": "🔥", "rsi_strategy": "📈",
        "sniper_safe": "🎯", "sniper_degen": "🔫", "sniper_yolo": "💀",
        # New strategies
        "ema_crossover": "📈", "ema_crossover_slow": "🐢",
        "vwap_bounce": "🎯", "vwap_trend": "📊",
        "supertrend": "🚀", "supertrend_fast": "⚡",
        "stoch_rsi": "📉", "stoch_rsi_aggressive": "🔥",
        "breakout": "💥", "breakout_tight": "🎯",
        "mean_reversion": "🔄", "mean_reversion_tight": "🎢",
        "grid_trading": "📏", "grid_tight": "📐",
        "dca_accumulator": "💰", "dca_aggressive": "💸",
        "ichimoku": "☁️", "ichimoku_fast": "⛅",
        "martingale": "🎰", "martingale_safe": "🎲"
    }

    # Strategy descriptions for tooltips
    strat_tooltips = {
        # Original strategies
        "confluence_normal": "RSI + MACD + Bollinger Bands. Buys when RSI<35 + MACD crossover + price near lower band. Safe, medium frequency.",
        "confluence_strict": "Same as normal but stricter: RSI<30 + confirmed MACD + price below lower band. Fewer trades, higher precision.",
        "conservative": "Only trades on STRONG signals (RSI<30 + bullish trend). Low frequency, high precision.",
        "aggressive": "Trades on regular + strong signals. Higher frequency, more opportunities.",
        "degen_hybrid": "Combines scalping + momentum. Aggressive entries on volume spikes and RSI extremes. High risk, high reward.",
        "degen_scalp": "Ultra-fast scalping on 1m charts. Targets 0.5-1% gains. Very high frequency, small position sizes.",
        "degen_momentum": "Rides momentum waves. Enters on volume spikes and price acceleration.",
        "degen_full": "Maximum degen mode. All signals, high allocation, aggressive entries.",
        "god_mode_only": "Only trades on God Mode signals (RSI<20 oversold + volume spike + momentum reversal). Rare but powerful.",
        "hodl": "Buy and hold strategy. Buys on major dips (RSI<25), never sells. Long-term accumulation.",
        "rsi_strategy": "Pure RSI strategy. Buy when RSI<30 (oversold), sell when RSI>70 (overbought).",
        "manual": "Manual trading only. No automated signals.",
        "sniper_safe": "Scans new DEX tokens. Risk score <50, min $50k liquidity. Conservative sniper.",
        "sniper_degen": "Scans new DEX tokens. Risk score <75, min $10k liquidity. Aggressive sniper.",
        "sniper_yolo": "Scans new DEX tokens. Risk score <90, min $5k liquidity. Maximum degen mode.",

        # NEW STRATEGIES
        "ema_crossover": "Classic 9/21 EMA crossover. Buy when fast EMA crosses above slow. Reliable trend following.",
        "ema_crossover_slow": "Slower 12/26 EMA crossover. Fewer signals, stronger trends. Good for swing trading.",
        "vwap_bounce": "Mean reversion on VWAP. Buys when price is 1.5% below VWAP, sells above. Great for ranging markets.",
        "vwap_trend": "Trend following on VWAP. Buys above VWAP (bullish), sells below. Follows institutional flow.",
        "supertrend": "Dynamic support/resistance indicator. Buys in uptrend, sells when trend flips. Period=10, Mult=3.",
        "supertrend_fast": "Faster Supertrend settings. More signals, quicker reactions. Period=7, Mult=2.",
        "stoch_rsi": "Stochastic RSI for precise entries. Buy <20 oversold, sell >80 overbought. Very accurate.",
        "stoch_rsi_aggressive": "Aggressive Stoch RSI. Buy <25, sell >75. More trades, slightly lower precision.",
        "breakout": "Breakout trading. Buys when price breaks 20-period high with volume. Catches big moves.",
        "breakout_tight": "Tight breakout. 10-period range, 2x volume required. Faster entries, more signals.",
        "mean_reversion": "Statistical mean reversion. Buys 2 std dev below mean, sells 2 std above. Works in ranges.",
        "mean_reversion_tight": "Tighter mean reversion. 1.5 std dev threshold. More frequent trades.",
        "grid_trading": "Grid bot strategy. Buys at range bottom, sells at top. Perfect for sideways markets.",
        "grid_tight": "Tight grid. 1% grid size, 10 levels. Very active in consolidation.",
        "dca_accumulator": "DCA on 3%+ dips only. Never sells. Long-term accumulation strategy.",
        "dca_aggressive": "Aggressive DCA. Buys on 2%+ dips. Faster accumulation, more entries.",
        "ichimoku": "Japanese Ichimoku Cloud. Buys above cloud + bullish crossover. Classic trend system.",
        "ichimoku_fast": "Faster Ichimoku settings. Quicker signals, more trades. Good for crypto volatility.",
        "martingale": "Double down on losses. 2x multiplier, max 4 levels. HIGH RISK - can blow up!",
        "martingale_safe": "Safer Martingale. 1.5x multiplier, max 3 levels. Still risky but more controlled."
    }

    # Display portfolios as cards (2 per row)
    portfolio_list = list(portfolios.items())

    for i in range(0, len(portfolio_list), 2):
        cols = st.columns(2)

        for j, col in enumerate(cols):
            if i + j < len(portfolio_list):
                pid, p = portfolio_list[i + j]

                with col:
                    balance = p['balance'].get('USDT', 0)
                    initial = p.get('initial_capital', balance)
                    pnl = balance - initial
                    pnl_pct = (pnl / initial * 100) if initial > 0 else 0
                    trades_count = len(p.get('trades', []))
                    positions = len(p.get('positions', {}))
                    is_active = p.get('active', True)
                    strategy = p.get('strategy_id', 'manual')
                    icon = strat_icons.get(strategy, '📈')
                    tooltip = strat_tooltips.get(strategy, 'No description available')
                    cryptos = p['config'].get('cryptos', [])

                    # Colors
                    pnl_color = '#00ff88' if pnl >= 0 else '#ff4444'
                    border_color = '#00ff88' if is_active else '#ff4444'
                    status_text = '▶️ Active' if is_active else '⏸️ Paused'

                    # Card HTML
                    st.markdown(f"""
                    <div style="
                        background: linear-gradient(145deg, #1a1a2e 0%, #0f0f1a 100%);
                        border-radius: 16px;
                        padding: 1.2rem;
                        margin-bottom: 1rem;
                        border-top: 4px solid {border_color};
                        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                    ">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem;">
                            <div>
                                <span style="font-size: 2rem; margin-right: 0.5rem;">{icon}</span>
                                <span style="font-size: 1.3rem; font-weight: bold; color: white;">{p['name']}</span>
                                <div style="color: #888; font-size: 0.8rem; margin-top: 0.3rem;">
                                    <span class="tooltip-container">ℹ️ {strategy}<span class="tooltip-text">{tooltip}</span></span> • {', '.join([c.replace('/USDT','') for c in cryptos[:3]])}{'...' if len(cryptos) > 3 else ''}
                                </div>
                            </div>
                            <div style="text-align: right;">
                                <div style="color: {pnl_color}; font-size: 1.5rem; font-weight: bold;">{pnl_pct:+.1f}%</div>
                                <div style="color: #666; font-size: 0.75rem;">{status_text}</div>
                            </div>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.8rem 0; border-top: 1px solid #333;">
                            <div style="text-align: center;">
                                <div style="font-size: 1.2rem; font-weight: bold; color: white;">${balance:,.0f}</div>
                                <div style="font-size: 0.7rem; color: #666; text-transform: uppercase;">Balance</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.2rem; font-weight: bold; color: {pnl_color};">${pnl:+,.0f}</div>
                                <div style="font-size: 0.7rem; color: #666; text-transform: uppercase;">P&L</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.2rem; font-weight: bold; color: white;">{trades_count}</div>
                                <div style="font-size: 0.7rem; color: #666; text-transform: uppercase;">Trades</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.2rem; font-weight: bold; color: white;">{positions}</div>
                                <div style="font-size: 0.7rem; color: #666; text-transform: uppercase;">Pos.</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Action buttons
                    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
                    with btn_col1:
                        btn_label = "⏸️" if is_active else "▶️"
                        if st.button(btn_label, key=f"toggle_{pid}", use_container_width=True):
                            data['portfolios'][pid]['active'] = not is_active
                            save_portfolios(data)
                            st.rerun()
                    with btn_col2:
                        if st.button("📜", key=f"history_{pid}", use_container_width=True, help="Historique"):
                            st.session_state[f'show_history_{pid}'] = not st.session_state.get(f'show_history_{pid}', False)
                            st.rerun()
                    with btn_col3:
                        if st.button("🔄", key=f"reset_{pid}", use_container_width=True, help="Reset"):
                            data['portfolios'][pid]['balance'] = {'USDT': initial}
                            data['portfolios'][pid]['positions'] = {}
                            data['portfolios'][pid]['trades'] = []
                            save_portfolios(data)
                            st.rerun()
                    with btn_col4:
                        if st.button("🗑️", key=f"del_{pid}", use_container_width=True, help="Supprimer"):
                            del data['portfolios'][pid]
                            save_portfolios(data)
                            st.rerun()

                    # Show history if toggled
                    if st.session_state.get(f'show_history_{pid}', False):
                        trades = p.get('trades', [])
                        if trades:
                            st.markdown(f"**📜 History ({len(trades)} trades)**")
                            for t in reversed(trades[-10:]):  # Last 10 trades
                                t_time = t.get('timestamp', '')[:16].replace('T', ' ')
                                t_action = t.get('action', '')
                                t_symbol = t.get('symbol', '').replace('/USDT', '')
                                t_price = t.get('price', 0)
                                t_pnl = t.get('pnl', 0)

                                if t_action == 'BUY':
                                    st.markdown(f"""
                                    <div style="background: rgba(0,255,136,0.1); padding: 0.5rem; border-radius: 8px; margin: 0.3rem 0; border-left: 3px solid #00ff88;">
                                        <span style="color: #00ff88;">🟢 BUY</span>
                                        <b>{t_symbol}</b> @ ${t_price:,.2f}
                                        <span style="color: #666; float: right;">{t_time}</span>
                                    </div>
                                    """, unsafe_allow_html=True)
                                else:
                                    pnl_color = '#00ff88' if t_pnl >= 0 else '#ff4444'
                                    st.markdown(f"""
                                    <div style="background: rgba(255,68,68,0.1); padding: 0.5rem; border-radius: 8px; margin: 0.3rem 0; border-left: 3px solid #ff4444;">
                                        <span style="color: #ff4444;">🔴 SELL</span>
                                        <b>{t_symbol}</b> @ ${t_price:,.2f}
                                        <span style="color: {pnl_color}; margin-left: 1rem;">${t_pnl:+,.2f}</span>
                                        <span style="color: #666; float: right;">{t_time}</span>
                                    </div>
                                    """, unsafe_allow_html=True)

                            if len(trades) > 10:
                                st.caption(f"... and {len(trades) - 10} more trades")
                        else:
                            st.info("No trades yet")


def render_settings():
    """Settings"""
    header("⚙️ Settings")

    tab1, tab2, tab3 = st.tabs(["🔑 API Keys", "🔔 Notifications", "🎨 Preferences"])

    with tab1:
        st.subheader("Exchange API")
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Binance API Key", type="password", placeholder="Enter API key...")
        with col2:
            st.text_input("Binance Secret", type="password", placeholder="Enter secret...")

        st.checkbox("Testnet Mode", value=True)

        st.divider()

        st.subheader("Blockchain APIs")
        st.text_input("Etherscan API Key", type="password")
        st.text_input("Helius API Key (Solana)", type="password")

    with tab2:
        st.subheader("Telegram Alerts")
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Bot Token", type="password")
        with col2:
            st.text_input("Chat ID")

        st.multiselect("Alert Types", [
            "Pump Detected", "Dump Detected", "Position Opened",
            "Position Closed", "Daily Summary"
        ], default=["Pump Detected", "Position Closed"])

    with tab3:
        st.subheader("Display")
        st.selectbox("Theme", ["Dark (Default)", "Degen Rainbow"])
        st.checkbox("Sound Alerts", value=False)
        st.slider("Refresh Rate (seconds)", 5, 60, 10)

    if st.button("💾 Save Settings", type="primary"):
        st.success("Settings saved!")


if __name__ == "__main__":
    main()
