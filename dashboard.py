"""
Trading Bot Dashboard - Interface Mobile-Friendly (No Scroll)
==============================================================

Dashboard web optimise pour controle mobile via AnyDesk.
Navigation par pages, sans scrollbar.
Lance avec: streamlit run dashboard.py
"""
import sys
import os

# Fix Windows encoding
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import asyncio
import json
import requests
import ccxt
import threading
import queue
try:
    from websocket import create_connection, WebSocketConnectionClosedException
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False

# Import des modules du bot
from signals.technical import TechnicalAnalyzer
from signals.sentiment import SentimentAnalyzer
from signals.onchain import OnChainAnalyzer
from signals.godmode import GodModeDetector, GodModeLevel
from core.confluence import ConfluenceEngine, TradeAction


# Cache des analyseurs (objets lourds)
@st.cache_resource
def get_technical_analyzer():
    return TechnicalAnalyzer()

@st.cache_resource
def get_sentiment_analyzer():
    return SentimentAnalyzer()

@st.cache_resource
def get_onchain_analyzer():
    return OnChainAnalyzer()

@st.cache_resource
def get_godmode_detector():
    return GodModeDetector()

# Configuration de la page
st.set_page_config(
    page_title="Trading Bot",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS minifie et charge une seule fois via session_state
if 'css_loaded' not in st.session_state:
    st.session_state.css_loaded = True
    st.markdown("""<style>
::-webkit-scrollbar{display:none!important;width:0!important;height:0!important}
*{scrollbar-width:none!important;-ms-overflow-style:none!important}
html,body,[data-testid="stAppViewContainer"],[data-testid="stVerticalBlock"]{overflow:hidden!important;max-height:100vh!important}
.main .block-container{padding:.5rem 1rem!important;max-height:100vh!important;overflow:hidden!important}
.main-header{font-size:1.5rem;font-weight:700;background:linear-gradient(90deg,#00d4ff,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;text-align:center;padding:.3rem;margin:0}
.price-card{background:#1a1a2e;padding:.8rem;border-radius:10px;text-align:center;margin-bottom:.5rem}
.pf-card{background:#1a1a2e;border-radius:16px;padding:1rem;margin-bottom:.8rem;position:relative}
.pf-card.active{box-shadow:0 4px 20px rgba(0,255,136,.15);border-top:4px solid #00ff88}
.pf-card.paused{opacity:.75;border-top:4px solid #ff4444}
.pf-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem}
.pf-icon{font-size:2rem;margin-right:.5rem}
.pf-name{font-size:1.1rem;font-weight:600;color:#fff}
.pf-strategy{font-size:.75rem;color:#888;padding:2px 8px;background:rgba(255,255,255,.1);border-radius:10px}
.pf-stats{display:flex;justify-content:space-between;margin:.8rem 0}
.pf-stat{text-align:center}
.pf-stat-value{font-size:1.2rem;font-weight:700}
.pf-stat-label{font-size:.7rem;color:#666;text-transform:uppercase}
.signal-box{padding:1rem;border-radius:12px;text-align:center;margin:.5rem 0}
.signal-buy{background:rgba(0,255,136,.2);border:2px solid #00ff88}
.signal-sell{background:rgba(255,68,68,.2);border:2px solid #ff4444}
.signal-hold{background:rgba(136,136,136,.2);border:2px solid #888}
.stButton>button{font-size:1.1rem!important;padding:.6rem 1rem!important;border-radius:8px!important}
[data-testid="stMetric"]{background-color:#1e1e2e;padding:.5rem;border-radius:8px}
[data-testid="stMetricValue"]{font-size:1.2rem!important}
#MainMenu,footer,header{visibility:hidden}
</style>""", unsafe_allow_html=True)


# ==================== CONSTANTS ====================

STRATEGIES = {
    "manuel": {"name": "Manuel", "icon": "🎮", "color": "#888888", "auto": False},
    "confluence_strict": {"name": "Strict", "icon": "🎯", "color": "#00d4ff", "auto": True, "buy_on": ["STRONG_BUY", "GOD_MODE_BUY"], "sell_on": ["STRONG_SELL"]},
    "confluence_normal": {"name": "Normal", "icon": "📊", "color": "#7c3aed", "auto": True, "buy_on": ["BUY", "STRONG_BUY", "GOD_MODE_BUY"], "sell_on": ["SELL", "STRONG_SELL"]},
    "god_mode_only": {"name": "God Mode", "icon": "🚨", "color": "#ff0000", "auto": True, "buy_on": ["GOD_MODE_BUY"], "sell_on": []},
    "dca_fear": {"name": "DCA Fear", "icon": "😱", "color": "#ff6600", "auto": True, "use_fear_greed": True},
    "rsi_strategy": {"name": "RSI", "icon": "📈", "color": "#00d4ff", "auto": True, "use_rsi": True},
    "aggressive": {"name": "Aggressive", "icon": "🔥", "color": "#ff4444", "auto": True, "buy_on": ["BUY", "STRONG_BUY", "GOD_MODE_BUY"], "sell_on": ["SELL", "STRONG_SELL"]},
    "conservative": {"name": "Safe", "icon": "🛡️", "color": "#00ff88", "auto": True, "buy_on": ["STRONG_BUY", "GOD_MODE_BUY"], "sell_on": ["STRONG_SELL"]},
    "hodl": {"name": "HODL", "icon": "💎", "color": "#f7931a", "auto": True, "buy_on": ["ALWAYS_FIRST"], "sell_on": []}
}

DEFAULT_CONFIG = {
    "cryptos": ["BTC/USDT"],
    "allocation_percent": 10,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "fear_greed_buy": 25,
    "fear_greed_sell": 75,
    "max_positions": 3,
    "auto_trade": True
}

AVAILABLE_CRYPTOS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT"
]

PORTFOLIOS_FILE = "data/portfolios.json"


# ==================== HELPER FUNCTIONS ====================

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@st.cache_data(ttl=10)
def fetch_live_price(symbol: str = "BTCUSDT") -> dict:
    try:
        binance_symbol = symbol.replace("/", "")
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={binance_symbol}"
        response = requests.get(url, timeout=1)
        if response.status_code == 200:
            data = response.json()
            return {'price': float(data['price']), 'change': 0}
    except:
        pass
    return None


@st.cache_data(ttl=5)
def fetch_all_live_prices() -> dict:
    """Endpoint leger: juste les prix (pas high/low/volume)"""
    try:
        # ticker/price est 10x plus rapide que ticker/24hr
        url = "https://api.binance.com/api/v3/ticker/price"
        response = requests.get(url, timeout=1)
        if response.status_code == 200:
            data = response.json()
            prices = {}
            wanted = {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'MATICUSDT'}
            for item in data:
                if item['symbol'] in wanted:
                    sym = item['symbol'].replace('USDT', '/USDT')
                    prices[sym] = {'price': float(item['price']), 'change': 0}
            return prices
    except:
        pass
    return {}


@st.cache_resource
def get_exchange():
    """Exchange ccxt cache pour eviter la reinitialisation"""
    return ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'spot'}})


@st.cache_data(ttl=30)
def fetch_real_ohlcv(symbol: str = "BTC/USDT", timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
    try:
        exchange = get_exchange()
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        return df
    except:
        return pd.DataFrame()


def save_portfolios():
    try:
        os.makedirs("data", exist_ok=True)
        data = {'portfolios': st.session_state.portfolios, 'counter': st.session_state.portfolio_counter}
        with open(PORTFOLIOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        # Invalide le cache apres sauvegarde
        load_portfolios_once.clear()
    except Exception as e:
        print(f"Erreur sauvegarde: {e}")


@st.cache_resource
def load_portfolios_once() -> tuple:
    """Charge le fichier UNE SEULE FOIS au demarrage (4MB = lent)"""
    try:
        if os.path.exists(PORTFOLIOS_FILE):
            with open(PORTFOLIOS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('portfolios', {}), data.get('counter', 0)
    except:
        pass
    return {}, 0


def load_portfolios() -> tuple:
    return load_portfolios_once()


def init_session():
    if 'page' not in st.session_state:
        st.session_state.page = 'prix'
    if 'portfolios' not in st.session_state:
        portfolios, counter = load_portfolios()
        st.session_state.portfolios = portfolios
        st.session_state.portfolio_counter = counter
    if 'portfolio_counter' not in st.session_state:
        st.session_state.portfolio_counter = 0
    if 'selected_portfolio' not in st.session_state:
        st.session_state.selected_portfolio = None
    if 'portfolio_page' not in st.session_state:
        st.session_state.portfolio_page = 0
    if 'symbol' not in st.session_state:
        st.session_state.symbol = "BTC/USDT"


def create_portfolio(name: str, strategy_id: str, initial_capital: float = 10000.0, config: dict = None) -> str:
    st.session_state.portfolio_counter += 1
    portfolio_id = f"portfolio_{st.session_state.portfolio_counter}"
    strat = STRATEGIES.get(strategy_id, STRATEGIES['manuel'])
    portfolio_config = DEFAULT_CONFIG.copy()
    if config:
        portfolio_config.update(config)

    balance = {'USDT': initial_capital}
    for crypto in AVAILABLE_CRYPTOS:
        asset = crypto.split('/')[0]
        balance[asset] = 0.0

    st.session_state.portfolios[portfolio_id] = {
        'id': portfolio_id,
        'name': name,
        'strategy_id': strategy_id,
        'strategy_name': strat['name'],
        'icon': strat['icon'],
        'color': strat.get('color', '#888888'),
        'config': portfolio_config,
        'balance': balance,
        'initial_capital': initial_capital,
        'positions': {},
        'trades': [],
        'created_at': datetime.now().isoformat(),
        'active': True
    }
    save_portfolios()
    return portfolio_id


def delete_portfolio(portfolio_id: str):
    if portfolio_id in st.session_state.portfolios:
        del st.session_state.portfolios[portfolio_id]
        save_portfolios()


def get_portfolio_value(portfolio: dict, prices: dict) -> float:
    total = portfolio['balance'].get('USDT', 0)
    for asset, qty in portfolio['balance'].items():
        if asset != 'USDT' and qty > 0:
            symbol = f"{asset}/USDT"
            if symbol in prices and prices[symbol].get('price'):
                total += qty * prices[symbol]['price']
    return total


def get_all_portfolio_values(portfolios: dict, prices: dict) -> dict:
    """Calcule toutes les valeurs en une fois"""
    return {pid: get_portfolio_value(p, prices) for pid, p in portfolios.items()}


def execute_portfolio_trade(portfolio_id: str, action: str, symbol: str, amount_usdt: float, price: float) -> dict:
    portfolio = st.session_state.portfolios[portfolio_id]
    asset = symbol.split('/')[0]
    timestamp = datetime.now()

    if action == 'BUY':
        if portfolio['balance']['USDT'] >= amount_usdt:
            qty = amount_usdt / price
            portfolio['balance']['USDT'] -= amount_usdt
            portfolio['balance'][asset] = portfolio['balance'].get(asset, 0) + qty

            if symbol not in portfolio['positions']:
                portfolio['positions'][symbol] = {'entry_price': price, 'quantity': qty, 'entry_time': timestamp}
            else:
                pos = portfolio['positions'][symbol]
                total_qty = pos['quantity'] + qty
                avg_price = (pos['entry_price'] * pos['quantity'] + price * qty) / total_qty
                portfolio['positions'][symbol] = {'entry_price': avg_price, 'quantity': total_qty, 'entry_time': pos['entry_time']}

            trade = {'timestamp': timestamp.isoformat(), 'action': 'BUY', 'symbol': symbol, 'price': price, 'quantity': qty, 'amount_usdt': amount_usdt, 'pnl': 0}
            portfolio['trades'].append(trade)
            save_portfolios()
            return {'success': True, 'message': f"Achete {qty:.4f} {asset}"}
        return {'success': False, 'message': "Solde insuffisant"}

    elif action == 'SELL':
        if portfolio['balance'].get(asset, 0) > 0:
            qty = portfolio['balance'][asset]
            sell_value = qty * price
            pnl = 0
            if symbol in portfolio['positions']:
                entry_price = portfolio['positions'][symbol]['entry_price']
                pnl = (price - entry_price) * qty
                del portfolio['positions'][symbol]

            portfolio['balance']['USDT'] += sell_value
            portfolio['balance'][asset] = 0

            trade = {'timestamp': timestamp.isoformat(), 'action': 'SELL', 'symbol': symbol, 'price': price, 'quantity': qty, 'amount_usdt': sell_value, 'pnl': pnl}
            portfolio['trades'].append(trade)
            save_portfolios()
            return {'success': True, 'message': f"Vendu ${pnl:+,.0f}"}
        return {'success': False, 'message': f"Pas de {asset}"}

    return {'success': False, 'message': "Action invalide"}


@st.cache_data(ttl=10)
def analyze_crypto_quick(symbol: str) -> dict:
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.replace('/', '')}&interval=1h&limit=50"
        response = requests.get(url, timeout=5)
        data = response.json()

        if not data or len(data) < 20:
            return None

        closes = np.array([float(d[4]) for d in data])

        # RSI vectorise (plus rapide)
        delta = np.diff(closes, prepend=closes[0])
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = np.convolve(gain, np.ones(14)/14, mode='valid')[-1]
        avg_loss = np.convolve(loss, np.ones(14)/14, mode='valid')[-1]
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        current_rsi = 100 - (100 / (1 + rs))

        # EMA rapide avec numpy
        def ema(data, span):
            alpha = 2 / (span + 1)
            result = np.zeros_like(data)
            result[0] = data[0]
            for i in range(1, len(data)):
                result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
            return result[-1]

        ema_12 = ema(closes, 12)
        ema_26 = ema(closes, 26)
        current_price = closes[-1]

        signal = "HOLD"
        if current_rsi < 30 and ema_12 > ema_26:
            signal = "STRONG_BUY"
        elif current_rsi < 35:
            signal = "BUY"
        elif current_rsi > 70 and ema_12 < ema_26:
            signal = "STRONG_SELL"
        elif current_rsi > 65:
            signal = "SELL"

        return {
            'symbol': symbol,
            'price': current_price,
            'rsi': current_rsi,
            'signal': signal,
            'trend': 'bullish' if ema_12 > ema_26 else 'bearish'
        }
    except:
        return None


def execute_strategy_signal(portfolio_id: str, action_str: str, symbol: str, price: float, fear_greed: int, rsi: float = 50.0):
    if portfolio_id not in st.session_state.portfolios:
        return None

    portfolio = st.session_state.portfolios[portfolio_id]
    strategy = STRATEGIES.get(portfolio['strategy_id'], {})
    config = portfolio['config']

    if symbol not in config.get('cryptos', []):
        return None
    if not config.get('auto_trade', True):
        return None
    if len(portfolio['positions']) >= config.get('max_positions', 3):
        if symbol not in portfolio['positions']:
            return None

    action_map = {
        "🟢 BUY": "BUY", "🟢🟢 STRONG BUY": "STRONG_BUY",
        "🔴 SELL": "SELL", "🔴🔴 STRONG SELL": "STRONG_SELL",
        "🚨 GOD MODE BUY": "GOD_MODE_BUY", "⚪ HOLD": "HOLD"
    }
    action_type = action_map.get(action_str, "HOLD")
    allocation = config.get('allocation_percent', 10)
    asset = symbol.split('/')[0]

    if strategy.get('use_fear_greed', False):
        if fear_greed < config.get('fear_greed_buy', 25) and portfolio['balance']['USDT'] > 100:
            amount = portfolio['balance']['USDT'] * (allocation / 100)
            return execute_portfolio_trade(portfolio_id, 'BUY', symbol, amount, price)
        elif fear_greed > config.get('fear_greed_sell', 75) and portfolio['balance'].get(asset, 0) > 0:
            return execute_portfolio_trade(portfolio_id, 'SELL', symbol, 0, price)
        return None

    if strategy.get('use_rsi', False):
        if rsi < config.get('rsi_oversold', 30) and portfolio['balance']['USDT'] > 100:
            amount = portfolio['balance']['USDT'] * (allocation / 100)
            return execute_portfolio_trade(portfolio_id, 'BUY', symbol, amount, price)
        elif rsi > config.get('rsi_overbought', 70) and portfolio['balance'].get(asset, 0) > 0:
            return execute_portfolio_trade(portfolio_id, 'SELL', symbol, 0, price)
        return None

    if strategy.get('buy_on') == ["ALWAYS_FIRST"]:
        if len(portfolio['trades']) == 0 and portfolio['balance']['USDT'] > 100:
            amount = portfolio['balance']['USDT'] * (allocation / 100)
            return execute_portfolio_trade(portfolio_id, 'BUY', symbol, amount, price)
        return None

    buy_signals = strategy.get('buy_on', [])
    sell_signals = strategy.get('sell_on', [])

    if action_type in buy_signals and portfolio['balance']['USDT'] > 100:
        amount = portfolio['balance']['USDT'] * (allocation / 100)
        return execute_portfolio_trade(portfolio_id, 'BUY', symbol, amount, price)
    elif action_type in sell_signals and portfolio['balance'].get(asset, 0) > 0:
        return execute_portfolio_trade(portfolio_id, 'SELL', symbol, 0, price)

    return None


def run_engine():
    results = []
    analyzed = {}

    for port_id, portfolio in st.session_state.portfolios.items():
        if not portfolio.get('active', True):
            continue
        if not portfolio['config'].get('auto_trade', True):
            continue

        for crypto in portfolio['config'].get('cryptos', []):
            if crypto not in analyzed:
                analyzed[crypto] = analyze_crypto_quick(crypto)

            analysis = analyzed.get(crypto)
            if not analysis:
                continue

            signal_map = {"STRONG_BUY": "🟢🟢 STRONG BUY", "BUY": "🟢 BUY", "SELL": "🔴 SELL", "STRONG_SELL": "🔴🔴 STRONG SELL", "HOLD": "⚪ HOLD"}
            action_str = signal_map.get(analysis['signal'], "⚪ HOLD")

            result = execute_strategy_signal(port_id, action_str, crypto, analysis['price'], 50, analysis['rsi'])
            if result and result.get('success'):
                results.append({'portfolio': portfolio['name'], 'crypto': crypto, 'action': analysis['signal'], 'price': analysis['price']})

    return results, analyzed


# ==================== PAGE FUNCTIONS ====================

def render_navigation():
    """Barre de navigation en haut"""
    cols = st.columns(5)
    pages = [('prix', '💰'), ('portfolios', '💼'), ('signaux', '🎯'), ('chart', '📈'), ('config', '⚙️')]

    for i, (page_id, icon) in enumerate(pages):
        with cols[i]:
            btn_type = "primary" if st.session_state.page == page_id else "secondary"
            if st.button(icon, key=f"nav_{page_id}", type=btn_type, use_container_width=True):
                st.session_state.page = page_id
                st.rerun()


def render_page_prix():
    """Page: Prix en direct"""
    st.markdown("### 💰 Prix")

    prices = fetch_all_live_prices()

    # Affichage simple en grille
    cols = st.columns(2)
    for i, (sym, data) in enumerate(list(prices.items())[:4]):
        with cols[i % 2]:
            st.metric(sym.replace('/USDT', ''), f"${data['price']:,.2f}" if data['price'] > 0 else "---")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with col2:
        if st.button("🚀 RUN", type="primary", use_container_width=True):
            results, _ = run_engine()
            st.success(f"{len(results)} trades!") if results else st.info("Aucun")


def render_page_portfolios():
    """Page: Liste des portfolios avec pagination - OPTIMISE pour 100+ portfolios"""
    prices = fetch_all_live_prices()
    total = len(st.session_state.portfolios)
    per_page = 10

    # Header avec tri (profit par defaut)
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"**💼 {total} portfolios**")
    with col2:
        sort_option = st.selectbox("", ["% Profit ↓", "% Profit ↑", "Valeur", "Nom"], label_visibility="collapsed", key="pf_sort")

    # Reset page si tri change
    if 'last_sort' not in st.session_state:
        st.session_state.last_sort = sort_option
    if st.session_state.last_sort != sort_option:
        st.session_state.portfolio_page = 0
        st.session_state.last_sort = sort_option

    # Calcul PnL% rapide (utilise seulement USDT, ignore les positions pour le tri)
    def quick_pnl_pct(item):
        port_id, portfolio = item
        # Approximation rapide: USDT + positions estimees
        usdt = portfolio['balance'].get('USDT', 0)
        positions_value = sum(
            portfolio['balance'].get(sym.split('/')[0], 0) * prices.get(sym, {}).get('price', 0)
            for sym in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']
        )
        value = usdt + positions_value
        init = portfolio['initial_capital']
        return ((value - init) / init * 100) if init > 0 else 0

    # Tri rapide
    portfolios_list = list(st.session_state.portfolios.items())
    if sort_option == "% Profit ↓":
        portfolios_list.sort(key=quick_pnl_pct, reverse=True)
    elif sort_option == "% Profit ↑":
        portfolios_list.sort(key=quick_pnl_pct)
    elif sort_option == "Valeur":
        portfolios_list.sort(key=lambda x: x[1]['balance'].get('USDT', 0), reverse=True)
    elif sort_option == "Nom":
        portfolios_list.sort(key=lambda x: x[1]['name'])

    total_pages = max(1, (total + per_page - 1) // per_page)

    # Seulement les portfolios de la page actuelle
    start = st.session_state.portfolio_page * per_page
    end = min(start + per_page, total)
    page_portfolios = portfolios_list[start:end]

    # Calcul des valeurs SEULEMENT pour les portfolios affiches
    for port_id, portfolio in page_portfolios:
        value = get_portfolio_value(portfolio, prices)
        pnl = value - portfolio['initial_capital']
        pnl_pct = (pnl / portfolio['initial_capital']) * 100 if portfolio['initial_capital'] > 0 else 0
        is_active = portfolio.get('active', True)
        n_trades = len(portfolio.get('trades', []))

        # Rendu ultra-simplifie
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            status = "🟢" if is_active else "⏸️"
            st.markdown(f"{status} **{portfolio['icon']} {portfolio['name'][:12]}**")
        with c2:
            color = "green" if pnl >= 0 else "red"
            st.markdown(f"${value:,.0f} | :{color}[{pnl_pct:+.1f}%]")
        with c3:
            if st.button("📊", key=f"v_{port_id}"):
                st.session_state.selected_portfolio = port_id
                st.session_state.page = 'detail'
                st.rerun()

    # Pagination
    if total_pages > 1:
        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("◀️", disabled=st.session_state.portfolio_page == 0, use_container_width=True):
                st.session_state.portfolio_page -= 1
                st.rerun()
        with col2:
            st.markdown(f"<p style='text-align:center; margin:0; padding: 0.5rem;'>{st.session_state.portfolio_page + 1} / {total_pages}</p>", unsafe_allow_html=True)
        with col3:
            if st.button("▶️", disabled=st.session_state.portfolio_page >= total_pages - 1, use_container_width=True):
                st.session_state.portfolio_page += 1
                st.rerun()

    # Si aucun portfolio
    if total == 0:
        st.markdown("""
        <div style="text-align: center; padding: 2rem; color: #666;">
            <div style="font-size: 3rem;">💼</div>
            <p>Aucun portfolio</p>
            <p style="font-size: 0.8rem;">Allez dans ⚙️ pour en créer un</p>
        </div>
        """, unsafe_allow_html=True)


@st.cache_data(ttl=15)
def get_full_analysis(symbol: str):
    """Analyse complete cachee pour eviter les appels repetes"""
    df = fetch_real_ohlcv(symbol, "1h", 100)
    if df.empty:
        return None

    current_price = df['close'].iloc[-1]

    # Utilise les analyseurs caches
    technical_analyzer = get_technical_analyzer()
    technical_result = technical_analyzer.analyze(df)
    tech_signal = technical_analyzer.get_signal_value(technical_result)

    # Sentiment & Onchain
    sentiment_result = run_async(get_sentiment_analyzer().analyze(symbol.split('/')[0]))
    onchain_result = run_async(get_onchain_analyzer().analyze(symbol.split('/')[0]))
    godmode_result = run_async(get_godmode_detector().detect(current_price))

    return {
        'df': df,
        'price': current_price,
        'technical': technical_result,
        'tech_signal': tech_signal,
        'sentiment': sentiment_result,
        'sent_signal': sentiment_result.signal,
        'onchain': onchain_result,
        'chain_signal': onchain_result.signal,
        'godmode': godmode_result
    }


def render_page_signaux():
    """Page: Signaux actuels"""
    symbol = st.session_state.symbol

    # Selector crypto
    col1, col2 = st.columns([3, 1])
    with col1:
        new_sym = st.selectbox("Crypto", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
                               index=["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"].index(symbol),
                               label_visibility="collapsed")
        if new_sym != symbol:
            st.session_state.symbol = new_sym
            st.rerun()
    with col2:
        if st.button("🔄", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # Fetch cached analysis
    analysis = get_full_analysis(symbol)
    if analysis is None:
        st.error("Erreur chargement donnees")
        return

    current_price = analysis['price']
    technical_result = analysis['technical']
    tech_signal = analysis['tech_signal']
    sentiment_result = analysis['sentiment']
    sent_signal = analysis['sent_signal']
    onchain_result = analysis['onchain']
    chain_signal = analysis['chain_signal']
    godmode_result = analysis['godmode']

    # Calculate action
    confluence_score = tech_signal + sent_signal + chain_signal
    signals_aligned = max(
        sum(1 for s in [tech_signal, sent_signal, chain_signal] if s > 0),
        sum(1 for s in [tech_signal, sent_signal, chain_signal] if s < 0)
    )

    if godmode_result.level == GodModeLevel.EXTREME:
        action, action_class = "🚨 GOD MODE BUY", "signal-buy"
    elif signals_aligned >= 3 and confluence_score > 0:
        action, action_class = "🟢🟢 STRONG BUY", "signal-buy"
    elif signals_aligned >= 3 and confluence_score < 0:
        action, action_class = "🔴🔴 STRONG SELL", "signal-sell"
    elif signals_aligned >= 2 and confluence_score > 0:
        action, action_class = "🟢 BUY", "signal-buy"
    elif signals_aligned >= 2 and confluence_score < 0:
        action, action_class = "🔴 SELL", "signal-sell"
    else:
        action, action_class = "⚪ HOLD", "signal-hold"

    # Display
    st.markdown(f"""
    <div class="signal-box {action_class}">
        <div style="font-size: 2rem; font-weight: bold;">{action}</div>
        <div style="font-size: 1.5rem; margin: 0.5rem 0;">${current_price:,.2f}</div>
        <div style="color: #888;">Signaux: {signals_aligned}/3</div>
    </div>
    """, unsafe_allow_html=True)

    # Signal details
    col1, col2, col3 = st.columns(3)
    with col1:
        sig = "🟢" if tech_signal > 0 else "🔴" if tech_signal < 0 else "⚪"
        st.metric("Tech", f"{sig}", f"RSI {technical_result.rsi:.0f}")
    with col2:
        sig = "🟢" if sent_signal > 0 else "🔴" if sent_signal < 0 else "⚪"
        st.metric("Sent", f"{sig}", f"F&G {sentiment_result.fear_greed_index}")
    with col3:
        sig = "🟢" if chain_signal > 0 else "🔴" if chain_signal < 0 else "⚪"
        st.metric("Chain", f"{sig}")

    # Execute button
    if st.button("⚡ EXECUTER SUR TOUS", type="primary", use_container_width=True):
        results = []
        for port_id, portfolio in st.session_state.portfolios.items():
            if portfolio.get('active', True):
                result = execute_strategy_signal(port_id, action, symbol, current_price,
                                                 sentiment_result.fear_greed_index, technical_result.rsi)
                if result and result.get('success'):
                    results.append(portfolio['name'])
        if results:
            st.success(f"Trades: {', '.join(results)}")
        else:
            st.info("Aucun trade execute")


@st.cache_data(ttl=15)
def get_chart_data(symbol: str, tf: str):
    """Prepare les donnees du chart avec cache - 30 bougies seulement"""
    df = fetch_real_ohlcv(symbol, tf, 30)  # Reduit de 50 a 30
    if df.empty:
        return None
    return df


def render_page_chart():
    """Page: Graphique compact"""
    symbol = st.session_state.symbol

    col1, col2 = st.columns([3, 1])
    with col1:
        new_sym = st.selectbox("", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"],
                               index=["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"].index(symbol),
                               label_visibility="collapsed", key="chart_sym")
        if new_sym != symbol:
            st.session_state.symbol = new_sym
            st.rerun()
    with col2:
        tf = st.selectbox("", ["1h", "4h", "1d"], label_visibility="collapsed", key="chart_tf")

    df = get_chart_data(symbol, tf)
    if df is None:
        st.error("Erreur donnees")
        return

    # Chart ultra-simplifie pour vitesse max
    fig = go.Figure(go.Candlestick(
        x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        increasing_line_color='#00ff88', decreasing_line_color='#ff4444'
    ))

    fig.update_layout(
        template='plotly_dark',
        height=300,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis_rangeslider_visible=False,
        showlegend=False,
        xaxis=dict(showticklabels=False, showgrid=False),
        yaxis=dict(side='right', showgrid=False)
    )

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False, 'staticPlot': True})

    # Quick stats
    current = df['close'].iloc[-1]
    prev = df['close'].iloc[-2]
    change = ((current - prev) / prev) * 100

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Prix", f"${current:,.2f}")
    with col2:
        st.metric("Change", f"{change:+.2f}%")
    with col3:
        st.metric("High", f"${df['high'].max():,.2f}")


def render_page_config():
    """Page: Configuration / Creation portfolio"""
    st.markdown("### ⚙️ Nouveau Portfolio")

    name = st.text_input("Nom", value=f"Portfolio {st.session_state.portfolio_counter + 1}")

    strategy = st.selectbox("Strategie", list(STRATEGIES.keys()),
                            format_func=lambda x: f"{STRATEGIES[x]['icon']} {STRATEGIES[x]['name']}")

    capital = st.number_input("Capital $", min_value=100, value=10000, step=1000)

    cryptos = st.multiselect("Cryptos", AVAILABLE_CRYPTOS, default=["BTC/USDT"])

    col1, col2 = st.columns(2)
    with col1:
        alloc = st.slider("Allocation %", 1, 100, 10)
    with col2:
        max_pos = st.slider("Max Positions", 1, 5, 3)

    if st.button("✅ CREER", type="primary", use_container_width=True):
        if not cryptos:
            st.error("Selectionnez au moins une crypto")
        elif not name:
            st.error("Entrez un nom")
        else:
            config = {'cryptos': cryptos, 'allocation_percent': alloc, 'max_positions': max_pos}
            create_portfolio(name, strategy, float(capital), config)
            st.success(f"Portfolio '{name}' cree!")
            st.session_state.page = 'portfolios'
            st.rerun()

    st.markdown("---")

    # Actions globales
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Play All", use_container_width=True):
            for pid in st.session_state.portfolios:
                st.session_state.portfolios[pid]['active'] = True
            save_portfolios()
            st.rerun()
    with col2:
        if st.button("⏸️ Pause All", use_container_width=True):
            for pid in st.session_state.portfolios:
                st.session_state.portfolios[pid]['active'] = False
            save_portfolios()
            st.rerun()


def render_page_detail():
    """Page: Detail d'un portfolio"""
    port_id = st.session_state.selected_portfolio
    if not port_id or port_id not in st.session_state.portfolios:
        st.session_state.page = 'portfolios'
        st.rerun()
        return

    portfolio = st.session_state.portfolios[port_id]
    prices = fetch_all_live_prices()
    value = get_portfolio_value(portfolio, prices)
    pnl = value - portfolio['initial_capital']
    pnl_pct = (pnl / portfolio['initial_capital']) * 100 if portfolio['initial_capital'] > 0 else 0
    is_active = portfolio.get('active', True)

    # Stats
    trades = portfolio.get('trades', [])
    wins = len([t for t in trades if t.get('pnl', 0) > 0])
    losses = len([t for t in trades if t.get('pnl', 0) < 0])
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    positions = len(portfolio.get('positions', {}))

    pnl_color = '#00ff88' if pnl >= 0 else '#ff4444'
    status_class = 'active' if is_active else 'paused'

    # Card principale
    st.markdown(f"""
    <div class="pf-card {status_class}">
        <div class="pf-header">
            <div style="display: flex; align-items: center;">
                <span class="pf-icon">{portfolio['icon']}</span>
                <div>
                    <div class="pf-name">{portfolio['name']}</div>
                    <span class="pf-strategy">{portfolio['strategy_name']}</span>
                </div>
            </div>
            <div style="text-align: right;">
                <div style="color: {pnl_color}; font-size: 1.5rem; font-weight: bold;">{pnl_pct:+.1f}%</div>
            </div>
        </div>
        <div class="pf-stats">
            <div class="pf-stat">
                <div class="pf-stat-value">${value:,.0f}</div>
                <div class="pf-stat-label">Valeur</div>
            </div>
            <div class="pf-stat">
                <div class="pf-stat-value" style="color: {pnl_color};">${pnl:+,.0f}</div>
                <div class="pf-stat-label">P&L</div>
            </div>
            <div class="pf-stat">
                <div class="pf-stat-value">{win_rate:.0f}%</div>
                <div class="pf-stat-label">Win Rate</div>
            </div>
            <div class="pf-stat">
                <div class="pf-stat-value">{len(trades)}</div>
                <div class="pf-stat-label">Trades</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Positions ouvertes
    if portfolio['positions']:
        st.markdown("**📊 Positions ouvertes:**")
        for sym, pos in portfolio['positions'].items():
            current = prices.get(sym, {}).get('price', pos['entry_price'])
            unrealized = (current - pos['entry_price']) * pos['quantity']
            unrealized_pct = ((current - pos['entry_price']) / pos['entry_price'] * 100) if pos['entry_price'] > 0 else 0
            color = '#00ff88' if unrealized >= 0 else '#ff4444'

            st.markdown(f"""
            <div style="background: #1a1a2e; padding: 0.5rem 0.8rem; border-radius: 8px; margin-bottom: 0.3rem; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: bold;">{sym.replace('/USDT', '')}</span>
                <span style="color: #888;">{pos['quantity']:.4f}</span>
                <span style="color: {color}; font-weight: bold;">${unrealized:+,.0f} ({unrealized_pct:+.1f}%)</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("<p style='color: #666; text-align: center;'>Aucune position ouverte</p>", unsafe_allow_html=True)

    # Actions
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Retour", use_container_width=True):
            st.session_state.page = 'portfolios'
            st.rerun()
    with col2:
        btn = "⏸️ Pause" if is_active else "▶️ Play"
        if st.button(btn, use_container_width=True, type="primary"):
            st.session_state.portfolios[port_id]['active'] = not is_active
            save_portfolios()
            st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Reset", use_container_width=True):
            portfolio['balance'] = {'USDT': portfolio['initial_capital']}
            for crypto in AVAILABLE_CRYPTOS:
                portfolio['balance'][crypto.split('/')[0]] = 0.0
            portfolio['positions'] = {}
            portfolio['trades'] = []
            save_portfolios()
            st.rerun()
    with col2:
        if st.button("🗑️ Suppr", use_container_width=True):
            delete_portfolio(port_id)
            st.session_state.page = 'portfolios'
            st.rerun()


# ==================== MAIN ====================

def main():
    init_session()

    # Header compact
    st.markdown('<p class="main-header">🎯 Trading Bot</p>', unsafe_allow_html=True)

    # Navigation
    render_navigation()

    # Render current page
    page = st.session_state.page

    if page == 'prix':
        render_page_prix()
    elif page == 'portfolios':
        render_page_portfolios()
    elif page == 'signaux':
        render_page_signaux()
    elif page == 'chart':
        render_page_chart()
    elif page == 'config':
        render_page_config()
    elif page == 'detail':
        render_page_detail()


if __name__ == "__main__":
    main()
