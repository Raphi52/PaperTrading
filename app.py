"""
Trading Bot - Dashboard Unifie
===============================

Interface avec:
- Dashboard (overview marché)
- Portfolios (100 stratégies automatiques)
- Settings
- Debug

Tout est automatique via bot.py - les stratégies degen, sniper, etc.
sont intégrées directement dans les portfolios.

Lance avec: streamlit run app.py
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

# Token to DexScreener URL mapping (for Binance tokens without chain info)
DEXSCREENER_TOKENS = {
    'BTC': 'https://dexscreener.com/ethereum/0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',  # WBTC
    'ETH': 'https://dexscreener.com/ethereum/0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',  # WETH
    'SOL': 'https://dexscreener.com/solana/so11111111111111111111111111111111111111112',
    'BNB': 'https://dexscreener.com/bsc/0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c',
    'DOGE': 'https://dexscreener.com/ethereum/0x4206931337dc273a630d328da6441786bfad668f',
    'PEPE': 'https://dexscreener.com/ethereum/0x6982508145454ce325ddbe47a25d4ec3d2311933',
    'SHIB': 'https://dexscreener.com/ethereum/0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce',
    'LINK': 'https://dexscreener.com/ethereum/0x514910771af9ca656af840dff83e8264ecf986ca',
    'UNI': 'https://dexscreener.com/ethereum/0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
    'AAVE': 'https://dexscreener.com/ethereum/0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9',
    'ARB': 'https://dexscreener.com/arbitrum/0x912ce59144191c1204e64559fe8253a0e49e6548',
    'OP': 'https://dexscreener.com/optimism/0x4200000000000000000000000000000000000042',
    'MATIC': 'https://dexscreener.com/polygon/0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270',
    'AVAX': 'https://dexscreener.com/avalanche/0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7',
    'ATOM': 'https://dexscreener.com/ethereum/0x8d983cb9388eac77af0474fa441c4815500cb7bb',
    'DOT': 'https://dexscreener.com/ethereum/0x7083609fce4d1d8dc0c979aab8c869ea2c873402',
    'ADA': 'https://dexscreener.com/ethereum/0x3ee2200efb3400fabb9aacf31297cbdd1d435d47',
    'XRP': 'https://dexscreener.com/ethereum/0x1d2f0da169ceb9fc7b3144628db156f3f6c60dbe',
    'LTC': 'https://dexscreener.com/ethereum/0x4338665cbb7b2485a8855a139b75d5e34ab0db94',
    'BONK': 'https://dexscreener.com/solana/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263',
    'WIF': 'https://dexscreener.com/solana/EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm',
    'JUP': 'https://dexscreener.com/solana/JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN',
    'INJ': 'https://dexscreener.com/ethereum/0xe28b3b32b6c345a34ff64674606124dd5aceca30',
    'SUI': 'https://dexscreener.com/ethereum/0x3f52b57840a0a40a72b2f35e4ba5e19a8e6e4d3d',
    'APT': 'https://dexscreener.com/ethereum/0x3c8665472ec5af30981b06b4e0143663ebedcc1e',
    'FTM': 'https://dexscreener.com/fantom/0x21be370d5312f44cb42ce377bc9b8a0cef1a4c83',
    'NEAR': 'https://dexscreener.com/ethereum/0x85f17cf997934a597031b2e18a9ab6ebd4b9f6a4',
    'CRV': 'https://dexscreener.com/ethereum/0xd533a949740bb3306d119cc777fa900ba034cd52',
    'MKR': 'https://dexscreener.com/ethereum/0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2',
    'LDO': 'https://dexscreener.com/ethereum/0x5a98fcbea516cf06857215779fd812ca3bef1b32',
    'APE': 'https://dexscreener.com/ethereum/0x4d224452801aced8b2f0aebe155379bb5d594381',
    'SAND': 'https://dexscreener.com/ethereum/0x3845badade8e6dff049820680d1f14bd3903a5d0',
    'MANA': 'https://dexscreener.com/ethereum/0x0f5d2fb29fb7d3cfee444a200298f468908cc942',
    'AXS': 'https://dexscreener.com/ethereum/0xbb0e17ef65f82ab018d8edd776e8dd940327b28b',
    'GALA': 'https://dexscreener.com/ethereum/0xd1d2eb1b1e90b638588728b4130137d262c87cae',
    'IMX': 'https://dexscreener.com/ethereum/0xf57e7e7c23978c3caec3c3548e3d615c346e79ff',
    'BLUR': 'https://dexscreener.com/ethereum/0x5283d291dbcf85356a21ba090e6db59121208b44',
    'GMX': 'https://dexscreener.com/arbitrum/0xfc5a1a6eb076a2c7ad06ed22c90d7e710e35ad0a',
    'PENDLE': 'https://dexscreener.com/ethereum/0x808507121b80c02388fad14726482e061b8da827',
    'RUNE': 'https://dexscreener.com/ethereum/0x3155ba85d5f96b2d030a4966af206230e46849cb',
    'FET': 'https://dexscreener.com/ethereum/0xaea46a60368a7bd060eec7df8cba43b7ef41ad85',
    'RNDR': 'https://dexscreener.com/ethereum/0x6de037ef9ad2725eb40118bb1702ebb27e4aeb24',
    'AGIX': 'https://dexscreener.com/ethereum/0x5b7533812759b45c2b44c19e320ba2cd2681b542',
    'WLD': 'https://dexscreener.com/ethereum/0x163f8c2467924be0ae7b5347228cabf260318753',
}

def get_dexscreener_url(symbol: str, token_address: str = '', chain: str = '') -> str:
    """Get DexScreener URL for a token"""
    clean_symbol = symbol.replace('/USDT', '').replace('\\USDT', '').upper()

    # If we have token address and chain, use direct link
    if token_address and chain:
        return f"https://dexscreener.com/{chain}/{token_address}"

    # Check our mapping
    if clean_symbol in DEXSCREENER_TOKENS:
        return DEXSCREENER_TOKENS[clean_symbol]

    # Fallback to search
    return f"https://dexscreener.com/search?q={clean_symbol}"

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
    """Charge les portfolios - JAMAIS de perte de donnees"""
    import glob

    try:
        if os.path.exists("data/portfolios.json"):
            with open("data/portfolios.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
                count = len(data.get('portfolios', {}))

                # Creer backup MASTER si beaucoup de portfolios
                if count >= 50:
                    backup_file = f"data/portfolios_MASTER_{count}.json"
                    if not os.path.exists(backup_file):
                        with open(backup_file, 'w', encoding='utf-8') as bf:
                            json.dump(data, bf, indent=2, default=str)
                        print(f"[OK] MASTER backup: {backup_file}")

                return data
    except Exception as e:
        print(f"[ERROR] Erreur load: {e}")

    # Si erreur ou fichier vide -> chercher le meilleur backup
    backups = glob.glob("data/portfolios_MASTER_*.json") + glob.glob("data/portfolios_backup_*.json")
    if backups:
        # Trouver celui avec le plus de portfolios
        best_backup = None
        best_count = 0
        for b in backups:
            try:
                with open(b, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                    c = len(d.get('portfolios', {}))
                    if c > best_count:
                        best_count = c
                        best_backup = b
            except:
                pass

        if best_backup:
            print(f"[RESTORE] Restauration: {best_backup} ({best_count} portfolios)")
            with open(best_backup, 'r', encoding='utf-8') as f:
                return json.load(f)

    return {"portfolios": {}, "counter": 0}


# ============ FILE LOCKING FOR RACE CONDITION PROTECTION ============
LOCK_FILE = "data/portfolios.lock"

def acquire_lock(timeout=5):
    """Acquire file lock with timeout"""
    start = time.time()
    while os.path.exists(LOCK_FILE):
        if time.time() - start > timeout:
            # Lock is stale, remove it
            try:
                os.remove(LOCK_FILE)
            except:
                pass
            break
        time.sleep(0.1)
    try:
        with open(LOCK_FILE, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except:
        return False

def release_lock():
    """Release file lock"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass


def save_portfolios(data: Dict):
    """Sauvegarde les portfolios - PROTECTION ABSOLUE with file locking"""
    if not acquire_lock():
        print("[WARN] Could not acquire lock for saving portfolios")
        return

    try:
        os.makedirs("data", exist_ok=True)
        new_count = len(data.get('portfolios', {}))

        # PROTECTION ABSOLUE: JAMAIS sauvegarder si moins de 50 portfolios et le fichier en a plus
        if os.path.exists("data/portfolios.json"):
            try:
                with open("data/portfolios.json", 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    existing_count = len(existing.get('portfolios', {}))

                    # Si on perdrait des portfolios, BLOQUER
                    if existing_count > new_count:
                        backup_file = f"data/portfolios_BLOCKED_{existing_count}_vs_{new_count}.json"
                        with open(backup_file, 'w', encoding='utf-8') as bf:
                            json.dump(existing, bf, indent=2, default=str)
                        print(f"[BLOCKED] Tentative d'ecraser {existing_count} portfolios avec {new_count}")
                        print(f"   Backup sauve: {backup_file}")
                        return  # NE PAS SAUVEGARDER
            except Exception as e:
                print(f"Erreur protection save: {e}")
                return  # En cas d'erreur, ne pas risquer

        # Write to temp file first, then rename (atomic operation)
        temp_file = "data/portfolios.json.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)

        # Atomic rename
        if os.path.exists("data/portfolios.json"):
            os.replace(temp_file, "data/portfolios.json")
        else:
            os.rename(temp_file, "data/portfolios.json")

        print(f"[OK] Sauvegarde {new_count} portfolios")
    finally:
        release_lock()


# ============ PORTFOLIO HISTORY FOR CHARTS ============

def load_portfolio_history() -> Dict:
    """Load portfolio value history"""
    try:
        with open("data/portfolio_history.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"last_update": None, "portfolios": {}}


def get_portfolio_gains(port_id: str, history_data: Dict) -> Dict:
    """Calculate % gains for different time periods"""
    gains = {
        'hour': None,
        'day': None,
        'week': None,
        'month': None
    }

    port_history = history_data.get('portfolios', {}).get(port_id, {})
    history = port_history.get('history', [])

    if len(history) < 2:
        return gains

    current_value = history[-1]['value']
    current_time = datetime.strptime(history[-1]['timestamp'], "%Y-%m-%d %H:%M:%S")

    # Find values at different time points
    for entry in reversed(history):
        entry_time = datetime.strptime(entry['timestamp'], "%Y-%m-%d %H:%M:%S")
        time_diff = current_time - entry_time

        # 1 hour ago
        if gains['hour'] is None and time_diff >= timedelta(hours=1):
            if entry['value'] > 0:
                gains['hour'] = ((current_value / entry['value']) - 1) * 100

        # 1 day ago
        if gains['day'] is None and time_diff >= timedelta(days=1):
            if entry['value'] > 0:
                gains['day'] = ((current_value / entry['value']) - 1) * 100

        # 1 week ago
        if gains['week'] is None and time_diff >= timedelta(weeks=1):
            if entry['value'] > 0:
                gains['week'] = ((current_value / entry['value']) - 1) * 100

        # 1 month ago
        if gains['month'] is None and time_diff >= timedelta(days=30):
            if entry['value'] > 0:
                gains['month'] = ((current_value / entry['value']) - 1) * 100

    return gains


def create_portfolio_chart(port_id: str, port_name: str, history_data: Dict) -> go.Figure:
    """Create a plotly chart for portfolio value history"""
    port_history = history_data.get('portfolios', {}).get(port_id, {})
    history = port_history.get('history', [])
    initial_capital = port_history.get('initial_capital', 10000)

    if len(history) < 2:
        # Return empty chart with message
        fig = go.Figure()
        fig.add_annotation(
            text="Not enough data yet. Chart will appear after a few scans.",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="#888")
        )
        fig.update_layout(
            height=300,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
        )
        return fig

    timestamps = [entry['timestamp'] for entry in history]
    values = [entry['value'] for entry in history]

    # Calculate % change from initial
    pct_changes = [(v / initial_capital - 1) * 100 for v in values]

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.1,
        subplot_titles=(f"Total Value", "% Change from Start")
    )

    # Value line
    color = '#00ff88' if values[-1] >= initial_capital else '#ff4444'

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=values,
            mode='lines',
            name='Value',
            line=dict(color=color, width=2),
            fill='tozeroy',
            fillcolor=f'rgba({"0,255,136" if values[-1] >= initial_capital else "255,68,68"},0.1)'
        ),
        row=1, col=1
    )

    # Initial capital line
    fig.add_hline(
        y=initial_capital,
        line_dash="dash",
        line_color="#888",
        annotation_text=f"Initial ${initial_capital:,.0f}",
        row=1, col=1
    )

    # % Change line
    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=pct_changes,
            mode='lines',
            name='% Change',
            line=dict(color='#00aaff', width=2),
        ),
        row=2, col=1
    )

    # Zero line for % change
    fig.add_hline(y=0, line_dash="dash", line_color="#666", row=2, col=1)

    fig.update_layout(
        height=400,
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(26,26,46,0.8)',
        margin=dict(l=50, r=20, t=40, b=30),
        font=dict(color='#888'),
    )

    fig.update_xaxes(gridcolor='rgba(255,255,255,0.1)', showgrid=True)
    fig.update_yaxes(gridcolor='rgba(255,255,255,0.1)', showgrid=True)

    return fig


@st.cache_data(ttl=10)
def get_all_prices_cached() -> Dict[str, float]:
    """Fetch ALL prices once - shared cache for all portfolios"""
    prices = {}
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            for p in response.json():
                if p['symbol'].endswith('USDT'):
                    sym = p['symbol'].replace('USDT', '/USDT')
                    prices[sym] = float(p['price'])
    except:
        pass
    return prices


def get_dexscreener_prices(addresses: List[str]) -> Dict[str, float]:
    """Fetch prices from DexScreener for sniper tokens"""
    prices = {}
    if not addresses:
        return prices

    try:
        # DexScreener accepts comma-separated addresses (max 30)
        for i in range(0, len(addresses), 30):
            batch = addresses[i:i+30]
            addr_str = ','.join(batch)
            url = f"https://api.dexscreener.com/latest/dex/tokens/{addr_str}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                for pair in data.get('pairs', []):
                    addr = pair.get('baseToken', {}).get('address', '')
                    price = float(pair.get('priceUsd', 0) or 0)
                    if addr and price > 0:
                        prices[addr.lower()] = price
    except:
        pass
    return prices


def get_current_prices(symbols: List[str]) -> Dict[str, float]:
    """Get prices from shared cache - NO API call per portfolio"""
    all_prices = get_all_prices_cached()
    return {sym: all_prices.get(sym, 0) for sym in symbols if sym in all_prices}


def calculate_all_portfolio_values(portfolios: Dict) -> Dict[str, Dict]:
    """Calculate ALL portfolio values in ONE pass - super fast"""
    binance_prices = get_all_prices_cached()

    # Collect ALL sniper addresses across all portfolios
    all_sniper_addresses = set()
    for p in portfolios.values():
        for pos in p.get('positions', {}).values():
            addr = pos.get('address', '')
            if addr:
                all_sniper_addresses.add(addr)

    # Get DexScreener prices for all sniper tokens
    dex_prices = get_dexscreener_prices(list(all_sniper_addresses)) if all_sniper_addresses else {}

    results = {}
    for pid, p in portfolios.items():
        usdt_balance = p['balance'].get('USDT', 0)
        positions = p.get('positions', {})
        positions_value = 0
        unrealized_pnl = 0

        for symbol, pos in positions.items():
            entry_price = pos.get('entry_price', 0)
            quantity = pos.get('quantity', 0)
            addr = pos.get('address', '')

            # Use DexScreener for sniper tokens, Binance for regular
            if addr:
                current_price = dex_prices.get(addr.lower(), entry_price)
            else:
                current_price = binance_prices.get(symbol, entry_price)

            current_value = quantity * current_price
            positions_value += current_value
            unrealized_pnl += current_value - (quantity * entry_price)

        results[pid] = {
            'total_value': usdt_balance + positions_value,
            'usdt_balance': usdt_balance,
            'positions_value': positions_value,
            'unrealized_pnl': unrealized_pnl
        }

    return results


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
    binance_prices = get_current_prices(symbols)

    # Collect sniper token addresses for DexScreener
    sniper_addresses = []
    sniper_addr_to_symbol = {}
    for symbol, pos in positions.items():
        addr = pos.get('address', '')
        if addr:
            sniper_addresses.append(addr)
            sniper_addr_to_symbol[addr.lower()] = symbol

    # Get DexScreener prices for sniper tokens
    dex_prices = get_dexscreener_prices(sniper_addresses) if sniper_addresses else {}

    positions_value = 0
    unrealized_pnl = 0
    positions_details = []

    for symbol, pos in positions.items():
        entry_price = pos.get('entry_price', 0)
        quantity = pos.get('quantity', 0)
        addr = pos.get('address', '')

        # Use DexScreener price for sniper tokens, Binance for regular tokens
        if addr:
            # Sniper token - use DexScreener price, fallback to entry
            current_price = dex_prices.get(addr.lower(), entry_price)
        else:
            # Regular token - use Binance price
            current_price = binance_prices.get(symbol, entry_price)

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
            'pnl_pct': pnl_pct,
            'token_address': pos.get('address', ''),
            'chain': pos.get('chain', ''),
            'entry_time': pos.get('entry_time', '')
        })

    return {
        'total_value': usdt_balance + positions_value,
        'usdt_balance': usdt_balance,
        'positions_value': positions_value,
        'unrealized_pnl': unrealized_pnl,
        'positions_details': positions_details
    }


@st.cache_data(ttl=60)
def fetch_price_history(symbol: str, entry_time: str, current_price: float) -> List[Dict]:
    """
    Fetch price history from Binance klines API.
    Returns list of {time, price} from entry_time until now.
    """
    try:
        from datetime import datetime, timezone

        # Parse entry time
        if not entry_time:
            return []

        # Handle ISO format
        entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)

        # Calculate time difference in minutes
        time_diff = (now - entry_dt.replace(tzinfo=timezone.utc)).total_seconds() / 60

        # Determine interval based on time difference
        if time_diff < 60:  # Less than 1 hour: 1m candles
            interval = '1m'
            limit = min(int(time_diff) + 1, 60)
        elif time_diff < 1440:  # Less than 1 day: 5m candles
            interval = '5m'
            limit = min(int(time_diff / 5) + 1, 288)
        elif time_diff < 10080:  # Less than 1 week: 1h candles
            interval = '1h'
            limit = min(int(time_diff / 60) + 1, 168)
        else:  # More than 1 week: 4h candles
            interval = '4h'
            limit = min(int(time_diff / 240) + 1, 200)

        # Convert to milliseconds timestamp
        start_time = int(entry_dt.timestamp() * 1000)

        # Fetch from Binance
        clean_symbol = symbol.replace('/', '').replace('\\', '').upper()
        if not clean_symbol.endswith('USDT'):
            clean_symbol += 'USDT'

        url = f"https://api.binance.com/api/v3/klines?symbol={clean_symbol}&interval={interval}&startTime={start_time}&limit={limit}"

        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return []

        data = response.json()
        if not data:
            return []

        # Parse klines: [timestamp, open, high, low, close, ...]
        prices = []
        for kline in data:
            prices.append({
                'time': datetime.fromtimestamp(kline[0] / 1000),
                'price': float(kline[4])  # Close price
            })

        # Add current price as last point
        prices.append({
            'time': datetime.now(),
            'price': current_price
        })

        return prices

    except Exception as e:
        return []


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
    # Initialize session state for navigation
    if 'page' not in st.session_state:
        st.session_state.page = "📈 Portfolios"

    # Sidebar Navigation
    with st.sidebar:
        st.markdown("## 🚀 Trading Bot")
        st.divider()

        # Navigation buttons - vertical stack
        nav_items = [
            ("📊", "Dashboard", "📊 Dashboard"),
            ("📈", "Portfolios", "📈 Portfolios"),
            ("⚙️", "Settings", "⚙️ Settings"),
            ("🐛", "Debug", "🐛 Debug")
        ]

        for icon, label, page_id in nav_items:
            is_active = st.session_state.page == page_id
            if is_active:
                # Active button style
                st.markdown(f"""
                <div style="background: linear-gradient(90deg, #00ff88 0%, #00cc6a 100%);
                            padding: 0.7rem 1rem; border-radius: 10px; margin-bottom: 0.5rem;
                            display: flex; align-items: center; cursor: pointer;">
                    <span style="font-size: 1.2rem; margin-right: 0.8rem;">{icon}</span>
                    <span style="color: #000; font-weight: bold;">{label}</span>
                </div>
                """, unsafe_allow_html=True)
            else:
                if st.button(f"{icon}  {label}", key=f"nav_{page_id}", use_container_width=True):
                    st.session_state.page = page_id
                    st.rerun()

        st.divider()

        # Calculate REAL total PnL from all portfolios - BATCH mode (1 API call)
        pf_data = load_portfolios()
        portfolios = pf_data.get('portfolios', {})
        all_values = calculate_all_portfolio_values(portfolios)

        total_value = sum(v['total_value'] for v in all_values.values())
        total_initial = sum(p.get('initial_capital', 1000) for p in portfolios.values())
        total_positions = sum(len(p.get('positions', {})) for p in portfolios.values())
        total_pnl = total_value - total_initial
        pnl_pct = (total_pnl / total_initial * 100) if total_initial > 0 else 0
        pnl_color = COLORS.BUY if total_pnl >= 0 else COLORS.SELL

        st.markdown(f"""
        <div style="background: {COLORS.BG_CARD}; padding: 1rem; border-radius: 10px;">
            <div style="color: {COLORS.TEXT_SECONDARY}; font-size: 0.8rem;">Total Portfolio Value</div>
            <div style="color: white; font-size: 1.3rem; font-weight: bold;">${total_value:,.0f}</div>
            <div style="color: {pnl_color}; font-size: 1rem; margin-top: 0.3rem;">
                {pnl_pct:+.2f}% (${total_pnl:+,.0f})
            </div>
            <div style="color: {COLORS.TEXT_SECONDARY}; font-size: 0.75rem; margin-top: 0.3rem;">
                {total_positions} positions ouvertes
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        # Portfolios count
        total_count = len(pf_data.get('portfolios', {}))
        st.markdown(f"### 🤖 {total_count} Portfolios")

        # Take Profit ALL button
        if st.button("💰 Take Profit ALL", use_container_width=True, type="primary"):
            pf_data = load_portfolios()
            symbols_to_price = set()
            # Collect all symbols
            for pid, p in pf_data.get('portfolios', {}).items():
                for symbol in p.get('positions', {}).keys():
                    symbols_to_price.add(symbol)

            # Get current prices
            if symbols_to_price:
                current_prices = get_current_prices(list(symbols_to_price))

                # Sell all positions in all portfolios
                for pid, p in pf_data.get('portfolios', {}).items():
                    for symbol, pos in list(p.get('positions', {}).items()):
                        asset = symbol.split('/')[0]
                        qty = pos.get('quantity', 0)
                        entry = pos.get('entry_price', 0)
                        current = current_prices.get(symbol, entry)
                        value = qty * current
                        pnl = value - (qty * entry)

                        pf_data['portfolios'][pid]['balance']['USDT'] += value
                        pf_data['portfolios'][pid]['balance'][asset] = 0
                        del pf_data['portfolios'][pid]['positions'][symbol]

                        pf_data['portfolios'][pid]['trades'].append({
                            'timestamp': datetime.now().isoformat(),
                            'action': 'SELL',
                            'symbol': symbol,
                            'price': current,
                            'quantity': qty,
                            'amount_usdt': value,
                            'pnl': pnl,
                            'reason': 'TAKE PROFIT ALL (manual)'
                        })

                save_portfolios(pf_data)
                st.toast("All positions sold!")
                st.rerun()

    # Main content based on page
    page = st.session_state.page
    if page == "📊 Dashboard":
        render_dashboard()
    elif page == "📈 Portfolios":
        render_portfolios()
    elif page == "⚙️ Settings":
        render_settings()
    elif page == "🐛 Debug":
        render_debug()


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


def render_portfolios():
    """Portfolios - Le coeur de l'application"""

    data = load_portfolios()
    portfolios = data.get('portfolios', {})
    all_prices = get_all_prices_cached()

    # ===================== SUMMARY DASHBOARD =====================
    if portfolios:
        # Calculate aggregate stats using proper function (handles sniper tokens)
        all_pf_values = calculate_all_portfolio_values(portfolios)

        total_aum = 0
        total_initial = 0
        total_pnl = 0
        best_pf = None
        worst_pf = None
        best_pnl_pct = -999
        worst_pnl_pct = 999
        winning_count = 0
        total_positions = 0
        total_trades = 0

        for pid, p in portfolios.items():
            pf_val = all_pf_values.get(pid, {})
            total_val = pf_val.get('total_value', p['balance'].get('USDT', 0))
            initial = p.get('initial_capital', 1000)
            pnl = total_val - initial
            pnl_pct = (pnl / initial * 100) if initial > 0 else 0

            total_aum += total_val
            total_initial += initial
            total_pnl += pnl
            total_positions += len(p.get('positions', {}))
            total_trades += len(p.get('trades', []))

            if pnl >= 0:
                winning_count += 1

            if pnl_pct > best_pnl_pct:
                best_pnl_pct = pnl_pct
                best_pf = (p['name'], pnl_pct)
            if pnl_pct < worst_pnl_pct:
                worst_pnl_pct = pnl_pct
                worst_pf = (p['name'], pnl_pct)

        overall_pnl_pct = ((total_aum - total_initial) / total_initial * 100) if total_initial > 0 else 0
        win_rate = (winning_count / len(portfolios) * 100) if portfolios else 0

        # Summary Header with gradient
        pnl_color = '#00ff88' if total_pnl >= 0 else '#ff4444'
        win_color = '#00ff88' if win_rate >= 50 else '#ff4444'

        summary_html = f'''<div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f0f1a 100%); border-radius: 20px; padding: 1.5rem 2rem; margin-bottom: 1.5rem; border: 1px solid #333; box-shadow: 0 10px 40px rgba(0,0,0,0.4);">
<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
<div>
<div style="font-size: 0.9rem; color: #888; text-transform: uppercase; letter-spacing: 1px;">Total Value (AUM)</div>
<div style="font-size: 2.5rem; font-weight: bold; color: white;">${total_aum:,.0f}</div>
<div style="font-size: 1rem; color: {pnl_color};">{overall_pnl_pct:+.2f}% all-time</div>
</div>
<div style="text-align: center;">
<div style="font-size: 0.9rem; color: #888;">P&L</div>
<div style="font-size: 2rem; font-weight: bold; color: {pnl_color};">${total_pnl:+,.0f}</div>
</div>
<div style="text-align: center;">
<div style="font-size: 0.9rem; color: #888;">Win Rate</div>
<div style="font-size: 2rem; font-weight: bold; color: {win_color};">{win_rate:.0f}%</div>
<div style="font-size: 0.8rem; color: #666;">{winning_count}/{len(portfolios)} profitable</div>
</div>
<div style="text-align: center;">
<div style="font-size: 0.9rem; color: #888;">Portfolios</div>
<div style="font-size: 2rem; font-weight: bold; color: #00aaff;">{len(portfolios)}</div>
<div style="font-size: 0.8rem; color: #666;">{total_positions} positions</div>
</div>
</div>
</div>'''
        st.markdown(summary_html, unsafe_allow_html=True)

        # Best & Worst performers row
        col_best, col_worst, col_trades = st.columns(3)
        with col_best:
            if best_pf:
                best_html = f'<div style="background: rgba(0,255,136,0.1); border-radius: 12px; padding: 1rem; border-left: 4px solid #00ff88;"><div style="font-size: 0.8rem; color: #888;">Best Performer</div><div style="font-size: 1.2rem; font-weight: bold; color: white;">{best_pf[0][:20]}</div><div style="font-size: 1.5rem; color: #00ff88; font-weight: bold;">{best_pf[1]:+.1f}%</div></div>'
                st.markdown(best_html, unsafe_allow_html=True)
        with col_worst:
            if worst_pf:
                worst_html = f'<div style="background: rgba(255,68,68,0.1); border-radius: 12px; padding: 1rem; border-left: 4px solid #ff4444;"><div style="font-size: 0.8rem; color: #888;">Worst Performer</div><div style="font-size: 1.2rem; font-weight: bold; color: white;">{worst_pf[0][:20]}</div><div style="font-size: 1.5rem; color: #ff4444; font-weight: bold;">{worst_pf[1]:+.1f}%</div></div>'
                st.markdown(worst_html, unsafe_allow_html=True)
        with col_trades:
            activity_html = f'<div style="background: rgba(0,170,255,0.1); border-radius: 12px; padding: 1rem; border-left: 4px solid #00aaff;"><div style="font-size: 0.8rem; color: #888;">Total Activity</div><div style="font-size: 1.2rem; font-weight: bold; color: white;">{total_trades} trades</div><div style="font-size: 1rem; color: #00aaff;">{total_positions} open positions</div></div>'
            st.markdown(activity_html, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

    # ===================== SEARCH & FILTERS =====================
    col_search, col_category, col_create = st.columns([2, 2, 1])

    with col_search:
        search_query = st.text_input("🔍 Search portfolios", placeholder="Name or strategy...", label_visibility="collapsed")

    with col_category:
        strategy_categories = {
            "All": [],
            "Whale": ["whale_gcr", "whale_hsaka", "whale_cobie", "whale_ansem", "whale_degen", "whale_smart_money"],
            "Sniper": ["sniper_safe", "sniper_degen", "sniper_yolo", "sniper_all_in", "sniper_spray", "sniper_quickflip"],
            "Classic": ["confluence_normal", "confluence_strict", "conservative", "aggressive", "rsi_strategy", "hodl"],
            "Degen": ["degen_hybrid", "degen_scalp", "degen_momentum", "degen_full", "god_mode_only"],
            "EMA/Trend": ["ema_crossover", "ema_crossover_slow", "supertrend", "supertrend_fast"],
            "Oscillators": ["stoch_rsi", "stoch_rsi_aggressive", "vwap_bounce", "vwap_trend"],
            "Ichimoku": ["ichimoku", "ichimoku_fast", "ichimoku_scalp", "ichimoku_swing", "ichimoku_long", "ichimoku_kumo_break", "ichimoku_tk_cross", "ichimoku_chikou", "ichimoku_momentum", "ichimoku_conservative"],
            "Trailing": ["trailing_scalp", "trailing_tight", "trailing_medium", "trailing_wide", "trailing_swing"],
            "Advanced": ["grid_trading", "grid_tight", "breakout", "breakout_tight", "mean_reversion"]
        }
        selected_category = st.selectbox("📂 Category", list(strategy_categories.keys()), label_visibility="collapsed")

    with col_create:
        if st.button("➕ New", use_container_width=True, type="primary"):
            st.session_state['show_create_portfolio'] = True

    # Create new portfolio modal
    if st.session_state.get('show_create_portfolio', False):
        with st.expander("➕ Create New Portfolio", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name", placeholder="My Portfolio", key="new_pf_name")
                capital = st.number_input("Starting Capital ($)", value=1000, min_value=100, key="new_pf_capital")
            with col2:
                strategy = st.selectbox("Strategy", [
                    "confluence_normal", "confluence_strict", "degen_hybrid",
                    "degen_scalp", "god_mode_only", "hodl"
                ], key="new_pf_strategy")
                cryptos = st.multiselect("Cryptos", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT", "PEPE/USDT"], key="new_pf_cryptos")

            col_create1, col_create2 = st.columns(2)
            with col_create1:
                if st.button("Create Portfolio", type="primary", use_container_width=True):
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
                        st.session_state['show_create_portfolio'] = False
                        st.success(f"Portfolio '{name}' created!")
                        st.rerun()
            with col_create2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state['show_create_portfolio'] = False
                    st.rerun()

    if not portfolios:
        st.markdown('<div style="text-align: center; padding: 3rem; color: #888;"><div style="font-size: 4rem; margin-bottom: 1rem;">📈</div><div style="font-size: 1.5rem; margin-bottom: 0.5rem;">No Portfolios Yet</div><div>Click the <b>➕ New</b> button above to create your first portfolio</div></div>', unsafe_allow_html=True)
        return

    # Strategy icons
    strat_icons = {
        # Original
        "confluence_normal": "📊", "confluence_strict": "🎯", "degen_hybrid": "🔥",
        "degen_scalp": "⚡", "degen_momentum": "🚀", "degen_full": "💀",
        "god_mode_only": "🚨", "hodl": "💎", "manual": "🎮",
        "conservative": "🛡️", "aggressive": "🔥", "rsi_strategy": "📈",
        "sniper_safe": "🎯", "sniper_degen": "🔫", "sniper_yolo": "💀",
        "sniper_all_in": "🚀", "sniper_spray": "💸", "sniper_quickflip": "⚡",
        # Whale copy-trading
        "whale_gcr": "🐋", "whale_hsaka": "🦈", "whale_cobie": "🐳",
        "whale_ansem": "🦑", "whale_degen": "🐙", "whale_smart_money": "💎",
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
Cette stratégie combine RSI + tendance EMA pour prendre des décisions.
Elle n'achète que quand PLUSIEURS signaux sont d'accord = moins d'erreurs.

📈 QUAND J'ACHÈTE ?
• Signal BUY: RSI < 35
• Signal STRONG_BUY: RSI < 30 ET tendance haussière (EMA12 > EMA26)

📉 QUAND JE VENDS ?
• Signal SELL: RSI > 65
• Signal STRONG_SELL: RSI > 70 ET tendance baissière (EMA12 < EMA26)

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
• STRONG_BUY uniquement = RSI < 30 ET EMA12 > EMA26
• (doit être survendu ET en tendance haussière)

📉 QUAND JE VENDS ?
• STRONG_SELL uniquement = RSI > 70 ET EMA12 < EMA26
• (doit être suracheté ET en tendance baissière)

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
L'opposé de Conservative. Entre très tôt dans les trades, sort tôt aussi.
Capture beaucoup plus de mouvements mais avec plus de risque.

📈 QUAND J'ACHÈTE ?
• RSI < 45 suffit (très large, beaucoup d'opportunités)
• OU RSI < 50 avec momentum positif > 0.2%

📉 QUAND JE VENDS ?
• RSI > 55 (sort très vite)
• OU momentum négatif < -0.3%

⚖️ NIVEAU DE RISQUE: Élevé
📊 FRÉQUENCE DES TRADES: Très Haute

💡 POUR QUI ?
Pour ceux qui veulent maximum d'action et acceptent beaucoup de trades perdants.
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
• RSI < 40 (relativement bas)
• ET momentum positif > 0.1% (début de rebond)

📉 QUAND JE VENDS ?
• RSI > 60 avec momentum négatif < -0.1%
• OU RSI > 50 avec momentum négatif (on sort vite !)

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
• Volume > 1.3x la moyenne (intérêt croissant)
• ET momentum positif > 0.3% sur 1h
• ET RSI < 70 (pas encore suracheté)

📉 QUAND JE VENDS ?
• Momentum négatif < -0.3%
• OU volume spike avec momentum négatif
• OU momentum < -0.2% (perte de force)

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
Scanne automatiquement les NOUVEAUX tokens sur toutes les chains (Solana, BSC, ETH, Base...).
Achète les plus "sûrs" parmi les nouveaux tokens.

📈 QUAND J'ACHÈTE ?
• Token créé récemment (< 2h)
• Score de risque < 60 (relativement safe)
• Liquidité > $10,000 (assez pour pouvoir revendre)

📉 QUAND JE VENDS ?
• Take Profit: +100% (double ton argent)
• Stop Loss: -50% (limite les pertes)

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
• Token récent (< 2h)
• Score de risque < 80 (accepte beaucoup de risque)
• Liquidité > $1,000 (minimum très bas)

📉 QUAND JE VENDS ?
• Take Profit: +100% (double ton argent)
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
• Token < 2h (très nouveau)
• Score de risque < 100 (accepte TOUT)
• Liquidité > $500 (minimum absolu)

📉 QUAND JE VENDS ?
• Take Profit: +100% (x2 ton argent)
• Stop Loss: -50%

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
• Position Bollinger < 17.5% (bottom du range)

📉 QUAND JE VENDS ?
• Position Bollinger > 82.5% (top du range)

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Haute

💡 POUR QUI ?
Pour consolidations serrées. Entre plus tôt que Grid normal.""",

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
• OU après une perte: RSI < 45 avec DOUBLE de la position !
• Maximum 4 niveaux de doublement (2x, 4x, 8x, 16x)

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
• Maximum 3 niveaux (1.5x, 2.25x, 3.4x) au lieu de 4

📈 QUAND J'ACHÈTE ?
• RSI < 35 (entrée normale)
• OU après perte: RSI < 45 avec 1.5x la position

📉 QUAND JE VENDS ?
• RSI > 65

⚠️ NIVEAU DE RISQUE: Très Élevé
📊 FRÉQUENCE DES TRADES: Variable

⚠️ TOUJOURS DANGEREUX
Moins explosif que le Martingale normal mais reste très risqué.
Exposition max = 3.4x au lieu de 16x.

💡 POUR QUI ?
Paper trading uniquement pour expérimenter.""",

        "dca_fear": """😱 DCA FEAR INDEX - Acheter la Peur

🎓 C'EST QUOI ?
Utilise le "Fear & Greed Index" (indice de peur et avidité) du marché crypto.
Cet indice mesure le sentiment global:
• 0-25 = Peur Extrême (tout le monde a peur)
• 25-50 = Peur
• 50-75 = Avidité
• 75-100 = Avidité Extrême (euphorie)

Warren Buffett: "Sois avide quand les autres ont peur"

📈 QUAND J'ACHÈTE ?
• Fear Index < 25 (peur extrême sur le marché)
• → Le marché panique = opportunité d'achat !

📉 QUAND JE VENDS ?
• Fear Index > 75 (euphorie extrême)
• → Tout le monde achète = temps de vendre

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Basse (quelques par mois)

💡 POUR QUI ?
Pour les investisseurs contrarians qui achètent quand le marché panique.
Stratégie long terme qui achète les crashs.

📊 OÙ VOIR L'INDEX ?
alternative.me/crypto/fear-and-greed-index/""",

        "funding_contrarian": """📊 FUNDING CONTRARIAN - Trade Contre la Foule

🎓 C'EST QUOI ?
Le "Funding Rate" est le taux que les longs paient aux shorts (ou vice versa)
sur les marchés futures. Il indique qui est "crowded" (trop nombreux).

• Funding positif élevé = beaucoup de longs = risque de dump
• Funding négatif élevé = beaucoup de shorts = risque de squeeze

📈 QUAND J'ACHÈTE ?
• Funding Rate très négatif (< -0.05%)
• → Les shorts sont crowded, potentiel short squeeze !

📉 QUAND JE VENDS ?
• Funding Rate très positif (> 0.05%)
• → Les longs sont crowded, potentiel dump

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Basse

💡 POUR QUI ?
Traders contrarians qui aiment aller contre le consensus.
Fonctionne bien pendant les périodes de forte spéculation.""",

        "funding_extreme": """🔥 FUNDING EXTREME - Positions Extrêmes Uniquement

🎓 C'EST QUOI ?
Comme Funding Contrarian mais n'agit QUE sur les extrêmes.
Attend des funding rates vraiment anormaux avant de trader.

📈 QUAND J'ACHÈTE ?
• Funding Rate < -0.1% (extrêmement négatif)
• → Short squeeze quasi-certain !

📉 QUAND JE VENDS ?
• Funding Rate > 0.1% (extrêmement positif)
• → Liquidations de longs imminentes

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Très Basse (rare)

💡 POUR QUI ?
Pour ceux qui veulent des signaux rares mais puissants.
Très efficace pendant les périodes de FOMO/panique.""",

        "oi_breakout": """📈 OI BREAKOUT - Open Interest Breakout

🎓 C'EST QUOI ?
L'Open Interest = nombre total de contrats futures ouverts.
• OI qui monte + prix qui monte = nouveaux acheteurs (bullish)
• OI qui monte + prix qui baisse = nouveaux vendeurs (bearish)

📈 QUAND J'ACHÈTE ?
• OI en hausse + tendance haussière (EMA)
• → De l'argent frais entre sur le marché

📉 QUAND JE VENDS ?
• Tendance devient baissière
• → Les acheteurs partent

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Pour suivre les flux de capitaux sur les futures.
Confirme les breakouts avec de l'argent réel.""",

        "oi_divergence": """🔄 OI DIVERGENCE - Divergences Prix/OI

🎓 C'EST QUOI ?
Cherche les divergences entre le prix et l'open interest.
Quand ils divergent, un retournement est possible.

📈 QUAND J'ACHÈTE ?
• Prix a chuté fortement (-2% ou plus)
• RSI < 35 (survendu)
• → Potentiel rebond

📉 QUAND JE VENDS ?
• Prix a monté fortement (+2% ou plus)
• RSI > 70 (suracheté)
• → Potentiel retournement

⚖️ NIVEAU DE RISQUE: Moyen-Élevé
📊 FRÉQUENCE DES TRADES: Moyenne

💡 POUR QUI ?
Traders qui cherchent les retournements.
Combine analyse technique et données futures.""",

        "funding_oi_combo": """🎯 FUNDING + OI COMBO - Double Confirmation

🎓 C'EST QUOI ?
Combine Funding Rate ET Open Interest pour des signaux plus fiables.
Deux confirmations valent mieux qu'une !

📈 QUAND J'ACHÈTE ?
• Funding négatif (shorts crowded)
• ET tendance haussière (EMA bullish)
• → Double confirmation d'achat

📉 QUAND JE VENDS ?
• Funding positif (longs crowded)
• ET tendance baissière
• → Double confirmation de vente

⚖️ NIVEAU DE RISQUE: Moyen
📊 FRÉQUENCE DES TRADES: Basse

💡 POUR QUI ?
Pour ceux qui veulent des signaux très fiables.
Moins de trades mais meilleure qualité."""
    }

    # Display portfolios with pagination (10 per page)
    portfolio_list = list(portfolios.items())
    PORTFOLIOS_PER_PAGE = 10

    # ===================== FILTERING =====================
    # Apply search filter
    if search_query:
        search_lower = search_query.lower()
        portfolio_list = [
            (pid, p) for pid, p in portfolio_list
            if search_lower in p.get('name', '').lower()
            or search_lower in p.get('strategy_id', '').lower()
        ]

    # Apply category filter
    if selected_category != "All":
        category_strategies = strategy_categories.get(selected_category, [])
        if category_strategies:
            portfolio_list = [
                (pid, p) for pid, p in portfolio_list
                if p.get('strategy_id', '') in category_strategies
            ]

    # ===================== SORTING =====================
    # Calculate portfolio values properly (handles sniper tokens with DexScreener)
    sort_pf_values = calculate_all_portfolio_values(portfolios)

    def get_pnl_pct(item):
        pid, p = item
        pf_val = sort_pf_values.get(pid, {})
        total = pf_val.get('total_value', p['balance'].get('USDT', 0))
        initial = p.get('initial_capital', 1000)
        return ((total - initial) / initial * 100) if initial > 0 else 0

    def get_positions_count(item):
        pid, p = item
        return len(p.get('positions', {}))

    def get_positions_value(item):
        pid, p = item
        pf_val = sort_pf_values.get(pid, {})
        return pf_val.get('positions_value', 0)

    # Sort controls - more compact
    col_sort, col_page_info = st.columns([3, 2])
    with col_sort:
        sort_option = st.radio(
            "Sort",
            ["📈 Best", "📉 Worst", "🔤 A-Z", "📊 Positions", "💰 Invested"],
            horizontal=True,
            key="pf_sort_radio",
            label_visibility="collapsed"
        )

    # Apply sorting
    if "Best" in sort_option:
        portfolio_list.sort(key=get_pnl_pct, reverse=True)
    elif "Worst" in sort_option:
        portfolio_list.sort(key=get_pnl_pct, reverse=False)
    elif "A-Z" in sort_option:
        portfolio_list.sort(key=lambda x: x[1].get('name', ''))
    elif "Positions" in sort_option:
        portfolio_list.sort(key=get_positions_count, reverse=True)
    elif "Invested" in sort_option:
        portfolio_list.sort(key=get_positions_value, reverse=True)

    # Reset page on filter/sort change
    filter_key = f"{search_query}_{selected_category}_{sort_option}"
    if st.session_state.get('last_filter') != filter_key:
        st.session_state.portfolio_page = 0
        st.session_state.last_filter = filter_key

    # Pagination
    if 'portfolio_page' not in st.session_state:
        st.session_state.portfolio_page = 0
    current_page = st.session_state.portfolio_page
    total_pages = max(1, (len(portfolio_list) + PORTFOLIOS_PER_PAGE - 1) // PORTFOLIOS_PER_PAGE)

    # Ensure current page is valid
    if current_page >= total_pages:
        current_page = total_pages - 1
        st.session_state.portfolio_page = current_page

    with col_page_info:
        st.markdown(f"<div style='text-align:right; color:#888; padding-top: 0.5rem;'>Showing {len(portfolio_list)} portfolios</div>", unsafe_allow_html=True)

    # Pagination controls
    if total_pages > 1:
        col_prev, col_pages, col_next = st.columns([1, 3, 1])
        with col_prev:
            if st.button("◀", disabled=current_page == 0, use_container_width=True, key="prev_page"):
                st.session_state.portfolio_page = max(0, current_page - 1)
                st.rerun()
        with col_pages:
            # Page number buttons
            page_cols = st.columns(min(total_pages, 7))
            # Show pages around current page
            start_page = max(0, min(current_page - 3, total_pages - 7))
            for i, pc in enumerate(page_cols):
                page_num = start_page + i
                if page_num < total_pages:
                    with pc:
                        if st.button(
                            str(page_num + 1),
                            use_container_width=True,
                            type="primary" if page_num == current_page else "secondary",
                            key=f"page_{page_num}"
                        ):
                            st.session_state.portfolio_page = page_num
                            st.rerun()
        with col_next:
            if st.button("▶", disabled=current_page >= total_pages - 1, use_container_width=True, key="next_page"):
                st.session_state.portfolio_page = min(total_pages - 1, current_page + 1)
                st.rerun()

    # Get current page portfolios
    start_idx = current_page * PORTFOLIOS_PER_PAGE
    end_idx = start_idx + PORTFOLIOS_PER_PAGE
    page_portfolios = portfolio_list[start_idx:end_idx]

    # No results message
    if not page_portfolios:
        st.markdown('<div style="text-align: center; padding: 2rem; color: #888;"><div style="font-size: 2rem; margin-bottom: 0.5rem;">🔍</div><div>No portfolios match your search criteria</div></div>', unsafe_allow_html=True)
        return

    st.markdown("<br>", unsafe_allow_html=True)

    for i in range(0, len(page_portfolios), 2):
        cols = st.columns(2)

        for j, col in enumerate(cols):
            if i + j < len(page_portfolios):
                pid, p = page_portfolios[i + j]

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
                    strategy = p.get('strategy_id', 'manual')
                    icon = strat_icons.get(strategy, '📈')
                    tooltip = strat_tooltips.get(strategy, 'No description available')
                    cryptos = p['config'].get('cryptos', [])

                    # Colors - green border if profit, red if loss
                    pnl_color = '#00ff88' if total_pnl >= 0 else '#ff4444'
                    unrealized_color = '#00ff88' if unrealized_pnl >= 0 else '#ff4444'

                    # Calculate P&L bar width (capped at -50% to +50% for visual)
                    pnl_bar_width = min(max(abs(pnl_pct), 0), 50) * 2  # 0-100% width
                    pnl_bar_dir = 'right' if pnl_pct >= 0 else 'left'

                    # Build coins HTML separately
                    coins_html = ''.join([
                        f'<span style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-size: 0.65rem; color: #aaa;">{c.replace("/USDT","")}</span>'
                        for c in cryptos[:6]
                    ])
                    if len(cryptos) > 6:
                        coins_html += f'<span style="color: #666; font-size: 0.65rem; margin-left: 4px;">+{len(cryptos)-6}</span>'

                    # Precompute colors
                    bar_bg = 'rgba(0,255,136,0.08)' if pnl_pct >= 0 else 'rgba(255,68,68,0.08)'
                    pos_color = '#00aaff' if positions_count > 0 else '#666'
                    name_display = p['name'][:25] + ('...' if len(p['name']) > 25 else '')

                    # Card HTML
                    card_html = f'''<div style="background: linear-gradient(145deg, #1a1a2e 0%, #0f0f1a 100%); border-radius: 16px; padding: 1.2rem; margin-bottom: 0.5rem; border-left: 4px solid {pnl_color}; box-shadow: 0 4px 20px rgba(0,0,0,0.3); position: relative; overflow: hidden;">
<div style="position: absolute; top: 0; {pnl_bar_dir}: 0; width: {pnl_bar_width}%; height: 100%; background: linear-gradient(90deg, {bar_bg} 0%, transparent 100%); pointer-events: none;"></div>
<div style="position: relative; z-index: 1;">
<div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.8rem;">
<div style="flex: 1;">
<div style="display: flex; align-items: center; gap: 0.5rem;">
<span style="font-size: 1.8rem;">{icon}</span>
<div>
<div style="font-size: 1.1rem; font-weight: bold; color: white;">{name_display}</div>
<div style="color: #666; font-size: 0.75rem;">{strategy}</div>
</div>
</div>
</div>
<div style="text-align: right;">
<div style="color: {pnl_color}; font-size: 1.8rem; font-weight: bold; line-height: 1;">{pnl_pct:+.1f}%</div>
<div style="color: {pnl_color}; font-size: 0.85rem;">${total_pnl:+,.0f}</div>
</div>
</div>
<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; padding-top: 0.8rem; border-top: 1px solid rgba(255,255,255,0.1);">
<div style="text-align: center;"><div style="font-size: 1.1rem; font-weight: bold; color: white;">${total_value:,.0f}</div><div style="font-size: 0.65rem; color: #666; text-transform: uppercase;">Value</div></div>
<div style="text-align: center;"><div style="font-size: 1.1rem; font-weight: bold; color: #888;">${initial:,.0f}</div><div style="font-size: 0.65rem; color: #666; text-transform: uppercase;">Initial</div></div>
<div style="text-align: center;"><div style="font-size: 1.1rem; font-weight: bold; color: white;">{trades_count}</div><div style="font-size: 0.65rem; color: #666; text-transform: uppercase;">Trades</div></div>
<div style="text-align: center;"><div style="font-size: 1.1rem; font-weight: bold; color: {pos_color};">{positions_count}</div><div style="font-size: 0.65rem; color: #666; text-transform: uppercase;">Open</div></div>
</div>
<div style="margin-top: 0.6rem; padding-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.05);">
<div style="display: flex; flex-wrap: wrap; gap: 0.3rem;">{coins_html}</div>
</div>
</div>
</div>'''
                    st.markdown(card_html, unsafe_allow_html=True)

                    # Position breakdown
                    if positions_count > 0:
                        pos_html = f'<div style="background: rgba(0,170,255,0.05); padding: 0.4rem 1rem; margin-top: -0.5rem; margin-bottom: 0.5rem; border-radius: 0 0 12px 12px; font-size: 0.7rem; display: flex; justify-content: space-between;"><span style="color: #888;">💵 ${usdt_balance:,.0f} cash</span><span style="color: #888;">📊 ${positions_value:,.0f} invested</span><span style="color: {unrealized_color};">📈 ${unrealized_pnl:+,.0f} unrealized</span></div>'
                        st.markdown(pos_html, unsafe_allow_html=True)

                    # Action buttons
                    btn_col1, btn_col2, btn_col3, btn_col4, btn_col5, btn_col6, btn_col7 = st.columns(7)
                    with btn_col1:
                        # Take Profit button - sells all positions and converts to USDT
                        if positions_count > 0:
                            if st.button("💰", key=f"tp_{pid}", use_container_width=True, help="Take Profit - Sell all"):
                                # Sell all positions at current prices
                                for pos_detail in pf_value['positions_details']:
                                    symbol = pos_detail['symbol']
                                    asset = symbol.split('/')[0]
                                    current_value = pos_detail['current_value']
                                    pnl = pos_detail['pnl']

                                    # Add to USDT balance
                                    data['portfolios'][pid]['balance']['USDT'] += current_value
                                    data['portfolios'][pid]['balance'][asset] = 0

                                    # Remove position
                                    if symbol in data['portfolios'][pid]['positions']:
                                        del data['portfolios'][pid]['positions'][symbol]

                                    # Record trade
                                    data['portfolios'][pid]['trades'].append({
                                        'timestamp': datetime.now().isoformat(),
                                        'action': 'SELL',
                                        'symbol': symbol,
                                        'price': pos_detail['current_price'],
                                        'quantity': pos_detail['quantity'],
                                        'amount_usdt': current_value,
                                        'pnl': pnl,
                                        'reason': 'TAKE PROFIT (manual)'
                                    })

                                save_portfolios(data)
                                st.rerun()
                        else:
                            st.button("💰", key=f"tp_{pid}", use_container_width=True, disabled=True, help="No positions to sell")
                    with btn_col2:
                        if st.button("ℹ️", key=f"info_{pid}", use_container_width=True):
                            st.session_state[f'show_info_{pid}'] = not st.session_state.get(f'show_info_{pid}', False)
                            st.rerun()
                    with btn_col3:
                        if st.button("📊", key=f"activity_{pid}", use_container_width=True, help="Activity & Trades"):
                            st.session_state[f'show_activity_{pid}'] = not st.session_state.get(f'show_activity_{pid}', False)
                            st.rerun()
                    with btn_col4:
                        pass  # Removed separate logs button
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
                    with btn_col7:
                        if st.button("📈", key=f"chart_{pid}", use_container_width=True, help="Value History Chart"):
                            st.session_state[f'show_chart_{pid}'] = not st.session_state.get(f'show_chart_{pid}', False)
                            st.rerun()

                    # Show strategy info if toggled
                    if st.session_state.get(f'show_info_{pid}', False):
                        st.info(f"**{strategy}**: {tooltip}")

                    # Show value chart if toggled
                    if st.session_state.get(f'show_chart_{pid}', False):
                        history_data = load_portfolio_history()
                        gains = get_portfolio_gains(pid, history_data)

                        # Show gains in different timeframes
                        st.markdown("**📈 Performance**")
                        gain_cols = st.columns(4)
                        timeframes = [('1H', gains['hour']), ('1D', gains['day']), ('1W', gains['week']), ('1M', gains['month'])]

                        for i, (label, value) in enumerate(timeframes):
                            with gain_cols[i]:
                                if value is not None:
                                    color = '#00ff88' if value >= 0 else '#ff4444'
                                    st.markdown(f"""
                                    <div style="text-align: center; padding: 0.5rem; background: rgba(255,255,255,0.05); border-radius: 8px;">
                                        <div style="color: #888; font-size: 0.75rem;">{label}</div>
                                        <div style="color: {color}; font-size: 1.2rem; font-weight: bold;">{value:+.2f}%</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                                else:
                                    st.markdown(f"""
                                    <div style="text-align: center; padding: 0.5rem; background: rgba(255,255,255,0.05); border-radius: 8px;">
                                        <div style="color: #888; font-size: 0.75rem;">{label}</div>
                                        <div style="color: #666; font-size: 1rem;">--</div>
                                    </div>
                                    """, unsafe_allow_html=True)

                        # Show the chart
                        fig = create_portfolio_chart(pid, p['name'], history_data)
                        st.plotly_chart(fig, use_container_width=True)

                    # Show unified activity if toggled
                    if st.session_state.get(f'show_activity_{pid}', False):
                        # Get trades - already sorted by time (newest last)
                        all_trades = p.get('trades', [])
                        total_count = len(all_trades)

                        col_act1, col_act2 = st.columns([3, 1])
                        with col_act1:
                            st.markdown(f"**📊 Activity ({total_count})**")
                        with col_act2:
                            show_all_act = st.checkbox("All", key=f"act_all_{pid}", value=False)

                        # Get only what we need to display (reversed for newest first)
                        if show_all_act:
                            display_trades = list(reversed(all_trades[-50:]))  # Max 50 even for "all"
                        else:
                            display_trades = list(reversed(all_trades[-10:]))  # Last 10

                        if display_trades:
                            strategy_config = p.get('config', {})
                            default_tp = strategy_config.get('take_profit', 50)
                            default_sl = strategy_config.get('stop_loss', 25)

                            for t in display_trades:
                                a_action = t.get('action', '')
                                a_symbol = t.get('symbol', '').replace('/USDT', '').replace('\\USDT', '')
                                a_price = t.get('price', 0)
                                a_pnl = t.get('pnl', 0)
                                a_amount = t.get('amount_usdt', 0)
                                a_token_address = t.get('token_address', '')
                                a_chain = t.get('chain', '')
                                timestamp = t.get('timestamp', '')
                                a_time = timestamp[11:16] if len(timestamp) > 16 else timestamp[-5:]

                                # Format price
                                if a_price >= 1:
                                    price_str = f"${a_price:.4f}"
                                elif a_price >= 0.0001:
                                    price_str = f"${a_price:.6f}"
                                else:
                                    price_str = f"${a_price:.10f}"

                                # Icon and colors
                                is_buy = 'BUY' in a_action
                                is_sell = 'SELL' in a_action or 'SOLD' in a_action
                                is_rug = 'RUG' in a_action

                                if is_rug:
                                    icon = "💀"
                                elif is_buy:
                                    icon = "🟢"
                                elif is_sell:
                                    icon = "🔴"
                                else:
                                    icon = "⚪"

                                # DexScreener link
                                if a_token_address and a_chain:
                                    dex_url = f"https://dexscreener.com/{a_chain}/{a_token_address}"
                                else:
                                    dex_url = f"https://dexscreener.com/search?q={a_symbol}"

                                # Build display line with clear visual distinction
                                if is_sell or is_rug:
                                    # SELL/RUG trades - show prominently with PnL
                                    pnl_color = "green" if a_pnl >= 0 else "red"
                                    pnl_icon = "✅" if a_pnl >= 0 else "❌"
                                    st.markdown(f"{icon} **{a_action}** [{a_symbol}]({dex_url}) → {pnl_icon} :{pnl_color}[**${a_pnl:+.2f}**] @ {price_str} • {a_time}")
                                else:
                                    # BUY trades
                                    st.markdown(f"{icon} **{a_action}** [{a_symbol}]({dex_url}) → Spent **${a_amount:.2f}** @ {price_str} • {a_time}")

                            if not show_all_act and total_count > 10:
                                st.caption(f"Showing 10 of {total_count} trades")
                        else:
                            st.info("No trades yet")

                    # Show positions detail when there are open positions
                    if positions_count > 0:
                        with st.expander(f"📊 Open Positions ({positions_count})", expanded=False):
                            # Get TP/SL from strategy config
                            strategy_config = p.get('config', {})
                            tp_pct = strategy_config.get('take_profit', 50)
                            sl_pct = strategy_config.get('stop_loss', 25)

                            for pos_detail in pf_value['positions_details']:
                                pos_symbol = pos_detail['symbol'].replace('/USDT', '').replace('\\USDT', '')
                                pos_qty = pos_detail['quantity']
                                pos_entry = pos_detail['entry_price']
                                pos_current = pos_detail['current_price']
                                pos_value = pos_detail['current_value']
                                pos_pnl = pos_detail['pnl']
                                pos_pnl_pct = pos_detail['pnl_pct']
                                pos_token_address = pos_detail.get('token_address', '')
                                pos_chain = pos_detail.get('chain', '')
                                pos_entry_time = pos_detail.get('entry_time', '')

                                # Calculate TP and SL prices
                                tp_price = pos_entry * (1 + tp_pct / 100)
                                sl_price = pos_entry * (1 - sl_pct / 100)

                                # DexScreener link
                                dex_url = get_dexscreener_url(pos_symbol, pos_token_address, pos_chain)

                                # Parse entry time for display
                                entry_dt_str = ""
                                if pos_entry_time:
                                    try:
                                        from datetime import datetime
                                        entry_dt = datetime.fromisoformat(pos_entry_time.replace('Z', '+00:00'))
                                        entry_dt_str = entry_dt.strftime("%d/%m %H:%M")
                                    except:
                                        entry_dt_str = pos_entry_time[:16] if len(pos_entry_time) > 16 else pos_entry_time

                                # Header with symbol, PnL and entry time
                                pnl_color = "green" if pos_pnl >= 0 else "red"
                                st.markdown(f"**[{pos_symbol}]({dex_url})** | :{pnl_color}[**{pos_pnl_pct:+.1f}%** (${pos_pnl:+.2f})] | Qty: {pos_qty:.4f} | Entry: {entry_dt_str}")

                                # Fetch real price history
                                price_history = fetch_price_history(pos_symbol, pos_entry_time, pos_current)

                                # Create price chart with horizontal TP/SL lines
                                fig = go.Figure()

                                if price_history and len(price_history) > 1:
                                    # Real price curve from historical data
                                    times = [p['time'] for p in price_history]
                                    prices = [p['price'] for p in price_history]

                                    # Price line
                                    fig.add_trace(go.Scatter(
                                        x=times, y=prices,
                                        mode='lines',
                                        line=dict(color='#00d4ff', width=2),
                                        name='Price',
                                        hovertemplate='%{x|%d/%m %H:%M}<br>$%{y:.6f}<extra></extra>'
                                    ))

                                    # Entry point marker (first point)
                                    fig.add_trace(go.Scatter(
                                        x=[times[0]], y=[pos_entry],
                                        mode='markers',
                                        marker=dict(size=10, color='#ffaa00', symbol='triangle-up'),
                                        name='Entry',
                                        hovertemplate=f'Entry: {entry_dt_str}<br>${pos_entry:.6f}<extra></extra>'
                                    ))

                                    # Current price marker (last point)
                                    fig.add_trace(go.Scatter(
                                        x=[times[-1]], y=[prices[-1]],
                                        mode='markers',
                                        marker=dict(size=10, color='#00d4ff', symbol='diamond'),
                                        name='Now',
                                        hovertemplate=f'Now<br>${pos_current:.6f}<extra></extra>'
                                    ))
                                else:
                                    # Fallback: simple line with entry time
                                    from datetime import datetime
                                    try:
                                        entry_dt = datetime.fromisoformat(pos_entry_time.replace('Z', '+00:00'))
                                        now = datetime.now()
                                        fig.add_trace(go.Scatter(
                                            x=[entry_dt, now], y=[pos_entry, pos_current],
                                            mode='lines+markers',
                                            line=dict(color='#00d4ff', width=2),
                                            marker=dict(size=[10, 10], color=['#ffaa00', '#00d4ff'], symbol=['triangle-up', 'diamond'])
                                        ))
                                    except:
                                        fig.add_trace(go.Scatter(
                                            x=[0, 1], y=[pos_entry, pos_current],
                                            mode='lines+markers',
                                            line=dict(color='#00d4ff', width=2),
                                            marker=dict(size=[6, 10], color=['#888', '#00d4ff'])
                                        ))

                                # Entry, TP, SL horizontal lines
                                fig.add_hline(y=pos_entry, line_dash="dash", line_color="#ffaa00", line_width=1,
                                             annotation_text=f"Entry ${pos_entry:.6f}", annotation_position="left", annotation_font_size=9)
                                fig.add_hline(y=tp_price, line_dash="solid", line_color="#00ff88", line_width=1,
                                             annotation_text=f"TP +{tp_pct}%", annotation_position="right", annotation_font_size=9)
                                fig.add_hline(y=sl_price, line_dash="solid", line_color="#ff4444", line_width=1,
                                             annotation_text=f"SL -{sl_pct}%", annotation_position="right", annotation_font_size=9)

                                fig.update_layout(
                                    height=180,
                                    margin=dict(l=10, r=60, t=10, b=30),
                                    paper_bgcolor='rgba(0,0,0,0)',
                                    plot_bgcolor='rgba(0,0,0,0.2)',
                                    showlegend=False,
                                    xaxis=dict(showticklabels=True, showgrid=False, tickfont=dict(size=9, color='#666'),
                                              tickformat='%d/%m %H:%M'),
                                    yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', tickformat='.6f', side='right', tickfont=dict(size=9)),
                                )

                                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})



def load_settings() -> Dict:
    """Load settings from file"""
    try:
        with open("data/settings.json", 'r') as f:
            return json.load(f)
    except:
        return {
            "binance_api_key": "",
            "binance_secret": "",
            "binance_testnet": True,
            "etherscan_api_key": "",
            "helius_api_key": "",
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "alert_types": ["Pump Detected", "Position Closed"],
            "refresh_rate": 10
        }

def save_settings(settings: Dict):
    """Save settings to file"""
    os.makedirs("data", exist_ok=True)
    with open("data/settings.json", 'w') as f:
        json.dump(settings, f, indent=2)

def render_settings():
    """Settings"""
    header("⚙️ Settings")

    # Load current settings
    settings = load_settings()

    tab1, tab2, tab3 = st.tabs(["🔑 API Keys", "🔔 Notifications", "🎨 Preferences"])

    with tab1:
        st.subheader("Exchange API")
        col1, col2 = st.columns(2)
        with col1:
            binance_key = st.text_input("Binance API Key", value=settings.get("binance_api_key", ""), type="password", placeholder="Enter API key...")
        with col2:
            binance_secret = st.text_input("Binance Secret", value=settings.get("binance_secret", ""), type="password", placeholder="Enter secret...")

        testnet = st.checkbox("Testnet Mode", value=settings.get("binance_testnet", True))

        st.divider()

        st.subheader("Blockchain APIs (Whale Tracking)")
        st.caption("Get free API keys:")
        st.markdown("""
        - **Etherscan**: [etherscan.io/apis](https://etherscan.io/apis) (100k calls/day free) - Works for ETH + BSC
        - **Helius (Solana)**: [helius.dev](https://helius.dev) (100k credits/month free)
        """)

        col1, col2 = st.columns(2)
        with col1:
            etherscan_key = st.text_input("Etherscan API Key", value=settings.get("etherscan_api_key", ""), type="password", placeholder="For ETH + BSC whale tracking")
        with col2:
            helius_key = st.text_input("Helius API Key (Solana)", value=settings.get("helius_api_key", ""), type="password", placeholder="For SOL whale tracking")

        # Show status
        st.divider()
        st.subheader("API Status")
        col1, col2 = st.columns(2)
        with col1:
            if settings.get("etherscan_api_key"):
                st.success("Etherscan (ETH+BSC): Connected")
            else:
                st.warning("Etherscan: Not configured")
        with col2:
            if settings.get("helius_api_key"):
                st.success("Helius (Solana): Connected")
            else:
                st.warning("Helius: Not configured")

    with tab2:
        st.subheader("Telegram Alerts")
        col1, col2 = st.columns(2)
        with col1:
            telegram_token = st.text_input("Bot Token", value=settings.get("telegram_bot_token", ""), type="password")
        with col2:
            telegram_chat = st.text_input("Chat ID", value=settings.get("telegram_chat_id", ""))

        alert_types = st.multiselect("Alert Types", [
            "Pump Detected", "Dump Detected", "Position Opened",
            "Position Closed", "Daily Summary", "Whale Alert"
        ], default=settings.get("alert_types", ["Pump Detected", "Position Closed"]))

    with tab3:
        st.subheader("Display")
        st.selectbox("Theme", ["Dark (Default)", "Degen Rainbow"])
        st.checkbox("Sound Alerts", value=False)
        refresh_rate = st.slider("Refresh Rate (seconds)", 5, 60, settings.get("refresh_rate", 10))

    if st.button("💾 Save Settings", type="primary"):
        new_settings = {
            "binance_api_key": binance_key,
            "binance_secret": binance_secret,
            "binance_testnet": testnet,
            "etherscan_api_key": etherscan_key,
            "helius_api_key": helius_key,
            "telegram_bot_token": telegram_token,
            "telegram_chat_id": telegram_chat,
            "alert_types": alert_types,
            "refresh_rate": refresh_rate
        }
        save_settings(new_settings)
        st.success("Settings saved!")
        st.rerun()


def render_debug():
    """Debug panel - real-time bot monitoring"""
    header("🐛 Debug Console")

    # Load debug state
    debug_file = "data/debug_log.json"
    debug_state = {
        'bot_status': {'running': False, 'started_at': None, 'scan_count': 0},
        'last_scan': {},
        'api_health': {},
        'recent_errors': [],
        'recent_trades': []
    }

    try:
        if os.path.exists(debug_file):
            with open(debug_file, 'r', encoding='utf-8') as f:
                debug_state = json.load(f)
    except:
        pass

    bot_status = debug_state.get('bot_status', {})
    last_scan = debug_state.get('last_scan', {})

    # === BOT STATUS BANNER ===
    is_running = bot_status.get('running', False)
    last_update = bot_status.get('last_update', 'Never')

    # Check if bot is actually running (last update < 10 min - scans take ~6 min)
    try:
        last_dt = datetime.strptime(last_update, "%Y-%m-%d %H:%M:%S")
        age_seconds = (datetime.now() - last_dt).total_seconds()
        actually_running = is_running and age_seconds < 600
    except:
        actually_running = False
        age_seconds = 9999

    if actually_running:
        st.markdown(f"""
        <div style="background: linear-gradient(90deg, #00ff88 0%, #00cc6a 100%); padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
            <span style="font-size: 1.5rem;">🟢</span>
            <b style="color: #000; font-size: 1.2rem;"> BOT RUNNING</b>
            <span style="color: #000; margin-left: 1rem;">Scan #{bot_status.get('scan_count', 0)} | Updated {int(age_seconds)}s ago</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background: #ff4444; padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">
            <span style="font-size: 1.5rem;">🔴</span>
            <b style="color: #fff; font-size: 1.2rem;"> BOT STOPPED</b>
            <span style="color: #fff; margin-left: 1rem;">Last seen: {last_update}</span>
        </div>
        """, unsafe_allow_html=True)

    # === LAST SCAN INFO ===
    st.subheader("📊 Last Scan")
    if last_scan:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Scan #", last_scan.get('scan_number', 'N/A'))
        with col2:
            st.metric("Duration", f"{last_scan.get('duration_seconds', 0)}s")
        with col3:
            st.metric("Portfolios", last_scan.get('active_portfolios', 0))
        with col4:
            st.metric("API Errors", last_scan.get('api_errors', 0))

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Classic Trades", last_scan.get('classic_trades', 0))
        with col2:
            st.metric("Sniper Trades", last_scan.get('sniper_trades', 0))
        with col3:
            st.metric("New Tokens", last_scan.get('new_tokens_found', 0))

        timeframes = last_scan.get('timeframes', [])
        tf_str = ', '.join(timeframes) if timeframes else '1h'
        st.caption(f"Scan time: {last_scan.get('timestamp', 'N/A')} | Timeframes: {tf_str} | Total tokens seen: {last_scan.get('total_tokens_seen', 0)}")
    else:
        st.info("No scan data yet. Start the bot to see activity.")

    st.divider()

    # === TABS ===
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Recent Trades", "🔴 Errors", "🔌 API Health", "📋 Full Report"])

    # TAB 1: Recent Trades
    with tab1:
        trades = debug_state.get('recent_trades', [])
        if not trades:
            st.info("No trades yet.")
        else:
            for trade in reversed(trades):
                action = trade.get('action', 'UNKNOWN')
                color = '#00ff88' if 'BUY' in action else '#ff4444'
                symbol = trade.get('symbol', '?')
                # Clean symbol for DexScreener search (remove /USDT, \USDT, etc.)
                clean_symbol = symbol.replace('/USDT', '').replace('\\USDT', '').replace('USDT', '')
                dex_url = f"https://dexscreener.com/search?q={clean_symbol}"
                symbol_link = f'<a href="{dex_url}" target="_blank" style="color: #00d4ff; text-decoration: none;">{symbol} 🔗</a>'
                st.markdown(f"""
                <div style="background: #1a1a2e; padding: 0.5rem 1rem; border-radius: 5px; margin-bottom: 0.5rem; border-left: 3px solid {color};">
                    <span style="color: {color}; font-weight: bold;">{action}</span>
                    <span> {symbol_link}</span>
                    <span style="color: #888;"> @ ${trade.get('price', 0):,.2f}</span>
                    <span style="color: #666; float: right;">{trade.get('timestamp', '')}</span>
                    <br><span style="color: #aaa; font-size: 0.8rem;">{trade.get('portfolio', '')} - {trade.get('reason', '')}</span>
                </div>
                """, unsafe_allow_html=True)

    # TAB 2: Errors
    with tab2:
        errors = debug_state.get('recent_errors', [])
        if not errors:
            st.success("No errors! Everything is working fine.")
        else:
            if st.button("🗑️ Clear Errors"):
                debug_state['recent_errors'] = []
                with open(debug_file, 'w', encoding='utf-8') as f:
                    json.dump(debug_state, f, indent=2)
                st.rerun()

            for err in reversed(errors):
                with st.expander(f"🔴 [{err.get('timestamp')}] {err.get('category')}: {err.get('message')}", expanded=False):
                    st.code(f"Type: {err.get('error_type', 'N/A')}\nMessage: {err.get('error_msg', 'N/A')}")
                    if err.get('context'):
                        st.json(err['context'])
                    if err.get('traceback'):
                        st.code(err['traceback'], language='python')

    # TAB 3: API Health
    with tab3:
        api_health = debug_state.get('api_health', {})
        if not api_health:
            st.info("No API calls recorded yet.")
        else:
            for api_name, status in api_health.items():
                is_ok = status.get('status') == 'ok'
                icon = "✅" if is_ok else "❌"
                st.markdown(f"""
                **{icon} {api_name}**
                - Status: `{status.get('status', 'unknown')}`
                - Last check: {status.get('last_check', 'N/A')}
                - Message: {status.get('message', 'N/A')}
                """)

        st.divider()
        st.markdown("**Live API Check:**")
        col1, col2 = st.columns(2)
        with col1:
            try:
                r = requests.get("https://api.binance.com/api/v3/ping", timeout=5)
                if r.status_code == 200:
                    st.success("Binance: OK")
                else:
                    st.error(f"Binance: {r.status_code}")
            except Exception as e:
                st.error(f"Binance: {e}")
        with col2:
            try:
                r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=5)
                if r.status_code == 200:
                    st.success("Fear&Greed: OK")
                else:
                    st.error(f"Fear&Greed: {r.status_code}")
            except Exception as e:
                st.error(f"Fear&Greed: {e}")

    # TAB 4: Full Report
    with tab4:
        st.markdown("### Copy this for debugging:")

        # Build report
        report = [
            "=" * 50,
            "TRADING BOT DEBUG REPORT",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 50,
            "",
            f"Bot Running: {actually_running}",
            f"Scan Count: {bot_status.get('scan_count', 0)}",
            f"Last Update: {last_update}",
            "",
            "--- LAST SCAN ---",
            json.dumps(last_scan, indent=2),
            "",
            "--- RECENT ERRORS ---",
        ]

        for err in debug_state.get('recent_errors', [])[-5:]:
            report.append(f"\n[{err.get('timestamp')}] {err.get('category')}: {err.get('message')}")
            report.append(f"  Error: {err.get('error_type')}: {err.get('error_msg')}")

        report.extend(["", "--- PORTFOLIOS ---"])
        try:
            pf_data = load_portfolios()
            for pid, p in pf_data.get('portfolios', {}).items():
                report.append(f"{p.get('name')} [{p.get('strategy_id')}]: ${p.get('balance', {}).get('USDT', 0):,.0f} | {len(p.get('positions', {}))} pos | {len(p.get('trades', []))} trades")
        except:
            report.append("Could not load portfolios")

        st.code("\n".join(report), language=None)


if __name__ == "__main__":
    main()
