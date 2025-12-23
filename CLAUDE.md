# CLAUDE.md - Paper Trading Bot

## Project Overview

This is a **multi-strategy cryptocurrency paper trading bot** with a Streamlit dashboard. It simulates trading across 209 portfolios, each running a different trading strategy. The bot can also execute real trades on Binance and DEXs (Solana, Ethereum, BSC).

**Primary Language:** Python 3.11+
**Framework:** Streamlit (dashboard), standalone Python (trading engine)

## Quick Start Commands

```bash
# Run the trading bot (background engine)
python bot.py

# Run the dashboard (Streamlit UI)
streamlit run app.py

# Run both (bot in background)
python bot.py &
streamlit run app.py
```

## Architecture

```
PaperTrading/
├── bot.py              # Main trading engine (runs independently)
├── app.py              # Streamlit dashboard UI
├── core/               # Core modules
│   ├── exchange.py     # CCXT Binance connection
│   ├── confluence.py   # Multi-signal confluence engine
│   ├── real_executor.py # Real trade execution (Binance + DEX)
│   ├── risk_guard.py   # Risk limits and daily loss protection
│   ├── security.py     # Key encryption (AES-256)
│   ├── jupiter.py      # Solana DEX (Jupiter)
│   ├── uniswap.py      # Ethereum DEX (Uniswap V3)
│   └── pancakeswap.py  # BSC DEX (PancakeSwap)
├── signals/            # Trading signal generators
│   ├── technical.py    # RSI, MACD, Bollinger, EMA
│   ├── sentiment.py    # Fear & Greed, social sentiment
│   ├── onchain.py      # Whale movements, exchange flows
│   ├── degen.py        # Degen momentum signals
│   └── godmode.py      # Multi-confluence "god mode"
├── sniper/             # Token sniping modules
│   ├── dex_sniper.py   # New token detection
│   ├── dexscreener.py  # DexScreener API
│   ├── token_sniper.py # Token analysis
│   └── whale_tracker.py # Whale wallet tracking
├── config/             # Configuration
│   ├── settings.py     # Global settings
│   └── degen_config.py # Degen strategy config
├── utils/              # Utilities
│   ├── theme.py        # Streamlit theming
│   ├── logger.py       # Colored logging
│   └── telegram_alerts.py # Telegram notifications
└── data/               # Runtime data (gitignored)
    ├── portfolios.json # All 209 portfolios
    ├── settings.json   # User settings
    ├── bot_log.txt     # Trading log
    └── debug_log.json  # Debug state
```

## Key Files

### bot.py (Trading Engine)
- **STRATEGIES dict** (line ~652): Defines 148 trading strategies with TP/SL
- **should_trade()** (line ~1989): Core decision logic for all strategies
- **execute_trade()** (line ~1895): Paper/real trade execution
- **run_engine()** (line ~2421): Main loop - scans every 60 seconds
- **analyze_crypto()** (line ~1688): Fetches price data and calculates indicators

### app.py (Dashboard)
- **render_dashboard()** (line ~1264): Market overview
- **render_portfolios()** (line ~1365): Portfolio management UI
- **render_settings()** (line ~5029): Settings panel
- **calculate_portfolio_value()** (line ~852): Real-time P&L calculation

### data/portfolios.json
Structure:
```json
{
  "portfolios": {
    "portfolio_id": {
      "id": "portfolio_id",
      "name": "Strategy Name",
      "strategy_id": "rsi_strategy",  // Maps to STRATEGIES dict
      "config": {
        "cryptos": ["BTC/USDT", "ETH/USDT"],
        "allocation_percent": 5,
        "max_positions": 20,
        "auto_trade": true
      },
      "balance": {"USDT": 10000.0},
      "positions": {},
      "trades": [],
      "initial_capital": 10000,
      "active": true
    }
  }
}
```

## Trading Strategies

The bot supports 148 strategies grouped into categories:

| Category | Count | Examples |
|----------|-------|----------|
| RSI-based | 30 | rsi_strategy, rsi_divergence |
| Degen/Momentum | 13 | degen_scalp, degen_hybrid |
| Whale Copy | 11 | whale_gcr, whale_hsaka |
| Ichimoku | 10 | ichimoku, ichimoku_fast |
| Scalping | 10 | scalp_rsi, scalp_bb |
| Legendary Investors | 8 | legend_buffett, legend_soros |
| EMA Crossover | 8 | ema_crossover, ema_crossover_slow |
| Sniper | 7 | sniper_safe, sniper_degen |
| Grid Trading | 7 | grid_trading, grid_tight |
| Congress Copy | 4 | congress_pelosi, congress_all |
| Other (combined) | 101 | vwap, supertrend, breakout, etc. |

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

## Smart Trading Filters

Entry filters (applied before any buy):
1. **Loss cooldown** - Pause 2h after 3 consecutive losses
2. **Token safety** - Block risky memecoins for non-degen strategies
3. **Pump chase prevention** - Don't buy if >5% in 1h or >15% in 24h
4. **Trend alignment** - Require EMA stack (Price > EMA9 > EMA21)
5. **RSI quality** - Skip overbought entries
6. **Volume confirmation** - Require adequate volume
7. **Correlation limit** - Max 2 positions in similar assets
8. **Entry quality score** - Skip low-score entries (<40/100)

Exit mechanisms:
- **Take Profit (TP)** - Configurable per strategy
- **Stop Loss (SL)** - Configurable per strategy
- **Trailing Stop** - Locks in profits (5% trail from high)
- **Partial TP** - Sell 50% at first target
- **Time-based exit** - max_hold_hours for degen strategies

## API Integrations

| Service | Purpose | Config Location |
|---------|---------|-----------------|
| Binance | Price data, real trading | data/settings.json |
| CoinGecko | Price fallback | None (public) |
| DexScreener | DEX token prices | None (public) |
| Helius | Solana RPC | data/settings.json |
| Etherscan | ETH gas prices | data/settings.json |
| Alternative.me | Fear & Greed Index | None (public) |

## File Locking

Both `bot.py` and `app.py` access `portfolios.json`. File locking prevents corruption:
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

### Error Handling
- All API calls wrapped in try/except
- Graceful degradation (use cached data on failure)
- Errors logged to debug_log.json

### Adding a New Strategy
1. Add to `STRATEGIES` dict in bot.py (~line 652):
```python
"my_strategy": {
    "auto": True,
    "use_rsi": True,  # or other flag
    "take_profit": 20,
    "stop_loss": 10
}
```

2. If new flag needed, add logic to `should_trade()` (~line 1989):
```python
if strategy.get('use_my_flag'):
    # Trading logic here
    if condition and has_cash:
        return ('BUY', "Reason")
    elif other_condition and has_position:
        return ('SELL', "Reason")
    return (None, "Waiting...")
```

3. Add timeframe to `STRATEGY_TIMEFRAMES` if not 1h default

### Testing Changes
```bash
# Run bot with visible output
python bot.py

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

## Git Workflow

```bash
# Standard commit
git add bot.py app.py
git commit -m "Description of changes"
git push

# Data files are gitignored except:
# - data/portfolios.json (portfolio state)
# - data/settings.json (user config)
```

## Performance Notes

- Bot scans every 60 seconds (`SCAN_INTERVAL`)
- 209 portfolios × N cryptos per portfolio = many API calls
- Uses caching to reduce API load
- Dashboard refreshes every 10 seconds (configurable)

## Contact

Repository: https://github.com/Raphi52/PaperTrading
