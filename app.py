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


@st.cache_data(ttl=30)  # Cache prices for 30 seconds
def get_current_prices(symbols: List[str]) -> Dict[str, float]:
    """Fetch current prices for multiple symbols from Binance"""
    prices = {}
    try:
        # Get all prices in one API call
        url = "https://api.binance.com/api/v3/ticker/price"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            all_prices = {p['symbol']: float(p['price']) for p in response.json()}
            for symbol in symbols:
                binance_symbol = symbol.replace('/', '')
                if binance_symbol in all_prices:
                    prices[symbol] = all_prices[binance_symbol]
    except:
        pass
    return prices


def calculate_portfolio_value(portfolio: Dict) -> Dict:
    """
    Calculate total portfolio value including open positions at current prices.
    Returns dict with: total_value, usdt_balance, positions_value, unrealized_pnl, positions_details
    """
    usdt_balance = portfolio['balance'].get('USDT', 0)
    positions = portfolio.get('positions', {})

    if not positions:
        return {
            'total_value': usdt_balance,
            'usdt_balance': usdt_balance,
            'positions_value': 0,
            'unrealized_pnl': 0,
            'positions_details': []
        }

    # Get current prices for all positions
    symbols = list(positions.keys())
    current_prices = get_current_prices(symbols)

    positions_value = 0
    unrealized_pnl = 0
    positions_details = []

    for symbol, pos in positions.items():
        entry_price = pos.get('entry_price', 0)
        quantity = pos.get('quantity', 0)
        current_price = current_prices.get(symbol, entry_price)  # Fallback to entry if no price

        current_value = quantity * current_price
        cost_basis = quantity * entry_price
        pnl = current_value - cost_basis
        pnl_pct = ((current_price / entry_price) - 1) * 100 if entry_price > 0 else 0

        positions_value += current_value
        unrealized_pnl += pnl

        positions_details.append({
            'symbol': symbol,
            'quantity': quantity,
            'entry_price': entry_price,
            'current_price': current_price,
            'current_value': current_value,
            'pnl': pnl,
            'pnl_pct': pnl_pct
        })

    return {
        'total_value': usdt_balance + positions_value,
        'usdt_balance': usdt_balance,
        'positions_value': positions_value,
        'unrealized_pnl': unrealized_pnl,
        'positions_details': positions_details
    }


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

        # Bot status - Control ALL portfolios
        st.markdown("### 🤖 All Portfolios")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ All ON", use_container_width=True):
                pf_data = load_portfolios()
                for pid in pf_data.get('portfolios', {}):
                    pf_data['portfolios'][pid]['active'] = True
                save_portfolios(pf_data)
                st.toast("All portfolios activated!")
                st.rerun()
        with col2:
            if st.button("⏹️ All OFF", use_container_width=True):
                pf_data = load_portfolios()
                for pid in pf_data.get('portfolios', {}):
                    pf_data['portfolios'][pid]['active'] = False
                save_portfolios(pf_data)
                st.toast("All portfolios paused!")
                st.rerun()

        # Count active
        pf_data = load_portfolios()
        active_count = sum(1 for p in pf_data.get('portfolios', {}).values() if p.get('active', True))
        total_count = len(pf_data.get('portfolios', {}))
        st.markdown(f"Active: **{active_count}/{total_count}**")

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
        all_trades = state.get('trades', [])

        # Toggle for full history
        show_all = st.checkbox("📋 Show full history", key="show_all_trades")
        trades = all_trades if show_all else all_trades[-10:]

        if trades:
            if show_all and len(all_trades) > 20:
                # Use expander for large histories
                with st.expander(f"📜 All {len(all_trades)} trades", expanded=True):
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

    # Strategy descriptions for tooltips - BEGINNER FRIENDLY
    strat_tooltips = {
        "confluence_normal": """📊 CONFLUENCE NORMAL - Stratégie Équilibrée

🎓 C'EST QUOI ?
Cette stratégie combine plusieurs indicateurs techniques pour prendre des décisions.
Elle n'achète que quand PLUSIEURS signaux sont d'accord = moins d'erreurs.

📈 QUAND J'ACHÈTE ?
• Le RSI doit être < 35 (le RSI mesure si un actif est "survendu" - trop descendu trop vite)
• ET il faut un signal BUY ou STRONG_BUY des autres indicateurs

📉 QUAND JE VENDS ?
• Le RSI doit être > 65 (l'actif est "suracheté" - monté trop vite)
• ET il faut un signal SELL ou STRONG_SELL

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne (quelques par semaine)

💡 POUR QUI ?
Parfait pour débuter ! Bon équilibre entre prudence et opportunités.
Fonctionne bien quand le marché a des tendances claires (pas en range plat).""",

        "confluence_strict": """🎯 CONFLUENCE STRICT - Ultra Prudent

🎓 C'EST QUOI ?
Version TRÈS prudente de Confluence. Attend des conditions quasi-parfaites avant d'agir.
Moins de trades, mais quand ça trade, c'est souvent gagnant.

📈 QUAND J'ACHÈTE ?
• RSI < 30 (vraiment très survendu - opportunité rare)
• ET signal STRONG_BUY uniquement (pas de simple BUY)

📉 QUAND JE VENDS ?
• RSI > 70 (vraiment très suracheté)
• ET signal STRONG_SELL uniquement

⚖️ NIVEAU DE RISQUE: Faible
📊 FRÉQUENCE DES TRADES: Basse (quelques par mois)

💡 POUR QUI ?
Pour ceux qui préfèrent rater des opportunités plutôt que faire des erreurs.
Idéal si tu as un gros capital et que tu veux le protéger.""",

        "conservative": """🛡️ CONSERVATIVE - Protection Maximale

🎓 C'EST QUOI ?
La stratégie la plus prudente. Elle vérifie que la TENDANCE générale est bonne
avant d'acheter, même si le prix semble attractif.

📈 QUAND J'ACHÈTE ?
• RSI < 30 (prix survendu)
• ET la moyenne mobile rapide (EMA12) est AU-DESSUS de la lente (EMA26)
  → Ça confirme que la tendance de fond est haussière

📉 QUAND JE VENDS ?
• RSI > 70 (prix suracheté)
• ET EMA12 < EMA26 (tendance devient baissière)

⚖️ NIVEAU DE RISQUE: Très Faible
📊 FRÉQUENCE DES TRADES: Très Basse

💡 POUR QUI ?
Pour les investisseurs prudents avec un capital important.
Tu rates beaucoup d'opportunités, mais tu évites les pièges.""",

        "aggressive": """🔥 AGGRESSIVE - Plus de Trades, Plus d'Action

🎓 C'EST QUOI ?
L'opposé de Conservative. Entre plus tôt dans les trades, sort plus tôt aussi.
Capture plus de mouvements mais avec plus de risque.

📈 QUAND J'ACHÈTE ?
• RSI < 35 suffit (pas besoin d'attendre 30)
• Un léger signal d'achat déclenche l'entrée

📉 QUAND JE VENDS ?
• RSI > 65 (n'attend pas 70)
• Sort dès les premiers signes de faiblesse

⚖️ NIVEAU DE RISQUE: Élevé
📊 FRÉQUENCE DES TRADES: Haute

💡 POUR QUI ?
Pour ceux qui veulent plus d'action et acceptent plus de trades perdants.
Utilise des petites positions pour limiter le risque par trade.""",

        "rsi_strategy": """📈 RSI PURE - Simple et Classique

🎓 C'EST QUOI ?
Le RSI (Relative Strength Index) mesure la "force" d'un mouvement de prix.
• RSI < 30 = "Survendu" = le prix a trop baissé, potentiel rebond
• RSI > 70 = "Suracheté" = le prix a trop monté, potentielle correction

📈 QUAND J'ACHÈTE ?
• RSI < 30 → Le prix a beaucoup baissé, on anticipe un rebond

📉 QUAND JE VENDS ?
• RSI > 70 → Le prix a beaucoup monté, on prend nos profits

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Excellente stratégie pour apprendre ! Simple à comprendre.
Fonctionne très bien sur les altcoins qui font des cycles réguliers.

⚠️ ATTENTION
En tendance forte, le RSI peut rester suracheté/survendu longtemps !""",

        "hodl": """💎 HODL - Diamond Hands (Mains de Diamant)

🎓 C'EST QUOI ?
HODL = "Hold On for Dear Life" (tenir coûte que coûte)
Tu achètes UNE FOIS et tu ne vends JAMAIS. Point.

📈 QUAND J'ACHÈTE ?
• Une seule fois au début, puis plus jamais

📉 QUAND JE VENDS ?
• JAMAIS. Tu gardes pour toujours.

⚖️ NIVEAU DE RISQUE: Dépend de l'actif
📊 FRÉQUENCE DES TRADES: Une seule fois

💡 POUR QUI ?
Pour les "Bitcoin Maxis" et ceux qui croient au long terme.
Parfait pour BTC et ETH si tu crois qu'ils vaudront plus dans 5-10 ans.

🧠 PHILOSOPHIE
"Time in the market beats timing the market"
(Rester investi bat essayer de timer le marché)""",

        "god_mode_only": """🚨 GOD MODE - Opportunités Rares mais Puissantes

🎓 C'EST QUOI ?
Cette stratégie attend des conditions EXCEPTIONNELLES. Quand le marché panique
et que tout le monde vend, elle achète. Ça arrive rarement mais c'est souvent très rentable.

📈 QUAND J'ACHÈTE ?
• RSI < 20 (extrêmement survendu - panique totale)
• ET Volume 2x la moyenne (beaucoup de monde vend/achète)
• ET le prix commence à rebondir (confirmation)
• ET le prix est très loin de sa moyenne (anomalie statistique)

📉 QUAND JE VENDS ?
Conditions inversées: RSI > 80 + volume spike + prix chute

⚖️ NIVEAU DE RISQUE: Moyen (rares mais gros trades)
📊 FRÉQUENCE DES TRADES: Très Rare (1-2 par mois max)

💡 POUR QUI ?
Pour les patients. Tu peux attendre des semaines sans trader.
Quand ça trade, c'est souvent un gros gain.

💎 EXEMPLE HISTORIQUE
Les crashs de -20% en une journée, suivis de rebonds de +15%.""",

        "degen_scalp": """⚡ DEGEN SCALP - Trading Ultra-Rapide

🎓 C'EST QUOI ?
Le "scalping" consiste à faire plein de petits trades rapides.
On vise des gains de 0.5-1% répétés plutôt qu'un gros gain.

📈 QUAND J'ACHÈTE ?
• RSI < 25 (survendu)
• ET le prix commence à remonter (momentum positif > 0.3%)

📉 QUAND JE VENDS ?
• RSI > 75 avec momentum négatif
• OU dès que RSI > 55 (on sort vite pour sécuriser !)

⚖️ NIVEAU DE RISQUE: Élevé
📊 FRÉQUENCE DES TRADES: Très Haute

💡 POUR QUI ?
Pour les traders actifs qui aiment l'action.
Nécessite de petites positions car beaucoup de trades.

⚠️ ATTENTION
Les frais de trading peuvent manger les profits si trop de trades !""",

        "degen_momentum": """🚀 DEGEN MOMENTUM - Surfer les Vagues

🎓 C'EST QUOI ?
Le "momentum" = la force du mouvement. Cette stratégie saute dans les pumps
quand ils commencent et sort quand ils s'essoufflent.

📈 QUAND J'ACHÈTE ?
• Volume > 2x la moyenne (beaucoup d'intérêt soudain !)
• ET le prix monte de +1% en 1h (momentum positif)
• ET RSI < 65 (pas encore suracheté)

📉 QUAND JE VENDS ?
• Le momentum devient négatif
• OU volume spike avec chute de prix

⚖️ NIVEAU DE RISQUE: Élevé
📊 FRÉQUENCE DES TRADES: Moyenne-Haute

💡 POUR QUI ?
Pour ceux qui veulent attraper les pumps.
Fonctionne bien sur les news et annonces.

⚠️ ATTENTION
Tu peux acheter au sommet si tu arrives trop tard !""",

        "degen_hybrid": """🎯 DEGEN HYBRID - Le Meilleur des Deux Mondes

🎓 C'EST QUOI ?
Combine les signaux de SCALP et MOMENTUM.
Si l'un OU l'autre donne un signal, on trade.

📈 QUAND J'ACHÈTE ?
• Signal de scalp (RSI bas + rebond)
• OU signal de momentum (volume + pump)

📉 QUAND JE VENDS ?
• Signal de scalp OU momentum
• OU RSI > 70

⚖️ NIVEAU DE RISQUE: Élevé
📊 FRÉQUENCE DES TRADES: Haute

💡 POUR QUI ?
Pour les degens assumés qui veulent maximum d'opportunités.
Nécessite une bonne gestion du risque.""",

        "degen_full": """💀 FULL DEGEN - Maximum Risk Maximum Reward

🎓 C'EST QUOI ?
Comme HYBRID mais avec des positions 2x plus grosses (10% au lieu de 5%).
Moon or Rekt. Soit tu gagnes gros, soit tu perds gros.

📈 QUAND J'ACHÈTE ?
• Mêmes conditions que Hybrid
• Mais position de 10% du capital au lieu de 5%

📉 QUAND JE VENDS ?
• Mêmes conditions que Hybrid

⚖️ NIVEAU DE RISQUE: TRÈS ÉLEVÉ ⚠️
📊 FRÉQUENCE DES TRADES: Haute

💡 POUR QUI ?
Pour tester en paper trading ce que ça fait de trader comme un degen.
NE PAS UTILISER AVEC DE L'ARGENT RÉEL sans expérience !""",

        "manual": """🎮 MANUAL - Trading Manuel

Aucun trade automatique. Ce portfolio est là pour que tu puisses
tester des trades manuellement si tu veux.""",

        "sniper_safe": """🎯 SNIPER SAFE - Chasse aux Nouveaux Tokens (Prudent)

🎓 C'EST QUOI ?
Scanne automatiquement les NOUVEAUX tokens créés sur Solana (DexScreener, Pump.fun).
Achète les plus "sûrs" parmi les nouveaux tokens.

📈 QUAND J'ACHÈTE ?
• Token créé il y a moins de 24h
• Score de risque < 50 (relativement safe)
• Liquidité > $50,000 (assez pour pouvoir revendre)

📉 QUAND JE VENDS ?
• Take Profit: +100% (double ton argent)
• Stop Loss: -30% (limite les pertes)

⚖️ NIVEAU DE RISQUE: Élevé (même "safe" c'est risqué)
📊 FRÉQUENCE DES TRADES: Dépend des nouveaux tokens

💡 POUR QUI ?
Pour s'exposer aux memecoins avec des limites.
La plupart des nouveaux tokens vont à 0, mais certains font x10-x100.""",

        "sniper_degen": """🔫 SNIPER DEGEN - Chasse Agressive

🎓 C'EST QUOI ?
Comme Sniper Safe mais accepte plus de risque.
Plus de tokens achetés, plus de chances de trouver une pépite.

📈 QUAND J'ACHÈTE ?
• Token < 24h
• Score de risque < 75 (accepte plus de risque)
• Liquidité > $10,000 (minimum)

📉 QUAND JE VENDS ?
• Take Profit: +200% (triple ton argent)
• Stop Loss: -50%

⚖️ NIVEAU DE RISQUE: Très Élevé
📊 FRÉQUENCE DES TRADES: Haute

💡 POUR QUI ?
Pour les degen memecoin hunters.""",

        "sniper_yolo": """💀 SNIPER YOLO - Lottery Tickets

🎓 C'EST QUOI ?
Achète presque TOUS les nouveaux tokens. La plupart iront à 0.
Mais ceux qui réussissent peuvent faire x100.

📈 QUAND J'ACHÈTE ?
• Token < 12h (très nouveau)
• Score de risque < 90 (accepte quasi tout)
• Liquidité > $5,000 (minimum vital)

📉 QUAND JE VENDS ?
• Take Profit: +500% (x6 ton argent)
• Stop Loss: -80% (laisse courir longtemps)

⚖️ NIVEAU DE RISQUE: EXTRÊME ⚠️
📊 FRÉQUENCE DES TRADES: Très Haute

💡 POUR QUI ?
Pour tester avec un petit capital qu'on accepte de perdre.
C'est comme acheter des tickets de loterie.""",

        "ema_crossover": """📈 EMA CROSSOVER (9/21) - Trend Following Classique

🎓 C'EST QUOI ?
L'EMA (Exponential Moving Average) est une moyenne mobile qui suit le prix.
• EMA rapide (9 périodes) réagit vite aux changements
• EMA lente (21 périodes) montre la tendance de fond

Quand la rapide CROISE la lente, ça indique un changement de tendance !

📈 QUAND J'ACHÈTE ?
• EMA 9 croise AU-DESSUS de EMA 21 = "Golden Cross"
• → La tendance devient haussière

📉 QUAND JE VENDS ?
• EMA 9 croise EN-DESSOUS de EMA 21 = "Death Cross"
• → La tendance devient baissière

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Stratégie classique utilisée depuis des décennies !
Fonctionne bien en tendance, moins bien en range.""",

        "ema_crossover_slow": """🐢 EMA CROSSOVER SLOW (12/26) - Plus Patient

🎓 C'EST QUOI ?
Même principe que EMA Crossover mais avec des périodes plus longues.
Filtre le "bruit" et les faux signaux, mais entre plus tard.

📈 QUAND J'ACHÈTE ?
• EMA 12 croise au-dessus de EMA 26

📉 QUAND JE VENDS ?
• EMA 12 croise en-dessous de EMA 26

⚖️ NIVEAU DE RISQUE: Moyen-Faible
📊 FRÉQUENCE DES TRADES: Basse

💡 POUR QUI ?
Pour ceux qui préfèrent moins de trades mais plus fiables.
Bon pour le swing trading sur plusieurs jours/semaines.""",

        "vwap_bounce": """🎯 VWAP BOUNCE - Mean Reversion Institutionnelle

🎓 C'EST QUOI ?
Le VWAP (Volume Weighted Average Price) = prix moyen pondéré par le volume.
C'est LA référence utilisée par les institutions et gros traders.

• Prix SOUS le VWAP = "bon marché" relativement
• Prix AU-DESSUS du VWAP = "cher" relativement

📈 QUAND J'ACHÈTE ?
• Prix est 1.5% EN-DESSOUS du VWAP
• → On parie que le prix va revenir vers le VWAP

📉 QUAND JE VENDS ?
• Prix est 1.5% AU-DESSUS du VWAP
• → On prend profit car le prix est "cher"

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Excellent pour les marchés qui oscillent autour d'une moyenne.
Moins efficace en forte tendance.""",

        "vwap_trend": """📊 VWAP TREND - Suivre les Institutions

🎓 C'EST QUOI ?
Contrairement à VWAP Bounce, on SUIT la tendance.
Si le prix est au-dessus du VWAP, les acheteurs dominent = on achète.

📈 QUAND J'ACHÈTE ?
• Prix > VWAP + 0.5%
• → Les acheteurs sont en contrôle

📉 QUAND JE VENDS ?
• Prix < VWAP - 0.5%
• → Les vendeurs prennent le contrôle

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Pour les jours de tendance claire.
Suit le flux de l'argent institutionnel.""",

        "supertrend": """🚀 SUPERTREND - Support/Résistance Dynamique

🎓 C'EST QUOI ?
Le Supertrend est une LIGNE qui suit le prix :
• En tendance HAUSSIÈRE: la ligne est EN-DESSOUS du prix (support)
• En tendance BAISSIÈRE: la ligne est AU-DESSUS du prix (résistance)

Quand le prix CROISE cette ligne, la tendance change !

📈 QUAND J'ACHÈTE ?
• Le prix passe AU-DESSUS de la ligne Supertrend
• ET RSI < 70 (pas suracheté)
• → Nouvelle tendance haussière !

📉 QUAND JE VENDS ?
• Le prix passe EN-DESSOUS de la ligne Supertrend
• → La tendance devient baissière

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Très populaire chez les traders techniques.
Visuellement facile à suivre sur un graphique.""",

        "supertrend_fast": """⚡ SUPERTREND FAST - Version Rapide

🎓 C'EST QUOI ?
Même chose que Supertrend mais avec des paramètres plus sensibles.
Réagit plus vite aux changements = plus de signaux (et plus de bruit).

📈 QUAND J'ACHÈTE ?
• Prix > Supertrend (paramètres rapides)
• ET RSI < 70

📉 QUAND JE VENDS ?
• Prix < Supertrend

⚖️ NIVEAU DE RISQUE: Moyen-Élevé
📊 FRÉQUENCE DES TRADES: Haute

💡 POUR QUI ?
Pour le scalping ou les marchés très volatils.""",

        "stoch_rsi": """📉 STOCHASTIC RSI - Timing Précis

🎓 C'EST QUOI ?
Le Stochastic RSI applique la formule Stochastique AU RSI.
C'est le "RSI du RSI" = encore plus sensible aux retournements.

Échelle de 0 à 100:
• < 20 = Très survendu (opportunité d'achat)
• > 80 = Très suracheté (opportunité de vente)

📈 QUAND J'ACHÈTE ?
• StochRSI < 20

📉 QUAND JE VENDS ?
• StochRSI > 80

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne-Haute

💡 POUR QUI ?
Pour ceux qui veulent des entrées très précises.
Excellent pour timer les retournements.""",

        "stoch_rsi_aggressive": """🔥 STOCH RSI AGGRESSIVE - Plus de Trades

🎓 C'EST QUOI ?
Comme Stochastic RSI mais avec des seuils élargis.
Entre plus tôt, sort plus tôt = plus de trades.

📈 QUAND J'ACHÈTE ?
• StochRSI < 25 (au lieu de 20)

📉 QUAND JE VENDS ?
• StochRSI > 75 (au lieu de 80)

⚖️ NIVEAU DE RISQUE: Élevé
📊 FRÉQUENCE DES TRADES: Haute

💡 POUR QUI ?
Pour traders actifs qui veulent plus d'opportunités.""",

        "breakout": """💥 BREAKOUT - Casser les Résistances

🎓 C'EST QUOI ?
Le marché alterne entre CONSOLIDATION (range) et EXPANSION (tendance).
Cette stratégie attend qu'un range soit cassé pour entrer.

Un breakout est confirmé par le VOLUME (beaucoup de monde participe).

📈 QUAND J'ACHÈTE ?
• Le prix casse le PLUS HAUT des 20 dernières périodes
• ET le volume est > 1.5x la moyenne (confirmation)
• → Le marché part à la hausse !

📉 QUAND JE VENDS ?
• Le prix casse le PLUS BAS des 20 périodes + volume
• → Le marché part à la baisse

⚖️ NIVEAU DE RISQUE: Moyen-Élevé
📊 FRÉQUENCE DES TRADES: Basse-Moyenne

💡 POUR QUI ?
Pour attraper les gros mouvements après consolidation.
Attention aux "faux breakouts" !""",

        "breakout_tight": """🎯 BREAKOUT TIGHT - Breakouts Rapides

🎓 C'EST QUOI ?
Comme Breakout mais sur un range plus court (10 périodes).
Plus de signaux, entrées plus rapides.

📈 QUAND J'ACHÈTE ?
• Prix casse le high des 10 dernières périodes
• ET volume > 2x la moyenne (confirmation plus stricte)

📉 QUAND JE VENDS ?
• Prix casse le low des 10 périodes

⚖️ NIVEAU DE RISQUE: Élevé
📊 FRÉQUENCE DES TRADES: Haute

💡 POUR QUI ?
Pour scalper les petits breakouts.""",

        "mean_reversion": """🔄 MEAN REVERSION - Retour à la Moyenne

🎓 C'EST QUOI ?
Principe statistique: les prix extrêmes finissent par revenir vers leur moyenne.
Comme un élastique étiré qui revient à sa position normale.

On mesure l'écart en "écarts-types" (σ = sigma):
• 2σ sous la moyenne = très rare, probable rebond
• 2σ au-dessus = très rare, probable correction

📈 QUAND J'ACHÈTE ?
• Prix est 2 écarts-types EN-DESSOUS de la moyenne mobile 20

📉 QUAND JE VENDS ?
• Prix est 2 écarts-types AU-DESSUS de la moyenne

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Basse

💡 POUR QUI ?
Stratégie mathématique qui fonctionne bien en range.
Attention en forte tendance: le prix peut rester extrême !""",

        "mean_reversion_tight": """🎢 MEAN REVERSION TIGHT - Plus Sensible

🎓 C'EST QUOI ?
Comme Mean Reversion mais avec un seuil de 1.5σ au lieu de 2σ.
Entre plus tôt sur les dips = plus de trades.

📈 QUAND J'ACHÈTE ?
• Prix 1.5σ sous la moyenne

📉 QUAND JE VENDS ?
• Prix 1.5σ au-dessus

⚖️ NIVEAU DE RISQUE: Moyen-Élevé
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Pour marchés moins volatils où 2σ arrive rarement.""",

        "grid_trading": """📏 GRID TRADING - Robot de Range

🎓 C'EST QUOI ?
Imagine une grille dessinée sur le graphique.
Le bot achète en bas de la grille, vend en haut. Répète.

Parfait quand le marché fait du "ping-pong" entre deux niveaux.

📈 QUAND J'ACHÈTE ?
• Prix dans les 20% BAS du range (Bollinger Bands)

📉 QUAND JE VENDS ?
• Prix dans les 20% HAUT du range

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne-Haute

💡 POUR QUI ?
Excellent en marché latéral (sideways).
PERD DE L'ARGENT en tendance forte !

⚠️ ATTENTION
Si le marché casse le range à la baisse, tu te retrouves avec
des positions perdantes.""",

        "grid_tight": """📐 GRID TIGHT - Grille Serrée

🎓 C'EST QUOI ?
Comme Grid Trading mais avec une grille plus serrée.
Plus de petits trades = plus de petits profits.

📈 QUAND J'ACHÈTE ?
• Bottom 20% du range

📉 QUAND JE VENDS ?
• Top 80% du range

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Haute

💡 POUR QUI ?
Pour consolidations serrées.""",

        "dca_accumulator": """💰 DCA ACCUMULATOR - Accumuler sur les Dips

🎓 C'EST QUOI ?
DCA = Dollar Cost Averaging = acheter régulièrement.
Cette version n'achète QUE quand le prix baisse significativement.

📈 QUAND J'ACHÈTE ?
• Le prix a chuté de 3%+ en 24h
• → On profite des soldes !

📉 QUAND JE VENDS ?
• JAMAIS. On accumule pour le long terme.

⚖️ NIVEAU DE RISQUE: Faible (long terme)
📊 FRÉQUENCE DES TRADES: Basse (seulement sur les dips)

💡 POUR QUI ?
Pour construire une position long terme progressivement.
Parfait pour BTC/ETH si tu crois au futur des cryptos.

🧠 PHILOSOPHIE
"Buy the dip" - Acheter les corrections est statistiquement gagnant
sur le long terme dans un marché haussier.""",

        "dca_aggressive": """💸 DCA AGGRESSIVE - Accumulation Rapide

🎓 C'EST QUOI ?
Comme DCA Accumulator mais achète sur des dips plus petits.
Accumule plus vite.

📈 QUAND J'ACHÈTE ?
• Le prix a chuté de 2%+ en 24h (au lieu de 3%)

📉 QUAND JE VENDS ?
• JAMAIS

⚖️ NIVEAU DE RISQUE: Faible-Moyen
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Pour accumuler plus rapidement en bull market.""",

        "ichimoku": """☁️ ICHIMOKU CLOUD - Système Japonais Complet

🎓 C'EST QUOI ?
L'Ichimoku est un système d'analyse technique COMPLET inventé au Japon.
Il montre en un coup d'œil: tendance, momentum, support/résistance.

Composants clés:
• Tenkan (9): ligne rapide
• Kijun (26): ligne lente
• Kumo (nuage): zone de support/résistance

📈 QUAND J'ACHÈTE ?
• Prix > Tenkan > Kijun (alignement haussier)
• ET prix AU-DESSUS du nuage
• → Toutes les conditions sont bullish !

📉 QUAND JE VENDS ?
• Prix < Tenkan < Kijun (alignement baissier)

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Basse-Moyenne

💡 POUR QUI ?
Pour les traders qui veulent un système complet et éprouvé.
Très respecté par les professionnels.""",

        "ichimoku_fast": """⛅ ICHIMOKU FAST - Version Crypto

🎓 C'EST QUOI ?
Ichimoku avec des périodes raccourcies pour la crypto (plus volatile).
Réagit plus vite aux changements.

📈 QUAND J'ACHÈTE ?
• Tenkan(7) > Kijun(22) + above cloud

📉 QUAND JE VENDS ?
• Croisement baissier

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Pour adapter l'Ichimoku classique aux cryptos.""",

        "martingale": """🎰 MARTINGALE - Double ou Rien (DANGER!)

🎓 C'EST QUOI ?
Stratégie de casino appliquée au trading:
Après chaque PERTE, tu DOUBLES ta mise suivante.
L'idée: un seul gain efface toutes les pertes précédentes.

📈 QUAND J'ACHÈTE ?
• RSI < 35 (entrée normale)
• OU après une perte: RSI < 40 avec DOUBLE de la position !

📉 QUAND JE VENDS ?
• RSI > 65

⚠️⚠️⚠️ NIVEAU DE RISQUE: EXTRÊME ⚠️⚠️⚠️
📊 FRÉQUENCE DES TRADES: Variable

⚠️ DANGER EXTRÊME
Après 4 pertes consécutives, ta position est 16x la taille initiale !
Une mauvaise série peut EXPLOSER ton compte.

💡 POUR QUI ?
EN PAPER TRADING UNIQUEMENT pour comprendre pourquoi c'est dangereux.
Les casinos interdisent cette stratégie pour une raison !""",

        "martingale_safe": """🎲 MARTINGALE SAFE - Version "Moins Pire"

🎓 C'EST QUOI ?
Martingale avec des limites:
• Multiplie par 1.5x au lieu de 2x
• Maximum 3 niveaux au lieu de 4

📈 QUAND J'ACHÈTE ?
• RSI < 35
• OU après perte: 1.5x la position précédente

📉 QUAND JE VENDS ?
• RSI > 65

⚠️ NIVEAU DE RISQUE: Très Élevé
📊 FRÉQUENCE DES TRADES: Variable

⚠️ TOUJOURS DANGEREUX
Moins explosif que le Martingale normal mais reste très risqué.

💡 POUR QUI ?
Paper trading uniquement pour expérimenter."""
    }

    # Display portfolios as cards (2 per row)
    portfolio_list = list(portfolios.items())

    for i in range(0, len(portfolio_list), 2):
        cols = st.columns(2)

        for j, col in enumerate(cols):
            if i + j < len(portfolio_list):
                pid, p = portfolio_list[i + j]

                with col:
                    # Calculate real portfolio value including positions
                    pf_value = calculate_portfolio_value(p)
                    total_value = pf_value['total_value']
                    usdt_balance = pf_value['usdt_balance']
                    positions_value = pf_value['positions_value']
                    unrealized_pnl = pf_value['unrealized_pnl']

                    initial = p.get('initial_capital', 1000)
                    # Total PnL = (current total value - initial capital)
                    total_pnl = total_value - initial
                    pnl_pct = (total_pnl / initial * 100) if initial > 0 else 0

                    trades_count = len(p.get('trades', []))
                    positions_count = len(p.get('positions', {}))
                    is_active = p.get('active', True)
                    strategy = p.get('strategy_id', 'manual')
                    icon = strat_icons.get(strategy, '📈')
                    tooltip = strat_tooltips.get(strategy, 'No description available')
                    cryptos = p['config'].get('cryptos', [])

                    # Colors
                    pnl_color = '#00ff88' if total_pnl >= 0 else '#ff4444'
                    unrealized_color = '#00ff88' if unrealized_pnl >= 0 else '#ff4444'
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
                                    {strategy} • {', '.join([c.replace('/USDT','') for c in cryptos[:3]])}{'...' if len(cryptos) > 3 else ''}
                                </div>
                            </div>
                            <div style="text-align: right;">
                                <div style="color: {pnl_color}; font-size: 1.5rem; font-weight: bold;">{pnl_pct:+.1f}%</div>
                                <div style="color: #666; font-size: 0.75rem;">{status_text}</div>
                            </div>
                        </div>
                        <div style="display: flex; justify-content: space-between; padding: 0.8rem 0; border-top: 1px solid #333;">
                            <div style="text-align: center;">
                                <div style="font-size: 1.2rem; font-weight: bold; color: white;">${total_value:,.0f}</div>
                                <div style="font-size: 0.7rem; color: #666; text-transform: uppercase;">Total Value</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.2rem; font-weight: bold; color: {pnl_color};">${total_pnl:+,.0f}</div>
                                <div style="font-size: 0.7rem; color: #666; text-transform: uppercase;">P&L</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.2rem; font-weight: bold; color: white;">{trades_count}</div>
                                <div style="font-size: 0.7rem; color: #666; text-transform: uppercase;">Trades</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.2rem; font-weight: bold; color: white;">{positions_count}</div>
                                <div style="font-size: 0.7rem; color: #666; text-transform: uppercase;">Pos.</div>
                            </div>
                        </div>
                        {"" if positions_count == 0 else f'''
                        <div style="padding: 0.5rem 0; border-top: 1px solid #333; font-size: 0.75rem;">
                            <span style="color: #888;">💵 Cash: ${usdt_balance:,.0f}</span>
                            <span style="color: #888; margin-left: 1rem;">📊 In positions: ${positions_value:,.0f}</span>
                            <span style="color: {unrealized_color}; margin-left: 1rem;">📈 Unrealized: ${unrealized_pnl:+,.0f}</span>
                        </div>
                        '''}
                    </div>
                    """, unsafe_allow_html=True)

                    # Action buttons
                    btn_col1, btn_col2, btn_col3, btn_col4, btn_col5, btn_col6 = st.columns(6)
                    with btn_col1:
                        btn_label = "⏸️" if is_active else "▶️"
                        if st.button(btn_label, key=f"toggle_{pid}", use_container_width=True):
                            data['portfolios'][pid]['active'] = not is_active
                            save_portfolios(data)
                            st.rerun()
                    with btn_col2:
                        if st.button("ℹ️", key=f"info_{pid}", use_container_width=True):
                            st.session_state[f'show_info_{pid}'] = not st.session_state.get(f'show_info_{pid}', False)
                            st.rerun()
                    with btn_col3:
                        if st.button("📜", key=f"history_{pid}", use_container_width=True):
                            st.session_state[f'show_history_{pid}'] = not st.session_state.get(f'show_history_{pid}', False)
                            st.rerun()
                    with btn_col4:
                        if st.button("🔍", key=f"logs_{pid}", use_container_width=True):
                            st.session_state[f'show_logs_{pid}'] = not st.session_state.get(f'show_logs_{pid}', False)
                            st.rerun()
                    with btn_col5:
                        if st.button("🔄", key=f"reset_{pid}", use_container_width=True):
                            data['portfolios'][pid]['balance'] = {'USDT': initial}
                            data['portfolios'][pid]['positions'] = {}
                            data['portfolios'][pid]['trades'] = []
                            data['portfolios'][pid]['decision_logs'] = []
                            save_portfolios(data)
                            st.rerun()
                    with btn_col6:
                        if st.button("🗑️", key=f"del_{pid}", use_container_width=True):
                            del data['portfolios'][pid]
                            save_portfolios(data)
                            st.rerun()

                    # Show strategy info if toggled
                    if st.session_state.get(f'show_info_{pid}', False):
                        st.info(f"**{strategy}**: {tooltip}")

                    # Show history if toggled
                    if st.session_state.get(f'show_history_{pid}', False):
                        trades = p.get('trades', [])
                        if trades:
                            # Toggle for full history
                            col_hist1, col_hist2 = st.columns([3, 1])
                            with col_hist1:
                                st.markdown(f"**📜 History ({len(trades)} trades)**")
                            with col_hist2:
                                show_all_pf = st.checkbox("All", key=f"show_all_{pid}", value=False)

                            display_trades = trades if show_all_pf else trades[-10:]

                            # Scrollable container for many trades
                            if show_all_pf and len(trades) > 15:
                                st.markdown(f"""<div style="max-height: 400px; overflow-y: auto; padding-right: 10px;">""", unsafe_allow_html=True)

                            for t in reversed(display_trades):
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

                            if show_all_pf and len(trades) > 15:
                                st.markdown("</div>", unsafe_allow_html=True)

                            if not show_all_pf and len(trades) > 10:
                                st.caption(f"... and {len(trades) - 10} more trades (check 'All' to see)")
                        else:
                            st.info("No trades yet")

                    # Show positions detail when there are open positions
                    if positions_count > 0:
                        with st.expander(f"📊 Open Positions ({positions_count})", expanded=False):
                            for pos_detail in pf_value['positions_details']:
                                pos_symbol = pos_detail['symbol'].replace('/USDT', '')
                                pos_qty = pos_detail['quantity']
                                pos_entry = pos_detail['entry_price']
                                pos_current = pos_detail['current_price']
                                pos_value = pos_detail['current_value']
                                pos_pnl = pos_detail['pnl']
                                pos_pnl_pct = pos_detail['pnl_pct']
                                pos_color = '#00ff88' if pos_pnl >= 0 else '#ff4444'

                                st.markdown(f"""
                                <div style="background: rgba(255,255,255,0.05); padding: 0.8rem; border-radius: 8px; margin: 0.5rem 0; border-left: 3px solid {pos_color};">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <div>
                                            <span style="font-size: 1.1rem; font-weight: bold; color: white;">{pos_symbol}</span>
                                            <span style="color: #888; margin-left: 0.5rem; font-size: 0.8rem;">{pos_qty:.6f} tokens</span>
                                        </div>
                                        <div style="text-align: right;">
                                            <span style="color: {pos_color}; font-size: 1.1rem; font-weight: bold;">{pos_pnl_pct:+.2f}%</span>
                                            <span style="color: {pos_color}; margin-left: 0.5rem;">${pos_pnl:+.2f}</span>
                                        </div>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; margin-top: 0.5rem; font-size: 0.8rem; color: #888;">
                                        <span>Entry: ${pos_entry:,.4f}</span>
                                        <span>Current: ${pos_current:,.4f}</span>
                                        <span>Value: ${pos_value:,.2f}</span>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)

                    # Show decision logs if toggled
                    if st.session_state.get(f'show_logs_{pid}', False):
                        decision_logs = p.get('decision_logs', [])
                        if decision_logs:
                            st.markdown(f"**🔍 Decision Logs ({len(decision_logs)} entries)**")
                            st.caption("Shows what the bot analyzed and why it made (or didn't make) trades")

                            # Filter options
                            log_col1, log_col2 = st.columns([2, 1])
                            with log_col1:
                                filter_action = st.selectbox(
                                    "Filter by action",
                                    ["All", "BUY", "SELL", "HOLD"],
                                    key=f"log_filter_{pid}"
                                )
                            with log_col2:
                                show_all_logs = st.checkbox("Show all", key=f"logs_all_{pid}")

                            # Filter logs
                            filtered_logs = decision_logs
                            if filter_action != "All":
                                filtered_logs = [l for l in decision_logs if l.get('action') == filter_action]

                            display_logs = filtered_logs if show_all_logs else filtered_logs[-20:]

                            # Display logs in scrollable container
                            st.markdown("""<div style="max-height: 400px; overflow-y: auto;">""", unsafe_allow_html=True)

                            for log_entry in reversed(display_logs):
                                log_time = log_entry.get('timestamp', '')[-8:]  # Just time
                                log_symbol = log_entry.get('symbol', '?')
                                log_action = log_entry.get('action', 'HOLD')
                                log_reason = log_entry.get('reason', 'No reason')
                                log_rsi = log_entry.get('rsi', 50)
                                log_price = log_entry.get('price', 0)

                                # Color based on action
                                if log_action == 'BUY':
                                    action_color = '#00ff88'
                                    action_icon = '🟢'
                                elif log_action == 'SELL':
                                    action_color = '#ff4444'
                                    action_icon = '🔴'
                                else:
                                    action_color = '#888888'
                                    action_icon = '⚪'

                                st.markdown(f"""
                                <div style="background: rgba(255,255,255,0.03); padding: 0.6rem; border-radius: 6px; margin: 0.3rem 0; border-left: 3px solid {action_color};">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <div>
                                            <span style="color: {action_color}; font-weight: bold;">{action_icon} {log_action}</span>
                                            <span style="color: white; margin-left: 0.5rem; font-weight: bold;">{log_symbol}</span>
                                            <span style="color: #888; margin-left: 0.5rem;">${log_price:,.2f}</span>
                                        </div>
                                        <span style="color: #666; font-size: 0.75rem;">{log_time}</span>
                                    </div>
                                    <div style="color: #aaa; font-size: 0.8rem; margin-top: 0.3rem;">
                                        {log_reason}
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)

                            st.markdown("</div>", unsafe_allow_html=True)

                            if not show_all_logs and len(filtered_logs) > 20:
                                st.caption(f"Showing last 20 of {len(filtered_logs)} logs")
                        else:
                            st.info("No decision logs yet. Run the bot to generate logs.")
                            st.caption("Logs show: timestamp, symbol, action (BUY/SELL/HOLD), reason, and indicators")


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
