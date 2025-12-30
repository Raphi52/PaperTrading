'use client';

import { useEffect, useState, useCallback, useMemo, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { Portfolio } from '@/lib/types';
import { XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Area, AreaChart, ComposedChart, Bar, Cell } from 'recharts';

interface PortfolioHistory {
  portfolios: Record<string, {
    name: string;
    initial_capital: number;
    history: { timestamp: string; value: number }[];
  }>;
}

interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

// Candlestick Chart Component
function CandlestickChart({ symbol, entryPrice, entryTime, tpPct = 20, slPct = 10 }: {
  symbol: string;
  entryPrice: number;
  entryTime: string;
  tpPct?: number;
  slPct?: number;
}) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchCandles = async () => {
      try {
        const since = new Date(entryTime).getTime();
        const res = await fetch(`/api/klines?symbol=${encodeURIComponent(symbol)}&since=${since}`);
        const data = await res.json();
        setCandles(data);
      } catch (e) {
        console.error('Failed to fetch candles:', e);
      }
      setLoading(false);
    };
    fetchCandles();
  }, [symbol, entryTime]);

  if (loading) {
    return (
      <div className="h-[280px] flex items-center justify-center text-gray-500 bg-[#0d1117] rounded-lg">
        <div className="animate-pulse">Loading chart...</div>
      </div>
    );
  }

  if (candles.length < 2) {
    return (
      <div className="h-[280px] flex items-center justify-center text-gray-500 text-sm bg-[#0d1117] rounded-lg">
        Pas assez de donnees
      </div>
    );
  }

  const tpPrice = entryPrice * (1 + tpPct / 100);
  const slPrice = entryPrice * (1 - slPct / 100);

  // Calculate min/max for Y axis with padding
  const allPrices = candles.flatMap(c => [c.high, c.low]);
  const priceMin = Math.min(...allPrices, slPrice);
  const priceMax = Math.max(...allPrices, tpPrice);
  const priceRange = priceMax - priceMin;
  const minPrice = priceMin - priceRange * 0.05;
  const maxPrice = priceMax + priceRange * 0.05;

  // Get date labels (first, middle, last)
  const formatDate = (ts: number) => {
    const d = new Date(ts);
    return `${d.getDate().toString().padStart(2, '0')}/${(d.getMonth() + 1).toString().padStart(2, '0')} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  const dateLabels = [
    { idx: 0, label: formatDate(candles[0].time) },
    { idx: Math.floor(candles.length / 2), label: formatDate(candles[Math.floor(candles.length / 2)].time) },
    { idx: candles.length - 1, label: formatDate(candles[candles.length - 1].time) },
  ];

  // Chart dimensions
  const chartHeight = 200;
  const chartWidth = 400;
  const margin = { top: 15, right: 60, bottom: 30, left: 10 };
  const innerWidth = chartWidth - margin.left - margin.right;
  const innerHeight = chartHeight - margin.top - margin.bottom;

  // Scale functions
  const xScale = (i: number) => margin.left + (i / Math.max(1, candles.length - 1)) * innerWidth;
  const yScale = (price: number) => margin.top + (1 - (price - minPrice) / (maxPrice - minPrice)) * innerHeight;

  // Candle width based on number of candles
  const gap = innerWidth / candles.length;
  const candleW = Math.max(2, Math.min(8, gap * 0.8));

  const formatPrice = (p: number) => p < 1 ? p.toFixed(6) : p < 100 ? p.toFixed(2) : p.toFixed(0);

  return (
    <div className="bg-[#0d1117] rounded-lg p-3">
      <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-[280px]" preserveAspectRatio="xMidYMid meet">
        {/* Background grid */}
        {[0, 0.25, 0.5, 0.75, 1].map(pct => (
          <line
            key={pct}
            x1={margin.left}
            y1={margin.top + pct * innerHeight}
            x2={chartWidth - margin.right}
            y2={margin.top + pct * innerHeight}
            stroke="#1e293b"
            strokeWidth="1"
          />
        ))}

        {/* TP Line (green) */}
        <line
          x1={margin.left}
          y1={yScale(tpPrice)}
          x2={chartWidth - margin.right}
          y2={yScale(tpPrice)}
          stroke="#22c55e"
          strokeWidth="1"
          strokeDasharray="6,4"
        />
        <rect x={chartWidth - margin.right + 5} y={yScale(tpPrice) - 10} width="50" height="20" fill="#22c55e" rx="4" />
        <text x={chartWidth - margin.right + 30} y={yScale(tpPrice)} fill="#000" fontSize="11" textAnchor="middle" dominantBaseline="middle" fontWeight="bold">
          TP +{tpPct}%
        </text>

        {/* Entry Line (orange dashed) */}
        <line
          x1={margin.left}
          y1={yScale(entryPrice)}
          x2={chartWidth - margin.right}
          y2={yScale(entryPrice)}
          stroke="#f59e0b"
          strokeWidth="1.5"
          strokeDasharray="4,3"
        />
        <rect x={chartWidth - margin.right + 5} y={yScale(entryPrice) - 10} width="50" height="20" fill="#f59e0b" rx="4" />
        <text x={chartWidth - margin.right + 30} y={yScale(entryPrice)} fill="#000" fontSize="10" textAnchor="middle" dominantBaseline="middle" fontWeight="bold">
          ENTRY
        </text>

        {/* SL Line (red) */}
        <line
          x1={margin.left}
          y1={yScale(slPrice)}
          x2={chartWidth - margin.right}
          y2={yScale(slPrice)}
          stroke="#ef4444"
          strokeWidth="1"
          strokeDasharray="6,4"
        />
        <rect x={chartWidth - margin.right + 5} y={yScale(slPrice) - 10} width="50" height="20" fill="#ef4444" rx="4" />
        <text x={chartWidth - margin.right + 30} y={yScale(slPrice)} fill="#fff" fontSize="11" textAnchor="middle" dominantBaseline="middle" fontWeight="bold">
          SL -{slPct}%
        </text>

        {/* Candlesticks */}
        {candles.map((candle, i) => {
          const x = xScale(i);
          const isGreen = candle.close >= candle.open;
          const color = isGreen ? '#22c55e' : '#ef4444';
          const bodyTop = yScale(Math.max(candle.open, candle.close));
          const bodyBottom = yScale(Math.min(candle.open, candle.close));
          const bodyH = Math.max(2, bodyBottom - bodyTop);

          return (
            <g key={i}>
              {/* Wick */}
              <line
                x1={x}
                y1={yScale(candle.high)}
                x2={x}
                y2={yScale(candle.low)}
                stroke={color}
                strokeWidth="1"
              />
              {/* Body */}
              <rect
                x={x - candleW / 2}
                y={bodyTop}
                width={candleW}
                height={bodyH}
                fill={color}
                rx="1"
              />
            </g>
          );
        })}

        {/* Current price line */}
        {candles.length > 0 && (
          <>
            <line
              x1={margin.left}
              y1={yScale(candles[candles.length - 1].close)}
              x2={chartWidth - margin.right}
              y2={yScale(candles[candles.length - 1].close)}
              stroke="#3b82f6"
              strokeWidth="1.5"
              strokeDasharray="4,3"
            />
            <rect x={chartWidth - margin.right + 5} y={yScale(candles[candles.length - 1].close) - 10} width="50" height="20" fill="#3b82f6" rx="4" />
            <text x={chartWidth - margin.right + 30} y={yScale(candles[candles.length - 1].close)} fill="#fff" fontSize="10" textAnchor="middle" dominantBaseline="middle" fontWeight="bold">
              NOW
            </text>
          </>
        )}

        {/* Date labels at bottom */}
        {dateLabels.map(({ idx, label }) => (
          <text
            key={idx}
            x={xScale(idx)}
            y={chartHeight - 8}
            fill="#94a3b8"
            fontSize="11"
            textAnchor="middle"
          >
            {label}
          </text>
        ))}
      </svg>
    </div>
  );
}

// Strategy icons mapping
const STRATEGY_ICONS: Record<string, string> = {
  'rsi': '📈', 'ema': '📊', 'macd': '📉', 'bollinger': '🔒', 'bb': '🔒',
  'degen': '🔥', 'scalp': '⚡', 'whale': '🐋', 'sniper': '🎯', 'grid': '📏',
  'ichimoku': '☁️', 'confluence': '🎯', 'hodl': '💎', 'momentum': '🚀',
  'breakout': '💥', 'mean_rev': '🔄', 'vwap': '📊', 'supertrend': '🚀',
  'stoch': '📉', 'trend': '📈', 'swing': '🎢', 'dca': '💰', 'martingale': '🎰',
  'congress': '🏛️', 'legend': '📖', 'trailing': '🎯', 'fib': '📐',
  'order_block': '🧱', 'liquidity': '💧', 'session': '🌐', 'fear_greed': '😱',
  'social': '📱', 'obv': '📊', 'volume': '📊', 'funding': '💹', 'oi': '📈',
};

const getStrategyIcon = (strategyId: string): string => {
  for (const [key, icon] of Object.entries(STRATEGY_ICONS)) {
    if (strategyId.toLowerCase().includes(key)) return icon;
  }
  return '📊';
};

// Strategy categories
const STRATEGY_CATEGORIES: Record<string, string[]> = {
  'All': [],
  '🐋 Whales': ['whale'],
  '🏛️ Congress': ['congress'],
  '📖 Legends': ['legend'],
  '🎯 Sniper': ['sniper'],
  '🔥 Degen': ['degen', 'god_mode'],
  '📈 RSI': ['rsi'],
  '📊 EMA/Trend': ['ema', 'trend', 'supertrend'],
  '☁️ Ichimoku': ['ichimoku'],
  '📉 MACD/Stoch': ['macd', 'stoch'],
  '🔒 Bollinger': ['bollinger', 'bb'],
  '📏 Grid': ['grid', 'range'],
  '⚡ Scalping': ['scalp'],
  '💰 DCA': ['dca'],
  '💥 Breakout': ['breakout'],
};

function DashboardContent() {
  const searchParams = useSearchParams();
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'portfolios'>(
    searchParams.get('tab') === 'portfolios' ? 'portfolios' : 'dashboard'
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<'pnl_pct' | 'pnl_usd' | 'worst' | 'value' | 'name' | 'positions'>('pnl_pct');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [currentPage, setCurrentPage] = useState(1);
  const [fearGreed, setFearGreed] = useState({ value: 0, text: 'Loading...' });
  const [showTradesModal, setShowTradesModal] = useState(false);
  const [selectedPortfolio, setSelectedPortfolio] = useState<Portfolio | null>(null);
  const [portfolioHistory, setPortfolioHistory] = useState<PortfolioHistory | null>(null);
  const [strategies, setStrategies] = useState<Record<string, { take_profit: number; stop_loss: number }>>({});
  const PORTFOLIOS_PER_PAGE = 30;

  // Fetch Fear & Greed
  useEffect(() => {
    fetch('https://api.alternative.me/fng/?limit=1')
      .then(r => r.json())
      .then(data => {
        const fg = data.data?.[0];
        if (fg) setFearGreed({ value: parseInt(fg.value), text: fg.value_classification });
      })
      .catch(() => setFearGreed({ value: 50, text: 'Neutral' }));
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const [portfoliosData, pricesData, historyData, strategiesData] = await Promise.all([
        api.getPortfolios(),
        api.getPrices(),
        fetch('/api/history').then(r => r.json()),
        fetch('/api/strategies').then(r => r.json()),
      ]);
      setPortfolios(portfoliosData);
      setPrices(pricesData);
      setPortfolioHistory(historyData);
      setStrategies(strategiesData);
      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch data:', error);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Calculate portfolio value with live prices
  const calculatePortfolioValue = useCallback((p: Portfolio) => {
    let total = p.balance?.['USDT'] || 0;
    for (const [symbol, pos] of Object.entries(p.positions || {})) {
      const price = prices[symbol] || pos.current_price || pos.entry_price;
      total += (pos.quantity || 0) * price;
    }
    return total;
  }, [prices]);

  // Memoized calculations
  const stats = useMemo(() => {
    const totalValue = portfolios.reduce((sum, p) => sum + calculatePortfolioValue(p), 0);
    const totalInitial = portfolios.reduce((sum, p) => sum + (p.initial_capital || 10000), 0);
    const totalPnl = totalValue - totalInitial;
    const totalPnlPct = totalInitial > 0 ? ((totalPnl / totalInitial) * 100) : 0;
    const winningCount = portfolios.filter(p => calculatePortfolioValue(p) > p.initial_capital).length;
    const winRate = portfolios.length > 0 ? (winningCount / portfolios.length) * 100 : 0;
    const totalPositions = portfolios.reduce((sum, p) => sum + Object.keys(p.positions || {}).length, 0);
    const totalTrades = portfolios.reduce((sum, p) => sum + (p.trades || []).length, 0);
    const activePortfolios = portfolios.filter(p => p.active).length;

    return { totalValue, totalInitial, totalPnl, totalPnlPct, winningCount, winRate, totalPositions, totalTrades, activePortfolios };
  }, [portfolios, calculatePortfolioValue]);

  // Best & Worst performers
  const { bestPerformers, worstPerformers } = useMemo(() => {
    const sorted = [...portfolios].sort((a, b) => {
      const pnlA = ((calculatePortfolioValue(a) - a.initial_capital) / a.initial_capital) * 100;
      const pnlB = ((calculatePortfolioValue(b) - b.initial_capital) / b.initial_capital) * 100;
      return pnlB - pnlA;
    });
    return {
      bestPerformers: sorted.slice(0, 5),
      worstPerformers: sorted.slice(-5).reverse(),
    };
  }, [portfolios, calculatePortfolioValue]);

  // Recent trades
  const allTrades = useMemo(() => {
    return portfolios.flatMap(p =>
      (p.trades || []).map(t => ({ ...t, portfolio: p.name, portfolioId: p.id }))
    ).sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [portfolios]);

  // Top held coins
  const topHeldCoins = useMemo(() => {
    const held: Record<string, { count: number; totalValue: number }> = {};
    portfolios.forEach(p => {
      Object.entries(p.positions || {}).forEach(([symbol, pos]) => {
        if (!held[symbol]) held[symbol] = { count: 0, totalValue: 0 };
        held[symbol].count++;
        held[symbol].totalValue += (pos.quantity || 0) * (prices[symbol] || pos.current_price || 0);
      });
    });
    return Object.entries(held)
      .sort((a, b) => b[1].totalValue - a[1].totalValue)
      .slice(0, 10)
      .map(([symbol, data]) => ({ symbol, ...data, price: prices[symbol] || 0 }));
  }, [portfolios, prices]);

  // Filter and sort portfolios
  const filteredPortfolios = useMemo(() => {
    let filtered = portfolios.filter(p => {
      const matchesSearch = p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        p.strategy_id.toLowerCase().includes(searchQuery.toLowerCase());

      if (selectedCategory === 'All') return matchesSearch;

      const categoryKeywords = STRATEGY_CATEGORIES[selectedCategory] || [];
      const matchesCategory = categoryKeywords.some(kw => p.strategy_id.toLowerCase().includes(kw));
      return matchesSearch && matchesCategory;
    });

    return filtered.sort((a, b) => {
      const valA = calculatePortfolioValue(a);
      const valB = calculatePortfolioValue(b);
      const pnlA = valA - a.initial_capital;
      const pnlB = valB - b.initial_capital;
      const pnlPctA = (pnlA / a.initial_capital) * 100;
      const pnlPctB = (pnlB / b.initial_capital) * 100;
      const posCountA = Object.keys(a.positions || {}).length;
      const posCountB = Object.keys(b.positions || {}).length;

      switch (sortBy) {
        case 'pnl_pct': return pnlPctB - pnlPctA;
        case 'pnl_usd': return pnlB - pnlA;
        case 'worst': return pnlPctA - pnlPctB;
        case 'value': return valB - valA;
        case 'name': return a.name.localeCompare(b.name);
        case 'positions': return posCountB - posCountA;
        default: return 0;
      }
    });
  }, [portfolios, searchQuery, selectedCategory, sortBy, calculatePortfolioValue]);

  // Pagination
  const totalPages = Math.ceil(filteredPortfolios.length / PORTFOLIOS_PER_PAGE);
  const paginatedPortfolios = filteredPortfolios.slice(
    (currentPage - 1) * PORTFOLIOS_PER_PAGE,
    currentPage * PORTFOLIOS_PER_PAGE
  );

  // Daily performance
  const dailyPerformance = useMemo(() => {
    const today = new Date().toDateString();
    const todayTrades = allTrades.filter(t =>
      new Date(t.timestamp).toDateString() === today && t.action === 'SELL'
    );
    const todayPnl = todayTrades.reduce((sum, t) => sum + (t.pnl || 0), 0);
    const todayWins = todayTrades.filter(t => (t.pnl || 0) > 0).length;
    return { trades: todayTrades.length, pnl: todayPnl, wins: todayWins };
  }, [allTrades]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <div className="text-white text-xl">Chargement des portfolios...</div>
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-[#0a0a0f] text-white">
      {/* Header */}
      <header className="bg-gradient-to-r from-[#0f0f1a] to-[#1a1a2e] border-b border-gray-800 sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-4 py-3">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-8">
              <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                Trading Bot
              </h1>
              <nav className="flex items-center gap-1">
                <button
                  onClick={() => setActiveTab('dashboard')}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'dashboard'
                      ? 'text-white bg-white/10'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  Dashboard
                </button>
                <button
                  onClick={() => setActiveTab('portfolios')}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'portfolios'
                      ? 'text-white bg-white/10'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  Portfolios
                </button>
                <a
                  href="/positions"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Positions
                </a>
                <a
                  href="/trades"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Trades
                </a>
                <a
                  href="/strategies"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Strategies
                </a>
                <a
                  href="/analytics"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Analytics
                </a>
                <a
                  href="/settings"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Settings
                </a>
              </nav>
            </div>
            <div className="flex items-center gap-3">
              <div className="hidden md:flex items-center gap-2 text-sm">
                <span className="text-gray-500">BTC</span>
                <span className="font-mono font-bold">${(prices['BTC/USDT'] || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                <span className="text-gray-500 ml-2">ETH</span>
                <span className="font-mono font-bold">${(prices['ETH/USDT'] || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
              </div>
              <div className="w-px h-6 bg-gray-700 hidden md:block"></div>
              <span className="px-3 py-1.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400 border border-green-500/30">
                Live
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Global Stats Bar */}
      <div className="bg-gradient-to-r from-[#1a1a2e] via-[#16213e] to-[#1a1a2e] border-b border-gray-800">
        <div className="max-w-[1600px] mx-auto px-4 py-5">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {/* Total Value */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Total Value</div>
              <div className="text-2xl md:text-3xl font-bold">${stats.totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
            </div>

            {/* P&L */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">P&L Total</div>
              <div className={`text-2xl md:text-3xl font-bold ${stats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.totalPnl >= 0 ? '+' : ''}${stats.totalPnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
              <div className={`text-sm ${stats.totalPnl >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                {stats.totalPnlPct >= 0 ? '+' : ''}{stats.totalPnlPct.toFixed(2)}%
              </div>
            </div>

            {/* Win Rate */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Win Rate</div>
              <div className={`text-2xl md:text-3xl font-bold ${stats.winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.winRate.toFixed(0)}%
              </div>
              <div className="text-sm text-gray-500">{stats.winningCount}/{portfolios.length} profitable</div>
            </div>

            {/* Portfolios */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Portfolios</div>
              <div className="text-2xl md:text-3xl font-bold text-blue-400">{portfolios.length}</div>
              <div className="text-sm text-gray-500">{stats.activePortfolios} actifs</div>
            </div>

            {/* Positions */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Positions</div>
              <div className="text-2xl md:text-3xl font-bold text-purple-400">{stats.totalPositions}</div>
              <div className="text-sm text-gray-500">{stats.totalTrades} trades</div>
            </div>

            {/* Fear & Greed */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Fear & Greed</div>
              <div className={`text-2xl md:text-3xl font-bold ${
                fearGreed.value < 30 ? 'text-red-400' : fearGreed.value < 50 ? 'text-orange-400' : fearGreed.value < 70 ? 'text-yellow-400' : 'text-green-400'
              }`}>{fearGreed.value}</div>
              <div className={`text-sm ${
                fearGreed.value < 30 ? 'text-red-400/70' : fearGreed.value < 50 ? 'text-orange-400/70' : fearGreed.value < 70 ? 'text-yellow-400/70' : 'text-green-400/70'
              }`}>{fearGreed.text}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-[1600px] mx-auto p-4">
        {activeTab === 'dashboard' ? (
          <div className="space-y-6">
            {/* Market Overview */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
              {['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'AVAX'].map(coin => {
                const price = prices[`${coin}/USDT`] || 0;
                return (
                  <div key={coin} className="bg-gray-800/50 rounded-xl p-3 border border-gray-700/50 hover:border-gray-600 transition-all hover:bg-gray-800">
                    <div className="text-xs text-gray-400 mb-1">{coin}</div>
                    <div className="font-bold font-mono">
                      ${price < 1 ? price.toFixed(4) : price < 100 ? price.toFixed(2) : price.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left Column - 2/3 */}
              <div className="lg:col-span-2 space-y-6">
                {/* Top Performers */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Best */}
                  <div className="bg-gradient-to-br from-green-500/10 to-green-900/10 rounded-xl border border-green-500/20 overflow-hidden">
                    <div className="px-4 py-3 border-b border-green-500/20 flex items-center gap-2">
                      <span className="text-green-400">🏆</span>
                      <span className="font-semibold text-green-400">Top Winners</span>
                    </div>
                    <div className="p-2">
                      {bestPerformers.slice(0, 5).map((p, i) => {
                        const pnlPct = ((calculatePortfolioValue(p) - p.initial_capital) / p.initial_capital) * 100;
                        return (
                          <div key={p.id || i} className="flex items-center justify-between p-2 hover:bg-green-500/5 rounded-lg transition-colors">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-gray-500 text-sm w-4">{i + 1}</span>
                              <span className="truncate text-sm">{p.name}</span>
                            </div>
                            <span className="text-green-400 font-mono font-bold text-sm">+{pnlPct.toFixed(1)}%</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Worst */}
                  <div className="bg-gradient-to-br from-red-500/10 to-red-900/10 rounded-xl border border-red-500/20 overflow-hidden">
                    <div className="px-4 py-3 border-b border-red-500/20 flex items-center gap-2">
                      <span className="text-red-400">📉</span>
                      <span className="font-semibold text-red-400">Worst Performers</span>
                    </div>
                    <div className="p-2">
                      {worstPerformers.slice(0, 5).map((p, i) => {
                        const pnlPct = ((calculatePortfolioValue(p) - p.initial_capital) / p.initial_capital) * 100;
                        return (
                          <div key={p.id || i} className="flex items-center justify-between p-2 hover:bg-red-500/5 rounded-lg transition-colors">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-gray-500 text-sm w-4">{i + 1}</span>
                              <span className="truncate text-sm">{p.name}</span>
                            </div>
                            <span className={`font-mono font-bold text-sm ${pnlPct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Top Held Coins */}
                <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-700/50 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span>💰</span>
                      <span className="font-semibold">Top Positions</span>
                    </div>
                    <span className="text-sm text-gray-500">{stats.totalPositions} positions ouvertes</span>
                  </div>
                  <div className="p-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {topHeldCoins.map((coin, i) => (
                        <div key={coin.symbol} className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg hover:bg-gray-800 transition-colors">
                          <div className="flex items-center gap-3">
                            <span className="text-lg w-6 text-center">{i + 1}</span>
                            <div>
                              <div className="font-medium">{coin.symbol.replace('/USDT', '')}</div>
                              <div className="text-xs text-gray-500">{coin.count} portfolios</div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-mono">${coin.price < 1 ? coin.price.toFixed(6) : coin.price.toFixed(2)}</div>
                            <div className="text-xs text-gray-500">${coin.totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Recent Trades */}
                <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-700/50 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span>📜</span>
                      <span className="font-semibold">Recent Trades</span>
                    </div>
                    <a href="/trades" className="text-sm text-blue-400 hover:text-blue-300 transition-colors">
                      See more →
                    </a>
                  </div>
                  <div className="divide-y divide-gray-700/30 max-h-[400px] overflow-y-auto">
                    {allTrades.slice(0, 15).map((t, i) => (
                      <div key={i} className={`flex items-center justify-between p-3 hover:bg-gray-800/30 transition-colors border-l-4 ${
                        t.action === 'BUY' ? 'border-l-green-500' : 'border-l-red-500'
                      }`}>
                        <div className="flex items-center gap-3">
                          <span className={`text-xl ${t.action === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                            {t.action === 'BUY' ? '▲' : '▼'}
                          </span>
                          <div>
                            <div className="font-medium">{t.symbol}</div>
                            <div className="text-xs text-gray-500">{t.portfolio}</div>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-mono text-sm">${t.price < 1 ? t.price.toFixed(6) : t.price.toFixed(2)}</div>
                          {t.action === 'SELL' && (
                            <div className={`text-xs font-bold ${(t.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {(t.pnl || 0) >= 0 ? '+' : ''}${(t.pnl || 0).toFixed(2)}
                            </div>
                          )}
                        </div>
                        <div className="text-xs text-gray-500 w-20 text-right">
                          {new Date(t.timestamp).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                    ))}
                    {allTrades.length === 0 && (
                      <div className="p-8 text-center text-gray-500">Aucun trade pour le moment</div>
                    )}
                  </div>
                </div>
              </div>

              {/* Right Column - 1/3 */}
              <div className="space-y-6">
                {/* Today's Performance */}
                <div className="bg-gradient-to-br from-blue-500/10 to-purple-500/10 rounded-xl border border-blue-500/20 p-4">
                  <div className="text-sm text-gray-400 mb-3">Performance du jour</div>
                  <div className={`text-3xl font-bold mb-2 ${dailyPerformance.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {dailyPerformance.pnl >= 0 ? '+' : ''}${dailyPerformance.pnl.toFixed(2)}
                  </div>
                  <div className="flex gap-4 text-sm">
                    <span className="text-gray-400">{dailyPerformance.trades} trades</span>
                    <span className="text-green-400">{dailyPerformance.wins} wins</span>
                    <span className="text-red-400">{dailyPerformance.trades - dailyPerformance.wins} losses</span>
                  </div>
                </div>

                {/* Quick Stats */}
                <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 p-4 space-y-4">
                  <div className="text-sm text-gray-400 mb-2">Statistiques</div>

                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">Capital Initial</span>
                      <span className="font-mono">${stats.totalInitial.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">Valeur Actuelle</span>
                      <span className="font-mono">${stats.totalValue.toLocaleString()}</span>
                    </div>
                    <div className="h-px bg-gray-700"></div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">Portfolios Actifs</span>
                      <span className="text-green-400">{stats.activePortfolios}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">Portfolios Pausés</span>
                      <span className="text-gray-500">{portfolios.length - stats.activePortfolios}</span>
                    </div>
                    <div className="h-px bg-gray-700"></div>
                    <div className="flex justify-between items-center">
                      <span className="text-gray-400">Avg P&L / Portfolio</span>
                      <span className={`font-mono ${stats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${(stats.totalPnl / portfolios.length).toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Top Strategies by Performance */}
                <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 p-4">
                  <div className="text-sm text-gray-400 mb-3">Top Strategies (par P&L moyen)</div>
                  <div className="space-y-2">
                    {(() => {
                      // Group portfolios by strategy and calculate avg P&L
                      const strategyStats: Record<string, { count: number; totalPnlPct: number; icon: string }> = {};
                      portfolios.forEach(p => {
                        const stratId = p.strategy_id;
                        const value = calculatePortfolioValue(p);
                        const pnlPct = ((value - p.initial_capital) / p.initial_capital) * 100;
                        if (!strategyStats[stratId]) {
                          strategyStats[stratId] = { count: 0, totalPnlPct: 0, icon: getStrategyIcon(stratId) };
                        }
                        strategyStats[stratId].count++;
                        strategyStats[stratId].totalPnlPct += pnlPct;
                      });

                      return Object.entries(strategyStats)
                        .map(([stratId, data]) => ({
                          stratId,
                          avgPnl: data.totalPnlPct / data.count,
                          count: data.count,
                          icon: data.icon,
                        }))
                        .sort((a, b) => b.avgPnl - a.avgPnl)
                        .slice(0, 8)
                        .map((strat, i) => (
                          <div key={strat.stratId} className="flex items-center gap-2 p-2 rounded-lg hover:bg-gray-800/50 transition-colors">
                            <span className="text-gray-500 text-xs w-4">{i + 1}</span>
                            <span className="text-base">{strat.icon}</span>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm truncate" title={strat.stratId}>
                                {strat.stratId.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                              </div>
                              <div className="text-xs text-gray-500">{strat.count} portfolio{strat.count > 1 ? 's' : ''}</div>
                            </div>
                            <span className={`font-mono font-bold text-sm ${strat.avgPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {strat.avgPnl >= 0 ? '+' : ''}{strat.avgPnl.toFixed(1)}%
                            </span>
                          </div>
                        ));
                    })()}
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Filters */}
            <div className="flex flex-wrap gap-3">
              <input
                type="text"
                placeholder="Rechercher..."
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                className="flex-1 min-w-[200px] bg-gray-800/50 border border-gray-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
              <select
                value={selectedCategory}
                onChange={(e) => { setSelectedCategory(e.target.value); setCurrentPage(1); }}
                className="bg-gray-800/50 border border-gray-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500"
              >
                {Object.keys(STRATEGY_CATEGORIES).map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
              {/* Sort Radio Buttons */}
              <div className="flex flex-wrap gap-1">
                {[
                  { value: 'pnl_usd', label: '💲 P&L $' },
                  { value: 'pnl_pct', label: '📈 P&L %' },
                  { value: 'worst', label: '📉 Worst' },
                  { value: 'value', label: '💵 Value' },
                  { value: 'name', label: '🔤 A-Z' },
                  { value: 'positions', label: '📊 Positions' },
                ].map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => { setSortBy(opt.value as typeof sortBy); setCurrentPage(1); }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      sortBy === opt.value
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-800/50 text-gray-400 hover:bg-gray-700 hover:text-white'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Pagination Top */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between">
                <div className="text-sm text-gray-400">
                  {filteredPortfolios.length} portfolios • Page {currentPage}/{totalPages}
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => setCurrentPage(1)}
                    disabled={currentPage === 1}
                    className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors"
                  >
                    ««
                  </button>
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors"
                  >
                    ‹
                  </button>
                  {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
                    let page;
                    if (totalPages <= 7) page = i + 1;
                    else if (currentPage <= 4) page = i + 1;
                    else if (currentPage >= totalPages - 3) page = totalPages - 6 + i;
                    else page = currentPage - 3 + i;
                    return (
                      <button
                        key={page}
                        onClick={() => setCurrentPage(page)}
                        className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                          currentPage === page
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-800 hover:bg-gray-700'
                        }`}
                      >
                        {page}
                      </button>
                    );
                  })}
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors"
                  >
                    ›
                  </button>
                  <button
                    onClick={() => setCurrentPage(totalPages)}
                    disabled={currentPage === totalPages}
                    className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors"
                  >
                    »»
                  </button>
                </div>
              </div>
            )}

            {/* Portfolio Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {paginatedPortfolios.map((portfolio, idx) => {
                const value = calculatePortfolioValue(portfolio);
                const pnl = value - portfolio.initial_capital;
                const pnlPct = (pnl / portfolio.initial_capital) * 100;
                const posCount = Object.keys(portfolio.positions || {}).length;
                const tradeCount = (portfolio.trades || []).length;

                return (
                  <div
                    key={portfolio.id || idx}
                    className={`bg-gray-800/30 rounded-xl border overflow-hidden transition-all hover:scale-[1.02] hover:shadow-xl cursor-pointer ${
                      portfolio.active ? 'border-gray-700/50 hover:border-gray-600' : 'border-gray-800 opacity-60'
                    }`}
                    onClick={() => { setSelectedPortfolio(portfolio); setShowTradesModal(true); }}
                  >
                    {/* Header */}
                    <div className={`p-4 border-b border-gray-700/30 ${
                      pnl >= 0 ? 'bg-gradient-to-r from-green-500/5 to-transparent' : 'bg-gradient-to-r from-red-500/5 to-transparent'
                    }`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-lg">{getStrategyIcon(portfolio.strategy_id)}</span>
                            <h3 className="font-semibold truncate">{portfolio.name}</h3>
                          </div>
                          <p className="text-xs text-gray-500 truncate mt-0.5">{portfolio.strategy_id}</p>
                        </div>
                        <span className={`px-2 py-1 rounded-full text-xs font-medium shrink-0 ${
                          portfolio.active
                            ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                            : 'bg-gray-700/50 text-gray-400'
                        }`}>
                          {portfolio.active ? 'Actif' : 'Pause'}
                        </span>
                      </div>
                    </div>

                    {/* Value */}
                    <div className="p-4 space-y-3">
                      <div className="flex justify-between items-baseline">
                        <span className="text-gray-500 text-sm">Valeur</span>
                        <span className="text-xl font-bold font-mono">${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                      </div>
                      <div className="flex justify-between items-baseline">
                        <span className="text-gray-500 text-sm">P&L</span>
                        <div className="text-right">
                          <span className={`text-lg font-bold font-mono ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {pnl >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%
                          </span>
                          <span className={`text-xs ml-1 ${pnl >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
                            (${pnl >= 0 ? '+' : ''}{pnl.toFixed(0)})
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Footer */}
                    <div className="px-4 py-2.5 bg-black/20 flex justify-between text-xs text-gray-500">
                      <span>{posCount} position{posCount !== 1 ? 's' : ''}</span>
                      <span>{tradeCount} trade{tradeCount !== 1 ? 's' : ''}</span>
                    </div>

                    {/* Positions Preview */}
                    {posCount > 0 && (
                      <div className="px-4 py-2.5 border-t border-gray-700/30">
                        <div className="flex flex-wrap gap-1.5">
                          {Object.entries(portfolio.positions || {}).slice(0, 3).map(([symbol, pos]) => {
                            const currentPrice = prices[symbol] || pos.current_price || pos.entry_price;
                            const posPnlPct = pos.entry_price > 0 ? ((currentPrice - pos.entry_price) / pos.entry_price) * 100 : 0;
                            return (
                              <span
                                key={symbol}
                                className={`text-xs px-2 py-1 rounded-lg font-medium ${
                                  posPnlPct >= 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                                }`}
                              >
                                {symbol.replace('/USDT', '')} {posPnlPct >= 0 ? '+' : ''}{posPnlPct.toFixed(1)}%
                              </span>
                            );
                          })}
                          {posCount > 3 && <span className="text-xs text-gray-500 py-1">+{posCount - 3}</span>}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {filteredPortfolios.length === 0 && (
              <div className="text-center py-16 text-gray-500">
                <div className="text-5xl mb-4">🔍</div>
                <p className="text-xl mb-2">Aucun portfolio trouvé</p>
                <p>Essayez de modifier vos filtres</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Portfolio Detail Modal */}
      {showTradesModal && selectedPortfolio && (() => {
        const historyData = portfolioHistory?.portfolios?.[selectedPortfolio.id || ''];
        const chartData = historyData?.history?.map(h => ({
          time: new Date(h.timestamp).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }),
          value: h.value,
          timestamp: new Date(h.timestamp).getTime(),
        })) || [];
        const initialCapital = selectedPortfolio.initial_capital || 10000;
        const currentValue = calculatePortfolioValue(selectedPortfolio);
        const pnl = currentValue - initialCapital;
        const pnlPct = (pnl / initialCapital) * 100;
        const isProfit = pnl >= 0;

        return (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setShowTradesModal(false)}>
            <div className="bg-[#1a1a2e] rounded-2xl border border-gray-700 w-full max-w-3xl max-h-[90vh] overflow-hidden" onClick={e => e.stopPropagation()}>
              {/* Header */}
              <div className="p-4 border-b border-gray-700 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <span className="text-3xl">{getStrategyIcon(selectedPortfolio.strategy_id)}</span>
                  <div>
                    <h2 className="text-xl font-bold">{selectedPortfolio.name}</h2>
                    <p className="text-sm text-gray-400">{selectedPortfolio.strategy_id}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="text-2xl font-bold font-mono">${currentValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                    <div className={`text-sm font-bold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                      {isProfit ? '+' : ''}{pnlPct.toFixed(2)}% ({isProfit ? '+' : ''}${pnl.toFixed(0)})
                    </div>
                  </div>
                  <button onClick={() => setShowTradesModal(false)} className="text-gray-400 hover:text-white text-2xl ml-2">×</button>
                </div>
              </div>

              <div className="p-4 max-h-[75vh] overflow-y-auto space-y-4">
                {/* Open Positions with Candlestick Charts */}
                {Object.keys(selectedPortfolio.positions || {}).length > 0 && (
                  <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 p-4">
                    <div className="text-sm text-gray-400 mb-3">Positions Ouvertes ({Object.keys(selectedPortfolio.positions || {}).length})</div>
                    <div className="space-y-4">
                      {Object.entries(selectedPortfolio.positions || {}).map(([symbol, pos]) => {
                        const currentPrice = prices[symbol] || pos.current_price || pos.entry_price;
                        const posPnlPct = pos.entry_price > 0 ? ((currentPrice - pos.entry_price) / pos.entry_price) * 100 : 0;
                        const posPnl = (currentPrice - pos.entry_price) * pos.quantity;
                        const posValue = currentPrice * pos.quantity;

                        // Get strategy's TP/SL
                        const strategyConfig = strategies[selectedPortfolio.strategy_id] || { take_profit: 20, stop_loss: 10 };
                        const tpPct = strategyConfig.take_profit;
                        const slPct = strategyConfig.stop_loss;

                        return (
                          <div key={symbol} className="bg-gray-800/50 rounded-lg p-3">
                            {/* Header */}
                            <div className="flex items-center justify-between mb-2">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-lg">{symbol.replace('/USDT', '')}</span>
                                <span className={`text-xs px-2 py-0.5 rounded ${posPnlPct >= 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                  {posPnlPct >= 0 ? '+' : ''}{posPnlPct.toFixed(2)}%
                                </span>
                                <span className="text-xs text-gray-500">TP:{tpPct}% SL:{slPct}%</span>
                              </div>
                              <div className="text-right text-sm">
                                <div className="text-gray-400">
                                  Entry: <span className="font-mono text-orange-400">${pos.entry_price < 1 ? pos.entry_price.toFixed(6) : pos.entry_price.toFixed(2)}</span>
                                </div>
                                <div className="text-gray-400">
                                  Now: <span className={`font-mono ${posPnlPct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                    ${currentPrice < 1 ? currentPrice.toFixed(6) : currentPrice.toFixed(2)}
                                  </span>
                                  <span className="text-gray-500 ml-1">({posPnl >= 0 ? '+' : ''}${posPnl.toFixed(2)})</span>
                                </div>
                              </div>
                            </div>

                            {/* Candlestick Chart */}
                            <CandlestickChart
                              symbol={symbol}
                              entryPrice={pos.entry_price}
                              entryTime={pos.entry_time}
                              tpPct={tpPct}
                              slPct={slPct}
                            />

                            {/* Position details */}
                            <div className="flex justify-between text-xs text-gray-500 mt-2">
                              <span>Qty: {pos.quantity.toFixed(4)}</span>
                              <span>Value: ${posValue.toFixed(2)}</span>
                              <span>Since: {new Date(pos.entry_time).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Recent Trades */}
                <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-sm text-gray-400">Recent Trades</div>
                    {(() => {
                      const trades = selectedPortfolio.trades || [];
                      const totalPnl = trades.filter(t => t.action === 'SELL').reduce((sum, t) => sum + (t.pnl || 0), 0);
                      const winTrades = trades.filter(t => t.action === 'SELL' && (t.pnl || 0) > 0).length;
                      const lossTrades = trades.filter(t => t.action === 'SELL' && (t.pnl || 0) < 0).length;
                      const winRate = (winTrades + lossTrades) > 0 ? (winTrades / (winTrades + lossTrades) * 100) : 0;
                      return trades.length > 0 ? (
                        <div className="flex items-center gap-3 text-xs">
                          <span className={`font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            P&L: {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
                          </span>
                          <span className="text-gray-600">•</span>
                          <span className="text-green-400">{winTrades}W</span>
                          <span className="text-red-400">{lossTrades}L</span>
                          <span className="text-gray-500">({winRate.toFixed(0)}%)</span>
                        </div>
                      ) : null;
                    })()}
                  </div>
                  <div className="space-y-1 max-h-[400px] overflow-y-auto">
                    {(selectedPortfolio.trades || []).slice().reverse().slice(0, 50).map((t, i) => {
                      const isBuy = t.action === 'BUY';
                      const amountUsd = t.amount_usdt || (t.price * t.quantity) || 0;
                      const tokenSymbol = t.symbol?.replace('/USDT', '') || '?';
                      const pnl = t.pnl || 0;

                      return (
                        <div key={i} className="flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-gray-800/50 group">
                          {/* Action icon */}
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm ${
                            isBuy ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                          }`}>
                            {isBuy ? '↓' : '↑'}
                          </div>

                          {/* Main info */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-white">{tokenSymbol}</span>
                              <span className="text-xs text-gray-500">
                                {t.quantity?.toFixed(t.quantity < 0.01 ? 6 : t.quantity < 1 ? 4 : 2)}
                              </span>
                            </div>
                            <div className="text-xs text-gray-500 truncate group-hover:whitespace-normal" title={t.reason}>
                              {t.reason || '-'}
                            </div>
                          </div>

                          {/* Amount + P&L */}
                          <div className="text-right shrink-0">
                            <div className={`font-bold ${isBuy ? 'text-green-400' : 'text-white'}`}>
                              {isBuy ? '-' : '+'}${amountUsd.toFixed(2)}
                            </div>
                            {!isBuy && (
                              <div className={`text-xs font-medium ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} P&L
                              </div>
                            )}
                            {isBuy && (
                              <div className="text-xs text-gray-500">
                                @ ${t.price?.toFixed(t.price < 1 ? 4 : 2)}
                              </div>
                            )}
                          </div>

                          {/* Time */}
                          <div className="text-xs text-gray-600 w-16 text-right shrink-0">
                            {new Date(t.timestamp).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })}
                            <br/>
                            {new Date(t.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                          </div>
                        </div>
                      );
                    })}
                    {(selectedPortfolio.trades || []).length === 0 && (
                      <div className="text-center py-8 text-gray-500">No trades yet</div>
                    )}
                  </div>
                </div>

                {/* Portfolio Value History - at the end */}
                <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 p-4">
                  <div className="text-sm text-gray-400 mb-3">Portfolio Value History</div>
                  {chartData.length >= 2 ? (
                    <div className="h-[250px]">
                      <ResponsiveContainer>
                        <AreaChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
                          <defs>
                            <linearGradient id="valueGradient" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                              <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                            </linearGradient>
                          </defs>
                          <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} />
                          <YAxis domain={['auto', 'auto']} tick={{ fill: '#9ca3af', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v.toFixed(0)}`} />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' }}
                            labelStyle={{ color: '#9ca3af' }}
                            formatter={(value) => [`$${(value as number).toFixed(2)}`, 'Value']}
                          />
                          <Area type="monotone" dataKey="value" stroke="#10b981" fill="url(#valueGradient)" strokeWidth={2} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-gray-500">Pas assez de données pour afficher le graphique</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </main>
  );
}

export default function Dashboard() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center text-white">Loading...</div>}>
      <DashboardContent />
    </Suspense>
  );
}
