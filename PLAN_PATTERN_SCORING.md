# Plan Complet: Systeme de Scoring Multi-Timeframe des Patterns

## Objectif Principal
Transformer le bot pour qu'il:
1. Analyse les patterns sur TOUS les timeframes (M1, M5, M15, M30, H1, H4, D1)
2. Calcule un score de CLARTE/CONFIANCE (0-100) pour chaque pattern
3. N'entre QUE sur les patterns avec score > 80 (haute confiance)
4. ROTATE dynamiquement les positions vers de meilleures opportunites

---

## Phase 1: Multi-Timeframe Data Collection

### 1.1 Nouvelle fonction `fetch_multi_timeframe_data()`
```python
TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']

def fetch_multi_timeframe_data(symbol: str) -> dict:
    """Fetch OHLCV data for all timeframes"""
    data = {}
    for tf in TIMEFRAMES:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol.replace('/', '')}&interval={tf}&limit=100"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data[tf] = response.json()
    return data
```

### 1.2 Cache intelligent
- Cache par timeframe avec TTL adapte:
  - M1: 30 secondes
  - M5: 2 minutes
  - M15: 5 minutes
  - M30: 10 minutes
  - H1: 30 minutes
  - H4: 2 heures
  - D1: 6 heures

---

## Phase 2: Pattern Detection Engine

### 2.1 Patterns a detecter par timeframe

#### Patterns de Candlestick
| Pattern | Signal | Score Base |
|---------|--------|------------|
| Hammer | Bullish | +15 |
| Inverted Hammer | Bullish | +12 |
| Engulfing Bullish | Bullish | +20 |
| Morning Star | Bullish | +25 |
| Three White Soldiers | Bullish | +25 |
| Doji | Reversal | +8 |
| Shooting Star | Bearish | -15 |
| Evening Star | Bearish | -25 |

#### Patterns de Structure
| Pattern | Signal | Score Base |
|---------|--------|------------|
| Double Bottom | Bullish | +30 |
| Double Top | Bearish | -30 |
| Head & Shoulders | Bearish | -35 |
| Inv. Head & Shoulders | Bullish | +35 |
| Triangle Ascendant | Bullish | +20 |
| Triangle Descendant | Bearish | -20 |
| Channel Breakout | Trend | +25 |
| Flag/Pennant | Continuation | +18 |

#### Patterns d'Indicateurs
| Pattern | Signal | Score Base |
|---------|--------|------------|
| RSI Divergence | Reversal | +25 |
| MACD Cross Up | Bullish | +15 |
| BB Squeeze Breakout | Momentum | +20 |
| Stoch RSI Cross | Entry | +12 |
| Volume Spike + Move | Confirm | +15 |

### 2.2 Nouvelle fonction `detect_patterns()`
```python
def detect_patterns(df: pd.DataFrame, timeframe: str) -> list:
    """Detect all patterns in the dataframe"""
    patterns = []

    # Candlestick patterns
    patterns.extend(detect_candlestick_patterns(df))

    # Structure patterns
    patterns.extend(detect_structure_patterns(df))

    # Indicator patterns
    patterns.extend(detect_indicator_patterns(df))

    # Adjust scores based on timeframe importance
    tf_multiplier = {
        '1m': 0.3,   # Court terme, moins fiable
        '5m': 0.5,
        '15m': 0.7,
        '30m': 0.85,
        '1h': 1.0,   # Reference
        '4h': 1.2,   # Plus fiable
        '1d': 1.5    # Tres fiable
    }

    for p in patterns:
        p['score'] *= tf_multiplier.get(timeframe, 1.0)
        p['timeframe'] = timeframe

    return patterns
```

---

## Phase 3: Pattern Clarity Scoring System

### 3.1 Criteres de Clarte

Un pattern est CLAIR quand:
1. **Multiple Timeframe Alignment** (+30 pts max)
   - Meme direction sur 3+ timeframes = +30
   - Meme direction sur 2 timeframes = +15

2. **Volume Confirmation** (+20 pts max)
   - Volume > 2x moyenne = +20
   - Volume > 1.5x moyenne = +10

3. **Support/Resistance Proximity** (+15 pts max)
   - Prix pres d'un niveau cle = +15
   - Prix dans une zone de valeur = +10

4. **Clean Price Action** (+15 pts max)
   - Peu de meches (clean candles) = +15
   - Faible volatilite pre-pattern = +10

5. **Indicator Confluence** (+20 pts max)
   - 4+ indicateurs alignes = +20
   - 3 indicateurs alignes = +15
   - 2 indicateurs alignes = +10

### 3.2 Fonction `calculate_pattern_clarity_score()`
```python
def calculate_pattern_clarity_score(
    symbol: str,
    multi_tf_data: dict,
    patterns_by_tf: dict
) -> dict:
    """
    Calculate pattern clarity score (0-100)
    Returns: {
        'score': 0-100,
        'patterns': [...],
        'timeframe_alignment': {...},
        'best_entry_tf': '15m',
        'confidence': 'HIGH' | 'MEDIUM' | 'LOW',
        'recommendation': 'STRONG_BUY' | 'BUY' | 'WAIT' | 'SELL'
    }
    """
    score = 0
    reasons = []

    # 1. Multi-Timeframe Alignment
    bullish_count = sum(1 for tf, patterns in patterns_by_tf.items()
                        if any(p['direction'] == 'bullish' for p in patterns))
    bearish_count = sum(1 for tf, patterns in patterns_by_tf.items()
                        if any(p['direction'] == 'bearish' for p in patterns))

    alignment = max(bullish_count, bearish_count)
    if alignment >= 5:
        score += 30
        reasons.append(f"MTF Alignment: {alignment}/7 TFs")
    elif alignment >= 3:
        score += 15
        reasons.append(f"MTF Alignment: {alignment}/7 TFs")

    # 2. Volume Confirmation (check H1 and H4)
    h1_vol = multi_tf_data.get('1h', {}).get('volume_ratio', 1)
    if h1_vol > 2.0:
        score += 20
        reasons.append(f"Volume Spike: {h1_vol:.1f}x")
    elif h1_vol > 1.5:
        score += 10
        reasons.append(f"Volume Elevated: {h1_vol:.1f}x")

    # 3. S/R Proximity
    # ... (check fib levels, order blocks, etc.)

    # 4. Clean Price Action
    # ... (analyze candle wicks, ATR)

    # 5. Indicator Confluence
    # ... (count aligned indicators)

    # Final classification
    if score >= 80:
        confidence = 'HIGH'
        recommendation = 'STRONG_BUY' if bullish_count > bearish_count else 'STRONG_SELL'
    elif score >= 60:
        confidence = 'MEDIUM'
        recommendation = 'BUY' if bullish_count > bearish_count else 'SELL'
    else:
        confidence = 'LOW'
        recommendation = 'WAIT'

    return {
        'score': min(100, score),
        'confidence': confidence,
        'recommendation': recommendation,
        'reasons': reasons,
        'bullish_tf_count': bullish_count,
        'bearish_tf_count': bearish_count,
        'best_entry_timeframe': find_best_entry_tf(patterns_by_tf)
    }
```

---

## Phase 4: Dynamic Position Rotation

### 4.1 Logique de Rotation

```python
def should_rotate_to_better_opportunity(
    current_position: dict,
    new_opportunity: dict,
    portfolio: dict
) -> tuple:
    """
    Compare current position with new opportunity.
    Returns: (should_rotate, reason)
    """
    current_score = current_position.get('pattern_score', 50)
    new_score = new_opportunity['pattern_clarity_score']
    current_pnl = current_position.get('pnl_pct', 0)

    # Rule 1: New opportunity significantly better (score diff > 30)
    if new_score - current_score > 30 and new_score >= 80:
        return (True, f"Better pattern: {new_score} vs {current_score}")

    # Rule 2: Current position stagnant + better opportunity
    if current_pnl < 2 and new_score >= 80 and new_score > current_score + 20:
        return (True, f"Stagnant position, rotating to score {new_score}")

    # Rule 3: Current position losing + much better opportunity
    if current_pnl < 0 and new_score >= 85:
        return (True, f"Cutting loss for better opportunity (score {new_score})")

    return (False, f"Keep current (score diff: {new_score - current_score})")
```

### 4.2 Execution de la Rotation
```python
def execute_rotation(portfolio: dict, old_symbol: str, new_symbol: str, new_analysis: dict):
    """Execute position rotation"""
    # 1. Sell current position
    result = execute_trade(portfolio, 'SELL', old_symbol, ...)

    if result['success']:
        # 2. Buy new position immediately
        result = execute_trade(portfolio, 'BUY', new_symbol, ...)

        # 3. Log rotation
        log_trade(f"ROTATION: {old_symbol} -> {new_symbol}")

    return result
```

---

## Phase 5: Strategy Timeframe Classification

### 5.1 Categories de Strategies

| Style | Timeframes Principaux | Min Score | Hold Time |
|-------|----------------------|-----------|-----------|
| Scalping | M1, M5, M15 | 85 | 5min - 2h |
| Day Trading | M15, M30, H1 | 80 | 1h - 8h |
| Swing | H1, H4, D1 | 75 | 1j - 7j |
| Position | H4, D1, W1 | 70 | 7j+ |

### 5.2 Adaptation des TP/SL par Timeframe
```python
TIMEFRAME_CONFIG = {
    'scalping': {'tp': 1.5, 'sl': 0.8, 'min_score': 85},
    'day_trading': {'tp': 3.0, 'sl': 1.5, 'min_score': 80},
    'swing': {'tp': 8.0, 'sl': 4.0, 'min_score': 75},
    'position': {'tp': 20.0, 'sl': 10.0, 'min_score': 70}
}
```

---

## Phase 6: Implementation Steps

### Step 1: Ajouter le fetching multi-timeframe
- [ ] Creer `fetch_multi_timeframe_data()`
- [ ] Ajouter cache intelligent par timeframe
- [ ] Gerer les rate limits Binance

### Step 2: Implementer la detection de patterns
- [ ] Creer `detect_candlestick_patterns()`
- [ ] Creer `detect_structure_patterns()`
- [ ] Creer `detect_indicator_patterns()`
- [ ] Combiner dans `detect_patterns()`

### Step 3: Creer le scoring de clarte
- [ ] Implementer `calculate_pattern_clarity_score()`
- [ ] Ajouter MTF alignment check
- [ ] Ajouter volume confirmation
- [ ] Ajouter S/R proximity check
- [ ] Ajouter indicator confluence

### Step 4: Modifier should_trade()
- [ ] Ajouter appel a `calculate_pattern_clarity_score()`
- [ ] Bloquer entrees si score < threshold
- [ ] Loguer les patterns detectes

### Step 5: Implementer la rotation
- [ ] Creer `should_rotate_to_better_opportunity()`
- [ ] Modifier la boucle principale pour comparer toutes les opportunites
- [ ] Executer les rotations automatiquement

### Step 6: Dashboard
- [ ] Afficher le score de pattern sur le frontend
- [ ] Montrer les patterns detectes par timeframe
- [ ] Visualiser les rotations

---

## Estimations

| Phase | Complexite | Lignes de Code |
|-------|-----------|----------------|
| Multi-TF Data | Moyenne | ~150 |
| Pattern Detection | Haute | ~400 |
| Clarity Scoring | Haute | ~250 |
| Rotation Logic | Moyenne | ~150 |
| Integration | Moyenne | ~200 |
| **Total** | | **~1150** |

---

## Risques et Mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| API Rate Limits | Haut | Cache agressif, parallel requests |
| Faux positifs patterns | Moyen | Seuil de score eleve (80+) |
| Latence multi-TF | Moyen | Fetch async, priorite aux TF importants |
| Rotation excessive | Moyen | Cooldown entre rotations, min score diff |

---

## Prochaines Etapes

1. **Valider ce plan** avec l'utilisateur
2. **Commencer par Phase 1**: Multi-TF data fetching
3. **Tester** sur quelques cryptos avant deploiement complet
4. **Iterer** sur les seuils de score selon les resultats

