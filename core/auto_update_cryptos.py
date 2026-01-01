"""
AUTO-UPDATE CRYPTO LIST
=======================
Automatically fetches top cryptos by volume from Binance
and updates portfolio configurations.

Runs daily or on-demand.
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict
import requests

# Config
UPDATE_INTERVAL_HOURS = 24  # Update once per day
STATE_FILE = "data/crypto_update_state.json"
PORTFOLIOS_FILE = "data/portfolios.json"

# Exclusions (stablecoins, wrapped tokens, gold, etc.)
EXCLUDED_TOKENS = {
    # Stablecoins
    'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'FDUSD', 'USDE', 'USDJ',
    'USD1', 'XUSD', 'BFUSD', 'EUR', 'GBP', 'AEUR', 'EURI',
    # Wrapped tokens
    'WBTC', 'WETH', 'WBNB', 'WBETH', 'STETH', 'CBETH', 'RETH',
    # Gold/Commodity tokens
    'PAXG', 'GOLD',
    # Index/Leveraged tokens
    'BTCDOM', 'DEFI', 'ETHDOM',
    # Low quality / pump tokens to exclude
    'AVNT', 'ASTER',
}

# Minimum volume filter (in USDT)
MIN_24H_VOLUME = 5_000_000  # $5M minimum for more coverage


def load_state() -> Dict:
    """Load update state"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {'last_update': None, 'top_cryptos': []}


def save_state(state: Dict):
    """Save update state"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[AUTO-UPDATE] Error saving state: {e}")


def fetch_top_cryptos_by_volume(limit: int = 100) -> List[str]:
    """
    Fetch top cryptos by 24h volume from Binance.
    Returns list of symbols like ['BTC/USDT', 'ETH/USDT', ...]
    """
    try:
        # Get 24h ticker data from Binance
        url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        tickers = response.json()

        # Filter USDT pairs only and exclude stablecoins
        usdt_pairs = []
        for ticker in tickers:
            symbol = ticker['symbol']
            if not symbol.endswith('USDT'):
                continue

            base = symbol.replace('USDT', '')
            if base in EXCLUDED_TOKENS:
                continue

            volume_usdt = float(ticker['quoteVolume'])
            if volume_usdt < MIN_24H_VOLUME:
                continue

            usdt_pairs.append({
                'symbol': f"{base}/USDT",
                'volume': volume_usdt,
                'price_change': float(ticker['priceChangePercent'])
            })

        # Sort by volume descending
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)

        # Return top N symbols
        top_symbols = [p['symbol'] for p in usdt_pairs[:limit]]

        print(f"[AUTO-UPDATE] Fetched {len(top_symbols)} top cryptos by volume")
        return top_symbols

    except Exception as e:
        print(f"[AUTO-UPDATE] Error fetching from Binance: {e}")
        return []


def should_update() -> bool:
    """Check if we should update (based on time interval)"""
    state = load_state()
    last_update = state.get('last_update')

    if not last_update:
        return True

    try:
        last_dt = datetime.fromisoformat(last_update)
        hours_since = (datetime.now() - last_dt).total_seconds() / 3600
        return hours_since >= UPDATE_INTERVAL_HOURS
    except:
        return True


def update_portfolios_cryptos(new_cryptos: List[str], portfolio_ids: List[str] = None):
    """
    Update crypto lists in specified portfolios.
    If portfolio_ids is None, updates portfolios with 'auto_update_cryptos': True
    """
    try:
        with open(PORTFOLIOS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        updated_count = 0
        for pid, portfolio in data['portfolios'].items():
            # Check if this portfolio should be auto-updated
            config = portfolio.get('config', {})

            if portfolio_ids:
                if pid not in portfolio_ids:
                    continue
            else:
                # Auto-update only if flag is set
                if not config.get('auto_update_cryptos', False):
                    continue

            # Update crypto list
            old_cryptos = config.get('cryptos', [])
            config['cryptos'] = new_cryptos
            portfolio['config'] = config

            # Log changes
            added = set(new_cryptos) - set(old_cryptos)
            removed = set(old_cryptos) - set(new_cryptos)

            if added or removed:
                print(f"[AUTO-UPDATE] {portfolio['name']}: +{len(added)} -{len(removed)} cryptos")
                updated_count += 1

        # Save
        with open(PORTFOLIOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[AUTO-UPDATE] Updated {updated_count} portfolios")
        return updated_count

    except Exception as e:
        print(f"[AUTO-UPDATE] Error updating portfolios: {e}")
        return 0


def run_auto_update(force: bool = False) -> Dict:
    """
    Main function to run auto-update.
    Returns status dict.
    """
    result = {
        'updated': False,
        'cryptos_count': 0,
        'portfolios_updated': 0,
        'timestamp': datetime.now().isoformat()
    }

    # Check if update needed
    if not force and not should_update():
        state = load_state()
        result['message'] = "Update not needed yet"
        result['cryptos_count'] = len(state.get('top_cryptos', []))
        return result

    print(f"[AUTO-UPDATE] Starting crypto list update...")

    # Fetch top cryptos
    top_cryptos = fetch_top_cryptos_by_volume(100)

    if not top_cryptos:
        result['message'] = "Failed to fetch cryptos"
        return result

    # Update portfolios
    portfolios_updated = update_portfolios_cryptos(top_cryptos)

    # Save state
    state = {
        'last_update': datetime.now().isoformat(),
        'top_cryptos': top_cryptos,
        'volume_threshold': MIN_24H_VOLUME
    }
    save_state(state)

    result['updated'] = True
    result['cryptos_count'] = len(top_cryptos)
    result['portfolios_updated'] = portfolios_updated
    result['message'] = f"Updated with {len(top_cryptos)} cryptos"
    result['top_5'] = top_cryptos[:5]

    print(f"[AUTO-UPDATE] Complete! Top 5: {', '.join(top_cryptos[:5])}")

    return result


def get_current_top_cryptos() -> List[str]:
    """Get current top cryptos from state (no API call)"""
    state = load_state()
    return state.get('top_cryptos', [])


def enable_auto_update_for_portfolio(portfolio_id: str):
    """Enable auto-update for a specific portfolio"""
    try:
        with open(PORTFOLIOS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if portfolio_id in data['portfolios']:
            data['portfolios'][portfolio_id]['config']['auto_update_cryptos'] = True

            with open(PORTFOLIOS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"[AUTO-UPDATE] Enabled for {portfolio_id}")
            return True
    except Exception as e:
        print(f"[AUTO-UPDATE] Error: {e}")
    return False


# Test
if __name__ == "__main__":
    print("Testing auto-update system...")
    result = run_auto_update(force=True)
    print(f"\nResult: {json.dumps(result, indent=2)}")
