# CLAUDE.md - Paper Trading Bot

## Quick Reference

```bash
# Start everything
python bot.py                    # Trading engine (background)
cd frontend && npm run dev       # Dashboard on localhost:3000

# Analytics
python analyze_strategies.py     # Full strategy analysis

# Quick stats
python -c "from core.database import get_global_stats; print(get_global_stats())"
```

## Project Overview

**Multi-strategy crypto paper trading bot** with 305 portfolios running 80+ unique strategies.

| Metric | Value |
|--------|-------|
| Total Portfolios | 305 |
| Unique Strategies | 80+ |
| Supported Cryptos | 63 |
| Scan Interval | 60 seconds |

**Stack:** Python 3.11+ (backend) + Next.js 16 (frontend) + SQLite (trades DB)

## Live Performance Tracking

### Get Current Stats
```python
from core.database import get_strategy_performance, get_global_stats

# Global stats
stats = get_global_stats()
print(f"Win Rate: {stats['win_rate']}%")
print(f"Total PnL: ${stats['total_pnl']:.2f}")
print(f"Total Trades: {stats['total_trades']}")

# Strategy performance
perf = get_strategy_performance()
sorted_perf = sorted(perf, key=lambda x: x.get('total_pnl', 0), reverse=True)
for s in sorted_perf[:10]:
    print(f"{s['strategy_id']}: ${s['total_pnl']:.2f} ({s['win_rate']:.1f}% WR)")
```

### Top Performing Strategies (Historical)
| Strategy | Typical PnL | Win Rate | Style |
|----------|-------------|----------|-------|
| stoch_rsi | +$5000-8000 | 75-80% | Momentum |
| degen_scalp | +$2000-4000 | 45-50% | Fast scalping |
| dca_fear | +$1000-1500 | 85%+ | Fear-based DCA |
| degen_full | +$500-1000 | 45-50% | Aggressive |
| grid_tight | +$500-1500 | 60-65% | Range trading |

### Strategies Needing Optimization
| Strategy | Issue | Fix Approach |
|----------|-------|--------------|
| ichimoku | Low WR (45%) | Widen TP, tighten entry conditions |
| stoch_rsi_aggressive | Small losses | Raise overbought threshold |
| ema_crossover | Choppy markets | Add trend filter |
| supertrend_fast | Whipsaws | Increase ATR multiplier |
| ichimoku_scalp | Very low WR | Reduce trade frequency |

## Architecture

```
PaperTrading/
├── bot.py                  # Main engine (4500+ lines)
│   ├── STRATEGIES dict     # ~line 1200 - All strategy configs
│   ├── should_trade()      # ~line 2800 - Entry/exit logic
│   ├── execute_trade()     # ~line 2600 - Trade execution
│   └── run_engine()        # ~line 4200 - Main loop
├── core/
│   ├── database.py         # SQLite storage & analytics
│   ├── exchange.py         # CCXT Binance connection
│   ├── confluence.py       # Multi-signal engine
│   ├── risk_manager.py     # Risk management
│   ├── alpha_signals.py    # Alpha signal generation
│   └── real_data.py        # Market data fetching
├── frontend/               # Next.js 16 Dashboard
│   └── src/app/
│       ├── page.tsx        # Main dashboard
│       ├── trades/         # Trade history
│       ├── analytics/      # Charts & stats
│       ├── strategies/     # Strategy management
│       └── api/            # REST endpoints
└── data/
    ├── portfolios.json     # Portfolio state
    ├── trading.db          # SQLite database
    └── settings.json       # API keys & config
```

## Strategy Optimization Guide

### 1. Analyze Performance
```bash
python -c "
from core.database import get_strategy_performance
perf = get_strategy_performance()
for s in sorted(perf, key=lambda x: x['total_pnl'])[:10]:
    print(f\"{s['strategy_id']}: {s['total_trades']} trades, \${s['total_pnl']:.2f}, WR: {s['win_rate']:.1f}%\")
"
```

### 2. Modify Strategy Parameters
Edit `STRATEGIES` dict in `bot.py` (~line 1200):

```python
"strategy_name": {
    "auto": True,
    "use_rsi": True,           # Strategy flag
    "take_profit": 15,         # TP percentage
    "stop_loss": 8,            # SL percentage (0 = disabled)
    "rsi_oversold": 30,        # Entry threshold
    "rsi_overbought": 70,      # Exit threshold
    "confirmations": 2,        # Bars to confirm signal
    "tooltip": "Description"
}
```

### 3. Key Parameters to Tune

| Parameter | Effect | When to Increase | When to Decrease |
|-----------|--------|------------------|------------------|
| take_profit | Exit target | Low WR, high avg loss | High WR, small gains |
| stop_loss | Risk limit | Too many big losses | Stopped out too often |
| rsi_oversold | Entry point | Missing entries | Too many bad entries |
| rsi_overbought | Exit point | Exiting too early | Holding too long |
| confirmations | Signal quality | False signals | Missing moves |

### 4. Strategy Flags Reference

```python
# In should_trade() function
use_rsi          # RSI oversold/overbought
use_ema_cross    # EMA crossover signals
use_stoch_rsi    # Stochastic RSI
use_degen        # Momentum scalping
use_grid         # Range/grid trading
use_ichimoku     # Ichimoku cloud
use_breakout     # Breakout detection
use_mean_rev     # Mean reversion
use_martingale   # Double down on loss
use_reinforce    # Average down
use_trailing     # Trailing stop
```

## Common Tasks

### Boost Winning Strategies
```python
import json
with open('data/portfolios.json', 'r') as f:
    data = json.load(f)

for p in data['portfolios'].values():
    if p['strategy_id'] in ['stoch_rsi', 'degen_scalp', 'dca_fear']:
        p['config']['allocation_percent'] = min(20, p['config'].get('allocation_percent', 5) + 5)

with open('data/portfolios.json', 'w') as f:
    json.dump(data, f, indent=2)
```

### Check Portfolio Health
```python
import json
with open('data/portfolios.json') as f:
    data = json.load(f)

for pid, p in data['portfolios'].items():
    balance = p.get('balance', {}).get('USDT', 10000)
    initial = p.get('initial_capital', 10000)
    pnl_pct = ((balance / initial) - 1) * 100
    if pnl_pct < -30:
        print(f"WARNING: {p['name']}: {pnl_pct:.1f}%")
```

### Reset a Portfolio
```python
import json
with open('data/portfolios.json', 'r') as f:
    data = json.load(f)

pid = 'portfolio_X'  # Replace with actual ID
data['portfolios'][pid]['balance'] = {'USDT': 10000}
data['portfolios'][pid]['positions'] = {}
data['portfolios'][pid]['trades'] = []

with open('data/portfolios.json', 'w') as f:
    json.dump(data, f, indent=2)
```

## Bot Commands

### Restart Bot
```bash
# Find and kill existing bot
tasklist | findstr python
taskkill //F //PID <PID>

# Start new instance
python bot.py
```

### Check Bot Status
```bash
# View recent log
tail -50 data/bot_log.txt

# Check if running
tasklist | findstr python
```

## Frontend Routes

| Route | Description |
|-------|-------------|
| `/` | Main dashboard - all portfolios |
| `/trades` | Trade history with filters |
| `/analytics` | Charts and performance graphs |
| `/strategies` | Strategy management |
| `/positions` | Open positions |
| `/settings` | API keys and config |

## Database Queries

### Recent Trades
```sql
SELECT * FROM trades ORDER BY timestamp DESC LIMIT 50;
```

### Strategy Performance
```sql
SELECT strategy_id,
       COUNT(*) as trades,
       SUM(pnl) as total_pnl,
       AVG(pnl) as avg_pnl,
       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
FROM trades
WHERE action = 'SELL'
GROUP BY strategy_id
ORDER BY total_pnl DESC;
```

### Daily PnL
```sql
SELECT DATE(timestamp) as day, SUM(pnl) as daily_pnl
FROM trades WHERE action = 'SELL'
GROUP BY DATE(timestamp)
ORDER BY day DESC LIMIT 30;
```

## Troubleshooting

### Bot Not Trading
1. Check `active: true` in portfolio
2. Check `auto_trade: true` in config
3. Check strategy has `auto: True` in STRATEGIES
4. Verify `cryptos` list is not empty
5. Check for loss cooldown (2h after 3 consecutive losses)

### File Lock Stuck
```bash
del data\portfolios.lock
```

### Encoding Errors (Windows)
Already fixed in bot.py:
```python
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
```

### Frontend Not Loading
```bash
cd frontend
del .next\dev\lock
npm run dev
```

## Strategy Categories

### Conservative (Low Risk)
- `hodl` - Buy and hold
- `dca_fear` - DCA on fear index
- `grid_tight` - Tight grid trading
- `reinforce_safe` - Safe averaging down

### Moderate
- `stoch_rsi` - Stochastic RSI momentum
- `ema_crossover` - EMA cross signals
- `supertrend` - Trend following
- `breakout` - Breakout detection

### Aggressive (High Risk)
- `degen_scalp` - Fast scalping
- `degen_full` - Full degen mode
- `martingale` - Double down (no SL)
- `meme_hunter` - Memecoin hunting

### Specialized
- `ichimoku_*` - Ichimoku variants
- `trailing_*` - Trailing stop variants
- `grid_*` - Grid trading variants
- `order_block_*` - Order block strategies

## API Integrations

| Service | Purpose | Rate Limit |
|---------|---------|------------|
| Binance | Price data | 1200/min |
| CoinGecko | Fallback prices | 50/min |
| DexScreener | DEX prices | 300/min |
| Alternative.me | Fear & Greed | 10/min |

## Performance Tips

1. **Reduce API calls**: Bot caches prices for 60s
2. **Limit portfolios**: More portfolios = more API calls
3. **Use SQLite**: JSON limited to 500 trades/portfolio
4. **Monitor memory**: Large portfolios.json can slow down

## File Structure

```
data/
├── portfolios.json    # Portfolio state (read/write by bot + frontend)
├── trading.db         # SQLite database (unlimited trades)
├── settings.json      # API keys and configuration
├── bot_log.txt        # Trading log
├── portfolios.lock    # File lock (auto-created)
└── crypto_update_state.json  # Crypto list cache
```

## Git Workflow

```bash
# Status
git status

# Commit changes
git add -A
git commit -m "Description"

# Push
git push origin main
```

## Contact

GitHub: https://github.com/Raphi52/PaperTrading
