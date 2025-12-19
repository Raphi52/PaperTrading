"""
DexScreener Sniper - Detection des nouvelles paires sur toutes les chains
=========================================================================

Detecte les nouveaux tokens via DexScreener API et simule le sniping.
Chains supportees: Solana, BSC, Ethereum, Arbitrum, Base, etc.
"""
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass
import json
import os

@dataclass
class NewToken:
    """Token nouvellement detecte"""
    chain: str
    pair_address: str
    token_address: str
    symbol: str
    name: str
    price_usd: float
    liquidity_usd: float
    volume_24h: float
    pair_created_at: datetime
    age_minutes: float
    price_change_5m: float
    price_change_1h: float
    buys: int
    sells: int
    dex: str
    url: str

class DexScreenerSniper:
    """Sniper multi-chain via DexScreener"""

    BASE_URL = "https://api.dexscreener.com/latest/dex"

    # Chains supportees
    CHAINS = {
        'solana': {'name': 'Solana', 'emoji': '🟣'},
        'bsc': {'name': 'BSC', 'emoji': '🟡'},
        'ethereum': {'name': 'Ethereum', 'emoji': '🔵'},
        'arbitrum': {'name': 'Arbitrum', 'emoji': '🔷'},
        'base': {'name': 'Base', 'emoji': '🔵'},
        'polygon': {'name': 'Polygon', 'emoji': '🟣'},
        'avalanche': {'name': 'Avalanche', 'emoji': '🔴'},
        'optimism': {'name': 'Optimism', 'emoji': '🔴'},
    }

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.seen_pairs = set()  # Pour eviter les doublons
        self.last_scan = {}

        # Filtres par defaut
        self.min_liquidity = self.config.get('min_liquidity', 1000)  # $1k min
        self.max_age_minutes = self.config.get('max_age_minutes', 30)  # Max 30 min
        self.min_volume = self.config.get('min_volume', 100)  # $100 min volume

        # Charger les pairs deja vues
        self._load_seen_pairs()

    def _load_seen_pairs(self):
        """Charge les pairs deja vues depuis le fichier"""
        try:
            if os.path.exists('data/sniper/seen_pairs.json'):
                with open('data/sniper/seen_pairs.json', 'r') as f:
                    self.seen_pairs = set(json.load(f))
        except:
            pass

    def _save_seen_pairs(self):
        """Sauvegarde les pairs vues"""
        try:
            os.makedirs('data/sniper', exist_ok=True)
            # Garder seulement les 10000 dernieres
            pairs_list = list(self.seen_pairs)[-10000:]
            with open('data/sniper/seen_pairs.json', 'w') as f:
                json.dump(pairs_list, f)
        except:
            pass

    def get_new_pairs(self, chain: str = None) -> List[NewToken]:
        """
        Recupere les nouvelles paires depuis DexScreener

        Args:
            chain: Chain specifique ou None pour toutes
        """
        new_tokens = []
        chains = [chain] if chain else list(self.CHAINS.keys())

        for c in chains:
            try:
                tokens = self._fetch_chain_pairs(c)
                new_tokens.extend(tokens)
            except Exception as e:
                print(f"Erreur scan {c}: {e}")

        return new_tokens

    def _fetch_chain_pairs(self, chain: str) -> List[NewToken]:
        """Recupere les paires d'une chain specifique"""
        url = f"{self.BASE_URL}/tokens/{chain}"

        # Utiliser l'endpoint boosted pour les nouveaux tokens
        url = f"https://api.dexscreener.com/token-boosts/latest/v1"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                # Fallback: chercher les paires recentes
                return self._fetch_recent_pairs(chain)

            data = response.json()
            return self._parse_tokens(data, chain)
        except:
            return self._fetch_recent_pairs(chain)

    def _fetch_recent_pairs(self, chain: str) -> List[NewToken]:
        """Recupere les paires recentes d'une chain"""
        # Utiliser la recherche par profil de trading
        url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return []

            data = response.json()
            pairs = data.get('pairs', [])

            return self._filter_new_pairs(pairs, chain)
        except Exception as e:
            return []

    def search_new_tokens(self, query: str = "new") -> List[NewToken]:
        """Recherche de nouveaux tokens via l'API search"""
        url = f"https://api.dexscreener.com/latest/dex/search?q={query}"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return []

            data = response.json()
            pairs = data.get('pairs', [])

            new_tokens = []
            for pair in pairs:
                token = self._parse_pair(pair)
                if token and self._is_valid_snipe(token):
                    new_tokens.append(token)

            return new_tokens[:50]  # Limiter a 50
        except:
            return []

    def get_trending_new(self) -> List[NewToken]:
        """Recupere les tokens trending/nouveaux de toutes les chains"""
        all_tokens = []

        # Methode 1: Token profiles (nouveaux tokens promus)
        try:
            url = "https://api.dexscreener.com/token-profiles/latest/v1"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for item in data[:50]:
                    token = self._parse_profile(item)
                    if token:
                        all_tokens.append(token)
        except:
            pass

        # Methode 2: Boosted tokens
        try:
            url = "https://api.dexscreener.com/token-boosts/latest/v1"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for item in data[:50]:
                    token = self._parse_boost(item)
                    if token:
                        all_tokens.append(token)
        except:
            pass

        # Methode 3: Recherche par chain - TOUTES les chains
        all_chains = ['solana', 'bsc', 'ethereum', 'base', 'arbitrum', 'polygon', 'avalanche', 'optimism']
        for chain in all_chains:
            try:
                url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    pairs = data.get('pairs', [])

                    for pair in pairs[:50]:  # 50 per chain
                        token = self._parse_pair(pair)
                        if token:
                            # Accept ALL tokens for sniper evaluation
                            all_tokens.append(token)
            except:
                pass

        # Methode 4: Search for fresh tokens
        try:
            for query in ['new', 'launch', 'fair']:
                url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    pairs = data.get('pairs', [])
                    for pair in pairs[:30]:
                        token = self._parse_pair(pair)
                        if token:
                            all_tokens.append(token)
        except:
            pass

        # Deduplicate par pair_address
        seen = set()
        unique_tokens = []
        for t in all_tokens:
            if t.pair_address not in seen:
                seen.add(t.pair_address)
                unique_tokens.append(t)

        # Trier par age (plus recent en premier)
        unique_tokens.sort(key=lambda x: x.age_minutes)

        return unique_tokens[:200]  # Return more tokens

    def _parse_pair(self, pair: Dict) -> Optional[NewToken]:
        """Parse une paire DexScreener en NewToken"""
        try:
            chain = pair.get('chainId', 'unknown')
            pair_address = pair.get('pairAddress', '')

            # Skip si deja vu
            if pair_address in self.seen_pairs:
                return None

            # Calculer l'age
            created_at = pair.get('pairCreatedAt')
            if created_at:
                created_dt = datetime.fromtimestamp(created_at / 1000)
                age_minutes = (datetime.now() - created_dt).total_seconds() / 60
            else:
                age_minutes = 999999

            base_token = pair.get('baseToken', {})

            token = NewToken(
                chain=chain,
                pair_address=pair_address,
                token_address=base_token.get('address', ''),
                symbol=base_token.get('symbol', 'UNKNOWN'),
                name=base_token.get('name', 'Unknown Token'),
                price_usd=float(pair.get('priceUsd', 0) or 0),
                liquidity_usd=float(pair.get('liquidity', {}).get('usd', 0) or 0),
                volume_24h=float(pair.get('volume', {}).get('h24', 0) or 0),
                pair_created_at=datetime.fromtimestamp(created_at / 1000) if created_at else datetime.now(),
                age_minutes=age_minutes,
                price_change_5m=float(pair.get('priceChange', {}).get('m5', 0) or 0),
                price_change_1h=float(pair.get('priceChange', {}).get('h1', 0) or 0),
                buys=int(pair.get('txns', {}).get('h24', {}).get('buys', 0) or 0),
                sells=int(pair.get('txns', {}).get('h24', {}).get('sells', 0) or 0),
                dex=pair.get('dexId', 'unknown'),
                url=pair.get('url', f"https://dexscreener.com/{chain}/{pair_address}")
            )

            return token
        except Exception as e:
            return None

    def _parse_profile(self, item: Dict) -> Optional[NewToken]:
        """Parse un token profile"""
        try:
            chain = item.get('chainId', 'unknown')
            token_address = item.get('tokenAddress', '')

            # Recuperer les details de la paire
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                return None

            data = response.json()
            pairs = data.get('pairs', [])
            if not pairs:
                return None

            # Prendre la premiere paire (plus liquide)
            return self._parse_pair(pairs[0])
        except:
            return None

    def _parse_boost(self, item: Dict) -> Optional[NewToken]:
        """Parse un boosted token"""
        return self._parse_profile(item)

    def _filter_new_pairs(self, pairs: List[Dict], chain: str) -> List[NewToken]:
        """Filtre les paires pour ne garder que les nouvelles"""
        new_tokens = []

        for pair in pairs:
            token = self._parse_pair(pair)
            if token and self._is_valid_snipe(token):
                new_tokens.append(token)

        return new_tokens

    def _is_valid_snipe(self, token: NewToken) -> bool:
        """Verifie si un token est valide pour le sniping"""
        # Verifier l'age
        if token.age_minutes > self.max_age_minutes:
            return False

        # Verifier la liquidite
        if token.liquidity_usd < self.min_liquidity:
            return False

        # Verifier le volume
        if token.volume_24h < self.min_volume:
            return False

        # Pas deja vu
        if token.pair_address in self.seen_pairs:
            return False

        return True

    def mark_as_seen(self, token: NewToken):
        """Marque un token comme deja vu"""
        self.seen_pairs.add(token.pair_address)
        self._save_seen_pairs()

    def get_token_price(self, chain: str, token_address: str) -> Optional[float]:
        """Recupere le prix actuel d'un token"""
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                return None

            data = response.json()
            pairs = data.get('pairs', [])
            if not pairs:
                return None

            return float(pairs[0].get('priceUsd', 0) or 0)
        except:
            return None

    def format_token(self, token: NewToken) -> str:
        """Formate un token pour l'affichage"""
        chain_info = self.CHAINS.get(token.chain, {'emoji': '?', 'name': token.chain})

        return (
            f"{chain_info['emoji']} {token.symbol} | "
            f"${token.price_usd:.8f} | "
            f"Liq: ${token.liquidity_usd:,.0f} | "
            f"Age: {token.age_minutes:.0f}m | "
            f"5m: {token.price_change_5m:+.1f}%"
        )


# Test
if __name__ == "__main__":
    sniper = DexScreenerSniper({
        'min_liquidity': 500,
        'max_age_minutes': 60,
        'min_volume': 50
    })

    print("Scanning for new tokens...")
    tokens = sniper.get_trending_new()

    print(f"\nFound {len(tokens)} tokens:\n")
    for t in tokens[:20]:
        print(sniper.format_token(t))
