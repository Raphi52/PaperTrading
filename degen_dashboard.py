"""
Degen Dashboard - Interface Live pour le Trading Degen
======================================================

Dashboard Streamlit avec:
- Live feed des positions
- Scanner temps reel
- PnL tracker
- Alertes visuelles

Usage:
    streamlit run degen_dashboard.py
"""
import sys
import os
import json
import time
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

from config.degen_config import degen_config
from degen_scanner import DegenScanner, ScanResult
from utils.theme import apply_theme, get_page_config, COLORS, header, alert, position_card

# Page config - utilise le theme unifie
st.set_page_config(**get_page_config("degen"))

# Appliquer le theme unifie
apply_theme()


def load_bot_state() -> Dict:
    """Charge l'etat du bot depuis les fichiers"""
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
        # Load state
        if os.path.exists('data/degen/state.json'):
            with open('data/degen/state.json', 'r') as f:
                data = json.load(f)
                state.update(data)

        # Load trades
        if os.path.exists('data/degen/trades.json'):
            with open('data/degen/trades.json', 'r') as f:
                state['trades'] = json.load(f)

    except Exception as e:
        st.error(f"Error loading state: {e}")

    return state


def get_live_prices(symbols: List[str]) -> Dict[str, float]:
    """Recupere les prix en temps reel"""
    prices = {}
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        response = requests.get(url, timeout=5)
        data = response.json()

        for item in data:
            symbol = item['symbol'].replace('USDT', '')
            if symbol in symbols:
                prices[symbol] = float(item['price'])
    except:
        pass
    return prices


def main():
    # Header - utilise le theme unifie
    header("🔥 DEGEN DASHBOARD 🔥", degen=True)

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")

        # Mode selection
        mode = st.radio("Mode", ["Live Monitoring", "Scanner", "Backtest Results"])

        st.divider()

        # Scanner settings
        if mode == "Scanner":
            max_symbols = st.slider("Tokens to scan", 20, 100, 50)
            min_volume = st.number_input("Min volume ($M)", value=5.0, step=1.0)
            min_score = st.slider("Min score", 0, 100, 50)
            auto_refresh = st.toggle("Auto refresh", value=True)
            if auto_refresh:
                refresh_rate = st.slider("Refresh (s)", 5, 60, 10)

        st.divider()

        # Bot controls
        st.header("🤖 Bot Controls")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ Start", use_container_width=True):
                st.info("Start bot: python degen_bot.py")
        with col2:
            if st.button("⏹️ Stop", use_container_width=True):
                st.info("Press Ctrl+C in terminal")

        st.divider()

        # Quick actions
        st.header("⚡ Quick Actions")
        if st.button("📊 Open Scanner", use_container_width=True):
            st.info("Run: streamlit run degen_scanner.py")
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.rerun()

    # Main content based on mode
    if mode == "Live Monitoring":
        render_live_monitoring()
    elif mode == "Scanner":
        render_scanner(max_symbols, min_volume, min_score, auto_refresh, refresh_rate if auto_refresh else 30)
    else:
        render_backtest_results()


def render_live_monitoring():
    """Affiche le monitoring en temps reel"""
    state = load_bot_state()

    # Stats row
    col1, col2, col3, col4, col5 = st.columns(5)

    pnl = state.get('total_pnl', 0)
    capital = state.get('capital', 1000)
    win_rate = (state['winning_trades'] / state['total_trades'] * 100) if state['total_trades'] > 0 else 0

    with col1:
        st.metric("💰 Capital", f"${capital:,.2f}")
    with col2:
        st.metric("📈 Total PnL", f"${pnl:+,.2f}", delta=f"{pnl/10:.1f}%" if pnl != 0 else None)
    with col3:
        st.metric("📊 Trades", state['total_trades'])
    with col4:
        st.metric("✅ Win Rate", f"{win_rate:.1f}%")
    with col5:
        positions = state.get('positions', {})
        st.metric("📌 Positions", f"{len(positions)}/5")

    st.divider()

    # Two columns: Positions and Recent Trades
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📌 Open Positions")

        positions = state.get('positions', {})

        if positions:
            # Get live prices
            symbols = list(positions.keys())
            live_prices = get_live_prices(symbols)

            for symbol, pos in positions.items():
                entry_price = pos.get('entry_price', 0)
                amount = pos.get('amount_usdt', 0)
                current_price = live_prices.get(symbol, entry_price)

                pnl = (current_price - entry_price) / entry_price * amount if entry_price > 0 else 0
                pnl_pct = (current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0

                card_class = "profit" if pnl >= 0 else "loss"
                pnl_color = COLORS.BUY if pnl >= 0 else COLORS.SELL

                st.markdown(f"""
                <div class="position-card {card_class}">
                    <div style="display: flex; justify-content: space-between;">
                        <h3 style="margin: 0; color: white;">{symbol}</h3>
                        <span style="color: {pnl_color}; font-size: 1.2rem; font-weight: bold;">
                            ${pnl:+.2f} ({pnl_pct:+.1f}%)
                        </span>
                    </div>
                    <div style="color: #888; margin-top: 0.5rem;">
                        Entry: ${entry_price:.4f} | Current: ${current_price:.4f} | Size: ${amount:.2f}
                    </div>
                    <div style="color: #666; font-size: 0.8rem; margin-top: 0.3rem;">
                        SL: ${pos.get('stop_loss', 0):.4f} | TP: ${pos.get('take_profit', 0):.4f}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No open positions")

    with col2:
        st.subheader("📜 Recent Trades")

        trades = state.get('trades', [])
        recent_trades = trades[-10:] if trades else []

        if recent_trades:
            for trade in reversed(recent_trades):
                pnl = trade.get('pnl', 0)
                pnl_pct = trade.get('pnl_percent', 0)
                emoji = "✅" if pnl > 0 else "❌"
                pnl_color = COLORS.BUY if pnl > 0 else COLORS.SELL

                exit_time = trade.get('exit_time', '')
                if isinstance(exit_time, str) and exit_time:
                    try:
                        exit_time = datetime.fromisoformat(exit_time).strftime('%H:%M:%S')
                    except:
                        exit_time = ''

                st.markdown(f"""
                <div style="padding: 0.5rem; border-bottom: 1px solid #333; display: flex; justify-content: space-between;">
                    <span>{emoji} <b>{trade.get('symbol', '')}</b></span>
                    <span style="color: {pnl_color};">${pnl:+.2f} ({pnl_pct:+.1f}%)</span>
                    <span style="color: #666;">{trade.get('reason', '')} | {exit_time}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No trades yet")

    st.divider()

    # PnL Chart
    st.subheader("📈 PnL Over Time")

    if trades:
        # Build cumulative PnL
        df_trades = pd.DataFrame(trades)
        df_trades['cumulative_pnl'] = df_trades['pnl'].cumsum()

        if 'exit_time' in df_trades.columns:
            df_trades['time'] = pd.to_datetime(df_trades['exit_time'])
        else:
            df_trades['time'] = range(len(df_trades))

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df_trades['time'],
            y=df_trades['cumulative_pnl'],
            mode='lines+markers',
            fill='tozeroy',
            line=dict(color='#48dbfb', width=2),
            fillcolor='rgba(72, 219, 251, 0.2)',
            name='Cumulative PnL'
        ))

        fig.update_layout(
            template='plotly_dark',
            height=300,
            margin=dict(l=0, r=0, t=20, b=0),
            xaxis_title="Time",
            yaxis_title="PnL ($)",
            showlegend=False
        )

        # Add zero line
        fig.add_hline(y=0, line_dash="dash", line_color="gray")

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No trade history to display")


def render_scanner(max_symbols: int, min_volume: float, min_score: int,
                   auto_refresh: bool, refresh_rate: int):
    """Affiche le scanner"""
    scanner = DegenScanner()
    scanner.config.max_symbols = max_symbols
    scanner.config.min_volume_24h = min_volume * 1_000_000

    # Scan
    with st.spinner(f"Scanning {max_symbols} tokens..."):
        results = scanner.scan_all()

    scan_time = datetime.now()

    # Stats
    pumps = [r for r in results if r.is_pump]
    dumps = [r for r in results if r.is_dump]
    opportunities = [r for r in results if r.score >= min_score]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🚀 Pumps", len(pumps))
    with col2:
        st.metric("📉 Dumps", len(dumps))
    with col3:
        st.metric("🎯 Opportunities", len(opportunities))
    with col4:
        st.markdown(f'<span class="live-dot"></span> {scan_time.strftime("%H:%M:%S")}', unsafe_allow_html=True)

    st.divider()

    # Alerts - utilise le theme unifie
    if pumps:
        st.subheader("🚀 PUMP ALERTS")
        for r in pumps[:5]:
            alert(
                f"🚀 <b>{r.symbol}</b> | ${r.price:.4f} | +{r.change_1m:.1f}% (1m) | Vol: {r.volume_ratio:.1f}x | Score: {r.score}",
                "pump"
            )

    if dumps:
        st.subheader("📉 DUMP ALERTS")
        for r in dumps[:5]:
            alert(
                f"📉 <b>{r.symbol}</b> | ${r.price:.4f} | {r.change_1m:.1f}% (1m) | Vol: {r.volume_ratio:.1f}x | Score: {r.score}",
                "dump"
            )

    st.divider()

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 All Tokens", "🎯 Top Opportunities", "📈 Heatmap"])

    with tab1:
        # Filter
        col1, col2 = st.columns([1, 1])
        with col1:
            sort_by = st.selectbox("Sort by", ["Score", "Change 1m", "Volume", "RSI"])
        with col2:
            signal_filter = st.multiselect(
                "Signals",
                ["PUMP_DETECTED", "DEGEN_BUY", "SCALP_BUY", "BUY", "NEUTRAL", "SELL"],
                default=["PUMP_DETECTED", "DEGEN_BUY", "SCALP_BUY", "BUY"]
            )

        # Filter results
        filtered = [r for r in results if r.signal in signal_filter] if signal_filter else results

        # Sort
        sort_key = {
            "Score": lambda x: x.score,
            "Change 1m": lambda x: x.change_1m,
            "Volume": lambda x: x.volume_24h,
            "RSI": lambda x: x.rsi
        }[sort_by]
        filtered.sort(key=sort_key, reverse=True)

        # Display
        if filtered:
            df = pd.DataFrame([{
                'Symbol': r.symbol,
                'Price': f"${r.price:.4f}" if r.price < 1 else f"${r.price:.2f}",
                '1m': f"{r.change_1m:+.1f}%",
                '5m': f"{r.change_5m:+.1f}%",
                'Vol': f"{r.volume_ratio:.1f}x",
                'RSI': f"{r.rsi:.0f}",
                'Score': r.score,
                'Signal': r.signal
            } for r in filtered])

            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab2:
        # Top opportunities
        top = sorted([r for r in results if r.score >= min_score], key=lambda x: x.score, reverse=True)[:10]

        for r in top:
            color = "#00ff88" if r.score >= 70 else ("#48dbfb" if r.score >= 50 else "#feca57")

            st.markdown(f"""
            <div class="position-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0; color: white;">{r.symbol}</h3>
                    <span style="color: {color}; font-size: 1.5rem; font-weight: bold;">
                        Score: {r.score}
                    </span>
                </div>
                <div style="color: #888; margin: 0.5rem 0;">
                    ${r.price:.4f} | 1m: {r.change_1m:+.1f}% | Vol: {r.volume_ratio:.1f}x | RSI: {r.rsi:.0f}
                </div>
                <div style="color: #48dbfb;">
                    Signal: {r.signal} | {', '.join(r.reasons[:2])}
                </div>
            </div>
            """, unsafe_allow_html=True)

    with tab3:
        # Heatmap
        st.markdown("### RSI vs Change Distribution")

        fig = go.Figure()

        for r in results[:100]:
            color = '#00ff88' if r.score > 50 else ('#ff4444' if r.score < -50 else '#888888')
            size = 10 + abs(r.score) / 5

            fig.add_trace(go.Scatter(
                x=[r.rsi],
                y=[r.change_1m],
                mode='markers+text',
                marker=dict(size=size, color=color, opacity=0.7),
                text=[r.symbol],
                textposition='top center',
                textfont=dict(size=8, color='white'),
                hovertemplate=f"<b>{r.symbol}</b><br>RSI: {r.rsi:.0f}<br>1m: {r.change_1m:+.1f}%<br>Score: {r.score}<extra></extra>"
            ))

        fig.add_vrect(x0=0, x1=30, fillcolor="green", opacity=0.1, line_width=0)
        fig.add_vrect(x0=70, x1=100, fillcolor="red", opacity=0.1, line_width=0)
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.add_vline(x=30, line_dash="dash", line_color="green")
        fig.add_vline(x=70, line_dash="dash", line_color="red")

        fig.update_layout(
            template='plotly_dark',
            height=500,
            showlegend=False,
            xaxis_title="RSI",
            yaxis_title="Change 1m (%)",
            xaxis=dict(range=[0, 100])
        )

        st.plotly_chart(fig, use_container_width=True)

    # Auto refresh
    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()


def render_backtest_results():
    """Affiche les resultats de backtest"""
    state = load_bot_state()
    trades = state.get('trades', [])

    if not trades:
        st.info("No trade history available. Run the bot first.")
        return

    st.subheader("📊 Performance Analysis")

    # Summary stats
    df = pd.DataFrame(trades)
    total_pnl = df['pnl'].sum()
    win_rate = len(df[df['pnl'] > 0]) / len(df) * 100

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total PnL", f"${total_pnl:+,.2f}")
    with col2:
        st.metric("Win Rate", f"{win_rate:.1f}%")
    with col3:
        st.metric("Total Trades", len(df))
    with col4:
        avg_pnl = df['pnl'].mean()
        st.metric("Avg Trade", f"${avg_pnl:+.2f}")

    st.divider()

    # Distribution by exit reason
    st.subheader("📈 Exit Reason Distribution")

    if 'reason' in df.columns:
        reason_stats = df.groupby('reason').agg({
            'pnl': ['count', 'sum', 'mean']
        }).round(2)
        reason_stats.columns = ['Count', 'Total PnL', 'Avg PnL']
        st.dataframe(reason_stats)

    # Trade distribution
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("PnL Distribution")
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=df['pnl'],
            nbinsx=30,
            marker_color='#48dbfb'
        ))
        fig.add_vline(x=0, line_dash="dash", line_color="white")
        fig.update_layout(
            template='plotly_dark',
            height=300,
            xaxis_title="PnL ($)",
            yaxis_title="Count"
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Win/Loss Ratio")
        wins = len(df[df['pnl'] > 0])
        losses = len(df[df['pnl'] <= 0])

        fig = go.Figure(data=[go.Pie(
            labels=['Wins', 'Losses'],
            values=[wins, losses],
            marker_colors=['#00ff88', '#ff4444'],
            hole=0.4
        )])
        fig.update_layout(
            template='plotly_dark',
            height=300,
            showlegend=True
        )
        st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
