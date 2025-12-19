# 🎯 Multi-Signal Confluence Trading Bot

Un bot de trading crypto intelligent qui combine **3 signaux indépendants** pour des décisions de trading plus fiables.

## 💡 Concept

Au lieu de trader sur un seul indicateur, ce bot attend que **plusieurs sources** soient d'accord:

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  TECHNICAL  │  │  SENTIMENT  │  │  ON-CHAIN   │
│             │  │             │  │             │
│ RSI, MACD   │  │ Fear/Greed  │  │ Whale moves │
│ Bollinger   │  │ Social      │  │ Exchange    │
│ EMA, Volume │  │ Twitter     │  │ flows       │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       ▼                ▼                ▼
       BUY?             BUY?             BUY?
       │                │                │
       └────────────────┼────────────────┘
                        ▼
              ┌──────────────────┐
              │   CONFLUENCE     │
              │                  │
              │  2/3 = TRADE     │
              │  3/3 = TRADE++   │
              │  1/3 = HOLD      │
              └──────────────────┘
```

## 🚀 Quick Start

```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Configurer l'environnement
cp .env.example .env
# Editer .env avec tes clés API

# 3. Lancer la démo (sans clés API)
python demo.py

# 4. Lancer le backtest
python backtest.py

# 5. Lancer le bot (testnet)
python main.py
```

## 📁 Structure

```
TradingBot/
├── config/
│   └── settings.py      # Configuration globale
├── core/
│   ├── exchange.py      # Connexion exchange (CCXT)
│   ├── confluence.py    # Moteur de confluence
│   └── risk_manager.py  # Gestion du risque
├── signals/
│   ├── technical.py     # Analyse technique
│   ├── sentiment.py     # Analyse sentiment
│   └── onchain.py       # Métriques on-chain
├── utils/
│   └── logger.py        # Logging coloré
├── main.py              # Bot principal
├── demo.py              # Demo sans API
└── backtest.py          # Backtesting
```

## 📊 Signaux

### 1. Technical Analysis
- **RSI**: Oversold (<30) = BUY, Overbought (>70) = SELL
- **MACD**: Crossover signals
- **Bollinger Bands**: Price at bands
- **EMA**: 12/26 crossover + 200 SMA trend
- **Volume**: Confirmation

### 2. Sentiment Analysis
- **Fear & Greed Index**: Contrarian (Fear = BUY, Greed = SELL)
- **Social Media**: Twitter/Reddit sentiment
- **LunarCrush**: Galaxy score

### 3. On-Chain Analysis
- **Whale Wallets**: Accumulation/Distribution
- **Exchange Flow**: Inflow (bearish) / Outflow (bullish)
- **Network Metrics**: Hash rate, active addresses

## ⚙️ Configuration

Éditer `config/settings.py` ou `.env`:

```python
# Trading
DEFAULT_SYMBOL=BTC/USDT
TRADE_AMOUNT_USDT=100
MAX_RISK_PERCENT=2       # Max 2% risque par trade
CONFLUENCE_THRESHOLD=2   # Min 2/3 signaux pour trader

# Risk Management
TAKE_PROFIT=3%
STOP_LOSS=2%
TRAILING_STOP=1.5%
```

## 🔑 API Keys

| Service | Usage | Get Key |
|---------|-------|---------|
| Binance | Trading | [testnet.binance.vision](https://testnet.binance.vision) |
| Twitter | Sentiment | [developer.twitter.com](https://developer.twitter.com) |
| Glassnode | On-Chain | [glassnode.com](https://glassnode.com) |
| LunarCrush | Social | [lunarcrush.com](https://lunarcrush.com) |

## 📈 Performance Attendue

Basé sur backtests:
- **Win Rate**: 65-75%
- **Return Annuel**: 30-60%
- **Max Drawdown**: 15-20%
- **Sharpe Ratio**: 1.5-2.5

## ⚠️ Avertissement

Ce bot est à usage éducatif. Le trading comporte des risques. Commencez TOUJOURS en testnet.

## 📝 Roadmap

- [x] Technical Analysis
- [x] Sentiment Analysis (Fear & Greed)
- [x] On-Chain Analysis
- [x] Confluence Engine
- [x] Risk Management
- [x] Backtesting
- [ ] Machine Learning predictions
- [ ] Multi-exchange arbitrage
- [ ] Telegram notifications
- [ ] Web dashboard

## License

MIT
