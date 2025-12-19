"""
Trading Bot Dashboard - Interface Graphique
============================================

Dashboard web moderne pour visualiser et controler le trading bot.
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

# Configuration de la page
st.set_page_config(
    page_title="Trading Bot Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personnalise
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #00d4ff, #7c3aed);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
        border-radius: 10px;
        padding: 1rem;
        border: 1px solid #3d3d5c;
    }
    .signal-buy {
        color: #00ff88;
        font-weight: bold;
    }
    .signal-sell {
        color: #ff4444;
        font-weight: bold;
    }
    .signal-hold {
        color: #888888;
    }
    .god-mode-extreme {
        background: linear-gradient(90deg, #ff0000, #ff6600);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: bold;
        font-size: 1.5rem;
    }
    .stMetric {
        background-color: #1e1e2e;
        padding: 1rem;
        border-radius: 10px;
    }
    .portfolio-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        transition: transform 0.2s;
    }
    .portfolio-card:hover {
        transform: translateY(-2px);
    }
    .portfolio-card.playing {
        border: 2px solid #00ff88;
        box-shadow: 0 0 15px rgba(0,255,136,0.3);
    }
    .portfolio-card.paused {
        border: 2px solid #ff4444;
        opacity: 0.7;
    }
    .pnl-positive { color: #00ff88; }
    .pnl-negative { color: #ff4444; }
</style>
""", unsafe_allow_html=True)


def fetch_live_price(symbol: str = "BTCUSDT") -> dict:
    """Recupere le prix en temps reel depuis Binance (sans cache)"""
    try:
        # Convert symbol format
        binance_symbol = symbol.replace("/", "")
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={binance_symbol}"
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            data = response.json()
            return {
                'price': float(data['lastPrice']),
                'change': float(data['priceChangePercent']),
                'high': float(data['highPrice']),
                'low': float(data['lowPrice']),
                'volume': float(data['quoteVolume']),
                'timestamp': datetime.now()
            }
    except Exception as e:
        pass
    return None


def fetch_all_live_prices() -> dict:
    """Recupere tous les prix en temps reel"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            prices = {}
            for item in data:
                if item['symbol'] in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']:
                    sym = item['symbol'].replace('USDT', '/USDT')
                    prices[sym] = {
                        'price': float(item['lastPrice']),
                        'change': float(item['priceChangePercent']),
                        'high': float(item['highPrice']),
                        'low': float(item['lowPrice']),
                        'volume': float(item['quoteVolume'])
                    }
            return prices
    except:
        pass
    return {}


@st.cache_data(ttl=60)  # Cache 1 minute
def fetch_real_ohlcv(symbol: str = "BTC/USDT", timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
    """Recupere les vraies donnees OHLCV depuis Binance"""
    try:
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })

        # Fetch OHLCV data
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)

        return df
    except Exception as e:
        st.warning(f"Erreur API Binance: {e}. Utilisation de donnees simulees.")
        return generate_sample_ohlcv(30, 'neutral')


@st.cache_data(ttl=300)  # Cache 5 minutes
def fetch_real_price(symbol: str = "BTC/USDT") -> float:
    """Recupere le prix actuel depuis Binance"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        ticker = exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        return 0.0


@st.cache_data(ttl=300)  # Cache 5 minutes
def fetch_multiple_prices() -> dict:
    """Recupere plusieurs prix en une fois"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        tickers = exchange.fetch_tickers(['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT'])
        return {
            symbol: {
                'price': data['last'],
                'change': data['percentage'],
                'high': data['high'],
                'low': data['low'],
                'volume': data['quoteVolume']
            }
            for symbol, data in tickers.items()
        }
    except Exception as e:
        return {}


def generate_sample_ohlcv(days: int = 30, trend: str = 'bullish') -> pd.DataFrame:
    """Genere des donnees OHLCV simulees (fallback)"""
    np.random.seed(int(datetime.now().timestamp()) % 1000)

    dates = pd.date_range(end=datetime.now(), periods=days * 24, freq='h')

    if trend == 'bullish':
        base_price = 40000 + np.cumsum(np.random.randn(len(dates)) * 100 + 15)
    elif trend == 'bearish':
        base_price = 50000 + np.cumsum(np.random.randn(len(dates)) * 100 - 15)
    else:
        base_price = 45000 + np.cumsum(np.random.randn(len(dates)) * 100)

    data = {
        'timestamp': dates,
        'open': base_price + np.random.randn(len(dates)) * 50,
        'high': base_price + abs(np.random.randn(len(dates)) * 100),
        'low': base_price - abs(np.random.randn(len(dates)) * 100),
        'close': base_price + np.random.randn(len(dates)) * 50,
        'volume': np.random.uniform(1000, 5000, len(dates))
    }

    df = pd.DataFrame(data)
    df['high'] = df[['open', 'close', 'high']].max(axis=1)
    df['low'] = df[['open', 'close', 'low']].min(axis=1)
    df.set_index('timestamp', inplace=True)

    return df


def create_candlestick_chart(df: pd.DataFrame) -> go.Figure:
    """Cree un graphique en chandeliers avec indicateurs"""
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=('Prix BTC/USDT', 'Volume', 'RSI')
    )

    # Chandelier
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='BTC',
            increasing_line_color='#00ff88',
            decreasing_line_color='#ff4444'
        ),
        row=1, col=1
    )

    # EMA 12 et 26
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()

    fig.add_trace(
        go.Scatter(x=df.index, y=ema12, name='EMA 12', line=dict(color='#00d4ff', width=1)),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=ema26, name='EMA 26', line=dict(color='#ff6600', width=1)),
        row=1, col=1
    )

    # Bollinger Bands
    sma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20

    fig.add_trace(
        go.Scatter(x=df.index, y=bb_upper, name='BB Upper', line=dict(color='rgba(128,128,128,0.5)', width=1, dash='dash')),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=bb_lower, name='BB Lower', line=dict(color='rgba(128,128,128,0.5)', width=1, dash='dash'), fill='tonexty', fillcolor='rgba(128,128,128,0.1)'),
        row=1, col=1
    )

    # Volume
    colors = ['#00ff88' if df['close'].iloc[i] >= df['open'].iloc[i] else '#ff4444' for i in range(len(df))]
    fig.add_trace(
        go.Bar(x=df.index, y=df['volume'], name='Volume', marker_color=colors),
        row=2, col=1
    )

    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    fig.add_trace(
        go.Scatter(x=df.index, y=rsi, name='RSI', line=dict(color='#7c3aed', width=2)),
        row=3, col=1
    )

    # Lignes RSI 30 et 70
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)

    fig.update_layout(
        template='plotly_dark',
        height=700,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False,
        margin=dict(l=50, r=50, t=50, b=50)
    )

    return fig


def create_signal_gauge(value: int, title: str) -> go.Figure:
    """Cree une jauge pour afficher un signal"""
    color = "#00ff88" if value > 0 else ("#ff4444" if value < 0 else "#888888")

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': title, 'font': {'size': 16, 'color': 'white'}},
        gauge={
            'axis': {'range': [-1, 1], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': color},
            'bgcolor': "#2d2d44",
            'borderwidth': 2,
            'bordercolor': "#3d3d5c",
            'steps': [
                {'range': [-1, -0.33], 'color': 'rgba(255,68,68,0.3)'},
                {'range': [-0.33, 0.33], 'color': 'rgba(128,128,128,0.3)'},
                {'range': [0.33, 1], 'color': 'rgba(0,255,136,0.3)'}
            ],
        },
        number={'font': {'color': color, 'size': 30}}
    ))

    fig.update_layout(
        template='plotly_dark',
        height=200,
        margin=dict(l=20, r=20, t=40, b=20)
    )

    return fig


def create_god_mode_chart(conditions: list) -> go.Figure:
    """Cree un graphique radar pour God Mode"""
    categories = [c.name[:15] for c in conditions]
    values = [1 if c.is_met else 0 for c in conditions]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        fillcolor='rgba(124, 58, 237, 0.3)',
        line=dict(color='#7c3aed', width=2),
        name='Conditions'
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1], showticklabels=False),
            bgcolor='#1e1e2e'
        ),
        template='plotly_dark',
        height=350,
        margin=dict(l=50, r=50, t=30, b=30),
        showlegend=False
    )

    return fig


def run_async(coro):
    """Execute une coroutine de maniere synchrone"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ==================== PAPER TRADING ====================

# Strategies disponibles (templates)
STRATEGIES = {
    "manuel": {
        "name": "Manuel",
        "description": "Trading manuel - Vous decidez",
        "icon": "🎮",
        "color": "#888888",
        "auto": False
    },
    "confluence_strict": {
        "name": "Confluence Strict",
        "description": "Trade uniquement sur STRONG_BUY/SELL (3/3 signaux)",
        "icon": "🎯",
        "color": "#00d4ff",
        "auto": True,
        "buy_on": ["STRONG_BUY", "GOD_MODE_BUY"],
        "sell_on": ["STRONG_SELL"]
    },
    "confluence_normal": {
        "name": "Confluence Normal",
        "description": "Trade sur BUY/SELL (2/3 signaux minimum)",
        "icon": "📊",
        "color": "#7c3aed",
        "auto": True,
        "buy_on": ["BUY", "STRONG_BUY", "GOD_MODE_BUY"],
        "sell_on": ["SELL", "STRONG_SELL"]
    },
    "god_mode_only": {
        "name": "God Mode Only",
        "description": "Accumule UNIQUEMENT en God Mode (rare mais x10)",
        "icon": "🚨",
        "color": "#ff0000",
        "auto": True,
        "buy_on": ["GOD_MODE_BUY"],
        "sell_on": []
    },
    "dca_fear": {
        "name": "DCA sur Fear",
        "description": "Achete quand Fear & Greed < seuil",
        "icon": "😱",
        "color": "#ff6600",
        "auto": True,
        "use_fear_greed": True
    },
    "rsi_strategy": {
        "name": "RSI Strategy",
        "description": "Achete RSI oversold, vend RSI overbought",
        "icon": "📈",
        "color": "#00d4ff",
        "auto": True,
        "use_rsi": True
    },
    "aggressive": {
        "name": "Aggressive",
        "description": "Suit tous les signaux BUY avec forte allocation",
        "icon": "🔥",
        "color": "#ff4444",
        "auto": True,
        "buy_on": ["BUY", "STRONG_BUY", "GOD_MODE_BUY"],
        "sell_on": ["SELL", "STRONG_SELL"]
    },
    "conservative": {
        "name": "Conservative",
        "description": "Petites positions, STRONG signals uniquement",
        "icon": "🛡️",
        "color": "#00ff88",
        "auto": True,
        "buy_on": ["STRONG_BUY", "GOD_MODE_BUY"],
        "sell_on": ["STRONG_SELL"]
    },
    "hodl": {
        "name": "HODL",
        "description": "Achete et ne vend jamais (benchmark)",
        "icon": "💎",
        "color": "#f7931a",
        "auto": True,
        "buy_on": ["ALWAYS_FIRST"],
        "sell_on": []
    }
}

# Configuration par defaut pour un nouveau portfolio
DEFAULT_CONFIG = {
    "cryptos": ["BTC/USDT"],  # Liste des cryptos a trader
    "allocation_percent": 10,  # % du portfolio par trade
    "rsi_oversold": 30,  # Seuil RSI oversold
    "rsi_overbought": 70,  # Seuil RSI overbought
    "fear_greed_buy": 25,  # Seuil F&G pour acheter
    "fear_greed_sell": 75,  # Seuil F&G pour vendre
    "stop_loss_percent": 5,  # Stop loss %
    "take_profit_percent": 10,  # Take profit %
    "max_positions": 3,  # Max positions simultanees
    "auto_trade": True  # Executer auto les signaux
}

# Liste des cryptos disponibles
AVAILABLE_CRYPTOS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT",
    "LINK/USDT", "UNI/USDT", "ATOM/USDT", "LTC/USDT", "FIL/USDT",
    "APT/USDT", "ARB/USDT", "OP/USDT", "INJ/USDT", "SUI/USDT"
]


PORTFOLIOS_FILE = "data/portfolios.json"


def save_portfolios():
    """Sauvegarde les portfolios dans un fichier JSON"""
    try:
        os.makedirs("data", exist_ok=True)
        data = {
            'portfolios': st.session_state.portfolios,
            'counter': st.session_state.portfolio_counter
        }
        with open(PORTFOLIOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        print(f"Erreur sauvegarde portfolios: {e}")


def load_portfolios() -> tuple:
    """Charge les portfolios depuis le fichier JSON"""
    try:
        if os.path.exists(PORTFOLIOS_FILE):
            with open(PORTFOLIOS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('portfolios', {}), data.get('counter', 0)
    except Exception as e:
        print(f"Erreur chargement portfolios: {e}")
    return {}, 0


def init_paper_trading():
    """Initialise le paper trading dans la session"""
    # Multi-portfolio system - charger depuis le fichier
    if 'portfolios' not in st.session_state:
        portfolios, counter = load_portfolios()
        st.session_state.portfolios = portfolios
        st.session_state.portfolio_counter = counter

    # Counter for unique IDs
    if 'portfolio_counter' not in st.session_state:
        st.session_state.portfolio_counter = 0

    # Selected portfolio for detailed view
    if 'selected_portfolio' not in st.session_state:
        st.session_state.selected_portfolio = None

    # Creer des portfolios de test si aucun n'existe
    if len(st.session_state.portfolios) == 0:
        create_test_portfolios()
        save_portfolios()  # Sauvegarder immediatement


def create_test_portfolios():
    """Cree des portfolios de test pour demontrer le systeme"""
    test_portfolios = [
        {
            "name": "BTC Conservative",
            "strategy": "conservative",
            "capital": 10000,
            "config": {
                "cryptos": ["BTC/USDT"],
                "allocation_percent": 5,
                "rsi_oversold": 25,
                "rsi_overbought": 75,
                "max_positions": 1,
                "auto_trade": True
            }
        },
        {
            "name": "ETH Aggressive",
            "strategy": "aggressive",
            "capital": 10000,
            "config": {
                "cryptos": ["ETH/USDT"],
                "allocation_percent": 25,
                "rsi_oversold": 35,
                "rsi_overbought": 65,
                "max_positions": 2,
                "auto_trade": True
            }
        },
        {
            "name": "Multi-Crypto RSI",
            "strategy": "rsi_strategy",
            "capital": 15000,
            "config": {
                "cryptos": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
                "allocation_percent": 15,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "max_positions": 3,
                "auto_trade": True
            }
        },
        {
            "name": "Altcoins DCA Fear",
            "strategy": "dca_fear",
            "capital": 10000,
            "config": {
                "cryptos": ["SOL/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT"],
                "allocation_percent": 10,
                "fear_greed_buy": 25,
                "fear_greed_sell": 75,
                "max_positions": 4,
                "auto_trade": True
            }
        },
        {
            "name": "BTC God Mode",
            "strategy": "god_mode_only",
            "capital": 20000,
            "config": {
                "cryptos": ["BTC/USDT"],
                "allocation_percent": 50,
                "max_positions": 1,
                "auto_trade": True
            }
        },
        {
            "name": "Top 5 Confluence",
            "strategy": "confluence_normal",
            "capital": 12000,
            "config": {
                "cryptos": ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"],
                "allocation_percent": 12,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "max_positions": 5,
                "auto_trade": True
            }
        },
        {
            "name": "HODL BTC",
            "strategy": "hodl",
            "capital": 10000,
            "config": {
                "cryptos": ["BTC/USDT"],
                "allocation_percent": 90,
                "max_positions": 1,
                "auto_trade": True
            }
        },
        {
            "name": "Strict Signals Only",
            "strategy": "confluence_strict",
            "capital": 10000,
            "config": {
                "cryptos": ["BTC/USDT", "ETH/USDT"],
                "allocation_percent": 20,
                "max_positions": 2,
                "auto_trade": True
            }
        }
    ]

    for p in test_portfolios:
        create_portfolio(p["name"], p["strategy"], p["capital"], p["config"])


def create_portfolio(name: str, strategy_id: str, initial_capital: float = 10000.0, config: dict = None) -> str:
    """Cree un nouveau portfolio avec strategie et configuration personnalisee"""
    st.session_state.portfolio_counter += 1
    portfolio_id = f"portfolio_{st.session_state.portfolio_counter}"

    strat = STRATEGIES.get(strategy_id, STRATEGIES['manuel'])

    # Merge default config with custom config
    portfolio_config = DEFAULT_CONFIG.copy()
    if config:
        portfolio_config.update(config)

    # Initialize balance for all cryptos
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

    save_portfolios()  # Sauvegarder
    return portfolio_id


def update_portfolio_config(portfolio_id: str, new_config: dict):
    """Met a jour la configuration d'un portfolio"""
    if portfolio_id in st.session_state.portfolios:
        st.session_state.portfolios[portfolio_id]['config'].update(new_config)
        save_portfolios()


def update_portfolio_strategy(portfolio_id: str, new_strategy_id: str):
    """Change la strategie d'un portfolio"""
    if portfolio_id in st.session_state.portfolios:
        strat = STRATEGIES.get(new_strategy_id, STRATEGIES['manuel'])
        st.session_state.portfolios[portfolio_id]['strategy_id'] = new_strategy_id
        st.session_state.portfolios[portfolio_id]['strategy_name'] = strat['name']
        st.session_state.portfolios[portfolio_id]['icon'] = strat['icon']
        st.session_state.portfolios[portfolio_id]['color'] = strat.get('color', '#888888')
        save_portfolios()


def delete_portfolio(portfolio_id: str):
    """Supprime un portfolio"""
    if portfolio_id in st.session_state.portfolios:
        del st.session_state.portfolios[portfolio_id]
        save_portfolios()


def get_portfolios_by_strategy(strategy_id: str) -> list:
    """Retourne tous les portfolios d'une strategie"""
    return [
        p for p in st.session_state.portfolios.values()
        if p['strategy'] == strategy_id
    ]


def get_all_portfolios_sorted() -> list:
    """Retourne tous les portfolios tries par P&L"""
    return sorted(
        st.session_state.portfolios.values(),
        key=lambda p: get_portfolio_value(p, {}) - p['initial_capital'],
        reverse=True
    )


def get_portfolio_value(portfolio: dict, prices: dict) -> float:
    """Calcule la valeur d'un portfolio"""
    total = portfolio['balance'].get('USDT', 0)
    for asset, qty in portfolio['balance'].items():
        if asset != 'USDT' and qty > 0:
            symbol = f"{asset}/USDT"
            if symbol in prices and prices[symbol].get('price'):
                total += qty * prices[symbol]['price']
    return total


def execute_portfolio_trade(portfolio_id: str, action: str, symbol: str, amount_usdt: float, price: float) -> dict:
    """Execute un trade sur un portfolio specifique"""
    portfolio = st.session_state.portfolios[portfolio_id]
    asset = symbol.split('/')[0]
    timestamp = datetime.now()

    if action == 'BUY':
        if portfolio['balance']['USDT'] >= amount_usdt:
            qty = amount_usdt / price
            portfolio['balance']['USDT'] -= amount_usdt
            portfolio['balance'][asset] = portfolio['balance'].get(asset, 0) + qty

            # Track position
            if symbol not in portfolio['positions']:
                portfolio['positions'][symbol] = {
                    'entry_price': price,
                    'quantity': qty,
                    'entry_time': timestamp
                }
            else:
                pos = portfolio['positions'][symbol]
                total_qty = pos['quantity'] + qty
                avg_price = (pos['entry_price'] * pos['quantity'] + price * qty) / total_qty
                portfolio['positions'][symbol] = {
                    'entry_price': avg_price,
                    'quantity': total_qty,
                    'entry_time': pos['entry_time']
                }

            trade = {
                'timestamp': timestamp.isoformat(),
                'action': 'BUY',
                'symbol': symbol,
                'price': price,
                'quantity': qty,
                'amount_usdt': amount_usdt,
                'pnl': 0
            }
            portfolio['trades'].append(trade)
            save_portfolios()
            return {'success': True, 'message': f"[{portfolio['name']}] Achete {qty:.6f} {asset}"}
        else:
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

            trade = {
                'timestamp': timestamp.isoformat(),
                'action': 'SELL',
                'symbol': symbol,
                'price': price,
                'quantity': qty,
                'amount_usdt': sell_value,
                'pnl': pnl
            }
            portfolio['trades'].append(trade)
            save_portfolios()
            return {'success': True, 'message': f"[{portfolio['name']}] Vendu | PnL: ${pnl:+,.2f}"}
        else:
            return {'success': False, 'message': f"Pas de {asset}"}

    return {'success': False, 'message': "Action invalide"}


def execute_strategy_signal(portfolio_id: str, action_str: str, symbol: str, price: float,
                           fear_greed: int, god_mode_level, rsi: float = 50.0):
    """Execute le signal selon la strategie et configuration du portfolio"""
    if portfolio_id not in st.session_state.portfolios:
        return None

    portfolio = st.session_state.portfolios[portfolio_id]
    strategy = STRATEGIES.get(portfolio['strategy_id'], {})
    config = portfolio['config']

    # Verifier si ce symbol est dans la liste des cryptos du portfolio
    if symbol not in config.get('cryptos', []):
        return None

    # Verifier si auto-trade est active
    if not config.get('auto_trade', True):
        return None

    # Verifier le nombre max de positions
    if len(portfolio['positions']) >= config.get('max_positions', 3):
        if symbol not in portfolio['positions']:
            return None  # Max positions atteint

    # Map action string to check
    action_map = {
        "🟢 BUY": "BUY",
        "🟢🟢 STRONG BUY": "STRONG_BUY",
        "🔴 SELL": "SELL",
        "🔴🔴 STRONG SELL": "STRONG_SELL",
        "🚨 GOD MODE BUY": "GOD_MODE_BUY",
        "⚪ HOLD": "HOLD"
    }
    action_type = action_map.get(action_str, "HOLD")
    allocation = config.get('allocation_percent', 10)
    asset = symbol.split('/')[0]

    # Strategie DCA Fear - utilise les seuils personnalises
    if strategy.get('use_fear_greed', False):
        fear_buy_threshold = config.get('fear_greed_buy', 25)
        fear_sell_threshold = config.get('fear_greed_sell', 75)

        if fear_greed < fear_buy_threshold and portfolio['balance']['USDT'] > 100:
            amount = portfolio['balance']['USDT'] * (allocation / 100)
            return execute_portfolio_trade(portfolio_id, 'BUY', symbol, amount, price)
        elif fear_greed > fear_sell_threshold and portfolio['balance'].get(asset, 0) > 0:
            return execute_portfolio_trade(portfolio_id, 'SELL', symbol, 0, price)
        return None

    # Strategie RSI - utilise les seuils personnalises
    if strategy.get('use_rsi', False):
        rsi_oversold = config.get('rsi_oversold', 30)
        rsi_overbought = config.get('rsi_overbought', 70)

        if rsi < rsi_oversold and portfolio['balance']['USDT'] > 100:
            amount = portfolio['balance']['USDT'] * (allocation / 100)
            return execute_portfolio_trade(portfolio_id, 'BUY', symbol, amount, price)
        elif rsi > rsi_overbought and portfolio['balance'].get(asset, 0) > 0:
            return execute_portfolio_trade(portfolio_id, 'SELL', symbol, 0, price)
        return None

    # Strategie HODL - achete une fois et ne vend jamais
    if strategy.get('buy_on') == ["ALWAYS_FIRST"]:
        if len(portfolio['trades']) == 0 and portfolio['balance']['USDT'] > 100:
            amount = portfolio['balance']['USDT'] * (allocation / 100)
            return execute_portfolio_trade(portfolio_id, 'BUY', symbol, amount, price)
        return None

    # Strategies standard basees sur les signaux confluence
    buy_signals = strategy.get('buy_on', [])
    sell_signals = strategy.get('sell_on', [])

    if action_type in buy_signals and portfolio['balance']['USDT'] > 100:
        amount = portfolio['balance']['USDT'] * (allocation / 100)
        return execute_portfolio_trade(portfolio_id, 'BUY', symbol, amount, price)
    elif action_type in sell_signals and portfolio['balance'].get(asset, 0) > 0:
        return execute_portfolio_trade(portfolio_id, 'SELL', symbol, 0, price)

    return None


def execute_signals_for_all_portfolios(action_str: str, symbol: str, price: float,
                                        fear_greed: int, god_mode_level, rsi: float = 50.0) -> list:
    """Execute le signal sur tous les portfolios actifs"""
    results = []
    for portfolio_id, portfolio in st.session_state.portfolios.items():
        if portfolio.get('active', True):
            result = execute_strategy_signal(
                portfolio_id, action_str, symbol, price,
                fear_greed, god_mode_level, rsi
            )
            if result and result.get('success'):
                results.append({
                    'portfolio': portfolio['name'],
                    'message': result['message']
                })
    return results


def analyze_crypto_quick(symbol: str) -> dict:
    """Analyse rapide d'une crypto - retourne signal, prix, RSI"""
    try:
        # Fetch OHLCV
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.replace('/', '')}&interval=1h&limit=100"
        response = requests.get(url, timeout=10)
        data = response.json()

        if not data or len(data) < 50:
            return None

        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                          'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                                          'taker_buy_quote', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)

        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]

        # Calculate EMAs
        ema_12 = df['close'].ewm(span=12).mean().iloc[-1]
        ema_26 = df['close'].ewm(span=26).mean().iloc[-1]

        # Current price
        current_price = df['close'].iloc[-1]

        # Determine signal
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
            'ema_12': ema_12,
            'ema_26': ema_26,
            'signal': signal,
            'trend': 'bullish' if ema_12 > ema_26 else 'bearish'
        }

    except Exception as e:
        return None


def run_portfolio_engine():
    """Execute le moteur de trading pour tous les portfolios actifs"""
    results = []
    analyzed_cryptos = {}  # Cache pour eviter d'analyser plusieurs fois la meme crypto

    for port_id, portfolio in st.session_state.portfolios.items():
        if not portfolio.get('active', True):
            continue

        config = portfolio['config']
        if not config.get('auto_trade', True):
            continue

        strategy = STRATEGIES.get(portfolio['strategy_id'], {})

        for crypto in config.get('cryptos', []):
            # Analyser la crypto (avec cache)
            if crypto not in analyzed_cryptos:
                analysis = analyze_crypto_quick(crypto)
                analyzed_cryptos[crypto] = analysis

            analysis = analyzed_cryptos.get(crypto)
            if not analysis:
                continue

            price = analysis['price']
            rsi = analysis['rsi']
            signal = analysis['signal']

            # Convertir signal en action string
            signal_map = {
                "STRONG_BUY": "🟢🟢 STRONG BUY",
                "BUY": "🟢 BUY",
                "SELL": "🔴 SELL",
                "STRONG_SELL": "🔴🔴 STRONG SELL",
                "HOLD": "⚪ HOLD"
            }
            action_str = signal_map.get(signal, "⚪ HOLD")

            # Executer selon la strategie
            result = execute_strategy_signal(
                port_id, action_str, crypto, price,
                50,  # fear_greed placeholder
                None,  # god_mode_level placeholder
                rsi
            )

            if result and result.get('success'):
                results.append({
                    'portfolio': portfolio['name'],
                    'crypto': crypto,
                    'action': signal,
                    'price': price,
                    'message': result['message']
                })

    return results, analyzed_cryptos


def reset_all_portfolios():
    """Reset tous les portfolios"""
    st.session_state.portfolios = {}
    st.session_state.portfolio_counter = 0
    save_portfolios()


def reset_strategy_portfolios(strategy_id: str):
    """Reset les portfolios d'une strategie"""
    to_delete = [pid for pid, p in st.session_state.portfolios.items() if p.get('strategy_id') == strategy_id]
    for pid in to_delete:
        del st.session_state.portfolios[pid]
    save_portfolios()




def main():
    # Init paper trading
    init_paper_trading()

    # Header
    st.markdown('<p class="main-header">🎯 Multi-Signal Confluence Trading Bot</p>', unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")

        symbol = st.selectbox("Symbole", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"])
        timeframe = st.selectbox("Timeframe", ["1h", "4h", "1d", "15m", "5m"])

        st.divider()

        # Toggle pour donnees reelles
        use_real_data = st.toggle("📡 Donnees Temps Reel", value=True)

        if not use_real_data:
            trend_sim = st.selectbox("Simulation Tendance", ["bullish", "bearish", "neutral"])
        else:
            trend_sim = "neutral"

        st.divider()

        st.header("📊 Parametres")
        confluence_threshold = st.slider("Seuil de Confluence", 1, 3, 2)
        risk_percent = st.slider("Risque par Trade (%)", 1, 5, 2)

        st.divider()

        # Auto-refresh
        auto_refresh = st.toggle("🔄 Auto-refresh", value=False)

        if auto_refresh:
            refresh_rate = st.select_slider(
                "Frequence",
                options=[30, 60, 120, 300, 600],
                value=60,
                format_func=lambda x: f"{x//60}min" if x >= 60 else f"{x}s"
            )
            auto_execute = st.toggle("⚡ Auto-Execute Signals", value=False,
                                      help="Execute automatiquement les signaux sur tous les portfolios")
        else:
            refresh_rate = 60
            auto_execute = False

        if st.button("🔄 Rafraichir Maintenant", type="primary", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.divider()

        if use_real_data:
            st.success("📡 Connecte a Binance API")
        else:
            st.info("🎮 Mode Simulation")

    # ==================== LIVE TICKER ====================
    if use_real_data:
        # Live prices (no cache - real-time)
        live_prices = fetch_all_live_prices()

        if live_prices:
            st.markdown("### ⚡ Prix en Direct")

            # Create live ticker row
            ticker_cols = st.columns(4)

            for i, (sym, data) in enumerate(live_prices.items()):
                with ticker_cols[i]:
                    change_delta = data['change']
                    arrow = "🟢 ↑" if change_delta > 0 else ("🔴 ↓" if change_delta < 0 else "⚪ →")

                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                                padding: 1rem; border-radius: 10px; text-align: center;
                                border: 1px solid {'#00ff88' if change_delta > 0 else '#ff4444' if change_delta < 0 else '#888'};">
                        <h4 style="margin: 0; color: #888;">{sym.replace('/USDT', '')}</h4>
                        <h2 style="margin: 0.5rem 0; color: white;">${data['price']:,.2f}</h2>
                        <p style="margin: 0; color: {'#00ff88' if change_delta > 0 else '#ff4444' if change_delta < 0 else '#888'};">
                            {arrow} {change_delta:+.2f}%
                        </p>
                        <p style="margin: 0.5rem 0 0 0; color: #666; font-size: 0.8rem;">
                            H: ${data['high']:,.2f} | L: ${data['low']:,.2f}
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

            # Auto-refresh toggle in sidebar already exists, let's add refresh rate option
            st.markdown(f"""
            <p style="text-align: center; color: #666; font-size: 0.8rem; margin-top: 0.5rem;">
                ⏱️ Derniere maj: {datetime.now().strftime('%H:%M:%S')}
            </p>
            """, unsafe_allow_html=True)

            st.divider()

    # ==================== PORTFOLIO CARDS ====================
    if st.session_state.portfolios:
        st.markdown("### 💼 Portfolios")

        # Global play/pause buttons
        ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2, 1, 1, 1])

        with ctrl_col1:
            st.markdown(f"**{len(st.session_state.portfolios)} portfolios** | Capital total: **${sum(p['initial_capital'] for p in st.session_state.portfolios.values()):,.0f}**")

        with ctrl_col2:
            if st.button("▶️ Play All", type="primary", use_container_width=True, key="btn_play_all"):
                for pid in st.session_state.portfolios:
                    st.session_state.portfolios[pid]['active'] = True
                save_portfolios()
                st.rerun()

        with ctrl_col3:
            if st.button("⏸️ Pause All", use_container_width=True, key="btn_pause_all"):
                for pid in st.session_state.portfolios:
                    st.session_state.portfolios[pid]['active'] = False
                save_portfolios()
                st.rerun()

        with ctrl_col4:
            if st.button("➕ Nouveau", use_container_width=True, key="btn_new_portfolio"):
                st.session_state.show_create_portfolio = not st.session_state.get('show_create_portfolio', False)
                st.rerun()

        # Run Engine button - prominent
        engine_col1, engine_col2 = st.columns([3, 1])
        with engine_col1:
            active_count = sum(1 for p in st.session_state.portfolios.values() if p.get('active', True))
            total_cryptos = len(set(c for p in st.session_state.portfolios.values() for c in p['config'].get('cryptos', [])))
            st.markdown(f"🔍 **{active_count} portfolios actifs** surveillant **{total_cryptos} cryptos**")

        with engine_col2:
            if st.button("🚀 RUN ENGINE", type="primary", use_container_width=True, key="btn_run_engine"):
                with st.spinner("Analyse en cours..."):
                    results, analyzed = run_portfolio_engine()
                    st.session_state['last_engine_results'] = results
                    st.session_state['last_engine_analysis'] = analyzed
                    st.session_state['last_engine_time'] = datetime.now().strftime('%H:%M:%S')
                    if results:
                        save_portfolios()
                st.rerun()

        # Show last engine results
        if st.session_state.get('last_engine_analysis'):
            with st.expander(f"📡 Dernière analyse ({st.session_state.get('last_engine_time', '')})", expanded=True):
                analysis_data = []
                for sym, data in st.session_state['last_engine_analysis'].items():
                    if data:
                        signal_color = "🟢" if "BUY" in data['signal'] else ("🔴" if "SELL" in data['signal'] else "⚪")
                        analysis_data.append({
                            'Crypto': sym.replace('/USDT', ''),
                            'Prix': f"${data['price']:,.2f}",
                            'RSI': f"{data['rsi']:.1f}",
                            'Trend': "📈" if data['trend'] == 'bullish' else "📉",
                            'Signal': f"{signal_color} {data['signal']}"
                        })

                if analysis_data:
                    st.dataframe(pd.DataFrame(analysis_data), hide_index=True, use_container_width=True)

                # Show executed trades
                if st.session_state.get('last_engine_results'):
                    st.markdown("**⚡ Trades exécutés:**")
                    for r in st.session_state['last_engine_results']:
                        st.success(f"{r['portfolio']}: {r['action']} {r['crypto']} @ ${r['price']:,.2f}")

        # Quick create portfolio form
        if st.session_state.get('show_create_portfolio', False):
            with st.container():
                st.markdown("#### ➕ Créer un Portfolio Rapide")
                qc_col1, qc_col2, qc_col3, qc_col4 = st.columns([2, 2, 1, 1])

                with qc_col1:
                    quick_name = st.text_input("Nom", value=f"Portfolio {st.session_state.portfolio_counter + 1}", key="quick_name")

                with qc_col2:
                    quick_strategy = st.selectbox(
                        "Stratégie",
                        list(STRATEGIES.keys()),
                        format_func=lambda x: f"{STRATEGIES[x]['icon']} {STRATEGIES[x]['name']}",
                        key="quick_strategy"
                    )

                with qc_col3:
                    quick_capital = st.number_input("Capital $", min_value=100, value=10000, step=1000, key="quick_capital")

                with qc_col4:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("✅ Créer", type="primary", use_container_width=True, key="btn_quick_create"):
                        create_portfolio(quick_name, quick_strategy, float(quick_capital))
                        st.session_state.show_create_portfolio = False
                        st.success(f"Portfolio '{quick_name}' créé!")
                        st.rerun()

                if st.button("❌ Annuler", use_container_width=True, key="btn_cancel_create"):
                    st.session_state.show_create_portfolio = False
                    st.rerun()

        # Portfolio cards grid (4 per row)
        portfolios_list = list(st.session_state.portfolios.items())

        # Pre-calculate prices for portfolio values
        temp_prices = fetch_multiple_prices() if use_real_data else {}
        temp_current_price = fetch_real_price(symbol) if use_real_data else 45000

        for row_start in range(0, len(portfolios_list), 4):
            row_portfolios = portfolios_list[row_start:row_start + 4]
            cols = st.columns(4)

            for idx, (port_id, portfolio) in enumerate(row_portfolios):
                with cols[idx]:
                    # Calculate value
                    value = portfolio['balance'].get('USDT', 0)
                    for asset, qty in portfolio['balance'].items():
                        if asset != 'USDT' and qty > 0:
                            sym = f"{asset}/USDT"
                            if temp_prices and sym in temp_prices and temp_prices[sym].get('price'):
                                value += qty * temp_prices[sym]['price']
                            elif sym == symbol:
                                value += qty * temp_current_price

                    initial = portfolio['initial_capital']
                    pnl = value - initial
                    pnl_pct = (pnl / initial) * 100 if initial > 0 else 0
                    is_active = portfolio.get('active', True)

                    # Card styling
                    border_color = '#00ff88' if is_active else '#ff4444'
                    status_icon = '▶️' if is_active else '⏸️'
                    pnl_color = '#00ff88' if pnl >= 0 else '#ff4444'

                    st.markdown(f"""
                    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                                border-radius: 12px; padding: 1rem;
                                border: 2px solid {border_color};
                                {'box-shadow: 0 0 15px rgba(0,255,136,0.2);' if is_active else 'opacity: 0.8;'}">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 1.5rem;">{portfolio['icon']}</span>
                            <span style="color: {border_color};">{status_icon}</span>
                        </div>
                        <h4 style="margin: 0.5rem 0 0.2rem 0; color: white; font-size: 0.95rem;">{portfolio['name'][:18]}</h4>
                        <p style="margin: 0; color: #888; font-size: 0.75rem;">{portfolio['strategy_name']}</p>
                        <h3 style="margin: 0.5rem 0; color: white;">${value:,.0f}</h3>
                        <p style="margin: 0; color: {pnl_color}; font-weight: bold;">
                            {'+' if pnl >= 0 else ''}{pnl_pct:.1f}% (${pnl:+,.0f})
                        </p>
                        <p style="margin: 0.3rem 0 0 0; color: #666; font-size: 0.7rem;">
                            {len(portfolio['trades'])} trades | {len(portfolio['positions'])} pos
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

                    # Buttons row
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        btn_label = "⏸️" if is_active else "▶️"
                        if st.button(btn_label, key=f"toggle_{port_id}", use_container_width=True):
                            st.session_state.portfolios[port_id]['active'] = not is_active
                            save_portfolios()
                            st.rerun()
                    with btn_col2:
                        if st.button("📊", key=f"view_{port_id}", use_container_width=True):
                            st.session_state.selected_portfolio = port_id

        # ==================== PORTFOLIO DETAIL VIEW ====================
        if st.session_state.get('selected_portfolio') and st.session_state.selected_portfolio in st.session_state.portfolios:
            port_id = st.session_state.selected_portfolio
            portfolio = st.session_state.portfolios[port_id]
            config = portfolio['config']

            # Calculate current value
            port_value = portfolio['balance'].get('USDT', 0)
            for asset, qty in portfolio['balance'].items():
                if asset != 'USDT' and qty > 0:
                    sym = f"{asset}/USDT"
                    if temp_prices and sym in temp_prices and temp_prices[sym].get('price'):
                        port_value += qty * temp_prices[sym]['price']

            port_pnl = port_value - portfolio['initial_capital']
            port_pnl_pct = (port_pnl / portfolio['initial_capital']) * 100 if portfolio['initial_capital'] > 0 else 0

            st.markdown("---")
            st.markdown(f"### {portfolio['icon']} {portfolio['name']} - Vue Détaillée")

            # Close button
            if st.button("❌ Fermer", key="close_detail"):
                st.session_state.selected_portfolio = None
                st.rerun()

            # Info tabs
            detail_tabs = st.tabs(["📊 Overview", "📜 Historique", "⚙️ Configuration", "📈 Positions"])

            with detail_tabs[0]:  # Overview
                ov_col1, ov_col2, ov_col3, ov_col4 = st.columns(4)

                with ov_col1:
                    st.metric("💰 Valeur Actuelle", f"${port_value:,.2f}")
                with ov_col2:
                    st.metric("📈 P&L Total", f"${port_pnl:+,.2f}", f"{port_pnl_pct:+.2f}%")
                with ov_col3:
                    st.metric("💵 Capital Initial", f"${portfolio['initial_capital']:,.2f}")
                with ov_col4:
                    st.metric("📊 Trades", len(portfolio['trades']))

                st.markdown("---")

                # Stats
                trades = portfolio['trades']
                if trades:
                    wins = len([t for t in trades if t.get('pnl', 0) > 0])
                    losses = len([t for t in trades if t.get('pnl', 0) < 0])
                    total_pnl = sum(t.get('pnl', 0) for t in trades)
                    avg_pnl = total_pnl / len(trades) if trades else 0
                    best_trade = max(trades, key=lambda x: x.get('pnl', 0))
                    worst_trade = min(trades, key=lambda x: x.get('pnl', 0))

                    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)

                    with stat_col1:
                        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
                        st.metric("🎯 Win Rate", f"{win_rate:.1f}%")
                    with stat_col2:
                        st.metric("✅ Gagnants", wins)
                    with stat_col3:
                        st.metric("❌ Perdants", losses)
                    with stat_col4:
                        st.metric("📊 P&L Moyen", f"${avg_pnl:+,.2f}")

                    st.markdown("---")

                    best_col, worst_col = st.columns(2)
                    with best_col:
                        st.success(f"🏆 Meilleur trade: ${best_trade.get('pnl', 0):+,.2f} ({best_trade.get('symbol', 'N/A')})")
                    with worst_col:
                        st.error(f"📉 Pire trade: ${worst_trade.get('pnl', 0):+,.2f} ({worst_trade.get('symbol', 'N/A')})")
                else:
                    st.info("Aucun trade effectué")

                # Balance breakdown
                st.markdown("#### 💼 Composition du Portfolio")
                balance_data = []
                for asset, qty in portfolio['balance'].items():
                    if qty > 0:
                        if asset == 'USDT':
                            val = qty
                        else:
                            sym = f"{asset}/USDT"
                            price = temp_prices.get(sym, {}).get('price', 0) if temp_prices else 0
                            val = qty * price
                        balance_data.append({
                            'Asset': asset,
                            'Quantité': f"{qty:.6f}" if asset != 'USDT' else f"${qty:,.2f}",
                            'Valeur USD': f"${val:,.2f}",
                            '% Portfolio': f"{(val/port_value*100):.1f}%" if port_value > 0 else "0%"
                        })

                if balance_data:
                    st.dataframe(pd.DataFrame(balance_data), hide_index=True, use_container_width=True)

            with detail_tabs[1]:  # Historique
                st.markdown("#### 📜 Historique des Trades")

                if portfolio['trades']:
                    trades_data = []
                    for t in reversed(portfolio['trades']):  # Most recent first
                        pnl_emoji = "🟢" if t.get('pnl', 0) > 0 else ("🔴" if t.get('pnl', 0) < 0 else "⚪")
                        trades_data.append({
                            'Date': t.get('timestamp', 'N/A')[:19] if isinstance(t.get('timestamp'), str) else str(t.get('timestamp', 'N/A'))[:19],
                            'Action': f"{'🟢 BUY' if t['action'] == 'BUY' else '🔴 SELL'}",
                            'Symbol': t.get('symbol', 'N/A'),
                            'Prix': f"${t.get('price', 0):,.2f}",
                            'Quantité': f"{t.get('quantity', 0):.6f}",
                            'Montant': f"${t.get('amount_usdt', 0):,.2f}",
                            'P&L': f"{pnl_emoji} ${t.get('pnl', 0):+,.2f}"
                        })

                    st.dataframe(pd.DataFrame(trades_data), hide_index=True, use_container_width=True, height=400)

                    # Export button
                    csv = pd.DataFrame(trades_data).to_csv(index=False)
                    st.download_button(
                        "📥 Exporter CSV",
                        csv,
                        f"{portfolio['name']}_trades.csv",
                        "text/csv",
                        use_container_width=True
                    )
                else:
                    st.info("Aucun trade dans l'historique")

            with detail_tabs[2]:  # Configuration
                st.markdown("#### ⚙️ Configuration du Portfolio")

                cfg_col1, cfg_col2 = st.columns(2)

                with cfg_col1:
                    st.markdown("**Stratégie**")
                    new_strategy = st.selectbox(
                        "Stratégie",
                        list(STRATEGIES.keys()),
                        index=list(STRATEGIES.keys()).index(portfolio['strategy_id']) if portfolio['strategy_id'] in STRATEGIES else 0,
                        format_func=lambda x: f"{STRATEGIES[x]['icon']} {STRATEGIES[x]['name']}",
                        key=f"strat_select_{port_id}"
                    )

                    st.markdown("**Cryptos à trader**")
                    new_cryptos = st.multiselect(
                        "Cryptos",
                        AVAILABLE_CRYPTOS,
                        default=config.get('cryptos', ['BTC/USDT']),
                        key=f"crypto_select_{port_id}"
                    )

                with cfg_col2:
                    st.markdown("**Paramètres**")
                    new_alloc = st.slider("Allocation par trade (%)", 1, 100, config.get('allocation_percent', 10), key=f"alloc_{port_id}_detail")
                    new_max_pos = st.slider("Max positions", 1, 10, config.get('max_positions', 3), key=f"maxpos_{port_id}_detail")
                    new_rsi_low = st.slider("RSI Oversold", 10, 50, config.get('rsi_oversold', 30), key=f"rsi_low_{port_id}_detail")
                    new_rsi_high = st.slider("RSI Overbought", 50, 90, config.get('rsi_overbought', 70), key=f"rsi_high_{port_id}_detail")

                st.markdown("---")

                save_col, reset_col, delete_col = st.columns(3)

                with save_col:
                    if st.button("💾 Sauvegarder", type="primary", use_container_width=True, key=f"save_detail_{port_id}"):
                        update_portfolio_config(port_id, {
                            'cryptos': new_cryptos,
                            'allocation_percent': new_alloc,
                            'max_positions': new_max_pos,
                            'rsi_oversold': new_rsi_low,
                            'rsi_overbought': new_rsi_high
                        })
                        if new_strategy != portfolio['strategy_id']:
                            update_portfolio_strategy(port_id, new_strategy)
                        st.success("Configuration sauvegardée!")
                        st.rerun()

                with reset_col:
                    if st.button("🔄 Reset Portfolio", use_container_width=True, key=f"reset_detail_{port_id}"):
                        portfolio['balance'] = {'USDT': portfolio['initial_capital']}
                        for crypto in AVAILABLE_CRYPTOS:
                            asset = crypto.split('/')[0]
                            portfolio['balance'][asset] = 0.0
                        portfolio['positions'] = {}
                        portfolio['trades'] = []
                        save_portfolios()
                        st.success("Portfolio réinitialisé!")
                        st.rerun()

                with delete_col:
                    if st.button("🗑️ Supprimer", use_container_width=True, key=f"delete_detail_{port_id}"):
                        delete_portfolio(port_id)
                        st.session_state.selected_portfolio = None
                        st.rerun()

            with detail_tabs[3]:  # Positions
                st.markdown("#### 📈 Positions Ouvertes")

                if portfolio['positions']:
                    pos_data = []
                    for sym, pos in portfolio['positions'].items():
                        asset = sym.split('/')[0]
                        entry = pos.get('entry_price', 0)
                        qty = pos.get('quantity', 0)
                        current = temp_prices.get(sym, {}).get('price', entry) if temp_prices else entry
                        unrealized = (current - entry) * qty
                        unrealized_pct = ((current - entry) / entry * 100) if entry > 0 else 0

                        pos_data.append({
                            'Symbol': sym,
                            'Quantité': f"{qty:.6f}",
                            'Prix Entrée': f"${entry:,.2f}",
                            'Prix Actuel': f"${current:,.2f}",
                            'P&L': f"{'🟢' if unrealized >= 0 else '🔴'} ${unrealized:+,.2f}",
                            'P&L %': f"{unrealized_pct:+.2f}%",
                            'Valeur': f"${qty * current:,.2f}"
                        })

                    st.dataframe(pd.DataFrame(pos_data), hide_index=True, use_container_width=True)

                    # Close position buttons
                    st.markdown("**Actions:**")
                    for sym in portfolio['positions'].keys():
                        if st.button(f"🔴 Fermer {sym}", key=f"close_pos_{port_id}_{sym}"):
                            current = temp_prices.get(sym, {}).get('price', 0) if temp_prices else 0
                            if current > 0:
                                execute_portfolio_trade(port_id, 'SELL', sym, 0, current)
                                st.success(f"Position {sym} fermée!")
                                st.rerun()
                else:
                    st.info("Aucune position ouverte")

        st.divider()

    # Recuperer les donnees
    if use_real_data:
        df = fetch_real_ohlcv(symbol, timeframe, 200)
        all_prices = fetch_multiple_prices()
    else:
        df = generate_sample_ohlcv(30, trend_sim)
        all_prices = {}

    current_price = df['close'].iloc[-1]
    price_change_24h = ((df['close'].iloc[-1] - df['close'].iloc[-25]) / df['close'].iloc[-25] * 100) if len(df) > 25 else 0

    # Apercu du marche (si donnees reelles)
    if use_real_data and all_prices:
        st.markdown("### 📊 Apercu du Marche")
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)

        for i, (sym, data) in enumerate(all_prices.items()):
            col = [mcol1, mcol2, mcol3, mcol4][i]
            with col:
                change_color = "green" if data['change'] and data['change'] > 0 else "red"
                st.metric(
                    label=sym.replace('/USDT', ''),
                    value=f"${data['price']:,.2f}" if data['price'] else "N/A",
                    delta=f"{data['change']:.2f}%" if data['change'] else None
                )
        st.divider()

    # Analyse
    technical_analyzer = TechnicalAnalyzer()
    technical_result = technical_analyzer.analyze(df)
    tech_signal = technical_analyzer.get_signal_value(technical_result)

    sentiment_result = run_async(SentimentAnalyzer().analyze(symbol.split('/')[0]))
    sent_signal = sentiment_result.signal

    onchain_result = run_async(OnChainAnalyzer().analyze(symbol.split('/')[0]))
    chain_signal = onchain_result.signal

    godmode_result = run_async(GodModeDetector().detect(current_price))

    # Calculer confluence
    confluence_score = tech_signal + sent_signal + chain_signal
    signals_aligned = max(
        sum(1 for s in [tech_signal, sent_signal, chain_signal] if s > 0),
        sum(1 for s in [tech_signal, sent_signal, chain_signal] if s < 0)
    )

    # Determiner l'action
    if godmode_result.level == GodModeLevel.EXTREME:
        action = "🚨 GOD MODE BUY"
        action_color = "#ff0000"
        confidence = 95
    elif signals_aligned >= 3 and confluence_score > 0:
        action = "🟢🟢 STRONG BUY"
        action_color = "#00ff88"
        confidence = 90
    elif signals_aligned >= 3 and confluence_score < 0:
        action = "🔴🔴 STRONG SELL"
        action_color = "#ff4444"
        confidence = 90
    elif signals_aligned >= 2 and confluence_score > 0:
        action = "🟢 BUY"
        action_color = "#00ff88"
        confidence = 70
    elif signals_aligned >= 2 and confluence_score < 0:
        action = "🔴 SELL"
        action_color = "#ff4444"
        confidence = 70
    else:
        action = "⚪ HOLD"
        action_color = "#888888"
        confidence = 50

    # Layout principal
    # Row 1: Metriques principales
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label=f"💰 {symbol}",
            value=f"${current_price:,.2f}",
            delta=f"{price_change_24h:.2f}%"
        )

    with col2:
        st.metric(
            label="📈 RSI (14)",
            value=f"{technical_result.rsi:.1f}",
            delta="Oversold" if technical_result.rsi < 30 else ("Overbought" if technical_result.rsi > 70 else "Neutral")
        )

    with col3:
        st.metric(
            label="😱 Fear & Greed",
            value=f"{sentiment_result.fear_greed_index}",
            delta="Extreme Fear" if sentiment_result.fear_greed_index < 25 else ("Extreme Greed" if sentiment_result.fear_greed_index > 75 else "Neutral")
        )

    with col4:
        god_mode_text = godmode_result.level.name
        st.metric(
            label="🔮 God Mode",
            value=god_mode_text,
            delta=f"Score: {godmode_result.score}/100"
        )

    st.divider()

    # Row 2: Action principale
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%); padding: 2rem; border-radius: 15px; text-align: center; border: 2px solid {action_color};">
            <h1 style="color: {action_color}; margin: 0; font-size: 3rem;">{action}</h1>
            <p style="color: #888; margin-top: 1rem; font-size: 1.2rem;">Confiance: {confidence}% | Signaux alignes: {signals_aligned}/3</p>
            <p style="color: #666; margin-top: 0.5rem;">Allocation recommandee: {godmode_result.recommended_allocation}%</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        # Mini tableau des signaux
        st.markdown("""
        <div style="background: #1e1e2e; padding: 1rem; border-radius: 10px;">
            <h4 style="color: white; margin-bottom: 1rem;">📊 Signaux</h4>
        </div>
        """, unsafe_allow_html=True)

        signal_data = {
            "Source": ["Technical", "Sentiment", "On-Chain"],
            "Signal": [
                "🟢 BUY" if tech_signal > 0 else ("🔴 SELL" if tech_signal < 0 else "⚪ NEUTRAL"),
                "🟢 BUY" if sent_signal > 0 else ("🔴 SELL" if sent_signal < 0 else "⚪ NEUTRAL"),
                "🟢 BUY" if chain_signal > 0 else ("🔴 SELL" if chain_signal < 0 else "⚪ NEUTRAL"),
            ],
            "Value": [tech_signal, sent_signal, chain_signal]
        }
        st.dataframe(pd.DataFrame(signal_data), hide_index=True, use_container_width=True)

    st.divider()

    # Row 3: Onglets principaux
    main_tabs = st.tabs([
        "📈 Analyse",
        "💼 Portfolios",
        "🏆 Leaderboard",
        "⚙️ Creer Portfolio"
    ])

    tab_analyse, tab_portfolios, tab_leaderboard, tab_create = main_tabs

    # ==================== TAB ANALYSE ====================
    with tab_analyse:
        subtab1, subtab2, subtab3 = st.tabs(["📈 Graphique", "🎯 Signaux", "🔮 God Mode"])

        with subtab1:
            st.plotly_chart(create_candlestick_chart(df), use_container_width=True)

        with subtab2:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.plotly_chart(create_signal_gauge(tech_signal, "Technical"), use_container_width=True)
            with col2:
                st.plotly_chart(create_signal_gauge(sent_signal, "Sentiment"), use_container_width=True)
            with col3:
                st.plotly_chart(create_signal_gauge(chain_signal, "On-Chain"), use_container_width=True)

        with subtab3:
            col1, col2 = st.columns([1, 1])

            with col1:
                st.plotly_chart(create_god_mode_chart(godmode_result.conditions), use_container_width=True)

            with col2:
                st.markdown(f"""
                <div style="background: #1e1e2e; padding: 1.5rem; border-radius: 10px;">
                    <h3 style="color: #7c3aed;">🔮 God Mode Status</h3>
                    <p style="font-size: 2rem; margin: 1rem 0;">
                        {"🚨" if godmode_result.level == GodModeLevel.EXTREME else "🟢" if godmode_result.level == GodModeLevel.ACTIVATED else "🟡" if godmode_result.level == GodModeLevel.WARMING_UP else "⚪"}
                        {godmode_result.level.name}
                    </p>
                    <p>Score: <b>{godmode_result.score}/100</b></p>
                    <p>Conditions: <b>{godmode_result.conditions_met}/{godmode_result.total_conditions}</b></p>
                    <p>Allocation: <b>{godmode_result.recommended_allocation}%</b></p>
                    <hr style="border-color: #3d3d5c;">
                    <p style="color: #888; font-size: 0.9rem;">{godmode_result.message}</p>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("**Conditions:**")
                for c in godmode_result.conditions:
                    status = "✅" if c.is_met else "❌"
                    st.text(f"{status} {c.name}: {c.value:.2f} (seuil: {c.threshold})")

    # ==================== TAB PORTFOLIOS ====================
    with tab_portfolios:
        st.markdown("### 💼 Gestion des Portfolios")

        if not st.session_state.portfolios:
            st.info("Aucun portfolio cree. Allez dans l'onglet 'Creer Portfolio' pour commencer!")
        else:
            # Execute button for all portfolios
            col_exec, col_reset = st.columns([3, 1])
            with col_exec:
                if st.button("▶️ Executer le Signal sur Tous les Portfolios", type="primary", use_container_width=True):
                    results = execute_signals_for_all_portfolios(
                        action, symbol, current_price,
                        sentiment_result.fear_greed_index, godmode_result.level,
                        technical_result.rsi
                    )
                    if results:
                        st.success(f"{len(results)} trades executes!")
                        for r in results:
                            st.write(f"  • {r['portfolio']}: {r['message']}")
                        st.rerun()
                    else:
                        st.info("Aucun trade execute (conditions non remplies)")

            with col_reset:
                if st.button("🗑️ Reset Tous", use_container_width=True):
                    reset_all_portfolios()
                    st.rerun()

            st.divider()

            # Display each portfolio
            for port_id, portfolio in st.session_state.portfolios.items():
                # Calculate portfolio value
                value = get_portfolio_value(portfolio, all_prices if use_real_data else {})
                if not use_real_data or not all_prices:
                    value = portfolio['balance']['USDT']
                    for asset, qty in portfolio['balance'].items():
                        if asset != 'USDT' and qty > 0:
                            if f"{asset}/USDT" == symbol:
                                value += qty * current_price

                initial = portfolio['initial_capital']
                pnl = value - initial
                pnl_pct = (pnl / initial) * 100 if initial > 0 else 0
                config = portfolio['config']

                border_color = '#00ff88' if pnl >= 0 else '#ff4444'

                with st.expander(f"{portfolio['icon']} **{portfolio['name']}** | ${value:,.2f} | P&L: ${pnl:+,.2f} ({pnl_pct:+.1f}%)"):
                    # Info row
                    info_col1, info_col2, info_col3, info_col4 = st.columns(4)
                    with info_col1:
                        st.metric("Valeur", f"${value:,.2f}")
                    with info_col2:
                        st.metric("P&L", f"${pnl:+,.2f}", f"{pnl_pct:+.1f}%")
                    with info_col3:
                        st.metric("Trades", len(portfolio['trades']))
                    with info_col4:
                        wins = len([t for t in portfolio['trades'] if t.get('pnl', 0) > 0])
                        total = len([t for t in portfolio['trades'] if t.get('pnl', 0) != 0])
                        wr = (wins / total * 100) if total > 0 else 0
                        st.metric("Win Rate", f"{wr:.0f}%")

                    # Strategy & Config
                    st.markdown(f"**Strategie:** {portfolio['strategy_name']}")
                    st.markdown(f"**Cryptos:** {', '.join(config.get('cryptos', []))}")

                    # Configuration editor
                    st.markdown("---")
                    st.markdown("**⚙️ Configuration:**")

                    cfg_col1, cfg_col2, cfg_col3 = st.columns(3)

                    with cfg_col1:
                        new_cryptos = st.multiselect(
                            "Cryptos a trader",
                            AVAILABLE_CRYPTOS,
                            default=config.get('cryptos', ['BTC/USDT']),
                            key=f"cryptos_{port_id}"
                        )

                    with cfg_col2:
                        new_alloc = st.slider(
                            "Allocation %",
                            1, 100,
                            config.get('allocation_percent', 10),
                            key=f"alloc_{port_id}"
                        )

                    with cfg_col3:
                        new_max_pos = st.slider(
                            "Max positions",
                            1, 10,
                            config.get('max_positions', 3),
                            key=f"maxpos_{port_id}"
                        )

                    cfg_col4, cfg_col5, cfg_col6 = st.columns(3)

                    with cfg_col4:
                        new_rsi_low = st.slider(
                            "RSI Oversold",
                            10, 50,
                            config.get('rsi_oversold', 30),
                            key=f"rsi_low_{port_id}"
                        )

                    with cfg_col5:
                        new_rsi_high = st.slider(
                            "RSI Overbought",
                            50, 90,
                            config.get('rsi_overbought', 70),
                            key=f"rsi_high_{port_id}"
                        )

                    with cfg_col6:
                        new_auto = st.checkbox(
                            "Auto-trade actif",
                            config.get('auto_trade', True),
                            key=f"auto_{port_id}"
                        )

                    # Save config button
                    btn_col1, btn_col2, btn_col3 = st.columns(3)

                    with btn_col1:
                        if st.button("💾 Sauvegarder Config", key=f"save_{port_id}", use_container_width=True):
                            update_portfolio_config(port_id, {
                                'cryptos': new_cryptos,
                                'allocation_percent': new_alloc,
                                'max_positions': new_max_pos,
                                'rsi_oversold': new_rsi_low,
                                'rsi_overbought': new_rsi_high,
                                'auto_trade': new_auto
                            })
                            st.success("Configuration sauvegardee!")
                            st.rerun()

                    with btn_col2:
                        if st.button("🔄 Reset Portfolio", key=f"reset_{port_id}", use_container_width=True):
                            # Reset balance
                            portfolio['balance'] = {'USDT': portfolio['initial_capital']}
                            for crypto in AVAILABLE_CRYPTOS:
                                asset = crypto.split('/')[0]
                                portfolio['balance'][asset] = 0.0
                            portfolio['positions'] = {}
                            portfolio['trades'] = []
                            st.success("Portfolio reset!")
                            st.rerun()

                    with btn_col3:
                        if st.button("🗑️ Supprimer", key=f"delete_{port_id}", use_container_width=True):
                            delete_portfolio(port_id)
                            st.rerun()

                    # Positions & Trades
                    st.markdown("---")
                    pos_col, trade_col = st.columns(2)

                    with pos_col:
                        st.markdown("**📊 Positions:**")
                        if portfolio['positions']:
                            for sym, pos in portfolio['positions'].items():
                                asset = sym.split('/')[0]
                                entry = pos['entry_price']
                                qty = pos['quantity']
                                # Get current price
                                curr = current_price if sym == symbol else entry
                                if use_real_data and all_prices and sym in all_prices:
                                    curr = all_prices[sym]['price']
                                unrealized = (curr - entry) * qty
                                st.write(f"• {asset}: {qty:.4f} @ ${entry:,.2f} | P&L: ${unrealized:+,.2f}")
                        else:
                            st.write("Aucune position")

                    with trade_col:
                        st.markdown("**📜 Derniers trades:**")
                        if portfolio['trades']:
                            for trade in portfolio['trades'][-5:]:
                                emoji = "🟢" if trade['action'] == 'BUY' else "🔴"
                                pnl_str = f" | ${trade['pnl']:+,.2f}" if trade.get('pnl', 0) != 0 else ""
                                st.write(f"{emoji} {trade['action']} {trade['symbol']} @ ${trade['price']:,.2f}{pnl_str}")
                        else:
                            st.write("Aucun trade")

    # ==================== TAB LEADERBOARD ====================
    with tab_leaderboard:
        st.markdown("### 🏆 Classement des Portfolios")

        if not st.session_state.portfolios:
            st.info("Aucun portfolio cree.")
        else:
            # Calculate all portfolio values
            portfolio_data = []
            for port_id, portfolio in st.session_state.portfolios.items():
                value = get_portfolio_value(portfolio, all_prices if use_real_data else {})
                if not use_real_data or not all_prices:
                    value = portfolio['balance']['USDT']
                    for asset, qty in portfolio['balance'].items():
                        if asset != 'USDT' and qty > 0 and f"{asset}/USDT" == symbol:
                            value += qty * current_price

                initial = portfolio['initial_capital']
                pnl = value - initial
                pnl_pct = (pnl / initial) * 100 if initial > 0 else 0

                trades = portfolio['trades']
                winning = len([t for t in trades if t.get('pnl', 0) > 0])
                losing = len([t for t in trades if t.get('pnl', 0) < 0])

                portfolio_data.append({
                    'id': port_id,
                    'icon': portfolio['icon'],
                    'name': portfolio['name'],
                    'strategy': portfolio['strategy_name'],
                    'cryptos': ', '.join(portfolio['config'].get('cryptos', [])[:3]),
                    'value': value,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'trades': len(trades),
                    'win_rate': (winning / max(winning + losing, 1)) * 100
                })

            portfolio_data.sort(key=lambda x: x['pnl'], reverse=True)

            # Leaderboard chart
            if portfolio_data:
                fig_leader = go.Figure()

                colors = ['#00ff88' if p['pnl'] >= 0 else '#ff4444' for p in portfolio_data]
                names = [f"{p['icon']} {p['name']}" for p in portfolio_data]
                pnls = [p['pnl'] for p in portfolio_data]

                fig_leader.add_trace(go.Bar(
                    x=pnls,
                    y=names,
                    orientation='h',
                    marker_color=colors,
                    text=[f"${p:+,.0f}" for p in pnls],
                    textposition='outside'
                ))

                fig_leader.update_layout(
                    template='plotly_dark',
                    height=max(300, len(portfolio_data) * 50),
                    margin=dict(l=20, r=100, t=20, b=20),
                    xaxis_title="P&L ($)",
                    yaxis=dict(autorange="reversed")
                )

                st.plotly_chart(fig_leader, use_container_width=True)

            # Table
            st.markdown("#### 📊 Details")

            df = pd.DataFrame([{
                'Rang': f"{'🥇' if i == 0 else '🥈' if i == 1 else '🥉' if i == 2 else f'#{i+1}'}",
                'Portfolio': f"{p['icon']} {p['name']}",
                'Strategie': p['strategy'],
                'Cryptos': p['cryptos'],
                'Valeur': f"${p['value']:,.2f}",
                'P&L': f"${p['pnl']:+,.2f}",
                'P&L %': f"{p['pnl_pct']:+.1f}%",
                'Trades': p['trades'],
                'Win Rate': f"{p['win_rate']:.0f}%"
            } for i, p in enumerate(portfolio_data)])

            st.dataframe(df, hide_index=True, use_container_width=True)

            # Summary
            if portfolio_data:
                st.divider()
                sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)

                best = portfolio_data[0]
                worst = portfolio_data[-1]
                avg_pnl = sum(p['pnl'] for p in portfolio_data) / len(portfolio_data)
                total_value = sum(p['value'] for p in portfolio_data)

                with sum_col1:
                    st.metric("🏆 Meilleur", f"{best['icon']} {best['name']}", f"${best['pnl']:+,.2f}")
                with sum_col2:
                    st.metric("📉 Pire", f"{worst['icon']} {worst['name']}", f"${worst['pnl']:+,.2f}")
                with sum_col3:
                    st.metric("📊 P&L Moyen", f"${avg_pnl:+,.2f}")
                with sum_col4:
                    st.metric("💰 Valeur Totale", f"${total_value:,.2f}")

    # ==================== TAB CREATE PORTFOLIO ====================
    with tab_create:
        st.markdown("### ⚙️ Creer un Nouveau Portfolio")
        st.markdown("*Chaque portfolio a sa propre strategie et configuration*")

        create_col1, create_col2 = st.columns(2)

        with create_col1:
            st.markdown("#### 📝 Informations")

            new_name = st.text_input("Nom du portfolio", value=f"Portfolio {st.session_state.portfolio_counter + 1}")

            new_strategy = st.selectbox(
                "Strategie",
                list(STRATEGIES.keys()),
                format_func=lambda x: f"{STRATEGIES[x]['icon']} {STRATEGIES[x]['name']} - {STRATEGIES[x]['description']}"
            )

            new_capital = st.number_input("Capital initial ($)", min_value=100.0, value=10000.0, step=1000.0)

        with create_col2:
            st.markdown("#### ⚙️ Configuration")

            new_cryptos = st.multiselect(
                "Cryptos a trader",
                AVAILABLE_CRYPTOS,
                default=["BTC/USDT", "ETH/USDT"]
            )

            cfg_row1, cfg_row2 = st.columns(2)

            with cfg_row1:
                new_allocation = st.slider("Allocation par trade (%)", 1, 100, 10)
                new_rsi_oversold = st.slider("RSI Oversold", 10, 50, 30)
                new_fear_buy = st.slider("Fear & Greed Buy (<)", 10, 50, 25)

            with cfg_row2:
                new_max_positions = st.slider("Max positions", 1, 10, 3)
                new_rsi_overbought = st.slider("RSI Overbought", 50, 90, 70)
                new_fear_sell = st.slider("Fear & Greed Sell (>)", 50, 90, 75)

            new_auto_trade = st.checkbox("Auto-trade actif", value=True)

        st.divider()

        # Preview
        st.markdown("#### 📋 Resume")
        strat = STRATEGIES[new_strategy]
        st.markdown(f"""
        - **Nom:** {new_name}
        - **Strategie:** {strat['icon']} {strat['name']}
        - **Capital:** ${new_capital:,.2f}
        - **Cryptos:** {', '.join(new_cryptos) if new_cryptos else 'Aucune'}
        - **Allocation:** {new_allocation}% par trade
        - **RSI:** {new_rsi_oversold} (oversold) / {new_rsi_overbought} (overbought)
        - **Fear & Greed:** <{new_fear_buy} (buy) / >{new_fear_sell} (sell)
        - **Max positions:** {new_max_positions}
        - **Auto-trade:** {'Oui' if new_auto_trade else 'Non'}
        """)

        if st.button("✅ Creer le Portfolio", type="primary", use_container_width=True):
            if not new_cryptos:
                st.error("Selectionnez au moins une crypto!")
            elif not new_name:
                st.error("Entrez un nom pour le portfolio!")
            else:
                config = {
                    'cryptos': new_cryptos,
                    'allocation_percent': new_allocation,
                    'rsi_oversold': new_rsi_oversold,
                    'rsi_overbought': new_rsi_overbought,
                    'fear_greed_buy': new_fear_buy,
                    'fear_greed_sell': new_fear_sell,
                    'max_positions': new_max_positions,
                    'auto_trade': new_auto_trade
                }

                portfolio_id = create_portfolio(new_name, new_strategy, new_capital, config)
                st.success(f"Portfolio '{new_name}' cree avec succes!")
                st.balloons()
                st.rerun()

    st.divider()

    # Row 4: Details techniques
    with st.expander("📊 Details Analyse Technique"):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Indicateurs de Momentum**")
            st.write(f"- RSI: {technical_result.rsi:.1f} ({technical_result.rsi_signal.name})")
            st.write(f"- MACD: {technical_result.macd_signal.name}")

        with col2:
            st.markdown("**Indicateurs de Tendance**")
            st.write(f"- EMA: {technical_result.ema_signal.name}")
            st.write(f"- Bollinger: {technical_result.bb_signal.name}")

        with col3:
            st.markdown("**Autres**")
            st.write(f"- Volume: {technical_result.volume_signal.name}")
            st.write(f"- Score Global: {technical_result.score}/100")

    with st.expander("😊 Details Sentiment"):
        col1, col2 = st.columns(2)

        # Classifier Fear & Greed
        fg = sentiment_result.fear_greed_index
        if fg < 25:
            fg_class = "Extreme Fear"
        elif fg < 45:
            fg_class = "Fear"
        elif fg < 55:
            fg_class = "Neutral"
        elif fg < 75:
            fg_class = "Greed"
        else:
            fg_class = "Extreme Greed"

        with col1:
            st.write(f"- Fear & Greed Index: {sentiment_result.fear_greed_index}")
            st.write(f"- Classification: {fg_class}")

        with col2:
            st.write(f"- Social Score: {sentiment_result.social_score}")
            st.write(f"- Score Global: {sentiment_result.score}")

    with st.expander("⛓️ Details On-Chain"):
        col1, col2 = st.columns(2)

        with col1:
            st.write(f"- Whale Activity: {onchain_result.whale_activity}")
            st.write(f"- Exchange Flow: {onchain_result.exchange_flow}")

        with col2:
            st.write(f"- Score: {onchain_result.score}")
            st.write(f"- Signal: {'+1 BUY' if chain_signal > 0 else ('-1 SELL' if chain_signal < 0 else '0 NEUTRAL')}")

    # Footer
    st.divider()

    # Timestamp
    st.markdown(f"""
    <div style="text-align: center; color: #666; padding: 1rem;">
        <p>🎯 Multi-Signal Confluence Trading Bot | Made with Streamlit</p>
        <p style="font-size: 0.8rem;">Derniere mise a jour: {datetime.now().strftime('%H:%M:%S')} | {"📡 Donnees en direct" if use_real_data else "🎮 Simulation"}</p>
        <p style="font-size: 0.8rem;">⚠️ Trading comporte des risques. Ce dashboard est a usage educatif.</p>
    </div>
    """, unsafe_allow_html=True)

    # Auto-refresh et Auto-execute
    if auto_refresh:
        # Auto-execute via portfolio engine
        if auto_execute and st.session_state.portfolios:
            results, analyzed = run_portfolio_engine()
            if results:
                st.session_state['last_engine_results'] = results
                st.session_state['last_engine_analysis'] = analyzed
                st.session_state['last_engine_time'] = datetime.now().strftime('%H:%M:%S')
                save_portfolios()

        import time
        time.sleep(refresh_rate)
        st.rerun()


if __name__ == "__main__":
    main()
