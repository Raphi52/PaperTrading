"""
Wallet Tracker - Suivi et Copy Trading des Whales
==================================================

Permet de:
- Suivre des wallets specifiques (whales, smart money)
- Detecter leurs transactions en temps reel
- Copier automatiquement leurs trades

Chains supportees:
- Ethereum (via Etherscan API)
- Solana (via Helius/Solscan API)
- BSC (via BSCScan API)

Usage:
    python -c "from core.wallet_tracker import WalletTracker; WalletTracker().run()"
"""
import os
import time
import json
import asyncio
import aiohttp
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from dotenv import load_dotenv

load_dotenv()


class Chain(Enum):
    """Chains supportees"""
    ETHEREUM = "ethereum"
    SOLANA = "solana"
    BSC = "bsc"
    BASE = "base"
    ARBITRUM = "arbitrum"


class TransactionType(Enum):
    """Types de transactions"""
    BUY = "buy"
    SELL = "sell"
    TRANSFER = "transfer"
    SWAP = "swap"
    UNKNOWN = "unknown"


@dataclass
class WalletConfig:
    """Configuration d'un wallet a suivre"""
    address: str
    chain: Chain
    name: str = ""  # Nom optionnel (ex: "Whale #1")
    copy_trades: bool = True
    copy_percentage: float = 100.0  # % du trade a copier
    min_trade_size_usd: float = 1000.0  # Ignorer les petits trades
    max_trade_size_usd: float = 100000.0  # Limiter les gros trades
    tokens_whitelist: List[str] = field(default_factory=list)  # Tokens a copier
    tokens_blacklist: List[str] = field(default_factory=list)  # Tokens a ignorer
    enabled: bool = True


@dataclass
class WalletTransaction:
    """Transaction detectee"""
    wallet_address: str
    wallet_name: str
    chain: Chain
    tx_hash: str
    tx_type: TransactionType
    token_address: str
    token_symbol: str
    amount: float
    amount_usd: float
    price: float
    timestamp: datetime
    block_number: int = 0

    def to_dict(self) -> Dict:
        return {
            "wallet": self.wallet_address[:8] + "..." + self.wallet_address[-6:],
            "wallet_name": self.wallet_name,
            "chain": self.chain.value,
            "type": self.tx_type.value,
            "token": self.token_symbol,
            "amount": self.amount,
            "amount_usd": self.amount_usd,
            "price": self.price,
            "time": self.timestamp.isoformat(),
            "tx": self.tx_hash[:16] + "..."
        }


class WalletTracker:
    """Tracker de wallets multi-chain"""

    def __init__(self):
        # API Keys
        self.etherscan_key = os.getenv("ETHERSCAN_API_KEY", "")
        self.bscscan_key = os.getenv("BSCSCAN_API_KEY", "")
        self.solana_key = os.getenv("HELIUS_API_KEY", os.getenv("SOLSCAN_API_KEY", ""))
        self.basescan_key = os.getenv("BASESCAN_API_KEY", "")

        # Wallets a suivre
        self.wallets: Dict[str, WalletConfig] = {}

        # Transactions vues (pour eviter les doublons)
        self.seen_txs: Set[str] = set()

        # Historique des transactions
        self.transactions: List[WalletTransaction] = []

        # Callbacks
        self.on_transaction_callbacks = []

        # State
        self.running = False
        self.last_check: Dict[str, datetime] = {}

        # Load config
        self._load_config()

    def _load_config(self):
        """Charge la configuration des wallets"""
        config_file = "data/wallets.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    for w in data.get('wallets', []):
                        self.add_wallet(WalletConfig(
                            address=w['address'],
                            chain=Chain(w.get('chain', 'ethereum')),
                            name=w.get('name', ''),
                            copy_trades=w.get('copy_trades', False),
                            copy_percentage=w.get('copy_percentage', 100),
                            min_trade_size_usd=w.get('min_trade_size_usd', 1000),
                            enabled=w.get('enabled', True)
                        ))
            except Exception as e:
                print(f"Error loading wallet config: {e}")

    def _save_config(self):
        """Sauvegarde la configuration"""
        os.makedirs("data", exist_ok=True)
        data = {
            'wallets': [
                {
                    'address': w.address,
                    'chain': w.chain.value,
                    'name': w.name,
                    'copy_trades': w.copy_trades,
                    'copy_percentage': w.copy_percentage,
                    'min_trade_size_usd': w.min_trade_size_usd,
                    'enabled': w.enabled
                }
                for w in self.wallets.values()
            ]
        }
        with open("data/wallets.json", 'w') as f:
            json.dump(data, f, indent=2)

    def add_wallet(self, config: WalletConfig):
        """Ajoute un wallet a suivre"""
        self.wallets[config.address.lower()] = config
        print(f"Added wallet: {config.name or config.address[:8]}... ({config.chain.value})")

    def remove_wallet(self, address: str):
        """Supprime un wallet"""
        address = address.lower()
        if address in self.wallets:
            del self.wallets[address]
            self._save_config()

    def on_transaction(self, callback):
        """Ajoute un callback pour les nouvelles transactions"""
        self.on_transaction_callbacks.append(callback)

    async def _notify_transaction(self, tx: WalletTransaction):
        """Notifie les callbacks d'une nouvelle transaction"""
        for callback in self.on_transaction_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(tx)
                else:
                    callback(tx)
            except Exception as e:
                print(f"Callback error: {e}")

    # ==================== ETHEREUM / EVM CHAINS ====================

    async def _fetch_eth_transactions(self, wallet: WalletConfig) -> List[WalletTransaction]:
        """Recupere les transactions Ethereum/EVM"""
        transactions = []

        # Determine API endpoint
        api_urls = {
            Chain.ETHEREUM: f"https://api.etherscan.io/api",
            Chain.BSC: f"https://api.bscscan.com/api",
            Chain.BASE: f"https://api.basescan.org/api",
            Chain.ARBITRUM: f"https://api.arbiscan.io/api",
        }

        api_keys = {
            Chain.ETHEREUM: self.etherscan_key,
            Chain.BSC: self.bscscan_key,
            Chain.BASE: self.basescan_key,
            Chain.ARBITRUM: self.etherscan_key,
        }

        base_url = api_urls.get(wallet.chain)
        api_key = api_keys.get(wallet.chain)

        if not base_url or not api_key:
            return []

        try:
            # Fetch token transfers
            params = {
                "module": "account",
                "action": "tokentx",
                "address": wallet.address,
                "page": 1,
                "offset": 50,
                "sort": "desc",
                "apikey": api_key
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(base_url, params=params) as response:
                    data = await response.json()

                    if data.get("status") != "1":
                        return []

                    for tx in data.get("result", []):
                        tx_hash = tx.get("hash", "")

                        # Skip if already seen
                        if tx_hash in self.seen_txs:
                            continue

                        self.seen_txs.add(tx_hash)

                        # Determine transaction type
                        from_addr = tx.get("from", "").lower()
                        to_addr = tx.get("to", "").lower()
                        wallet_addr = wallet.address.lower()

                        if to_addr == wallet_addr:
                            tx_type = TransactionType.BUY
                        elif from_addr == wallet_addr:
                            tx_type = TransactionType.SELL
                        else:
                            tx_type = TransactionType.TRANSFER

                        # Parse amount
                        value = int(tx.get("value", 0))
                        decimals = int(tx.get("tokenDecimal", 18))
                        amount = value / (10 ** decimals)

                        # Create transaction object
                        wallet_tx = WalletTransaction(
                            wallet_address=wallet.address,
                            wallet_name=wallet.name,
                            chain=wallet.chain,
                            tx_hash=tx_hash,
                            tx_type=tx_type,
                            token_address=tx.get("contractAddress", ""),
                            token_symbol=tx.get("tokenSymbol", "UNKNOWN"),
                            amount=amount,
                            amount_usd=0,  # Would need price API
                            price=0,
                            timestamp=datetime.fromtimestamp(int(tx.get("timeStamp", 0))),
                            block_number=int(tx.get("blockNumber", 0))
                        )

                        transactions.append(wallet_tx)

        except Exception as e:
            print(f"Error fetching ETH transactions: {e}")

        return transactions

    # ==================== SOLANA ====================

    async def _fetch_solana_transactions(self, wallet: WalletConfig) -> List[WalletTransaction]:
        """Recupere les transactions Solana via Helius"""
        transactions = []

        if not self.solana_key:
            return []

        try:
            url = f"https://api.helius.xyz/v0/addresses/{wallet.address}/transactions"
            params = {
                "api-key": self.solana_key,
                "limit": 50
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        return []

                    data = await response.json()

                    for tx in data:
                        tx_hash = tx.get("signature", "")

                        if tx_hash in self.seen_txs:
                            continue

                        self.seen_txs.add(tx_hash)

                        # Parse token transfers
                        token_transfers = tx.get("tokenTransfers", [])
                        for transfer in token_transfers:
                            from_addr = transfer.get("fromUserAccount", "")
                            to_addr = transfer.get("toUserAccount", "")

                            if to_addr == wallet.address:
                                tx_type = TransactionType.BUY
                            elif from_addr == wallet.address:
                                tx_type = TransactionType.SELL
                            else:
                                continue

                            wallet_tx = WalletTransaction(
                                wallet_address=wallet.address,
                                wallet_name=wallet.name,
                                chain=Chain.SOLANA,
                                tx_hash=tx_hash,
                                tx_type=tx_type,
                                token_address=transfer.get("mint", ""),
                                token_symbol=transfer.get("tokenSymbol", "UNKNOWN"),
                                amount=float(transfer.get("tokenAmount", 0)),
                                amount_usd=0,
                                price=0,
                                timestamp=datetime.fromtimestamp(tx.get("timestamp", 0)),
                                block_number=tx.get("slot", 0)
                            )

                            transactions.append(wallet_tx)

        except Exception as e:
            print(f"Error fetching Solana transactions: {e}")

        return transactions

    # ==================== MAIN LOOP ====================

    async def check_wallet(self, wallet: WalletConfig) -> List[WalletTransaction]:
        """Verifie les transactions d'un wallet"""
        if not wallet.enabled:
            return []

        if wallet.chain == Chain.SOLANA:
            return await self._fetch_solana_transactions(wallet)
        else:
            return await self._fetch_eth_transactions(wallet)

    async def check_all_wallets(self) -> List[WalletTransaction]:
        """Verifie tous les wallets"""
        all_transactions = []

        for wallet in self.wallets.values():
            try:
                txs = await self.check_wallet(wallet)
                all_transactions.extend(txs)

                # Notify callbacks
                for tx in txs:
                    await self._notify_transaction(tx)

            except Exception as e:
                print(f"Error checking wallet {wallet.address[:8]}: {e}")

            # Rate limiting
            await asyncio.sleep(0.5)

        # Add to history
        self.transactions.extend(all_transactions)

        # Keep only last 1000 transactions
        if len(self.transactions) > 1000:
            self.transactions = self.transactions[-1000:]

        return all_transactions

    async def run(self, interval: int = 30):
        """Lance le tracker en boucle"""
        self.running = True
        print(f"Wallet Tracker started - monitoring {len(self.wallets)} wallets")

        while self.running:
            try:
                transactions = await self.check_all_wallets()

                if transactions:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] "
                          f"Found {len(transactions)} new transactions")

                    for tx in transactions:
                        emoji = "🟢" if tx.tx_type == TransactionType.BUY else "🔴"
                        print(f"  {emoji} {tx.wallet_name or tx.wallet_address[:8]}: "
                              f"{tx.tx_type.value.upper()} {tx.amount:.4f} {tx.token_symbol}")

            except Exception as e:
                print(f"Error in tracker loop: {e}")

            await asyncio.sleep(interval)

    def stop(self):
        """Arrete le tracker"""
        self.running = False

    # ==================== COPY TRADING ====================

    def get_copy_trade_params(self, tx: WalletTransaction,
                              available_capital: float) -> Optional[Dict]:
        """
        Calcule les parametres pour copier un trade

        Returns:
            Dict avec {symbol, amount_usdt, action} ou None si pas de copie
        """
        wallet = self.wallets.get(tx.wallet_address.lower())
        if not wallet or not wallet.copy_trades:
            return None

        # Check transaction type
        if tx.tx_type not in [TransactionType.BUY, TransactionType.SELL]:
            return None

        # Check trade size
        if tx.amount_usd < wallet.min_trade_size_usd:
            return None

        # Check blacklist
        if tx.token_symbol in wallet.tokens_blacklist:
            return None

        # Check whitelist (if defined)
        if wallet.tokens_whitelist and tx.token_symbol not in wallet.tokens_whitelist:
            return None

        # Calculate copy size
        copy_amount_usd = tx.amount_usd * (wallet.copy_percentage / 100)
        copy_amount_usd = min(copy_amount_usd, wallet.max_trade_size_usd)
        copy_amount_usd = min(copy_amount_usd, available_capital * 0.2)  # Max 20% of capital

        return {
            "symbol": tx.token_symbol,
            "action": "BUY" if tx.tx_type == TransactionType.BUY else "SELL",
            "amount_usdt": copy_amount_usd,
            "original_wallet": tx.wallet_name or tx.wallet_address[:8],
            "original_amount_usd": tx.amount_usd
        }

    # ==================== STATS ====================

    def get_stats(self) -> Dict:
        """Retourne les statistiques"""
        buys = [tx for tx in self.transactions if tx.tx_type == TransactionType.BUY]
        sells = [tx for tx in self.transactions if tx.tx_type == TransactionType.SELL]

        return {
            "wallets_tracked": len(self.wallets),
            "total_transactions": len(self.transactions),
            "buys": len(buys),
            "sells": len(sells),
            "last_update": max([tx.timestamp for tx in self.transactions], default=None)
        }


# ==================== FAMOUS WALLETS ====================

FAMOUS_WALLETS = {
    # Ethereum whales (examples - replace with real addresses)
    "vitalik.eth": WalletConfig(
        address="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        chain=Chain.ETHEREUM,
        name="Vitalik",
        copy_trades=False  # Just watch
    ),

    # Solana whales (examples)
    "sol_whale_1": WalletConfig(
        address="",  # Add real address
        chain=Chain.SOLANA,
        name="SOL Whale #1",
        copy_trades=True,
        copy_percentage=10
    ),
}


def add_famous_wallets(tracker: WalletTracker):
    """Ajoute des wallets celebres au tracker"""
    for name, config in FAMOUS_WALLETS.items():
        if config.address:
            tracker.add_wallet(config)


# ==================== CLI ====================

def run_cli():
    """Lance le tracker en mode CLI"""
    import argparse

    parser = argparse.ArgumentParser(description="Wallet Tracker")
    parser.add_argument("--add", type=str, help="Add wallet address")
    parser.add_argument("--chain", type=str, default="ethereum",
                        choices=["ethereum", "solana", "bsc", "base"])
    parser.add_argument("--name", type=str, default="", help="Wallet name")
    parser.add_argument("--copy", action="store_true", help="Enable copy trading")
    parser.add_argument("--interval", type=int, default=30, help="Check interval (seconds)")

    args = parser.parse_args()

    tracker = WalletTracker()

    if args.add:
        tracker.add_wallet(WalletConfig(
            address=args.add,
            chain=Chain(args.chain),
            name=args.name,
            copy_trades=args.copy
        ))
        tracker._save_config()
        print(f"Added wallet: {args.add}")
        return

    # Run tracker
    asyncio.run(tracker.run(interval=args.interval))


if __name__ == "__main__":
    run_cli()
