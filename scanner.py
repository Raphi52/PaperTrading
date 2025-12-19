"""
Multi-Crypto Scanner - Detecte les opportunites sur des centaines de cryptos
=============================================================================

Lance avec: streamlit run scanner.py
"""
import sys
import os

if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

import streamlit as st
import pandas as pd
import numpy as np
import requests
import ccxt
from datetime import datetime, timedelta
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Page config
st.set_page_config(
    page_title="Crypto Scanner",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS
st.markdown("""
<style>
    .scanner-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #00d4ff, #7c3aed);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
    }
    .opportunity-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.5rem;
    }
    .buy-signal { border-left: 4px solid #00ff88; }
    .sell-signal { border-left: 4px solid #ff4444; }
    .neutral-signal { border-left: 4px solid #888888; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60)
def get_all_binance_symbols() -> list:
    """Recupere tous les symboles USDT de Binance"""
    try:
        url = "https://api.binance.com/api/v3/exchangeInfo"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            symbols = [
                s['symbol'] for s in data['symbols']
                if s['quoteAsset'] == 'USDT'
                and s['status'] == 'TRADING'
                and not any(x in s['symbol'] for x in ['UP', 'DOWN', 'BEAR', 'BULL'])
            ]
            return sorted(symbols)
    except:
        pass
    return []


@st.cache_data(ttl=30)
def get_top_cryptos(limit: int = 100) -> list:
    """Recupere les top cryptos par volume"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Filter USDT pairs and sort by volume
            usdt_pairs = [
                d for d in data
                if d['symbol'].endswith('USDT')
                and not any(x in d['symbol'] for x in ['UP', 'DOWN', 'BEAR', 'BULL'])
            ]
            sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
            return sorted_pairs[:limit]
    except:
        pass
    return []


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
    rsi = 100 - (100 / (1 + rs))
    return rsi


def analyze_crypto(symbol: str, klines: list) -> dict:
    """Analyse rapide d'une crypto"""
    if not klines or len(klines) < 50:
        return None

    closes = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]

    current_price = closes[-1]

    # RSI
    rsi = calculate_rsi(closes)

    # EMAs
    ema12 = pd.Series(closes).ewm(span=12).mean().iloc[-1]
    ema26 = pd.Series(closes).ewm(span=26).mean().iloc[-1]
    ema50 = pd.Series(closes).ewm(span=50).mean().iloc[-1] if len(closes) >= 50 else ema26

    # Price change
    change_1h = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else 0
    change_24h = ((closes[-1] - closes[-25]) / closes[-25] * 100) if len(closes) >= 25 else 0
    change_7d = ((closes[-1] - closes[-169]) / closes[-169] * 100) if len(closes) >= 169 else 0

    # Volume analysis
    avg_volume = np.mean(volumes[-20:])
    current_volume = volumes[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

    # Bollinger Bands
    sma20 = np.mean(closes[-20:])
    std20 = np.std(closes[-20:])
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20
    bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5

    # Signals
    signals = 0
    reasons = []

    # RSI signal
    if rsi < 30:
        signals += 1
        reasons.append(f"RSI oversold ({rsi:.0f})")
    elif rsi > 70:
        signals -= 1
        reasons.append(f"RSI overbought ({rsi:.0f})")

    # EMA signal
    if current_price > ema12 > ema26:
        signals += 1
        reasons.append("Bullish EMA")
    elif current_price < ema12 < ema26:
        signals -= 1
        reasons.append("Bearish EMA")

    # Bollinger signal
    if bb_position < 0.1:
        signals += 1
        reasons.append("Near BB lower")
    elif bb_position > 0.9:
        signals -= 1
        reasons.append("Near BB upper")

    # Volume signal
    if volume_ratio > 2:
        reasons.append(f"High volume ({volume_ratio:.1f}x)")

    # Determine signal strength
    if signals >= 2:
        signal = "STRONG_BUY"
        color = "#00ff88"
    elif signals == 1:
        signal = "BUY"
        color = "#88ff88"
    elif signals <= -2:
        signal = "STRONG_SELL"
        color = "#ff4444"
    elif signals == -1:
        signal = "SELL"
        color = "#ff8888"
    else:
        signal = "NEUTRAL"
        color = "#888888"

    return {
        'symbol': symbol.replace('USDT', ''),
        'price': current_price,
        'change_1h': change_1h,
        'change_24h': change_24h,
        'change_7d': change_7d,
        'rsi': rsi,
        'volume_ratio': volume_ratio,
        'bb_position': bb_position,
        'signal': signal,
        'signal_score': signals,
        'color': color,
        'reasons': reasons,
        'ema_trend': 'up' if ema12 > ema26 else 'down'
    }


@st.cache_data(ttl=60)
def fetch_klines(symbol: str, interval: str = '1h', limit: int = 200) -> list:
    """Recupere les klines pour un symbole"""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return []


def scan_cryptos(symbols: list, interval: str = '1h', progress_bar=None) -> list:
    """Scanne plusieurs cryptos"""
    results = []

    for i, sym_data in enumerate(symbols):
        symbol = sym_data['symbol'] if isinstance(sym_data, dict) else sym_data

        if progress_bar:
            progress_bar.progress((i + 1) / len(symbols), f"Scanning {symbol}...")

        klines = fetch_klines(symbol, interval)
        if klines:
            analysis = analyze_crypto(symbol, klines)
            if analysis:
                # Add 24h data from ticker
                if isinstance(sym_data, dict):
                    analysis['volume_24h'] = float(sym_data.get('quoteVolume', 0))
                    analysis['price'] = float(sym_data.get('lastPrice', analysis['price']))
                    analysis['change_24h'] = float(sym_data.get('priceChangePercent', analysis['change_24h']))
                results.append(analysis)

    return results


def main():
    st.markdown('<p class="scanner-header">🔍 Multi-Crypto Scanner</p>', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; color: #888;">Scanne des centaines de cryptos pour detecter les opportunites</p>', unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")

        scan_count = st.selectbox("Nombre de cryptos", [25, 50, 100, 200, 500], index=2)
        timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)

        st.divider()

        st.header("🎯 Filtres")
        min_volume = st.number_input("Volume min (M$)", value=1.0, step=1.0)

        signal_filter = st.multiselect(
            "Signaux",
            ["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"],
            default=["STRONG_BUY", "BUY"]
        )

        rsi_filter = st.slider("RSI Range", 0, 100, (0, 100))

        st.divider()

        auto_refresh = st.toggle("🔄 Auto-refresh", value=False)
        if auto_refresh:
            refresh_rate = st.select_slider("Frequence", [30, 60, 120, 300], value=60, format_func=lambda x: f"{x}s")

        scan_button = st.button("🔍 Scanner Maintenant", type="primary", use_container_width=True)

    # Main content
    if scan_button or 'scan_results' not in st.session_state:
        with st.spinner(f"Scanning {scan_count} cryptos..."):
            # Get top cryptos
            top_cryptos = get_top_cryptos(scan_count)

            if top_cryptos:
                progress = st.progress(0, "Demarrage du scan...")
                results = scan_cryptos(top_cryptos, timeframe, progress)
                progress.empty()

                st.session_state.scan_results = results
                st.session_state.scan_time = datetime.now()
            else:
                st.error("Impossible de recuperer les donnees")
                return

    results = st.session_state.get('scan_results', [])
    scan_time = st.session_state.get('scan_time', datetime.now())

    if not results:
        st.warning("Aucun resultat. Cliquez sur 'Scanner Maintenant'")
        return

    # Apply filters
    filtered = [
        r for r in results
        if r['signal'] in signal_filter
        and r.get('volume_24h', 0) >= min_volume * 1_000_000
        and rsi_filter[0] <= r['rsi'] <= rsi_filter[1]
    ]

    # Stats
    st.markdown(f"**{len(filtered)}** opportunites trouvees sur **{len(results)}** cryptos scannees | Derniere maj: {scan_time.strftime('%H:%M:%S')}")

    # Summary metrics
    col1, col2, col3, col4, col5 = st.columns(5)

    strong_buys = len([r for r in filtered if r['signal'] == 'STRONG_BUY'])
    buys = len([r for r in filtered if r['signal'] == 'BUY'])
    neutrals = len([r for r in filtered if r['signal'] == 'NEUTRAL'])
    sells = len([r for r in filtered if r['signal'] == 'SELL'])
    strong_sells = len([r for r in filtered if r['signal'] == 'STRONG_SELL'])

    with col1:
        st.metric("🟢🟢 Strong Buy", strong_buys)
    with col2:
        st.metric("🟢 Buy", buys)
    with col3:
        st.metric("⚪ Neutral", neutrals)
    with col4:
        st.metric("🔴 Sell", sells)
    with col5:
        st.metric("🔴🔴 Strong Sell", strong_sells)

    st.divider()

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Liste", "🎯 Top Opportunites", "📈 Heatmap"])

    with tab1:
        # Sort options
        sort_col, order_col = st.columns([2, 1])
        with sort_col:
            sort_by = st.selectbox("Trier par", ["Signal Score", "RSI", "Change 24h", "Volume", "Symbol"])
        with order_col:
            sort_order = st.selectbox("Ordre", ["Desc", "Asc"])

        # Sort
        sort_key = {
            "Signal Score": lambda x: x['signal_score'],
            "RSI": lambda x: x['rsi'],
            "Change 24h": lambda x: x['change_24h'],
            "Volume": lambda x: x.get('volume_24h', 0),
            "Symbol": lambda x: x['symbol']
        }[sort_by]

        sorted_results = sorted(filtered, key=sort_key, reverse=(sort_order == "Desc"))

        # Display as table
        if sorted_results:
            df = pd.DataFrame([{
                'Symbol': r['symbol'],
                'Price': f"${r['price']:.4f}" if r['price'] < 1 else f"${r['price']:.2f}",
                '24h %': f"{r['change_24h']:+.2f}%",
                'RSI': f"{r['rsi']:.0f}",
                'Volume': f"${r.get('volume_24h', 0)/1e6:.1f}M",
                'Signal': r['signal'],
                'Score': r['signal_score'],
                'Reasons': ', '.join(r['reasons'][:2])
            } for r in sorted_results])

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "24h %": st.column_config.TextColumn("24h %"),
                    "Signal": st.column_config.TextColumn("Signal"),
                    "Score": st.column_config.ProgressColumn("Score", min_value=-3, max_value=3, format="%d")
                }
            )

    with tab2:
        # Top opportunities
        top_buys = sorted([r for r in results if r['signal_score'] >= 2], key=lambda x: x['signal_score'], reverse=True)[:10]
        top_sells = sorted([r for r in results if r['signal_score'] <= -2], key=lambda x: x['signal_score'])[:10]

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 🟢 Top BUY Signals")
            for r in top_buys:
                st.markdown(f"""
                <div class="opportunity-card buy-signal">
                    <div style="display: flex; justify-content: space-between;">
                        <h4 style="margin: 0; color: white;">{r['symbol']}</h4>
                        <span style="color: #00ff88;">{r['signal']}</span>
                    </div>
                    <p style="color: #888; margin: 0.5rem 0;">${r['price']:.4f if r['price'] < 1 else r['price']:.2f} | RSI: {r['rsi']:.0f} | 24h: {r['change_24h']:+.1f}%</p>
                    <p style="color: #aaa; font-size: 0.8rem; margin: 0;">{', '.join(r['reasons'])}</p>
                </div>
                """, unsafe_allow_html=True)

            if not top_buys:
                st.info("Aucun signal STRONG_BUY actuellement")

        with col2:
            st.markdown("### 🔴 Top SELL Signals")
            for r in top_sells:
                st.markdown(f"""
                <div class="opportunity-card sell-signal">
                    <div style="display: flex; justify-content: space-between;">
                        <h4 style="margin: 0; color: white;">{r['symbol']}</h4>
                        <span style="color: #ff4444;">{r['signal']}</span>
                    </div>
                    <p style="color: #888; margin: 0.5rem 0;">${r['price']:.4f if r['price'] < 1 else r['price']:.2f} | RSI: {r['rsi']:.0f} | 24h: {r['change_24h']:+.1f}%</p>
                    <p style="color: #aaa; font-size: 0.8rem; margin: 0;">{', '.join(r['reasons'])}</p>
                </div>
                """, unsafe_allow_html=True)

            if not top_sells:
                st.info("Aucun signal STRONG_SELL actuellement")

    with tab3:
        # Heatmap of RSI and 24h change
        st.markdown("### Heatmap RSI vs Change 24h")

        fig = go.Figure()

        for r in results[:100]:  # Limit to 100 for performance
            color = '#00ff88' if r['signal_score'] > 0 else ('#ff4444' if r['signal_score'] < 0 else '#888888')
            size = 10 + abs(r['signal_score']) * 5

            fig.add_trace(go.Scatter(
                x=[r['rsi']],
                y=[r['change_24h']],
                mode='markers+text',
                marker=dict(size=size, color=color, opacity=0.7),
                text=[r['symbol']],
                textposition='top center',
                textfont=dict(size=8, color='white'),
                name=r['symbol'],
                hovertemplate=f"<b>{r['symbol']}</b><br>RSI: {r['rsi']:.0f}<br>24h: {r['change_24h']:+.2f}%<br>Signal: {r['signal']}<extra></extra>"
            ))

        fig.add_vrect(x0=0, x1=30, fillcolor="green", opacity=0.1, line_width=0)
        fig.add_vrect(x0=70, x1=100, fillcolor="red", opacity=0.1, line_width=0)
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.add_vline(x=30, line_dash="dash", line_color="green")
        fig.add_vline(x=70, line_dash="dash", line_color="red")

        fig.update_layout(
            template='plotly_dark',
            height=600,
            showlegend=False,
            xaxis_title="RSI",
            yaxis_title="Change 24h (%)",
            xaxis=dict(range=[0, 100]),
        )

        st.plotly_chart(fig, use_container_width=True)

        st.markdown("""
        **Lecture:**
        - 🟢 Zone verte (RSI < 30): Oversold = Opportunite d'achat
        - 🔴 Zone rouge (RSI > 70): Overbought = Opportunite de vente
        - Taille des points = Force du signal
        """)

    # Auto-refresh
    if auto_refresh:
        import time
        time.sleep(refresh_rate)
        st.rerun()


if __name__ == "__main__":
    main()
