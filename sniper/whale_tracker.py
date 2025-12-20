"""
Whale Tracker - Copy trading des whales crypto
==============================================

Suit les transactions des plus gros wallets et copie leurs trades.
Utilise des APIs publiques pour tracker les mouvements.
"""
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import json
import os

@dataclass
class WhaleTransaction:
    """Transaction d'une whale"""
    whale_name: str
    wallet: str
    action: str  # BUY or SELL
    token_symbol: str
    token_address: str
    amount_usd: float
    price: float
    chain: str
    timestamp: datetime
    tx_hash: str

# Known whale wallets (public, famous traders)
WHALE_WALLETS = {
    # Ethereum whales
    "eth_whale_1": {
        "name": "Jump Trading",
        "wallet": "0x9507c04b10486547584c37bcbd931b2a4fee9a41",
        "chain": "ethereum",
        "type": "institution"
    },
    "eth_whale_2": {
        "name": "Wintermute",
        "wallet": "0x4f3a120e72c76c22ae802d129f599bfdbc31cb81",
        "chain": "ethereum",
        "type": "market_maker"
    },
    "eth_whale_3": {
        "name": "Alameda Remains",
        "wallet": "0x84d34f4f83a87596cd3fb6887cff8f17bf5a7b83",
        "chain": "ethereum",
        "type": "fund"
    },

    # Solana whales
    "sol_whale_1": {
        "name": "SOL Whale Alpha",
        "wallet": "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",
        "chain": "solana",
        "type": "trader"
    },

    # BSC whales
    "bsc_whale_1": {
        "name": "BSC Degen King",
        "wallet": "0x8894e0a0c962cb723c1976a4421c95949be2d4e3",
        "chain": "bsc",
        "type": "degen"
    },

    # Famous traders (simulated based on public info)
    "trader_1": {
        "name": "GCR (simulated)",
        "wallet": "gcr_simulated",
        "chain": "multi",
        "type": "legendary",
        "style": "contrarian"
    },
    "trader_2": {
        "name": "Hsaka (simulated)",
        "wallet": "hsaka_simulated",
        "chain": "multi",
        "type": "legendary",
        "style": "momentum"
    },
    "trader_3": {
        "name": "Cobie (simulated)",
        "wallet": "cobie_simulated",
        "chain": "multi",
        "type": "legendary",
        "style": "value"
    },
    "trader_4": {
        "name": "Ansem (simulated)",
        "wallet": "ansem_simulated",
        "chain": "solana",
        "type": "legendary",
        "style": "memecoin"
    },
    "trader_5": {
        "name": "CryptoCobain (simulated)",
        "wallet": "cobain_simulated",
        "chain": "multi",
        "type": "legendary",
        "style": "degen"
    },

    # US Congress Members (famous for their trading performance)
    "congress_pelosi": {
        "name": "Nancy Pelosi",
        "wallet": "pelosi_simulated",
        "chain": "multi",
        "type": "congress",
        "style": "congress_tech",
        "focus": ["NVDA", "GOOGL", "MSFT", "AAPL", "AMZN", "META", "TSLA", "AMD", "CRM", "AVGO"]
    },
    "congress_tuberville": {
        "name": "Tommy Tuberville",
        "wallet": "tuberville_simulated",
        "chain": "multi",
        "type": "congress",
        "style": "congress_defense",
        "focus": ["LMT", "RTX", "NOC", "BA", "GD"]
    },
    "congress_crenshaw": {
        "name": "Dan Crenshaw",
        "wallet": "crenshaw_simulated",
        "chain": "multi",
        "type": "congress",
        "style": "congress_energy",
        "focus": ["XOM", "CVX", "OXY", "SLB", "HAL"]
    },
    "congress_mccaul": {
        "name": "Michael McCaul",
        "wallet": "mccaul_simulated",
        "chain": "multi",
        "type": "congress",
        "style": "congress_tech",
        "focus": ["NVDA", "MSFT", "GOOGL", "META", "INTC"]
    },
    "congress_all": {
        "name": "Congress Composite",
        "wallet": "congress_all_simulated",
        "chain": "multi",
        "type": "congress",
        "style": "congress_composite",
        "focus": ["NVDA", "GOOGL", "MSFT", "AAPL", "AMZN", "META", "TSLA", "AMD"]
    },

    # ============ LEGENDARY INVESTORS (World's Best) ============

    # Warren Buffett - Value investing, quality at discount
    "legend_buffett": {
        "name": "Warren Buffett",
        "wallet": "buffett_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_value",
        "description": "Buy wonderful companies at fair prices, hold forever"
    },

    # Ray Dalio - All Weather, risk parity, macro
    "legend_dalio": {
        "name": "Ray Dalio",
        "wallet": "dalio_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_allweather",
        "description": "Balanced portfolio, hedge all environments"
    },

    # Jim Simons - Quant king, Renaissance Technologies (66% annual returns)
    "legend_simons": {
        "name": "Jim Simons",
        "wallet": "simons_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_quant",
        "description": "Pure quant, statistical arbitrage, mean reversion"
    },

    # George Soros - Macro legend, broke Bank of England
    "legend_soros": {
        "name": "George Soros",
        "wallet": "soros_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_macro",
        "description": "Reflexivity, big macro bets, trend following"
    },

    # Michael Burry - Contrarian, The Big Short
    "legend_burry": {
        "name": "Michael Burry",
        "wallet": "burry_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_contrarian",
        "description": "Deep value, contrarian, short overvalued assets"
    },

    # Cathie Wood - Innovation, disruptive tech (ARK)
    "legend_cathie": {
        "name": "Cathie Wood",
        "wallet": "cathie_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_innovation",
        "description": "Disruptive innovation, high growth, 5-year horizon"
    },

    # Stanley Druckenmiller - Macro, Soros protégé
    "legend_druckenmiller": {
        "name": "Stanley Druckenmiller",
        "wallet": "druckenmiller_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_macro",
        "description": "Macro trends, concentrated bets, owns Bitcoin"
    },

    # Paul Tudor Jones - Macro, trend following
    "legend_ptj": {
        "name": "Paul Tudor Jones",
        "wallet": "ptj_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_trend",
        "description": "Trend following, momentum, 5% BTC allocation"
    },

    # Carl Icahn - Activist investor
    "legend_icahn": {
        "name": "Carl Icahn",
        "wallet": "icahn_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_activist",
        "description": "Activist, undervalued assets, force change"
    },

    # Bill Ackman - Concentrated bets, activist
    "legend_ackman": {
        "name": "Bill Ackman",
        "wallet": "ackman_simulated",
        "chain": "multi",
        "type": "legend",
        "style": "legend_concentrated",
        "description": "Concentrated portfolio, high conviction bets"
    }
}

class WhaleTracker:
    """Track whale transactions and generate copy-trade signals"""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.last_transactions = {}
        self.cache_file = "data/whale_cache.json"
        self._load_cache()

    def _load_cache(self):
        """Load cached transactions"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    self.last_transactions = json.load(f)
        except:
            self.last_transactions = {}

    def _save_cache(self):
        """Save transaction cache"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.last_transactions, f, default=str)
        except:
            pass

    def get_whale_signals(self, whale_ids: List[str] = None) -> List[Dict]:
        """
        Get trading signals from whale activity
        Returns list of {action, symbol, whale, confidence, reason}
        """
        signals = []
        whales = whale_ids or list(WHALE_WALLETS.keys())

        for whale_id in whales:
            whale = WHALE_WALLETS.get(whale_id)
            if not whale:
                continue

            try:
                whale_signals = self._get_whale_activity(whale_id, whale)
                signals.extend(whale_signals)
            except Exception as e:
                print(f"Error tracking {whale['name']}: {e}")

        return signals

    def _get_whale_activity(self, whale_id: str, whale: Dict) -> List[Dict]:
        """Get activity for a specific whale"""
        signals = []

        # For simulated traders, generate signals based on their style
        if whale['wallet'].endswith('_simulated'):
            signals = self._simulate_legendary_trader(whale_id, whale)
        else:
            # Real wallet tracking via public APIs
            signals = self._track_real_wallet(whale_id, whale)

        return signals

    def _simulate_legendary_trader(self, whale_id: str, whale: Dict) -> List[Dict]:
        """
        Simulate signals from legendary traders based on their known styles.
        In production, this would use their actual public calls/tweets.
        """
        signals = []
        style = whale.get('style', 'momentum')

        # Get market data to base decisions on
        try:
            market_data = self._get_market_overview()
        except:
            market_data = {}

        # Generate signals based on trader style
        if style == 'contrarian':
            # GCR style: Buy fear, sell greed
            signals = self._contrarian_signals(whale, market_data)
        elif style == 'momentum':
            # Hsaka style: Ride the wave
            signals = self._momentum_signals(whale, market_data)
        elif style == 'value':
            # Cobie style: Fundamentals + patience
            signals = self._value_signals(whale, market_data)
        elif style == 'memecoin':
            # Ansem style: Early memecoin entries
            signals = self._memecoin_signals(whale, market_data)
        elif style == 'degen':
            # Full degen: High risk high reward
            signals = self._degen_signals(whale, market_data)
        elif style.startswith('congress_'):
            # Congress member style: Buy their favorite sectors
            signals = self._congress_signals(whale, market_data)
        elif style.startswith('legend_'):
            # Legendary investors
            signals = self._legend_signals(whale, market_data)

        return signals

    def _get_market_overview(self) -> Dict:
        """Get current market conditions"""
        try:
            # Fear & Greed Index
            fg_response = requests.get("https://api.alternative.me/fng/", timeout=5)
            fg_data = fg_response.json()
            fear_greed = int(fg_data['data'][0]['value'])

            # BTC price and change
            btc_response = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=5)
            btc_data = btc_response.json()
            btc_change = float(btc_data['priceChangePercent'])

            # Top movers
            tickers = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=5).json()
            usdt_pairs = [t for t in tickers if t['symbol'].endswith('USDT') and 'UP' not in t['symbol'] and 'DOWN' not in t['symbol']]

            top_gainers = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']), reverse=True)[:10]
            top_losers = sorted(usdt_pairs, key=lambda x: float(x['priceChangePercent']))[:10]

            return {
                'fear_greed': fear_greed,
                'btc_change': btc_change,
                'top_gainers': top_gainers,
                'top_losers': top_losers,
                'market_trend': 'bullish' if btc_change > 2 else 'bearish' if btc_change < -2 else 'neutral'
            }
        except Exception as e:
            return {'fear_greed': 50, 'btc_change': 0, 'market_trend': 'neutral', 'top_gainers': [], 'top_losers': []}

    def _contrarian_signals(self, whale: Dict, market: Dict) -> List[Dict]:
        """GCR-style contrarian signals: buy fear, sell greed"""
        signals = []
        fg = market.get('fear_greed', 50)

        # Extreme fear = buy signal
        if fg < 25:
            for loser in market.get('top_losers', [])[:3]:
                symbol = loser['symbol'].replace('USDT', '/USDT')
                change = float(loser['priceChangePercent'])
                if change < -10:  # Only big drops
                    signals.append({
                        'action': 'BUY',
                        'symbol': symbol,
                        'whale': whale['name'],
                        'confidence': min(90, 100 - fg),
                        'reason': f"CONTRARIAN: Fear={fg}, {symbol} down {change:.1f}%"
                    })

        # Extreme greed = sell signal
        elif fg > 80:
            for gainer in market.get('top_gainers', [])[:3]:
                symbol = gainer['symbol'].replace('USDT', '/USDT')
                change = float(gainer['priceChangePercent'])
                if change > 15:  # Only big pumps
                    signals.append({
                        'action': 'SELL',
                        'symbol': symbol,
                        'whale': whale['name'],
                        'confidence': min(90, fg),
                        'reason': f"CONTRARIAN: Greed={fg}, {symbol} up {change:.1f}%"
                    })

        return signals

    def _momentum_signals(self, whale: Dict, market: Dict) -> List[Dict]:
        """Hsaka-style momentum: ride strong trends"""
        signals = []

        for gainer in market.get('top_gainers', [])[:10]:
            symbol = gainer['symbol'].replace('USDT', '/USDT')
            change = float(gainer['priceChangePercent'])
            volume = float(gainer.get('quoteVolume', 0))

            # Strong momentum with decent volume
            if change > 5 and volume > 5_000_000:  # >5% gain, >$5M volume
                signals.append({
                    'action': 'BUY',
                    'symbol': symbol,
                    'whale': whale['name'],
                    'confidence': min(85, 50 + change),
                    'reason': f"MOMENTUM: {symbol} +{change:.1f}% with ${volume/1e6:.0f}M volume"
                })

        return signals

    def _value_signals(self, whale: Dict, market: Dict) -> List[Dict]:
        """Cobie-style value investing: quality at discount"""
        signals = []

        # Quality tokens that are down (expanded list)
        quality_tokens = [
            'ETH/USDT', 'SOL/USDT', 'LINK/USDT', 'AAVE/USDT', 'UNI/USDT', 'MKR/USDT',
            'AVAX/USDT', 'DOT/USDT', 'ATOM/USDT', 'NEAR/USDT', 'ARB/USDT', 'OP/USDT',
            'MATIC/USDT', 'LDO/USDT', 'CRV/USDT', 'SNX/USDT', 'COMP/USDT', 'SUSHI/USDT',
            'INJ/USDT', 'TIA/USDT', 'SEI/USDT', 'SUI/USDT', 'APT/USDT', 'FTM/USDT',
            'RUNE/USDT', 'GMX/USDT', 'DYDX/USDT', 'ENS/USDT', 'GRT/USDT', 'FIL/USDT'
        ]

        for loser in market.get('top_losers', [])[:20]:
            symbol = loser['symbol'].replace('USDT', '/USDT')
            change = float(loser['priceChangePercent'])

            if symbol in quality_tokens and change < -5:  # -5% threshold
                signals.append({
                    'action': 'BUY',
                    'symbol': symbol,
                    'whale': whale['name'],
                    'confidence': 75,
                    'reason': f"VALUE: Quality token {symbol} on sale ({change:.1f}%)"
                })

        return signals

    def _memecoin_signals(self, whale: Dict, market: Dict) -> List[Dict]:
        """Ansem-style memecoin plays"""
        signals = []

        # Extended memecoin list
        memecoins = [
            'DOGE/USDT', 'SHIB/USDT', 'PEPE/USDT', 'FLOKI/USDT', 'BONK/USDT', 'WIF/USDT',
            'TURBO/USDT', 'MEME/USDT', 'SATS/USDT', 'RATS/USDT', 'ORDI/USDT', '1000SATS/USDT',
            'PEOPLE/USDT', 'LUNC/USDT', 'BABYDOGE/USDT', 'ELON/USDT', 'LADYS/USDT',
            'WOJAK/USDT', 'BITCOIN/USDT', 'COQ/USDT', 'MYRO/USDT', 'SILLY/USDT',
            'MOG/USDT', 'BRETT/USDT', 'POPCAT/USDT', 'NEIRO/USDT', 'GOAT/USDT'
        ]

        for gainer in market.get('top_gainers', [])[:20]:
            symbol = gainer['symbol'].replace('USDT', '/USDT')
            change = float(gainer['priceChangePercent'])

            if symbol in memecoins and change > 3:  # Lower threshold to 3%
                signals.append({
                    'action': 'BUY',
                    'symbol': symbol,
                    'whale': whale['name'],
                    'confidence': 60,
                    'reason': f"MEME: {symbol} pumping +{change:.1f}%"
                })

        # Also buy any meme that's really pumping, even if not in list
        for gainer in market.get('top_gainers', [])[:5]:
            symbol = gainer['symbol'].replace('USDT', '/USDT')
            change = float(gainer['priceChangePercent'])

            if change > 15 and symbol not in [s['symbol'] for s in signals]:
                signals.append({
                    'action': 'BUY',
                    'symbol': symbol,
                    'whale': whale['name'],
                    'confidence': 55,
                    'reason': f"MEME FOMO: {symbol} pumping hard +{change:.1f}%"
                })

        return signals

    def _degen_signals(self, whale: Dict, market: Dict) -> List[Dict]:
        """Full degen: chase pumps aggressively"""
        signals = []

        for gainer in market.get('top_gainers', [])[:12]:
            symbol = gainer['symbol'].replace('USDT', '/USDT')
            change = float(gainer['priceChangePercent'])

            if change > 7:  # Lower threshold
                signals.append({
                    'action': 'BUY',
                    'symbol': symbol,
                    'whale': whale['name'],
                    'confidence': min(70, 40 + change),
                    'reason': f"DEGEN: Chasing {symbol} +{change:.1f}%"
                })

        return signals

    def _congress_signals(self, whale: Dict, market: Dict) -> List[Dict]:
        """
        Congress member trading style - maps their stock picks to crypto equivalents.
        Pelosi loves tech (NVDA, GOOGL) -> AI tokens, L1s
        Tuberville loves defense -> Infrastructure tokens
        """
        signals = []
        style = whale.get('style', 'congress_tech')

        # Map stock sectors to crypto equivalents
        SECTOR_CRYPTO_MAP = {
            # Tech stocks -> AI & Infrastructure tokens
            'tech': [
                'RENDER/USDT', 'FET/USDT', 'AGIX/USDT', 'OCEAN/USDT', 'TAO/USDT',  # AI tokens
                'SOL/USDT', 'ETH/USDT', 'AVAX/USDT', 'NEAR/USDT', 'INJ/USDT',  # L1s (tech infrastructure)
                'ARB/USDT', 'OP/USDT', 'MATIC/USDT',  # L2s
                'LINK/USDT', 'GRT/USDT',  # Infrastructure
            ],
            # Defense stocks -> Security & Infrastructure tokens
            'defense': [
                'ETH/USDT', 'SOL/USDT', 'DOT/USDT', 'ATOM/USDT',  # Secure L1s
                'LINK/USDT', 'BAND/USDT',  # Oracles (data security)
                'ZEC/USDT', 'XMR/USDT',  # Privacy (if available)
            ],
            # Energy stocks -> DeFi & Staking tokens
            'energy': [
                'LDO/USDT', 'RPL/USDT',  # Staking (energy for blockchain)
                'AAVE/USDT', 'COMP/USDT', 'MKR/USDT',  # DeFi blue chips
                'CRV/USDT', 'CVX/USDT',  # Yield
            ],
        }

        # Determine which sector based on style
        if 'tech' in style:
            target_cryptos = SECTOR_CRYPTO_MAP['tech']
            sector_name = "TECH"
        elif 'defense' in style:
            target_cryptos = SECTOR_CRYPTO_MAP['defense']
            sector_name = "DEFENSE"
        elif 'energy' in style:
            target_cryptos = SECTOR_CRYPTO_MAP['energy']
            sector_name = "ENERGY"
        else:  # composite
            target_cryptos = SECTOR_CRYPTO_MAP['tech'] + SECTOR_CRYPTO_MAP['defense'][:3]
            sector_name = "COMPOSITE"

        # Check market data for these cryptos
        all_tickers = market.get('top_gainers', []) + market.get('top_losers', [])

        for ticker in all_tickers:
            symbol = ticker['symbol'].replace('USDT', '/USDT')
            if symbol not in target_cryptos:
                continue

            change = float(ticker['priceChangePercent'])
            volume = float(ticker.get('quoteVolume', 0))

            # Pelosi style: Buy quality on dips OR momentum plays
            if change < -3 and change > -15:  # Buy the dip on quality
                signals.append({
                    'action': 'BUY',
                    'symbol': symbol,
                    'whale': whale['name'],
                    'confidence': 75,
                    'reason': f"CONGRESS {sector_name}: {symbol} dip buy ({change:.1f}%) - {whale['name']} style"
                })
            elif change > 5 and volume > 10_000_000:  # Momentum with volume
                signals.append({
                    'action': 'BUY',
                    'symbol': symbol,
                    'whale': whale['name'],
                    'confidence': 70,
                    'reason': f"CONGRESS {sector_name}: {symbol} momentum +{change:.1f}% - {whale['name']} style"
                })

        return signals

    def _legend_signals(self, whale: Dict, market: Dict) -> List[Dict]:
        """
        Legendary investor signals - each legend has their unique style.
        Maps their investment philosophy to crypto.
        """
        signals = []
        style = whale.get('style', 'legend_value')
        name = whale.get('name', 'Legend')
        fg = market.get('fear_greed', 50)

        # Blue chip cryptos (Buffett would approve)
        BLUE_CHIPS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']

        # Quality DeFi (established protocols)
        QUALITY_DEFI = ['AAVE/USDT', 'UNI/USDT', 'MKR/USDT', 'LINK/USDT', 'LDO/USDT', 'SNX/USDT']

        # L1/L2 Infrastructure
        INFRASTRUCTURE = ['ETH/USDT', 'SOL/USDT', 'AVAX/USDT', 'DOT/USDT', 'ATOM/USDT', 'NEAR/USDT',
                         'ARB/USDT', 'OP/USDT', 'MATIC/USDT', 'INJ/USDT', 'SUI/USDT', 'APT/USDT', 'SEI/USDT']

        # Innovation/AI tokens (Cathie Wood style)
        INNOVATION = ['RENDER/USDT', 'FET/USDT', 'AGIX/USDT', 'OCEAN/USDT', 'TAO/USDT', 'GRT/USDT',
                     'AR/USDT', 'FIL/USDT', 'RNDR/USDT', 'WLD/USDT']

        # High beta / momentum plays
        HIGH_BETA = ['SOL/USDT', 'AVAX/USDT', 'INJ/USDT', 'SUI/USDT', 'TIA/USDT', 'SEI/USDT',
                    'JUP/USDT', 'PYTH/USDT', 'JTO/USDT', 'BONK/USDT', 'WIF/USDT']

        all_tickers = market.get('top_gainers', []) + market.get('top_losers', [])

        if style == 'legend_value':
            # BUFFETT: Buy quality on fear, extreme patience
            if fg < 30:  # Only buy when others are fearful
                for ticker in all_tickers:
                    symbol = ticker['symbol'].replace('USDT', '/USDT')
                    change = float(ticker['priceChangePercent'])
                    if symbol in BLUE_CHIPS + QUALITY_DEFI and change < -5:
                        signals.append({
                            'action': 'BUY',
                            'symbol': symbol,
                            'whale': name,
                            'confidence': 85,
                            'reason': f"BUFFETT: Quality {symbol} on sale ({change:.1f}%), Fear={fg}"
                        })

        elif style == 'legend_allweather':
            # DALIO: Balanced, buy dips across sectors
            for ticker in all_tickers:
                symbol = ticker['symbol'].replace('USDT', '/USDT')
                change = float(ticker['priceChangePercent'])
                if symbol in BLUE_CHIPS + INFRASTRUCTURE[:5] and -8 < change < -3:
                    signals.append({
                        'action': 'BUY',
                        'symbol': symbol,
                        'whale': name,
                        'confidence': 70,
                        'reason': f"DALIO: Balanced buy {symbol} ({change:.1f}%)"
                    })

        elif style == 'legend_quant':
            # SIMONS: Mean reversion, statistical patterns
            for ticker in all_tickers:
                symbol = ticker['symbol'].replace('USDT', '/USDT')
                change = float(ticker['priceChangePercent'])
                volume = float(ticker.get('quoteVolume', 0))

                # Mean reversion: big drops with volume = buy
                if change < -8 and volume > 20_000_000:
                    signals.append({
                        'action': 'BUY',
                        'symbol': symbol,
                        'whale': name,
                        'confidence': 75,
                        'reason': f"SIMONS: Mean reversion {symbol} ({change:.1f}%), Vol ${volume/1e6:.0f}M"
                    })
                # Momentum breakout
                elif change > 10 and volume > 50_000_000:
                    signals.append({
                        'action': 'BUY',
                        'symbol': symbol,
                        'whale': name,
                        'confidence': 70,
                        'reason': f"SIMONS: Momentum breakout {symbol} +{change:.1f}%"
                    })

        elif style == 'legend_macro':
            # SOROS/DRUCKENMILLER: Big macro trends, reflexivity
            btc_change = market.get('btc_change', 0)
            trend = market.get('market_trend', 'neutral')

            if trend == 'bullish' and btc_change > 3:
                # Risk-on: buy high beta
                for ticker in market.get('top_gainers', [])[:5]:
                    symbol = ticker['symbol'].replace('USDT', '/USDT')
                    change = float(ticker['priceChangePercent'])
                    if symbol in HIGH_BETA and change > 5:
                        signals.append({
                            'action': 'BUY',
                            'symbol': symbol,
                            'whale': name,
                            'confidence': 75,
                            'reason': f"SOROS: Macro bullish, riding {symbol} +{change:.1f}%"
                        })
            elif trend == 'bearish' and fg < 25:
                # Capitulation = opportunity
                for ticker in market.get('top_losers', [])[:3]:
                    symbol = ticker['symbol'].replace('USDT', '/USDT')
                    change = float(ticker['priceChangePercent'])
                    if symbol in BLUE_CHIPS and change < -10:
                        signals.append({
                            'action': 'BUY',
                            'symbol': symbol,
                            'whale': name,
                            'confidence': 80,
                            'reason': f"SOROS: Capitulation buy {symbol} ({change:.1f}%), Fear={fg}"
                        })

        elif style == 'legend_contrarian':
            # BURRY: Extreme contrarian, buy max fear
            if fg < 20:  # Extreme fear only
                for ticker in market.get('top_losers', [])[:5]:
                    symbol = ticker['symbol'].replace('USDT', '/USDT')
                    change = float(ticker['priceChangePercent'])
                    if change < -12:
                        signals.append({
                            'action': 'BUY',
                            'symbol': symbol,
                            'whale': name,
                            'confidence': 80,
                            'reason': f"BURRY: Max fear buy {symbol} ({change:.1f}%), Fear={fg}"
                        })

        elif style == 'legend_innovation':
            # CATHIE WOOD: Disruptive tech, AI, innovation
            for ticker in all_tickers:
                symbol = ticker['symbol'].replace('USDT', '/USDT')
                change = float(ticker['priceChangePercent'])

                if symbol in INNOVATION:
                    if change < -5:  # Buy dips on innovation
                        signals.append({
                            'action': 'BUY',
                            'symbol': symbol,
                            'whale': name,
                            'confidence': 70,
                            'reason': f"CATHIE: Innovation dip {symbol} ({change:.1f}%)"
                        })
                    elif change > 8:  # Add on strength
                        signals.append({
                            'action': 'BUY',
                            'symbol': symbol,
                            'whale': name,
                            'confidence': 65,
                            'reason': f"CATHIE: Innovation momentum {symbol} +{change:.1f}%"
                        })

        elif style == 'legend_trend':
            # PTJ: Trend following, momentum
            for ticker in market.get('top_gainers', [])[:8]:
                symbol = ticker['symbol'].replace('USDT', '/USDT')
                change = float(ticker['priceChangePercent'])
                volume = float(ticker.get('quoteVolume', 0))

                if change > 7 and volume > 30_000_000:
                    signals.append({
                        'action': 'BUY',
                        'symbol': symbol,
                        'whale': name,
                        'confidence': 70,
                        'reason': f"PTJ: Trend follow {symbol} +{change:.1f}%"
                    })

        elif style == 'legend_activist' or style == 'legend_concentrated':
            # ICAHN/ACKMAN: Concentrated, high conviction
            # Buy the biggest movers with conviction
            for ticker in market.get('top_gainers', [])[:3]:
                symbol = ticker['symbol'].replace('USDT', '/USDT')
                change = float(ticker['priceChangePercent'])
                volume = float(ticker.get('quoteVolume', 0))

                if change > 10 and volume > 50_000_000 and symbol in INFRASTRUCTURE:
                    signals.append({
                        'action': 'BUY',
                        'symbol': symbol,
                        'whale': name,
                        'confidence': 80,
                        'reason': f"ACKMAN: High conviction {symbol} +{change:.1f}%"
                    })

        return signals

    def _track_real_wallet(self, whale_id: str, whale: Dict) -> List[Dict]:
        """Track real wallet via blockchain explorers"""
        signals = []
        chain = whale.get('chain', 'ethereum')
        wallet = whale['wallet']

        # For now, return empty - would need API keys for real tracking
        # In production: use Etherscan, BSCScan, Solscan APIs

        return signals


# Whale-based strategies
WHALE_STRATEGIES = {
    "whale_gcr": {
        "name": "Copy GCR (Contrarian)",
        "whales": ["trader_1"],
        "style": "contrarian",
        "take_profit": 50,
        "stop_loss": 20
    },
    "whale_hsaka": {
        "name": "Copy Hsaka (Momentum)",
        "whales": ["trader_2"],
        "style": "momentum",
        "take_profit": 30,
        "stop_loss": 15
    },
    "whale_cobie": {
        "name": "Copy Cobie (Value)",
        "whales": ["trader_3"],
        "style": "value",
        "take_profit": 100,
        "stop_loss": 25
    },
    "whale_ansem": {
        "name": "Copy Ansem (Memecoins)",
        "whales": ["trader_4"],
        "style": "memecoin",
        "take_profit": 100,
        "stop_loss": 30
    },
    "whale_degen": {
        "name": "Copy Degens (YOLO)",
        "whales": ["trader_5"],
        "style": "degen",
        "take_profit": 50,
        "stop_loss": 25
    },
    "whale_smart_money": {
        "name": "Smart Money Composite",
        "whales": ["trader_1", "trader_2", "trader_3"],
        "style": "composite",
        "take_profit": 40,
        "stop_loss": 20
    },
    # Congress Members
    "congress_pelosi": {
        "name": "Copy Pelosi (Tech)",
        "whales": ["congress_pelosi"],
        "style": "congress_tech",
        "take_profit": 50,
        "stop_loss": 20
    },
    "congress_tuberville": {
        "name": "Copy Tuberville (Defense)",
        "whales": ["congress_tuberville"],
        "style": "congress_defense",
        "take_profit": 40,
        "stop_loss": 20
    },
    "congress_crenshaw": {
        "name": "Copy Crenshaw (Energy)",
        "whales": ["congress_crenshaw"],
        "style": "congress_energy",
        "take_profit": 40,
        "stop_loss": 20
    },
    "congress_all": {
        "name": "Congress Composite",
        "whales": ["congress_pelosi", "congress_mccaul", "congress_tuberville"],
        "style": "congress_composite",
        "take_profit": 50,
        "stop_loss": 20
    },

    # ============ LEGENDARY INVESTORS ============
    "legend_buffett": {
        "name": "Copy Buffett (Value)",
        "whales": ["legend_buffett"],
        "style": "legend_value",
        "take_profit": 100,
        "stop_loss": 25
    },
    "legend_dalio": {
        "name": "Copy Dalio (All Weather)",
        "whales": ["legend_dalio"],
        "style": "legend_allweather",
        "take_profit": 40,
        "stop_loss": 15
    },
    "legend_simons": {
        "name": "Copy Simons (Quant)",
        "whales": ["legend_simons"],
        "style": "legend_quant",
        "take_profit": 30,
        "stop_loss": 15
    },
    "legend_soros": {
        "name": "Copy Soros (Macro)",
        "whales": ["legend_soros"],
        "style": "legend_macro",
        "take_profit": 50,
        "stop_loss": 20
    },
    "legend_burry": {
        "name": "Copy Burry (Contrarian)",
        "whales": ["legend_burry"],
        "style": "legend_contrarian",
        "take_profit": 100,
        "stop_loss": 30
    },
    "legend_cathie": {
        "name": "Copy Cathie (Innovation)",
        "whales": ["legend_cathie"],
        "style": "legend_innovation",
        "take_profit": 100,
        "stop_loss": 35
    },
    "legend_ptj": {
        "name": "Copy PTJ (Trend)",
        "whales": ["legend_ptj"],
        "style": "legend_trend",
        "take_profit": 40,
        "stop_loss": 20
    },
    "legend_ackman": {
        "name": "Copy Ackman (Concentrated)",
        "whales": ["legend_ackman"],
        "style": "legend_concentrated",
        "take_profit": 50,
        "stop_loss": 20
    }
}


def get_whale_signals_for_strategy(strategy_id: str) -> List[Dict]:
    """Get whale signals for a specific strategy"""
    strategy = WHALE_STRATEGIES.get(strategy_id)
    if not strategy:
        return []

    tracker = WhaleTracker()
    signals = tracker.get_whale_signals(strategy.get('whales'))

    return signals


# Test
if __name__ == "__main__":
    tracker = WhaleTracker()

    print("Testing whale signals...")
    signals = tracker.get_whale_signals()

    print(f"\nFound {len(signals)} signals:\n")
    for s in signals[:10]:
        print(f"  {s['action']} {s['symbol']} - {s['whale']} ({s['confidence']}%)")
        print(f"    Reason: {s['reason']}")
