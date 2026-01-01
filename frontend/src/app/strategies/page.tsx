'use client';

import { useEffect, useState, useMemo } from 'react';
import Header from '@/components/Header';

interface StrategyStats {
  strategy_id: string;
  portfolios: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  pnl: number;
  exit_reasons: Record<string, number>;
  active: boolean;
  avg_pnl?: number;
  best_trade?: number;
  worst_trade?: number;
  avg_hold_time?: string;
  portfolio_names?: string[];
  symbols_traded?: string[];
  daily_pnl?: { date: string; pnl: number }[];
}

// Strategy categories for grouping
const STRATEGY_CATEGORIES: Record<string, string[]> = {
  'RSI-Based': ['rsi_strategy', 'rsi_divergence', 'rsi_divergence_fast', 'stoch_rsi', 'stoch_rsi_aggressive'],
  'EMA Crossover': ['ema_crossover', 'ema_crossover_slow', 'ema_crossover_fast'],
  'Degen/Momentum': ['degen_scalp', 'degen_momentum', 'degen_hybrid', 'degen_ultra'],
  'Ichimoku': ['ichimoku', 'ichimoku_fast', 'ichimoku_scalp', 'ichimoku_swing', 'ichimoku_momentum'],
  'Grid Trading': ['grid_trading', 'grid_tight', 'grid_wide'],
  'Mean Reversion': ['mean_reversion', 'mean_reversion_tight', 'mean_reversion_short'],
  'Breakout': ['breakout', 'breakout_tight', 'donchian_breakout'],
  'Scalping': ['scalp_rsi', 'scalp_bb', 'scalp_macd', 'trailing_scalp'],
  'DCA': ['dca_fear', 'dca_accumulator', 'dca_aggressive'],
  'Sentiment': ['social_sentiment', 'fear_greed_extreme'],
  'Other': []
};

function getCategory(strategyId: string): string {
  for (const [cat, strategies] of Object.entries(STRATEGY_CATEGORIES)) {
    if (strategies.includes(strategyId)) return cat;
  }
  return 'Other';
}

// Strategy descriptions in French for beginners
const STRATEGY_DESCRIPTIONS: Record<string, { description: string; descriptionFR: string; buyWhen: string; sellWhen: string; risk: string; timeframe: string; flags: string[] }> = {
  'stoch_rsi': {
    description: 'Stochastic RSI momentum strategy',
    descriptionFR: "Achete quand le prix est trop bas (survendu) et vend quand il est trop haut (surachat). C'est comme acheter en soldes et revendre au prix fort.",
    buyWhen: "StochRSI < 20 (survendu) + RSI < 40",
    sellWhen: "StochRSI > 80 (surachat) OU Take Profit atteint",
    risk: 'Medium', timeframe: '1h', flags: ['use_stoch_rsi']
  },
  'stoch_rsi_aggressive': {
    description: 'Aggressive Stochastic RSI',
    descriptionFR: "Version plus agressive du StochRSI - entre plus tot dans les trades mais prend plus de risques. Pour ceux qui veulent plus d'action.",
    buyWhen: "StochRSI < 30 (moins strict)",
    sellWhen: "StochRSI > 70 OU momentum negatif",
    risk: 'High', timeframe: '15m', flags: ['use_stoch_rsi']
  },
  'degen_scalp': {
    description: 'Fast scalping on momentum',
    descriptionFR: "Trades ultra-rapides qui surfent sur les mouvements de prix. Entre et sort en quelques minutes pour grappiller des petits gains. Style casino.",
    buyWhen: "Momentum positif + RSI 40-60 + Volume eleve",
    sellWhen: "+3% profit OU -2% perte OU apres 2-6h",
    risk: 'High', timeframe: '5m', flags: ['use_degen']
  },
  'degen_full': {
    description: 'Full degen mode',
    descriptionFR: "Mode YOLO total - achete tout ce qui bouge, vise des gains rapides. Peut gagner gros ou perdre gros. Pour les joueurs.",
    buyWhen: "N'importe quel signal positif + pas en perte",
    sellWhen: "+5% profit OU -3% perte OU signal contraire",
    risk: 'Very High', timeframe: '5m', flags: ['use_degen']
  },
  'dca_fear': {
    description: 'DCA on Fear index',
    descriptionFR: "Achete automatiquement quand tout le monde a peur (indice Fear & Greed bas). Strategie de Warren Buffett: 'Sois avide quand les autres ont peur'.",
    buyWhen: "Fear & Greed Index < 25 (Extreme Fear)",
    sellWhen: "Fear & Greed Index > 75 (Extreme Greed) OU +15% profit",
    risk: 'Low', timeframe: '4h', flags: ['use_fear_greed', 'use_dca']
  },
  'grid_tight': {
    description: 'Tight grid trading',
    descriptionFR: "Place des ordres d'achat et vente a intervalles reguliers comme un filet. Gagne de l'argent quand le prix oscille. Ideal pour les marches calmes.",
    buyWhen: "Prix baisse de 0.5% depuis dernier achat",
    sellWhen: "Prix monte de 0.5% depuis dernier achat",
    risk: 'Medium', timeframe: '15m', flags: ['use_grid']
  },
  'grid_trading': {
    description: 'Standard grid trading',
    descriptionFR: "Comme grid_tight mais avec des intervalles plus larges. Moins de trades mais moins de frais aussi.",
    buyWhen: "Prix baisse de 1-2% depuis dernier achat",
    sellWhen: "Prix monte de 1-2% depuis dernier achat",
    risk: 'Medium', timeframe: '1h', flags: ['use_grid']
  },
  'ema_crossover': {
    description: 'EMA crossover trend following',
    descriptionFR: "Suit la tendance avec 2 moyennes mobiles. Achete quand la rapide croise au-dessus de la lente (signal haussier). Simple et efficace.",
    buyWhen: "EMA 9 croise AU-DESSUS de EMA 21 (golden cross)",
    sellWhen: "EMA 9 croise EN-DESSOUS de EMA 21 (death cross) OU TP/SL",
    risk: 'Medium', timeframe: '1h', flags: ['use_ema_cross']
  },
  'ichimoku': {
    description: 'Ichimoku cloud system',
    descriptionFR: "Systeme japonais qui utilise un 'nuage' pour voir la tendance. Si le prix est au-dessus du nuage = haussier, en-dessous = baissier.",
    buyWhen: "Prix casse AU-DESSUS du nuage + Tenkan > Kijun",
    sellWhen: "Prix passe EN-DESSOUS du nuage OU Tenkan < Kijun",
    risk: 'Medium', timeframe: '4h', flags: ['use_ichimoku']
  },
  'ichimoku_scalp': {
    description: 'Ichimoku scalping',
    descriptionFR: "Version rapide d'Ichimoku pour du scalping. Trades plus courts mais meme logique de nuage.",
    buyWhen: "Prix au-dessus du nuage + Tenkan/Kijun cross up",
    sellWhen: "+2% profit OU signal contraire",
    risk: 'High', timeframe: '15m', flags: ['use_ichimoku']
  },
  'supertrend': {
    description: 'Supertrend indicator',
    descriptionFR: "Indicateur qui trace une ligne sous le prix en tendance haussiere, au-dessus en baissiere. Tres visuel et facile a suivre.",
    buyWhen: "Supertrend passe VERT (sous le prix)",
    sellWhen: "Supertrend passe ROUGE (au-dessus du prix) OU TP/SL",
    risk: 'Medium', timeframe: '1h', flags: ['use_supertrend']
  },
  'supertrend_fast': {
    description: 'Fast Supertrend',
    descriptionFR: "Supertrend plus reactif - detecte les changements de tendance plus vite mais peut donner de faux signaux.",
    buyWhen: "Supertrend flip vert + confirmation RSI",
    sellWhen: "Supertrend flip rouge OU momentum negatif",
    risk: 'High', timeframe: '15m', flags: ['use_supertrend']
  },
  'breakout': {
    description: 'Breakout detection',
    descriptionFR: "Detecte quand le prix casse un niveau important (resistance/support). Achete sur cassure haussiere, comme un ressort qui se libere.",
    buyWhen: "Prix casse resistance + Volume > moyenne",
    sellWhen: "Retour sous resistance OU TP +10% OU SL -5%",
    risk: 'High', timeframe: '1h', flags: ['use_breakout']
  },
  'mean_reversion': {
    description: 'Mean reversion',
    descriptionFR: "Parie que le prix va revenir a sa moyenne. Achete quand le prix s'eloigne trop vers le bas, vend quand il s'eloigne trop vers le haut.",
    buyWhen: "Prix > 2 ecarts-types SOUS la moyenne",
    sellWhen: "Prix revient a la moyenne OU depasse +1 ecart-type",
    risk: 'High', timeframe: '4h', flags: ['use_mean_rev']
  },
  'martingale': {
    description: 'Martingale (no SL)',
    descriptionFR: "DANGER: Double la mise apres chaque perte pour recuperer. Pas de stop loss. Peut tout perdre en une mauvaise serie. Style casino.",
    buyWhen: "Signal d'achat + Double la taille si position perdante",
    sellWhen: "Position globale en profit (recupere toutes les pertes)",
    risk: 'Very High', timeframe: '1h', flags: ['use_martingale']
  },
  'martingale_safe': {
    description: 'Safer Martingale',
    descriptionFR: "Martingale avec des limites - ne double pas indefiniment. Moins risque mais peut quand meme faire mal.",
    buyWhen: "Signal + Renforce jusqu'a 3-4x max",
    sellWhen: "Profit global OU limite de renforcement atteinte",
    risk: 'High', timeframe: '1h', flags: ['use_martingale']
  },
  'trailing_scalp': {
    description: 'Trailing stop scalping',
    descriptionFR: "Scalping avec stop suiveur - le stop loss monte avec le prix pour securiser les gains. Laisse courir les winners.",
    buyWhen: "Momentum positif + RSI < 60",
    sellWhen: "Trailing stop touche (suit le prix a -2%) OU TP +5%",
    risk: 'Medium', timeframe: '5m', flags: ['use_trailing']
  },
  'trailing_tight': {
    description: 'Tight trailing stop',
    descriptionFR: "Stop suiveur serre - securise les gains rapidement mais peut sortir trop tot. Pour les prudents.",
    buyWhen: "Signal haussier confirme",
    sellWhen: "Trailing stop serre (-1%) touche OU TP +3%",
    risk: 'Low', timeframe: '5m', flags: ['use_trailing']
  },
  'hodl': {
    description: 'Buy and hold',
    descriptionFR: "Achete et garde longtemps sans toucher. Strategie 'HODL' - pour ceux qui croient au long terme et ne veulent pas stresser.",
    buyWhen: "Allocation initiale OU DCA mensuel",
    sellWhen: "Jamais (ou objectif long terme atteint)",
    risk: 'Low', timeframe: 'Daily', flags: ['use_hodl']
  },
  'rsi_divergence': {
    description: 'RSI divergence',
    descriptionFR: "Detecte quand le prix et le RSI ne vont pas dans le meme sens (divergence). Signal de retournement potentiel.",
    buyWhen: "Prix fait nouveau bas MAIS RSI fait bas plus haut (divergence bull)",
    sellWhen: "Prix fait nouveau haut MAIS RSI fait haut plus bas (divergence bear)",
    risk: 'Medium', timeframe: '1h', flags: ['use_rsi']
  },
  'rsi_divergence_fast': {
    description: 'Fast RSI divergence',
    descriptionFR: "Version rapide - detecte les divergences plus vite mais avec plus de faux signaux.",
    buyWhen: "Divergence bullish detectee sur 3-5 bougies",
    sellWhen: "Divergence bearish OU +5% OU -3%",
    risk: 'High', timeframe: '15m', flags: ['use_rsi']
  },
  'bollinger_squeeze': {
    description: 'Bollinger squeeze',
    descriptionFR: "Attend que les bandes de Bollinger se resserrent (calme avant la tempete) puis trade l'explosion qui suit.",
    buyWhen: "Bandes serrees + cassure vers le HAUT",
    sellWhen: "Retour dans les bandes OU bande opposee touchee",
    risk: 'Medium', timeframe: '1h', flags: ['use_breakout']
  },
  'macd_crossover': {
    description: 'MACD crossover',
    descriptionFR: "Trade les croisements du MACD - un indicateur qui montre la force et la direction de la tendance.",
    buyWhen: "MACD croise AU-DESSUS de la ligne signal",
    sellWhen: "MACD croise EN-DESSOUS de la ligne signal",
    risk: 'Medium', timeframe: '1h', flags: ['use_ema_cross']
  },
  'volume_breakout': {
    description: 'Volume breakout',
    descriptionFR: "Achete quand le prix casse avec un gros volume - signe que le mouvement est serieux et pas un faux signal.",
    buyWhen: "Cassure resistance + Volume > 2x moyenne",
    sellWhen: "Volume retombe OU prix retrace 50%",
    risk: 'Medium', timeframe: '1h', flags: ['use_breakout']
  },
  'meme_hunter': {
    description: 'Meme coin hunter',
    descriptionFR: "Chasse les memecoins qui pompent. Tres speculatif - peut faire x2 ou -50% en une journee. Pour les degens.",
    buyWhen: "Pump detecte (+10% en 1h) + Volume explosif",
    sellWhen: "+20% profit OU -10% perte OU momentum mort",
    risk: 'Very High', timeframe: '5m', flags: ['use_degen']
  },
  'whale_tracker': {
    description: 'Whale tracking',
    descriptionFR: "Copie les mouvements des gros portefeuilles (whales). Si les riches achetent, on achete aussi.",
    buyWhen: "Grosse transaction whale detectee (>$1M achat)",
    sellWhen: "Whale vend OU +15% profit OU -8% perte",
    risk: 'Medium', timeframe: '1h', flags: ['use_whale']
  },
  'funding_contrarian': {
    description: 'Funding rate contrarian',
    descriptionFR: "Trade contre le consensus - quand tout le monde est long (funding positif), on short, et vice versa.",
    buyWhen: "Funding rate tres negatif (trop de shorts)",
    sellWhen: "Funding rate tres positif (trop de longs)",
    risk: 'High', timeframe: '4h', flags: ['use_funding']
  },
  'order_block_bull': {
    description: 'Order block (bullish)',
    descriptionFR: "Identifie les zones ou les institutions ont achete massivement. Achete quand le prix revient sur ces zones.",
    buyWhen: "Prix revient sur order block bullish + reaction",
    sellWhen: "Order block casse OU objectif atteint",
    risk: 'Medium', timeframe: '1h', flags: ['use_orderflow']
  },
  'order_block_bear': {
    description: 'Order block (bearish)',
    descriptionFR: "Inverse - identifie les zones de vente institutionnelle pour shorter ou eviter d'acheter la.",
    buyWhen: "Prix casse order block bearish vers le haut",
    sellWhen: "Prix atteint order block bearish (resistance)",
    risk: 'Medium', timeframe: '1h', flags: ['use_orderflow']
  },
  'liquidity_sweep': {
    description: 'Liquidity sweep',
    descriptionFR: "Attend que le prix aille chercher la liquidite (stop loss des autres) puis trade le retournement. Malin.",
    buyWhen: "Prix balaye les stops sous support + reversal",
    sellWhen: "Objectif atteint OU nouveau sweep",
    risk: 'High', timeframe: '15m', flags: ['use_orderflow']
  },
  'reinforce_safe': {
    description: 'Safe reinforcement',
    descriptionFR: "Rachete quand une position baisse pour moyenner le prix d'entree a la baisse. Version prudente avec limites.",
    buyWhen: "Position existante -5% + max 2 renforts",
    sellWhen: "Prix moyen + 5% profit",
    risk: 'Medium', timeframe: '1h', flags: ['use_reinforce']
  },
  'reinforce_moderate': {
    description: 'Moderate reinforcement',
    descriptionFR: "Renforcement moyen - rachete plus agressivement sur les baisses mais avec des gardes-fous.",
    buyWhen: "Position existante -3% + max 3 renforts",
    sellWhen: "Prix moyen + 3% profit",
    risk: 'High', timeframe: '1h', flags: ['use_reinforce']
  },
  'reinforce_aggressive': {
    description: 'Aggressive reinforcement',
    descriptionFR: "Renforcement agressif - all-in sur les baisses. Peut transformer une perte en gros gain... ou en desastre.",
    buyWhen: "Position existante -2% + renforce 2x a chaque fois",
    sellWhen: "Prix moyen + 2% profit (mais gros volume)",
    risk: 'Very High', timeframe: '1h', flags: ['use_reinforce']
  },
  'scalp_rsi': {
    description: 'RSI scalping',
    descriptionFR: "Scalping base sur le RSI - trades rapides sur les extremes de surachat/survente.",
    buyWhen: "RSI < 25 (tres survendu)",
    sellWhen: "RSI > 70 OU +2% profit OU -1% perte",
    risk: 'Medium', timeframe: '5m', flags: ['use_rsi', 'use_scalp']
  },
  'scalp_bb': {
    description: 'Bollinger scalping',
    descriptionFR: "Scalping sur les bandes de Bollinger - achete en bas de bande, vend en haut.",
    buyWhen: "Prix touche bande BASSE de Bollinger",
    sellWhen: "Prix touche bande HAUTE OU bande mediane",
    risk: 'Medium', timeframe: '5m', flags: ['use_scalp']
  },
  'fear_greed_extreme': {
    description: 'Fear & Greed extreme',
    descriptionFR: "Trade uniquement sur les extremes de peur (achat) ou euphorie (vente). Patience requise mais efficace.",
    buyWhen: "Fear & Greed < 20 (Extreme Fear)",
    sellWhen: "Fear & Greed > 80 (Extreme Greed)",
    risk: 'Low', timeframe: '4h', flags: ['use_fear_greed']
  },
  'social_sentiment': {
    description: 'Social sentiment',
    descriptionFR: "Analyse le sentiment sur les reseaux sociaux. Achete quand c'est negatif (contrarian), ou suit la hype.",
    buyWhen: "Sentiment Twitter/Reddit tres negatif (contrarian)",
    sellWhen: "Sentiment devient tres positif (euphorie)",
    risk: 'High', timeframe: '1h', flags: ['use_sentiment']
  },
  'cci_extreme': {
    description: 'CCI extreme',
    descriptionFR: "Utilise l'indicateur CCI pour detecter les prix extremes. Similaire au RSI mais calcule differemment.",
    buyWhen: "CCI < -100 (survendu)",
    sellWhen: "CCI > +100 (surachat)",
    risk: 'Medium', timeframe: '1h', flags: ['use_cci']
  },
  'williams_r': {
    description: 'Williams %R',
    descriptionFR: "Indicateur de momentum qui mesure les niveaux de surachat/survente. Cree par Larry Williams, trader legendaire.",
    buyWhen: "Williams %R < -80 (survendu)",
    sellWhen: "Williams %R > -20 (surachat)",
    risk: 'Medium', timeframe: '1h', flags: ['use_williams']
  },
  'donchian_breakout': {
    description: 'Donchian breakout',
    descriptionFR: "Achete quand le prix atteint un nouveau plus haut sur X periodes. Strategie des Tortues, prouvee depuis 40 ans.",
    buyWhen: "Prix casse le plus HAUT des 20 dernieres periodes",
    sellWhen: "Prix casse le plus BAS des 10 dernieres periodes",
    risk: 'Medium', timeframe: '4h', flags: ['use_breakout']
  },
  'pivot_classic': {
    description: 'Pivot points',
    descriptionFR: "Trade sur les niveaux pivot calcules chaque jour. Support et resistance automatiques utilises par les pros.",
    buyWhen: "Prix rebondit sur Support 1 (S1) ou S2",
    sellWhen: "Prix atteint Resistance 1 (R1) ou R2",
    risk: 'Low', timeframe: 'Daily', flags: ['use_pivot']
  },
  'keltner_channel': {
    description: 'Keltner channel',
    descriptionFR: "Canaux bases sur l'ATR - achete quand le prix touche le bas du canal, vend en haut. Bon pour les ranges.",
    buyWhen: "Prix touche bande BASSE du canal Keltner",
    sellWhen: "Prix touche bande HAUTE du canal Keltner",
    risk: 'Medium', timeframe: '1h', flags: ['use_channel']
  },
  'heikin_ashi': {
    description: 'Heikin Ashi trend',
    descriptionFR: "Utilise les bougies Heikin Ashi qui lissent le bruit. Plus facile de voir la vraie tendance.",
    buyWhen: "Bougie HA devient VERTE apres une serie rouge",
    sellWhen: "Bougie HA devient ROUGE apres une serie verte",
    risk: 'Medium', timeframe: '1h', flags: ['use_ha']
  },
  'confluence_normal': {
    description: 'Multi-signal confluence',
    descriptionFR: "N'achete que quand plusieurs indicateurs sont d'accord (confluence). Moins de trades mais meilleure qualite.",
    buyWhen: "RSI + EMA + MACD tous bullish en meme temps",
    sellWhen: "2+ indicateurs deviennent bearish",
    risk: 'Low', timeframe: '1h', flags: ['use_confluence']
  },
  'fib_retracement': {
    description: 'Fibonacci retracement',
    descriptionFR: "Achete sur les niveaux de Fibonacci (38%, 50%, 61%). Niveaux 'magiques' respectes par beaucoup de traders.",
    buyWhen: "Prix retrace au niveau 61.8% Fibonacci + rebond",
    sellWhen: "Prix atteint 0% (ancien sommet) ou casse 78.6%",
    risk: 'Medium', timeframe: '4h', flags: ['use_fib']
  },
  'range_sniper': {
    description: 'Range sniper',
    descriptionFR: "Snipe les extremites des ranges - achete tout en bas, vend tout en haut. Precision chirurgicale.",
    buyWhen: "Prix au BAS du range identifie + rebond",
    sellWhen: "Prix au HAUT du range OU cassure du range",
    risk: 'Medium', timeframe: '15m', flags: ['use_range']
  },
  'ai_tokens': {
    description: 'AI tokens focus',
    descriptionFR: "Focus sur les tokens lies a l'IA (FET, RNDR, etc.). Secteur hype avec gros potentiel mais volatile.",
    buyWhen: "RSI < 35 sur token IA + news positive secteur",
    sellWhen: "RSI > 70 OU -10% depuis entree",
    risk: 'High', timeframe: '1h', flags: ['use_sector']
  },
};

function getStrategyInfo(strategyId: string) {
  return STRATEGY_DESCRIPTIONS[strategyId] || {
    description: 'Custom strategy',
    descriptionFR: "Strategie personnalisee - consulte le code pour plus de details.",
    buyWhen: "Conditions specifiques a cette strategie",
    sellWhen: "Take Profit ou Stop Loss atteint",
    risk: 'Unknown',
    timeframe: '1h',
    flags: []
  };
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<StrategyStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<'pnl' | 'win_rate' | 'trades' | 'name'>('pnl');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [filterCategory, setFilterCategory] = useState<string>('All');
  const [showOnlyActive, setShowOnlyActive] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyStats | null>(null);

  useEffect(() => {
    const fetchStrategies = async () => {
      try {
        const res = await fetch('/api/strategy-stats');
        const data = await res.json();
        setStrategies(Array.isArray(data) ? data : []);
      } catch (e) {
        console.error('Failed to fetch strategies:', e);
      }
      setLoading(false);
    };
    fetchStrategies();
  }, []);

  // Calculate totals
  const totals = useMemo(() => {
    const totalPnl = strategies.reduce((sum, s) => sum + s.pnl, 0);
    const totalTrades = strategies.reduce((sum, s) => sum + s.total_trades, 0);
    const totalWins = strategies.reduce((sum, s) => sum + s.wins, 0);
    const avgWinRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0;
    const profitable = strategies.filter(s => s.pnl > 0).length;
    const losing = strategies.filter(s => s.pnl < 0).length;
    return { totalPnl, totalTrades, avgWinRate, profitable, losing };
  }, [strategies]);

  // Filter and sort
  const filteredStrategies = useMemo(() => {
    let result = [...strategies];

    // Search filter
    if (search) {
      result = result.filter(s =>
        s.strategy_id.toLowerCase().includes(search.toLowerCase())
      );
    }

    // Category filter
    if (filterCategory !== 'All') {
      result = result.filter(s => getCategory(s.strategy_id) === filterCategory);
    }

    // Active filter
    if (showOnlyActive) {
      result = result.filter(s => s.active);
    }

    // Sort
    result.sort((a, b) => {
      let cmp = 0;
      switch (sortBy) {
        case 'pnl': cmp = a.pnl - b.pnl; break;
        case 'win_rate': cmp = a.win_rate - b.win_rate; break;
        case 'trades': cmp = a.total_trades - b.total_trades; break;
        case 'name': cmp = a.strategy_id.localeCompare(b.strategy_id); break;
      }
      return sortDir === 'desc' ? -cmp : cmp;
    });

    return result;
  }, [strategies, search, filterCategory, showOnlyActive, sortBy, sortDir]);

  // Get unique categories
  const categories = useMemo(() => {
    const cats = new Set<string>();
    strategies.forEach(s => cats.add(getCategory(s.strategy_id)));
    return ['All', ...Array.from(cats).sort()];
  }, [strategies]);

  const handleSort = (field: typeof sortBy) => {
    if (sortBy === field) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    } else {
      setSortBy(field);
      setSortDir('desc');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="text-white text-xl animate-pulse">Loading strategies...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      <Header />

      <div className="p-6">
      {/* Page Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold">Strategies</h1>
          <span className="text-gray-400">({strategies.length} total)</span>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-5 gap-4 mb-6">
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Total P&L (7d)</div>
          <div className={`text-2xl font-bold ${totals.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${totals.totalPnl >= 0 ? '+' : ''}{totals.totalPnl.toFixed(2)}
          </div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Total Trades</div>
          <div className="text-2xl font-bold">{totals.totalTrades}</div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Avg Win Rate</div>
          <div className={`text-2xl font-bold ${totals.avgWinRate >= 50 ? 'text-green-400' : 'text-yellow-400'}`}>
            {totals.avgWinRate.toFixed(1)}%
          </div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Profitable</div>
          <div className="text-2xl font-bold text-green-400">{totals.profitable}</div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Losing</div>
          <div className="text-2xl font-bold text-red-400">{totals.losing}</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-6">
        <input
          type="text"
          placeholder="Search strategies..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="bg-[#1a1a2e] border border-gray-700 rounded px-3 py-2 w-64 focus:outline-none focus:border-blue-500"
        />
        <select
          value={filterCategory}
          onChange={e => setFilterCategory(e.target.value)}
          className="bg-[#1a1a2e] border border-gray-700 rounded px-3 py-2 focus:outline-none"
        >
          {categories.map(cat => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showOnlyActive}
            onChange={e => setShowOnlyActive(e.target.checked)}
            className="w-4 h-4"
          />
          <span className="text-sm">Active only</span>
        </label>
        <div className="text-gray-400 text-sm ml-auto">
          Showing {filteredStrategies.length} strategies
        </div>
      </div>

      {/* Table */}
      <div className="bg-[#1a1a2e] rounded-lg overflow-hidden">
        <table className="w-full">
          <thead className="bg-[#252540]">
            <tr>
              <th
                className="text-left px-4 py-3 cursor-pointer hover:bg-[#2a2a4a]"
                onClick={() => handleSort('name')}
              >
                Strategy {sortBy === 'name' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th className="text-left px-4 py-3">Category</th>
              <th className="text-center px-4 py-3">Portfolios</th>
              <th
                className="text-center px-4 py-3 cursor-pointer hover:bg-[#2a2a4a]"
                onClick={() => handleSort('trades')}
              >
                Trades {sortBy === 'trades' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th
                className="text-center px-4 py-3 cursor-pointer hover:bg-[#2a2a4a]"
                onClick={() => handleSort('win_rate')}
              >
                Win Rate {sortBy === 'win_rate' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th
                className="text-right px-4 py-3 cursor-pointer hover:bg-[#2a2a4a]"
                onClick={() => handleSort('pnl')}
              >
                P&L (7d) {sortBy === 'pnl' && (sortDir === 'desc' ? '↓' : '↑')}
              </th>
              <th className="text-center px-4 py-3">Exit Reasons</th>
              <th className="text-center px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredStrategies.map((s, i) => (
              <tr
                key={s.strategy_id}
                className={`border-t border-gray-800 hover:bg-[#252540] cursor-pointer ${i % 2 === 0 ? 'bg-[#1a1a2e]' : 'bg-[#161625]'}`}
                onClick={() => setSelectedStrategy(s)}
              >
                <td className="px-4 py-3 font-mono text-sm">{s.strategy_id}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-1 bg-[#2a2a4a] rounded text-xs">
                    {getCategory(s.strategy_id)}
                  </span>
                </td>
                <td className="text-center px-4 py-3">{s.portfolios}</td>
                <td className="text-center px-4 py-3">
                  <span className="text-green-400">{s.wins}W</span>
                  <span className="text-gray-500 mx-1">/</span>
                  <span className="text-red-400">{s.losses}L</span>
                </td>
                <td className="text-center px-4 py-3">
                  <span className={`font-bold ${s.win_rate >= 50 ? 'text-green-400' : s.win_rate >= 35 ? 'text-yellow-400' : 'text-red-400'}`}>
                    {s.win_rate.toFixed(1)}%
                  </span>
                </td>
                <td className={`text-right px-4 py-3 font-bold ${s.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ${s.pnl >= 0 ? '+' : ''}{s.pnl.toFixed(2)}
                </td>
                <td className="text-center px-4 py-3">
                  <div className="flex items-center justify-center gap-1">
                    {Object.entries(s.exit_reasons).slice(0, 3).map(([type, count]) => (
                      <span
                        key={type}
                        className={`px-1.5 py-0.5 rounded text-xs ${
                          type === 'TP' ? 'bg-green-900 text-green-300' :
                          type === 'SL' ? 'bg-red-900 text-red-300' :
                          type === 'TIME' ? 'bg-yellow-900 text-yellow-300' :
                          'bg-gray-700 text-gray-300'
                        }`}
                        title={`${type}: ${count}`}
                      >
                        {type}:{count}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="text-center px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs ${s.active ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}`}>
                    {s.active ? 'Active' : 'Inactive'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filteredStrategies.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            No strategies found matching your filters
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="mt-4 flex items-center gap-6 text-sm text-gray-400">
        <span>Exit Reasons:</span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-green-900 rounded"></span> TP = Take Profit
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-red-900 rounded"></span> SL = Stop Loss
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-yellow-900 rounded"></span> TIME = Time Exit
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-gray-700 rounded"></span> Other = Signal/Trail
        </span>
      </div>
      </div>

      {/* Strategy Detail Modal */}
      {selectedStrategy && (
        <div
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedStrategy(null)}
        >
          <div
            className="bg-[#1a1a2e] rounded-2xl border border-gray-700 w-full max-w-3xl max-h-[90vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="p-6 border-b border-gray-700 sticky top-0 bg-[#1a1a2e] z-10">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-2xl font-bold font-mono">{selectedStrategy.strategy_id}</h2>
                  <div className="flex items-center gap-3 mt-2">
                    <span className="px-2 py-1 bg-[#2a2a4a] rounded text-xs">{getCategory(selectedStrategy.strategy_id)}</span>
                    <span className={`px-2 py-1 rounded text-xs ${selectedStrategy.active ? 'bg-green-900 text-green-300' : 'bg-gray-700 text-gray-400'}`}>
                      {selectedStrategy.active ? 'Active' : 'Inactive'}
                    </span>
                    <span className={`px-2 py-1 rounded text-xs ${
                      getStrategyInfo(selectedStrategy.strategy_id).risk === 'Low' ? 'bg-green-900 text-green-300' :
                      getStrategyInfo(selectedStrategy.strategy_id).risk === 'Medium' ? 'bg-yellow-900 text-yellow-300' :
                      getStrategyInfo(selectedStrategy.strategy_id).risk === 'High' ? 'bg-orange-900 text-orange-300' :
                      'bg-red-900 text-red-300'
                    }`}>
                      Risk: {getStrategyInfo(selectedStrategy.strategy_id).risk}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedStrategy(null)}
                  className="text-gray-500 hover:text-white text-2xl leading-none p-2"
                >
                  &times;
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="p-6 space-y-6">
              {/* Description */}
              <div className="bg-black/20 rounded-xl p-4">
                <div className="text-sm text-gray-400 mb-2">Comment ca marche ?</div>
                <div className="text-white text-lg">{getStrategyInfo(selectedStrategy.strategy_id).descriptionFR}</div>
                <div className="mt-3 flex gap-4 text-sm">
                  <span className="text-gray-400">Timeframe: <span className="text-white">{getStrategyInfo(selectedStrategy.strategy_id).timeframe}</span></span>
                  {getStrategyInfo(selectedStrategy.strategy_id).flags.length > 0 && (
                    <span className="text-gray-400">
                      Flags: {getStrategyInfo(selectedStrategy.strategy_id).flags.map(f => (
                        <span key={f} className="ml-1 px-1.5 py-0.5 bg-purple-900/50 text-purple-300 rounded text-xs">{f}</span>
                      ))}
                    </span>
                  )}
                </div>
              </div>

              {/* Buy/Sell Conditions */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-green-900/20 border border-green-700/50 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-green-400 text-xl">&#9650;</span>
                    <span className="text-green-400 font-semibold">Achete quand</span>
                  </div>
                  <div className="text-white">{getStrategyInfo(selectedStrategy.strategy_id).buyWhen}</div>
                </div>
                <div className="bg-red-900/20 border border-red-700/50 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-red-400 text-xl">&#9660;</span>
                    <span className="text-red-400 font-semibold">Vend quand</span>
                  </div>
                  <div className="text-white">{getStrategyInfo(selectedStrategy.strategy_id).sellWhen}</div>
                </div>
              </div>

              {/* P&L Banner */}
              <div className={`p-5 rounded-xl ${selectedStrategy.pnl >= 0 ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
                <div className="flex justify-between items-center">
                  <div>
                    <div className="text-sm text-gray-400">Total P&L</div>
                    <div className={`text-4xl font-bold ${selectedStrategy.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {selectedStrategy.pnl >= 0 ? '+' : ''}${selectedStrategy.pnl.toFixed(2)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-gray-400">Win Rate</div>
                    <div className={`text-3xl font-bold ${selectedStrategy.win_rate >= 50 ? 'text-green-400' : 'text-yellow-400'}`}>
                      {selectedStrategy.win_rate.toFixed(1)}%
                    </div>
                  </div>
                </div>
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-black/20 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase">Total Trades</div>
                  <div className="text-2xl font-bold">{selectedStrategy.total_trades}</div>
                </div>
                <div className="bg-black/20 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase">Wins</div>
                  <div className="text-2xl font-bold text-green-400">{selectedStrategy.wins}</div>
                </div>
                <div className="bg-black/20 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase">Losses</div>
                  <div className="text-2xl font-bold text-red-400">{selectedStrategy.losses}</div>
                </div>
                <div className="bg-black/20 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase">Portfolios</div>
                  <div className="text-2xl font-bold text-purple-400">{selectedStrategy.portfolios}</div>
                </div>
              </div>

              {/* Avg P&L per trade */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-black/20 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase">Avg P&L / Trade</div>
                  <div className={`text-xl font-bold ${(selectedStrategy.pnl / Math.max(1, selectedStrategy.total_trades)) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${(selectedStrategy.pnl / Math.max(1, selectedStrategy.total_trades)).toFixed(2)}
                  </div>
                </div>
                <div className="bg-black/20 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase">Profit Factor</div>
                  <div className="text-xl font-bold text-blue-400">
                    {selectedStrategy.losses > 0 ? (selectedStrategy.wins / selectedStrategy.losses).toFixed(2) : 'N/A'}
                  </div>
                </div>
                <div className="bg-black/20 rounded-lg p-4">
                  <div className="text-xs text-gray-500 uppercase">Expectancy</div>
                  <div className={`text-xl font-bold ${(selectedStrategy.win_rate / 100 * 2 - 1) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {((selectedStrategy.win_rate / 100) * 1.5 - (1 - selectedStrategy.win_rate / 100)).toFixed(2)}
                  </div>
                </div>
              </div>

              {/* Exit Reasons */}
              <div className="bg-black/20 rounded-xl p-4">
                <div className="text-sm text-gray-400 mb-3">Exit Reasons Breakdown</div>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(selectedStrategy.exit_reasons).map(([type, count]) => {
                    const total = Object.values(selectedStrategy.exit_reasons).reduce((a, b) => a + b, 0);
                    const pct = total > 0 ? (count / total * 100).toFixed(1) : '0';
                    return (
                      <div
                        key={type}
                        className={`px-4 py-3 rounded-lg ${
                          type === 'TP' || type.includes('TP') ? 'bg-green-900/30 border border-green-700' :
                          type === 'SL' || type.includes('SL') ? 'bg-red-900/30 border border-red-700' :
                          type === 'TIME' || type.includes('TIME') ? 'bg-yellow-900/30 border border-yellow-700' :
                          type === 'TRAIL' || type.includes('TRAIL') ? 'bg-blue-900/30 border border-blue-700' :
                          'bg-gray-800 border border-gray-700'
                        }`}
                      >
                        <div className="text-lg font-bold">{count}</div>
                        <div className="text-xs text-gray-400">{type} ({pct}%)</div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Visual Win/Loss Bar */}
              <div className="bg-black/20 rounded-xl p-4">
                <div className="text-sm text-gray-400 mb-3">Win/Loss Distribution</div>
                <div className="h-8 rounded-full overflow-hidden flex">
                  <div
                    className="bg-green-500 h-full flex items-center justify-center text-xs font-bold"
                    style={{ width: `${selectedStrategy.win_rate}%` }}
                  >
                    {selectedStrategy.win_rate > 15 && `${selectedStrategy.wins}W`}
                  </div>
                  <div
                    className="bg-red-500 h-full flex items-center justify-center text-xs font-bold"
                    style={{ width: `${100 - selectedStrategy.win_rate}%` }}
                  >
                    {selectedStrategy.win_rate < 85 && `${selectedStrategy.losses}L`}
                  </div>
                </div>
              </div>

              {/* Recommendations */}
              <div className="bg-black/20 rounded-xl p-4">
                <div className="text-sm text-gray-400 mb-3">Recommendations</div>
                <div className="space-y-2 text-sm">
                  {selectedStrategy.win_rate < 40 && (
                    <div className="flex items-start gap-2 text-red-400">
                      <span>!</span>
                      <span>Low win rate - consider tightening entry conditions or widening TP</span>
                    </div>
                  )}
                  {selectedStrategy.win_rate >= 60 && selectedStrategy.pnl < 0 && (
                    <div className="flex items-start gap-2 text-yellow-400">
                      <span>!</span>
                      <span>High win rate but negative P&L - losses are too big, tighten SL</span>
                    </div>
                  )}
                  {selectedStrategy.win_rate >= 50 && selectedStrategy.pnl > 0 && (
                    <div className="flex items-start gap-2 text-green-400">
                      <span>+</span>
                      <span>Strategy performing well - consider increasing allocation</span>
                    </div>
                  )}
                  {selectedStrategy.total_trades < 10 && (
                    <div className="flex items-start gap-2 text-gray-400">
                      <span>i</span>
                      <span>Low sample size - need more trades for reliable statistics</span>
                    </div>
                  )}
                  {Object.keys(selectedStrategy.exit_reasons).includes('SL') &&
                   selectedStrategy.exit_reasons['SL'] > selectedStrategy.exit_reasons['TP'] && (
                    <div className="flex items-start gap-2 text-orange-400">
                      <span>!</span>
                      <span>More SL exits than TP - consider widening SL or tightening entries</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
