"""
SQLite Database for Trade History
=================================
Efficient storage and analysis of trades.

Tables:
- trades: All trade history
- portfolio_snapshots: Periodic portfolio value snapshots
"""

import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import json

DB_PATH = "data/trading.db"


def get_connection() -> sqlite3.Connection:
    """Get database connection with row factory"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database tables"""
    conn = get_connection()
    cursor = conn.cursor()

    # Trades table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            portfolio_id TEXT NOT NULL,
            portfolio_name TEXT,
            strategy_id TEXT,
            action TEXT NOT NULL,
            symbol TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            amount_usdt REAL,
            pnl REAL DEFAULT 0,
            pnl_pct REAL DEFAULT 0,
            fee REAL DEFAULT 0,
            slippage REAL DEFAULT 0,
            is_real INTEGER DEFAULT 0,
            reason TEXT,
            token_address TEXT,
            chain TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Portfolio snapshots for historical charts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            portfolio_id TEXT NOT NULL,
            total_value REAL NOT NULL,
            usdt_balance REAL,
            positions_value REAL,
            positions_count INTEGER,
            total_pnl REAL,
            pnl_pct REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create indexes for fast queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_portfolio ON trades(portfolio_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_portfolio ON portfolio_snapshots(portfolio_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON portfolio_snapshots(timestamp)")

    conn.commit()
    conn.close()
    # Silently initialized (avoid colorama issues with Streamlit)


def insert_trade(
    portfolio_id: str,
    portfolio_name: str,
    strategy_id: str,
    action: str,
    symbol: str,
    price: float,
    quantity: float,
    amount_usdt: float = 0,
    pnl: float = 0,
    pnl_pct: float = 0,
    fee: float = 0,
    slippage: float = 0,
    is_real: bool = False,
    reason: str = "",
    token_address: str = "",
    chain: str = "",
    timestamp: str = None
):
    """Insert a trade into the database"""
    if timestamp is None:
        timestamp = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO trades (
            timestamp, portfolio_id, portfolio_name, strategy_id,
            action, symbol, price, quantity, amount_usdt,
            pnl, pnl_pct, fee, slippage, is_real, reason,
            token_address, chain
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp, portfolio_id, portfolio_name, strategy_id,
        action, symbol, price, quantity, amount_usdt,
        pnl, pnl_pct, fee, slippage, 1 if is_real else 0, reason,
        token_address, chain
    ))

    conn.commit()
    conn.close()


def insert_trade_from_dict(portfolio_id: str, portfolio_name: str, strategy_id: str, trade: Dict):
    """Insert trade from dictionary - handles field name variations"""
    # Handle field name variations
    fee = trade.get('fee', 0) or trade.get('fees', 0) or 0
    slippage = trade.get('slippage', 0) or trade.get('slippage_pct', 0) or 0

    insert_trade(
        portfolio_id=portfolio_id,
        portfolio_name=portfolio_name,
        strategy_id=strategy_id,
        action=trade.get('action', ''),
        symbol=trade.get('symbol', ''),
        price=trade.get('price', 0),
        quantity=trade.get('quantity', 0),
        amount_usdt=trade.get('amount_usdt', 0),
        pnl=trade.get('pnl', 0),
        pnl_pct=trade.get('pnl_pct', 0),
        fee=fee,
        slippage=slippage,
        is_real=trade.get('is_real', False),
        reason=trade.get('reason', ''),
        token_address=trade.get('token_address', trade.get('address', '')),
        chain=trade.get('chain', ''),
        timestamp=trade.get('timestamp')
    )


def insert_snapshot(
    portfolio_id: str,
    total_value: float,
    usdt_balance: float = 0,
    positions_value: float = 0,
    positions_count: int = 0,
    total_pnl: float = 0,
    pnl_pct: float = 0
):
    """Insert portfolio snapshot"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO portfolio_snapshots (
            timestamp, portfolio_id, total_value, usdt_balance,
            positions_value, positions_count, total_pnl, pnl_pct
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(), portfolio_id, total_value,
        usdt_balance, positions_value, positions_count, total_pnl, pnl_pct
    ))

    conn.commit()
    conn.close()


# ============ ANALYSIS FUNCTIONS ============

def get_trades_count() -> int:
    """Get total number of trades"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM trades")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_portfolio_trades(portfolio_id: str, limit: int = 100) -> List[Dict]:
    """Get trades for a specific portfolio"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM trades
        WHERE portfolio_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (portfolio_id, limit))

    trades = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return trades


def get_recent_trades(limit: int = 100) -> List[Dict]:
    """Get most recent trades across all portfolios"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM trades
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))

    trades = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return trades


def get_strategy_performance() -> List[Dict]:
    """Get performance stats by strategy"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            strategy_id,
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
            ROUND(SUM(CASE WHEN pnl > 0 THEN 1.0 ELSE 0 END) * 100.0 / COUNT(*), 2) as win_rate,
            ROUND(SUM(pnl), 2) as total_pnl,
            ROUND(AVG(pnl), 2) as avg_pnl,
            ROUND(SUM(fee), 2) as total_fees
        FROM trades
        WHERE action = 'SELL'
        GROUP BY strategy_id
        ORDER BY total_pnl DESC
    """)

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_portfolio_performance() -> List[Dict]:
    """Get performance stats by portfolio"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            portfolio_id,
            portfolio_name,
            strategy_id,
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
            ROUND(SUM(CASE WHEN pnl > 0 THEN 1.0 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) as win_rate,
            ROUND(SUM(pnl), 2) as total_pnl,
            ROUND(AVG(pnl), 2) as avg_pnl
        FROM trades
        WHERE action = 'SELL'
        GROUP BY portfolio_id
        ORDER BY total_pnl DESC
    """)

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_symbol_performance() -> List[Dict]:
    """Get performance stats by trading pair"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            symbol,
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
            ROUND(SUM(CASE WHEN pnl > 0 THEN 1.0 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0), 2) as win_rate,
            ROUND(SUM(pnl), 2) as total_pnl,
            ROUND(AVG(pnl), 2) as avg_pnl
        FROM trades
        WHERE action = 'SELL'
        GROUP BY symbol
        ORDER BY total_pnl DESC
    """)

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_daily_pnl(days: int = 30) -> List[Dict]:
    """Get daily PnL for the last N days"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            DATE(timestamp) as date,
            COUNT(*) as trades,
            ROUND(SUM(pnl), 2) as daily_pnl,
            ROUND(SUM(fee), 2) as daily_fees
        FROM trades
        WHERE action = 'SELL'
        AND timestamp >= datetime('now', ?)
        GROUP BY DATE(timestamp)
        ORDER BY date DESC
    """, (f'-{days} days',))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_hourly_activity(hours: int = 24) -> List[Dict]:
    """Get trading activity by hour"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            strftime('%H', timestamp) as hour,
            COUNT(*) as trades,
            ROUND(SUM(pnl), 2) as pnl
        FROM trades
        WHERE timestamp >= datetime('now', ?)
        GROUP BY strftime('%H', timestamp)
        ORDER BY hour
    """, (f'-{hours} hours',))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_global_stats() -> Dict:
    """Get global trading statistics"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN action = 'BUY' THEN 1 ELSE 0 END) as total_buys,
            SUM(CASE WHEN action = 'SELL' THEN 1 ELSE 0 END) as total_sells,
            ROUND(SUM(CASE WHEN action = 'SELL' AND pnl > 0 THEN 1.0 ELSE 0 END) * 100.0 /
                  NULLIF(SUM(CASE WHEN action = 'SELL' THEN 1 ELSE 0 END), 0), 2) as win_rate,
            ROUND(SUM(CASE WHEN action = 'SELL' THEN pnl ELSE 0 END), 2) as total_pnl,
            ROUND(AVG(CASE WHEN action = 'SELL' THEN pnl END), 2) as avg_pnl,
            ROUND(SUM(fee), 2) as total_fees,
            MIN(timestamp) as first_trade,
            MAX(timestamp) as last_trade,
            COUNT(DISTINCT portfolio_id) as active_portfolios,
            COUNT(DISTINCT symbol) as symbols_traded
        FROM trades
    """)

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else {}


def export_to_csv(filepath: str = "data/trades_export.csv"):
    """Export all trades to CSV"""
    import csv

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY timestamp")

    rows = cursor.fetchall()
    if rows:
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in cursor.description])
            writer.writerows(rows)

    conn.close()
    return len(rows)


# Initialize on import
init_database()
