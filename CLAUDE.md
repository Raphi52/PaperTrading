# CLAUDE.md - Paper Trading Bot

## Project Overview

This is a **multi-strategy cryptocurrency paper trading bot** with a modern Next.js dashboard. It simulates trading across **200+ portfolios**, each running a different trading strategy. The bot can also execute real trades on Binance and DEXs (Solana, Ethereum, BSC).

**Primary Language:** Python 3.11+ (backend), TypeScript/Next.js 14 (frontend)
**Database:** SQLite for trade history (unlimited storage), JSON for dashboard state
**Architecture:** Python trading engine + Next.js REST API frontend

## Quick Start Commands

```bash
# Run the trading bot (background engine)
python bot.py

# Run the Next.js dashboard (in frontend/ directory)
cd frontend && npm run dev

# Or build and run production
cd frontend && npm run build && npm start
```

## Architecture

```
PaperTrading/
├── bot.py                  # Main trading engine (runs independently)
├── core/                   # Core modules
│   ├── database.py         # SQLite trade storage & analytics
│   ├── exchange.py         # CCXT Binance connection
│   ├── confluence.py       # Multi-signal confluence engine
│   ├── real_executor.py    # Real trade execution (Binance + DEX)
│   ├── risk_guard.py       # Risk limits and daily loss protection
│   ├── risk_manager.py     # Advanced risk management
│   ├── security.py         # Key encryption (AES-256)
│   ├── alpha_signals.py    # Alpha signal generation
│   ├── real_data.py        # Real market data fetching
│   ├── jupiter.py          # Solana DEX (Jupiter)
│   ├── uniswap.py          # Ethereum DEX (Uniswap V3)
│   └── pancakeswap.py      # BSC DEX (PancakeSwap)
├── signals/                # Trading signal generators
│   ├── technical.py        # RSI, MACD, Bollinger, EMA
│   ├── sentiment.py        # Fear & Greed, social sentiment
│   ├── onchain.py          # Whale movements, exchange flows
│   ├── degen.py            # Degen momentum signals
│   └── godmode.py          # Multi-confluence "god mode"
├── sniper/                 # Token sniping modules
│   ├── dex_sniper.py       # New token detection
│   ├── dexscreener.py      # DexScreener API
│   ├── token_sniper.py     # Token analysis
│   └── whale_tracker.py    # Whale wallet tracking
├── frontend/               # Next.js 14 Dashboard
│   ├── src/app/
│   │   ├── page.tsx        # Main dashboard (portfolios overview)
│   │   ├── trades/page.tsx # Trade history with filters
│   │   ├── settings/       # Settings management
│   │   └── api/            # REST API endpoints
│   └── package.json
├── config/                 # Configuration
│   ├── settings.py         # Global settings
│   └── degen_config.py     # Degen strategy config
└── data/                   # Runtime data
    ├── portfolios.json     # Portfolio state (limited to 500 trades/portfolio)
    ├── trading.db          # SQLite database (unlimited trades)
    ├── settings.json       # User settings
    └── bot_log.txt         # Trading log
```

## Key Files

### bot.py (Trading Engine)
- **STRATEGIES dict** (~line 1200): Defines 150+ trading strategies with TP/SL
- **should_trade()** (~line 2800): Core decision logic for all strategies
- **execute_trade()** (~line 2600): Paper/real trade execution with fee simulation
- **run_engine()** (~line 4200): Main loop - scans every 60 seconds
- **analyze_crypto()** (~line 2400): Fetches price data and calculates indicators

### core/database.py (SQLite Storage)
- **init_database()**: Creates trades and portfolio_snapshots tables
- **insert_trade()**: Records every trade with full details
- **get_strategy_performance()**: Analytics by strategy
- **get_daily_pnl()**: Daily P&L breakdown
- **get_global_stats()**: Global win rate, total P&L, etc.

### frontend/src/app/page.tsx (Dashboard)
- Portfolio cards with real-time P&L
- Total balance calculation
- Active positions display
- Quick actions (pause/resume)

### frontend/src/app/trades/page.tsx (Trade History)
- Filterable trade list from SQLite
- Date range filters
- Strategy/portfolio filters
- Trade detail modal with legitimacy analysis

### data/portfolios.json
Structure:
```json
{
  "portfolios": {
    "portfolio_id": {
      "id": "portfolio_id",
      "name": "Strategy Name",
      "strategy_id": "rsi_strategy",
      "config": {
        "cryptos": ["BTC/USDT", "ETH/USDT"],
        "allocation_percent": 5,
        "max_positions": 20,
        "auto_trade": true
      },
      "balance": {"USDT": 10000.0},
      "positions": {},
      "trades": [],  // Limited to last 500
      "initial_capital": 10000,
      "active": true
    }
  }
}
```

## Trading Strategies (150+)

The bot supports 150+ strategies grouped into categories:

| Category | Count | Examples |
|----------|-------|----------|
| RSI-based | 30 | rsi_strategy, rsi_divergence, rsi_momentum |
| Degen/Momentum | 13 | degen_scalp, degen_hybrid, degen_momentum |
| Whale Copy | 11 | whale_gcr, whale_hsaka, whale_cobie |
| Ichimoku | 10 | ichimoku, ichimoku_fast, ichimoku_cloud |
| Scalping | 10 | scalp_rsi, scalp_bb, scalp_ema |
| Legendary Investors | 8 | legend_buffett, legend_soros, legend_dalio |
| EMA Crossover | 8 | ema_crossover, ema_crossover_slow, ema_signal |
| Sniper | 7 | sniper_safe, sniper_degen, sniper_volume |
| Grid Trading | 7 | grid_trading, grid_tight, grid_adaptive |
| Congress Copy | 4 | congress_pelosi, congress_all |
| Reinforcement | 3 | reinforce_safe, reinforce_moderate, reinforce_aggressive |
| Martingale | 1 | martingale (no SL, unlimited levels) |
| Other | 50+ | vwap, supertrend, breakout, mean_reversion, etc. |

### Strategy Flags (used in should_trade())
- `use_rsi` - RSI oversold/overbought
- `use_ema_cross` - EMA 9/21 or 12/26 crossover
- `use_degen` - Momentum/scalping modes
- `use_sniper` - New token hunting
- `use_whale` - Copy trader signals
- `use_ichimoku` - Ichimoku cloud system
- `use_grid` - Range trading
- `use_mean_rev` - Mean reversion
- `use_breakout` - Consolidation breaks
- `use_fear_greed` - Fear & Greed contrarian
- `use_martingale` - Double down on losses (no SL)
- `use_reinforce` - Averaging down system
- `use_stoch_rsi` - Stochastic RSI momentum

## Smart Trading Filters

### Entry filters (applied before any buy):
1. **Loss cooldown** - Pause 2h after 3 consecutive losses
2. **Token safety** - Block risky memecoins for non-degen strategies
3. **Pump chase prevention** - Don't buy if >5% in 1h or >15% in 24h
4. **Trend alignment** - Require EMA stack (Price > EMA9 > EMA21)
5. **RSI quality** - Skip overbought entries
6. **Volume confirmation** - Require adequate volume
7. **Correlation limit** - Max 2 positions in similar assets
8. **Entry quality score** - Skip low-score entries (<40/100)

### Exit mechanisms:
- **Take Profit (TP)** - Configurable per strategy
- **Stop Loss (SL)** - Configurable per strategy (0 = disabled)
- **Trailing Stop** - Locks in profits (5% trail from high)
- **Partial TP** - Sell 50% at first target
- **Time-based exit** - max_hold_hours for degen strategies
- **EMA DOWN** - Smart exit (only if in profit OR RSI<45 AND bearish)

## Fee Simulation

All trades simulate realistic transaction costs:
- **CEX (Binance):** 0.1% per trade (buy + sell = 0.2% total)
- **DEX trades:** 0.3% swap fee + estimated gas
- **Slippage:** 0.05% - 0.5% based on volume

Martingale and reinforcement strategies pay fees on every buy, making them realistic.

## Special Strategies

### Martingale (`use_martingale`)
- No stop loss (SL = 0)
- Unlimited levels (max_levels = 999)
- Doubles position size on each loss
- Goal: Recover all losses on eventual win

### Position Reinforcement (`use_reinforce`)
- Averages down when position drops below threshold
- `reinforce_threshold`: -3% to -5% (when to buy more)
- `reinforce_levels`: 2-4 (max reinforcements)
- `reinforce_mult`: 1.0-2.0 (size multiplier each level)
- Recalculates average entry price

## API Integrations

| Service | Purpose | Config Location |
|---------|---------|-----------------|
| Binance | Price data, real trading | data/settings.json |
| CoinGecko | Price fallback | None (public) |
| DexScreener | DEX token prices | None (public) |
| Helius | Solana RPC | data/settings.json |
| Etherscan | ETH gas prices | data/settings.json |
| Alternative.me | Fear & Greed Index | None (public) |

## Database Schema (SQLite)

### trades table
```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    portfolio_id TEXT,
    portfolio_name TEXT,
    strategy_id TEXT,
    action TEXT,  -- BUY, SELL, REINFORCE
    symbol TEXT,
    price REAL,
    quantity REAL,
    amount_usdt REAL,
    pnl REAL,
    pnl_pct REAL,
    fee REAL,
    slippage REAL,
    is_real INTEGER,
    reason TEXT,  -- Exit reason (TP HIT, SL HIT, EMA DOWN, etc.)
    token_address TEXT,
    chain TEXT
);
```

### Key indexes for performance
- `idx_trades_portfolio` - Fast portfolio queries
- `idx_trades_timestamp` - Date range filters
- `idx_trades_strategy` - Strategy analytics
- `idx_trades_symbol` - Symbol performance

## File Locking

Both `bot.py` and the frontend access `portfolios.json`. File locking prevents corruption:
- Lock file: `data/portfolios.lock`
- Functions: `acquire_lock()`, `release_lock()`
- Atomic writes: Write to temp file, then rename

## Real Trading Mode

**DISABLED BY DEFAULT** - Requires explicit activation:

1. Set `real_trading.enabled: true` in settings.json
2. Configure wallet keys (encrypted with master password)
3. Set risk limits per portfolio:
   - `trading_mode`: "paper" or "real"
   - `max_daily_loss_usd`: Daily loss limit
   - `max_trade_size_usd`: Max position size

Security layers:
- AES-256 key encryption
- Master password (bcrypt hash)
- Daily loss limits with auto-lock
- Emergency stop button

## Development Guidelines

### Code Style
- Functions use snake_case
- Constants use UPPER_SNAKE_CASE
- Type hints for function parameters
- Docstrings for public functions

### Adding a New Strategy
1. Add to `STRATEGIES` dict in bot.py:
```python
"my_strategy": {
    "auto": True,
    "use_rsi": True,  # or other flag
    "take_profit": 20,
    "stop_loss": 10,
    "tooltip": "Description here"
}
```

2. If new flag needed, add logic to `should_trade()`:
```python
if strategy.get('use_my_flag'):
    if buy_condition and has_cash:
        return ('BUY', "Buy reason")
    elif sell_condition and has_position:
        return ('SELL', "Sell reason")
    return (None, "Waiting...")
```

3. Add timeframe to `STRATEGY_TIMEFRAMES` if not 1h default

### Testing Changes
```bash
# Run bot with visible output
python bot.py

# Query trades from SQLite
python -c "
from core.database import get_recent_trades, get_strategy_performance
print(get_strategy_performance())
"

# Check specific portfolio
python -c "
import json
with open('data/portfolios.json') as f:
    data = json.load(f)
print(data['portfolios']['portfolio_3'])
"
```

## Common Issues

### Portfolio not trading
- Check `active: true` in portfolio
- Check `auto_trade: true` in config
- Check strategy has `auto: True` in STRATEGIES
- Check `cryptos` list is not empty

### Encoding errors (Windows)
Fixed at top of bot.py:
```python
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
```

### File lock stuck
Delete `data/portfolios.lock` if bot crashed

### Missing prices
- Binance API rate limited - uses cached prices
- DEX tokens need DexScreener lookup

## Performance Notes

- Bot scans every 60 seconds (`SCAN_INTERVAL`)
- 200+ portfolios × N cryptos per portfolio = many API calls
- Uses caching to reduce API load
- JSON limited to 500 trades/portfolio (SQLite unlimited)
- Dashboard refreshes on demand via REST API

## Recent Optimizations (Dec 2024)

### Exit Logic Improvements
- **EMA DOWN**: Only sells if in profit OR (RSI<45 AND mom_4h<-1) OR bearish_score>=40
- **Degen exit**: Changed from (RSI>65 OR mom<-0.3) to (RSI>75 AND mom<-1)
- **TIME EXIT**: Extended degen_scalp from 2h to 6h max hold

### Stop Loss Adjustments
- **Trailing strategies**: Widened SL from 1.5-3% to 3-6%
- **Grid strategies**: Widened SL from 2% to 4%
- **Social sentiment**: Widened SL from 9% to 12%

### Threshold Adjustments
- **stoch_rsi_aggressive**: Raised overbought from 65 to 80
- **Grid BB exit**: Raised from 70% to 85%
- **Degen momentum exit**: Changed from -1.5% to -3%

### Confirmation Reductions (to increase activity)
- **EMA crossover**: 4→2 confirmations
- **Ichimoku**: 4→3 confirmations
- **Breakout**: score >= 30 → >= 15
- **Mean reversion**: score >= 35 → >= 20

## Repository

GitHub: https://github.com/Raphi52/PaperTrading
