'use client';

import { useEffect, useState, useMemo } from 'react';
import { api } from '@/lib/api';
import { Portfolio } from '@/lib/types';

interface Trade {
  id?: string;  // Unique trade ID (e.g., T1A2B3C4)
  symbol: string;
  action: 'BUY' | 'SELL';
  price: number;
  quantity: number;
  timestamp: string;
  reason?: string;
  pnl?: number;
  pnl_pct?: number;
  fee?: number;
  amount_usdt?: number;
  portfolio: string;
  portfolioId?: string;
  entry_price?: number;  // Stored in SELL trades: actual weighted average entry price
  entry_time?: string;
}

interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Indicators {
  rsi: number;
  ema9: number;
  ema21: number;
  ema50: number;
  macd: { macd: number; signal: number; histogram: number };
  bb: { upper: number; middle: number; lower: number; width: number };
  volumeRatio: number;
  priceChange1h: number;
  priceChange24h: number;
  trend: string;
  atrPercent: number;
  currentPrice: number;
}

// Mini Candlestick Chart Component
function TradeCandlestickChart({ symbol, tradePrice, tradeTime, isBuy, entryPrice, entryTime }: {
  symbol: string;
  tradePrice: number;
  tradeTime: string;
  isBuy: boolean;
  entryPrice?: number;
  entryTime?: string;
}) {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchCandles = async () => {
      try {
        // For SELL trades with entry info, get candles from entry time
        // Otherwise get 24h before trade
        const tradeTs = new Date(tradeTime).getTime();
        const entryTs = entryTime ? new Date(entryTime).getTime() : null;
        const since = entryTs ? Math.min(entryTs, tradeTs) - (2 * 60 * 60 * 1000) : tradeTs - (24 * 60 * 60 * 1000);
        const res = await fetch(`/api/klines?symbol=${encodeURIComponent(symbol)}&since=${since}`);
        const data = await res.json();
        setCandles(data);
      } catch (e) {
        console.error('Failed to fetch candles:', e);
      }
      setLoading(false);
    };
    fetchCandles();
  }, [symbol, tradeTime, entryTime]);

  if (loading) {
    return (
      <div className="h-[300px] flex items-center justify-center text-gray-500 bg-[#0d1117] rounded-lg">
        <div className="animate-pulse">Loading chart...</div>
      </div>
    );
  }

  if (candles.length < 2) {
    return (
      <div className="h-[300px] flex items-center justify-center text-gray-500 text-sm bg-[#0d1117] rounded-lg">
        Not enough data
      </div>
    );
  }

  // Find trade candle index (exit for SELL, entry for BUY)
  const tradeTs = new Date(tradeTime).getTime();
  let tradeIdx = candles.findIndex(c => c.time >= tradeTs);
  if (tradeIdx === -1) tradeIdx = candles.length - 1;

  // Find entry candle index for SELL trades
  const entryTs = entryTime ? new Date(entryTime).getTime() : null;
  let entryIdx = entryTs ? candles.findIndex(c => c.time >= entryTs) : -1;
  if (entryTs && entryIdx === -1) entryIdx = 0;

  // Chart dimensions
  const chartHeight = 280;
  const chartWidth = 600;
  const margin = { top: 20, right: 80, bottom: 30, left: 10 };
  const innerWidth = chartWidth - margin.left - margin.right;
  const innerHeight = chartHeight - margin.top - margin.bottom;

  // Calculate min/max for Y axis - include entry price for SELL trades
  const allPrices = candles.flatMap(c => [c.high, c.low]);
  if (entryPrice) allPrices.push(entryPrice);
  allPrices.push(tradePrice);
  const priceMin = Math.min(...allPrices);
  const priceMax = Math.max(...allPrices);
  const priceRange = priceMax - priceMin;
  const minPrice = priceMin - priceRange * 0.08;
  const maxPrice = priceMax + priceRange * 0.08;

  // Scale functions
  const xScale = (i: number) => margin.left + (i / Math.max(1, candles.length - 1)) * innerWidth;
  const yScale = (price: number) => margin.top + (1 - (price - minPrice) / (maxPrice - minPrice)) * innerHeight;

  // Candle width
  const gap = innerWidth / candles.length;
  const candleW = Math.max(2, Math.min(8, gap * 0.8));

  const formatPrice = (p: number) => p < 1 ? p.toFixed(6) : p < 100 ? p.toFixed(2) : p.toFixed(0);

  // For SELL trades, we show entry (BUY) and exit (SELL)
  const showEntry = !isBuy && entryPrice && entryIdx >= 0;

  return (
    <div className="bg-[#0d1117] rounded-lg p-3">
      <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full h-[300px]" preserveAspectRatio="xMidYMid meet">
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

        {/* Connection line between entry and exit for SELL trades */}
        {showEntry && (
          <line
            x1={xScale(entryIdx)}
            y1={yScale(entryPrice)}
            x2={xScale(tradeIdx)}
            y2={yScale(tradePrice)}
            stroke={(tradePrice > entryPrice) ? '#22c55e' : '#ef4444'}
            strokeWidth="2"
            strokeDasharray="4,4"
            opacity="0.6"
          />
        )}

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

        {/* Entry point (BUY) for SELL trades */}
        {showEntry && (
          <>
            {/* Entry vertical line */}
            <line
              x1={xScale(entryIdx)}
              y1={margin.top}
              x2={xScale(entryIdx)}
              y2={chartHeight - margin.bottom}
              stroke="#22c55e"
              strokeWidth="1.5"
              strokeDasharray="4,4"
              opacity="0.4"
            />
            {/* Entry dot */}
            <circle
              cx={xScale(entryIdx)}
              cy={yScale(entryPrice)}
              r="8"
              fill="#22c55e"
              stroke="#fff"
              strokeWidth="2"
            />
            {/* Entry label */}
            <text
              x={xScale(entryIdx)}
              y={yScale(entryPrice) - 14}
              fill="#22c55e"
              fontSize="11"
              textAnchor="middle"
              fontWeight="bold"
            >
              BUY ${formatPrice(entryPrice)}
            </text>
          </>
        )}

        {/* Exit/Trade point */}
        <>
          {/* Trade vertical line */}
          <line
            x1={xScale(tradeIdx)}
            y1={margin.top}
            x2={xScale(tradeIdx)}
            y2={chartHeight - margin.bottom}
            stroke={isBuy ? '#22c55e' : '#ef4444'}
            strokeWidth="1.5"
            strokeDasharray="4,4"
            opacity="0.4"
          />
          {/* Trade dot */}
          <circle
            cx={xScale(tradeIdx)}
            cy={yScale(tradePrice)}
            r="8"
            fill={isBuy ? '#22c55e' : '#ef4444'}
            stroke="#fff"
            strokeWidth="2"
          />
          {/* Trade label */}
          <text
            x={xScale(tradeIdx)}
            y={yScale(tradePrice) + 18}
            fill={isBuy ? '#22c55e' : '#ef4444'}
            fontSize="11"
            textAnchor="middle"
            fontWeight="bold"
          >
            {isBuy ? 'BUY' : 'SELL'} ${formatPrice(tradePrice)}
          </text>
        </>

        {/* P&L indicator for SELL trades */}
        {showEntry && (
          <text
            x={(xScale(entryIdx) + xScale(tradeIdx)) / 2}
            y={(yScale(entryPrice) + yScale(tradePrice)) / 2 - 8}
            fill={(tradePrice > entryPrice) ? '#22c55e' : '#ef4444'}
            fontSize="12"
            textAnchor="middle"
            fontWeight="bold"
          >
            {tradePrice > entryPrice ? '+' : ''}{(((tradePrice - entryPrice) / entryPrice) * 100).toFixed(1)}%
          </text>
        )}

        {/* Date labels */}
        {[0, Math.floor(candles.length / 2), candles.length - 1].map(idx => (
          <text
            key={idx}
            x={xScale(idx)}
            y={chartHeight - 8}
            fill="#94a3b8"
            fontSize="10"
            textAnchor="middle"
          >
            {new Date(candles[idx]?.time || 0).toLocaleDateString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
          </text>
        ))}
      </svg>
    </div>
  );
}

// Indicator Badge Component
function IndicatorBadge({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className={`px-3 py-2 rounded-lg bg-${color}-500/10 border border-${color}-500/30`}>
      <div className="text-xs text-gray-400">{label}</div>
      <div className={`font-mono font-bold text-${color}-400`}>{value}</div>
    </div>
  );
}

export default function TradesPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<'date' | 'pnl_high' | 'pnl_low' | 'symbol'>('date');
  const [filterAction, setFilterAction] = useState<'all' | 'BUY' | 'SELL'>('all');
  const [filterDate, setFilterDate] = useState<'all' | 'today' | 'yesterday' | '7days' | '30days'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [loadingIndicators, setLoadingIndicators] = useState(false);
  const TRADES_PER_PAGE = 50;

  useEffect(() => {
    const fetchData = async () => {
      try {
        const data = await api.getPortfolios();
        setPortfolios(data);
        setLoading(false);
      } catch (error) {
        console.error('Failed to fetch data:', error);
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  // Fetch indicators when trade is selected
  useEffect(() => {
    if (!selectedTrade) {
      setIndicators(null);
      return;
    }

    const fetchIndicators = async () => {
      setLoadingIndicators(true);
      try {
        const timestamp = new Date(selectedTrade.timestamp).getTime();
        const res = await fetch(`/api/indicators?symbol=${encodeURIComponent(selectedTrade.symbol)}&timestamp=${timestamp}`);
        const data = await res.json();
        setIndicators(data);
      } catch (e) {
        console.error('Failed to fetch indicators:', e);
      }
      setLoadingIndicators(false);
    };
    fetchIndicators();
  }, [selectedTrade]);

  const allTrades = useMemo(() => {
    return portfolios.flatMap(p =>
      (p.trades || []).map(t => ({ ...t, portfolio: p.name, portfolioId: p.id }))
    );
  }, [portfolios]);

  // Find entry info for a SELL trade
  const findEntryTrade = (sellTrade: Trade): { entry_price: number; entry_time: string } | null => {
    if (sellTrade.action !== 'SELL') return null;

    // First: Use stored entry_price if available (accurate for grid/DCA strategies)
    if (sellTrade.entry_price && sellTrade.entry_price > 0) {
      // Find the first BUY for this symbol in the portfolio to get entry_time
      const portfolioTrades = allTrades
        .filter(t => t.portfolioId === sellTrade.portfolioId && t.symbol === sellTrade.symbol && t.action === 'BUY')
        .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

      const sellTime = new Date(sellTrade.timestamp).getTime();
      const firstBuy = portfolioTrades.find(t => new Date(t.timestamp).getTime() < sellTime);

      return {
        entry_price: sellTrade.entry_price,
        entry_time: firstBuy?.timestamp || sellTrade.timestamp
      };
    }

    // Fallback: Find the most recent BUY before this SELL
    const portfolioTrades = allTrades
      .filter(t => t.portfolioId === sellTrade.portfolioId && t.symbol === sellTrade.symbol)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

    const sellTime = new Date(sellTrade.timestamp).getTime();
    let lastBuy = null;

    for (const t of portfolioTrades) {
      const tradeTime = new Date(t.timestamp).getTime();
      if (tradeTime >= sellTime) break;
      if (t.action === 'BUY') {
        lastBuy = t;
      }
    }

    if (lastBuy) {
      return { entry_price: lastBuy.price, entry_time: lastBuy.timestamp };
    }
    return null;
  };

  const filteredAndSortedTrades = useMemo(() => {
    let trades = [...allTrades];

    // Date filter
    if (filterDate !== 'all') {
      const now = new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const yesterdayStart = new Date(todayStart.getTime() - 24 * 60 * 60 * 1000);

      trades = trades.filter(t => {
        const tradeDate = new Date(t.timestamp);
        switch (filterDate) {
          case 'today':
            return tradeDate >= todayStart;
          case 'yesterday':
            return tradeDate >= yesterdayStart && tradeDate < todayStart;
          case '7days':
            return tradeDate >= new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
          case '30days':
            return tradeDate >= new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
          default:
            return true;
        }
      });
    }

    if (filterAction !== 'all') {
      trades = trades.filter(t => t.action === filterAction);
    }

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      trades = trades.filter(t =>
        ((t as Trade).id || '').toLowerCase().includes(query) ||
        t.symbol.toLowerCase().includes(query) ||
        t.portfolio.toLowerCase().includes(query) ||
        (t.reason || '').toLowerCase().includes(query)
      );
    }

    switch (sortBy) {
      case 'date':
        trades.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
        break;
      case 'pnl_high':
        trades.sort((a, b) => (b.pnl || 0) - (a.pnl || 0));
        break;
      case 'pnl_low':
        trades.sort((a, b) => (a.pnl || 0) - (b.pnl || 0));
        break;
      case 'symbol':
        trades.sort((a, b) => a.symbol.localeCompare(b.symbol));
        break;
    }

    return trades;
  }, [allTrades, sortBy, filterAction, filterDate, searchQuery]);

  const totalPages = Math.ceil(filteredAndSortedTrades.length / TRADES_PER_PAGE);
  const paginatedTrades = filteredAndSortedTrades.slice(
    (currentPage - 1) * TRADES_PER_PAGE,
    currentPage * TRADES_PER_PAGE
  );

  const stats = useMemo(() => {
    const sells = allTrades.filter(t => t.action === 'SELL');
    const totalPnl = sells.reduce((sum, t) => sum + (t.pnl || 0), 0);
    const wins = sells.filter(t => (t.pnl || 0) > 0).length;
    const losses = sells.filter(t => (t.pnl || 0) < 0).length;
    const winRate = sells.length > 0 ? (wins / sells.length) * 100 : 0;
    const avgWin = wins > 0 ? sells.filter(t => (t.pnl || 0) > 0).reduce((sum, t) => sum + (t.pnl || 0), 0) / wins : 0;
    const avgLoss = losses > 0 ? sells.filter(t => (t.pnl || 0) < 0).reduce((sum, t) => sum + (t.pnl || 0), 0) / losses : 0;
    return { totalPnl, wins, losses, winRate, avgWin, avgLoss, totalTrades: allTrades.length };
  }, [allTrades]);

  // Get trend color and icon
  const getTrendInfo = (trend: string) => {
    switch (trend) {
      case 'strong_bullish': return { color: 'green', icon: '🚀', text: 'Strong Bullish' };
      case 'bullish': return { color: 'green', icon: '📈', text: 'Bullish' };
      case 'strong_bearish': return { color: 'red', icon: '💀', text: 'Strong Bearish' };
      case 'bearish': return { color: 'red', icon: '📉', text: 'Bearish' };
      default: return { color: 'gray', icon: '➡️', text: 'Neutral' };
    }
  };

  // Get RSI status
  const getRSIStatus = (rsi: number) => {
    if (rsi >= 70) return { color: 'red', text: 'Overbought' };
    if (rsi <= 30) return { color: 'green', text: 'Oversold' };
    if (rsi >= 60) return { color: 'yellow', text: 'High' };
    if (rsi <= 40) return { color: 'yellow', text: 'Low' };
    return { color: 'gray', text: 'Neutral' };
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <div className="text-white text-xl">Loading trades...</div>
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
              <a href="/" className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                Trading Bot
              </a>
              <nav className="flex items-center gap-1">
                <a
                  href="/"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Dashboard
                </a>
                <a
                  href="/?tab=portfolios"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Portfolios
                </a>
                <a
                  href="/positions"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Positions
                </a>
                <a
                  href="/trades"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-white bg-white/10"
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
                  href="/settings"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Settings
                </a>
              </nav>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-400">{stats.totalTrades} trades</span>
              <span className="px-3 py-1.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400 border border-green-500/30">
                Live
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="bg-gradient-to-r from-[#1a1a2e] via-[#16213e] to-[#1a1a2e] border-b border-gray-800">
        <div className="max-w-[1600px] mx-auto px-4 py-4">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <div className="bg-black/20 rounded-xl p-3 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Total P&L</div>
              <div className={`text-xl font-bold ${stats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.totalPnl >= 0 ? '+' : ''}${stats.totalPnl.toFixed(2)}
              </div>
            </div>
            <div className="bg-black/20 rounded-xl p-3 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Win Rate</div>
              <div className={`text-xl font-bold ${stats.winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.winRate.toFixed(1)}%
              </div>
            </div>
            <div className="bg-black/20 rounded-xl p-3 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Wins</div>
              <div className="text-xl font-bold text-green-400">{stats.wins}</div>
            </div>
            <div className="bg-black/20 rounded-xl p-3 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Losses</div>
              <div className="text-xl font-bold text-red-400">{stats.losses}</div>
            </div>
            <div className="bg-black/20 rounded-xl p-3 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Avg Win</div>
              <div className="text-xl font-bold text-green-400">+${stats.avgWin.toFixed(2)}</div>
            </div>
            <div className="bg-black/20 rounded-xl p-3 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Avg Loss</div>
              <div className="text-xl font-bold text-red-400">${stats.avgLoss.toFixed(2)}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-[1600px] mx-auto p-4">
        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-4">
          <input
            type="text"
            placeholder="Search ID, symbol, portfolio..."
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
            className="flex-1 min-w-[200px] bg-gray-800/50 border border-gray-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />

          <div className="flex gap-1">
            {[
              { value: 'all', label: 'All' },
              { value: 'BUY', label: 'Buys' },
              { value: 'SELL', label: 'Sells' },
            ].map(opt => (
              <button
                key={opt.value}
                onClick={() => { setFilterAction(opt.value as typeof filterAction); setCurrentPage(1); }}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                  filterAction === opt.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-800/50 text-gray-400 hover:bg-gray-700 hover:text-white'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className="flex gap-1">
            {[
              { value: 'all', label: 'All Time' },
              { value: 'today', label: 'Today' },
              { value: 'yesterday', label: 'Yesterday' },
              { value: '7days', label: '7 Days' },
              { value: '30days', label: '30 Days' },
            ].map(opt => (
              <button
                key={opt.value}
                onClick={() => { setFilterDate(opt.value as typeof filterDate); setCurrentPage(1); }}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                  filterDate === opt.value
                    ? 'bg-green-600 text-white'
                    : 'bg-gray-800/50 text-gray-400 hover:bg-gray-700 hover:text-white'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div className="flex gap-1">
            {[
              { value: 'date', label: 'Latest' },
              { value: 'pnl_high', label: 'Best P&L' },
              { value: 'pnl_low', label: 'Worst P&L' },
              { value: 'symbol', label: 'A-Z' },
            ].map(opt => (
              <button
                key={opt.value}
                onClick={() => { setSortBy(opt.value as typeof sortBy); setCurrentPage(1); }}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                  sortBy === opt.value
                    ? 'bg-purple-600 text-white'
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
          <div className="flex items-center justify-between mb-4">
            <div className="text-sm text-gray-400">
              {filteredAndSortedTrades.length} trades - Page {currentPage}/{totalPages}
            </div>
            <div className="flex gap-1">
              <button onClick={() => setCurrentPage(1)} disabled={currentPage === 1} className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors">First</button>
              <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1} className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors">Prev</button>
              <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors">Next</button>
              <button onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages} className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors">Last</button>
            </div>
          </div>
        )}

        {/* Trades Table */}
        <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700/50 text-left text-xs text-gray-500 uppercase tracking-wider">
                  <th className="px-4 py-3">ID</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Symbol</th>
                  <th className="px-4 py-3">Price</th>
                  <th className="px-4 py-3">Amount</th>
                  <th className="px-4 py-3">P&L</th>
                  <th className="px-4 py-3">Portfolio</th>
                  <th className="px-4 py-3">Reason</th>
                  <th className="px-4 py-3">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/30">
                {paginatedTrades.map((t, i) => {
                  const isBuy = t.action === 'BUY';
                  const amountUsd = t.amount_usdt || (t.price * t.quantity) || 0;
                  const pnl = t.pnl || 0;

                  return (
                    <tr
                      key={`${t.portfolioId}-${t.timestamp}-${i}`}
                      className="hover:bg-gray-800/50 transition-colors cursor-pointer"
                      onClick={() => setSelectedTrade(t)}
                    >
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">
                          {(t as Trade).id || '-'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium ${
                          isBuy ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                        }`}>
                          {isBuy ? '↓ BUY' : '↑ SELL'}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium">{t.symbol}</td>
                      <td className="px-4 py-3 font-mono text-sm">
                        ${t.price < 1 ? t.price.toFixed(6) : t.price.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 font-mono text-sm">${amountUsd.toFixed(2)}</td>
                      <td className="px-4 py-3">
                        {t.action === 'SELL' ? (
                          <span className={`font-mono font-bold ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-gray-500">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">{t.portfolio}</td>
                      <td className="px-4 py-3 text-xs text-gray-500 max-w-[200px] truncate" title={t.reason}>
                        {t.reason || '-'}
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                        {new Date(t.timestamp).toLocaleDateString('en-US', {
                          month: 'short',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {filteredAndSortedTrades.length === 0 && (
            <div className="text-center py-16 text-gray-500">
              <div className="text-5xl mb-4">🔍</div>
              <p className="text-xl mb-2">No trades found</p>
              <p>Try adjusting your filters</p>
            </div>
          )}
        </div>

        {/* Pagination Bottom */}
        {totalPages > 1 && (
          <div className="flex justify-center mt-4">
            <div className="flex gap-1">
              {Array.from({ length: Math.min(10, totalPages) }, (_, i) => {
                let page;
                if (totalPages <= 10) page = i + 1;
                else if (currentPage <= 5) page = i + 1;
                else if (currentPage >= totalPages - 4) page = totalPages - 9 + i;
                else page = currentPage - 4 + i;
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
            </div>
          </div>
        )}
      </div>

      {/* Trade Detail Modal */}
      {selectedTrade && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setSelectedTrade(null)}>
          <div className="bg-[#1a1a2e] rounded-2xl border border-gray-700 w-full max-w-4xl max-h-[90vh] overflow-hidden" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="p-4 border-b border-gray-700 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <span className={`text-3xl ${selectedTrade.action === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>
                  {selectedTrade.action === 'BUY' ? '↓' : '↑'}
                </span>
                <div>
                  <h2 className="text-xl font-bold flex items-center gap-2">
                    <span className="font-mono text-sm text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded">
                      {selectedTrade.id || '-'}
                    </span>
                    {selectedTrade.symbol}
                    <span className={`text-sm px-2 py-0.5 rounded ${selectedTrade.action === 'BUY' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                      {selectedTrade.action}
                    </span>
                  </h2>
                  <p className="text-sm text-gray-400">
                    {new Date(selectedTrade.timestamp).toLocaleString('en-US', {
                      weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
                      hour: '2-digit', minute: '2-digit', second: '2-digit'
                    })}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                {selectedTrade.action === 'SELL' && (
                  <div className="text-right">
                    <div className="text-sm text-gray-400">P&L</div>
                    <div className={`text-2xl font-bold ${(selectedTrade.pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(selectedTrade.pnl || 0) >= 0 ? '+' : ''}${(selectedTrade.pnl || 0).toFixed(2)}
                    </div>
                  </div>
                )}
                <button onClick={() => setSelectedTrade(null)} className="text-gray-400 hover:text-white text-2xl p-1">×</button>
              </div>
            </div>

            <div className="p-4 max-h-[75vh] overflow-y-auto space-y-4">
              {/* Chart */}
              {(() => {
                // For SELL trades, find the corresponding BUY trade
                const entryInfo = selectedTrade.action === 'SELL' ? findEntryTrade(selectedTrade) : null;
                return (
                  <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 p-4">
                    <div className="text-sm text-gray-400 mb-3 flex items-center justify-between">
                      <span>Price Chart at Trade Time</span>
                      {entryInfo ? (
                        <span className="text-xs text-gray-500">From entry to exit</span>
                      ) : (
                        <span className="text-xs text-gray-500">24h window around trade</span>
                      )}
                    </div>
                    <TradeCandlestickChart
                      symbol={selectedTrade.symbol}
                      tradePrice={selectedTrade.price}
                      tradeTime={selectedTrade.timestamp}
                      isBuy={selectedTrade.action === 'BUY'}
                      entryPrice={entryInfo?.entry_price}
                      entryTime={entryInfo?.entry_time}
                    />
                  </div>
                );
              })()}

              {/* Indicators */}
              <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 p-4">
                <div className="text-sm text-gray-400 mb-3">Indicators at Trade Time</div>
                {loadingIndicators ? (
                  <div className="flex items-center justify-center py-8">
                    <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full"></div>
                  </div>
                ) : indicators ? (
                  <div className="space-y-4">
                    {/* Trend & RSI Row */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className={`p-3 rounded-lg border ${
                        indicators.trend.includes('bullish') ? 'bg-green-500/10 border-green-500/30' :
                        indicators.trend.includes('bearish') ? 'bg-red-500/10 border-red-500/30' :
                        'bg-gray-500/10 border-gray-500/30'
                      }`}>
                        <div className="text-xs text-gray-400">Trend</div>
                        <div className="flex items-center gap-2">
                          <span className="text-lg">{getTrendInfo(indicators.trend).icon}</span>
                          <span className={`font-bold ${
                            indicators.trend.includes('bullish') ? 'text-green-400' :
                            indicators.trend.includes('bearish') ? 'text-red-400' : 'text-gray-400'
                          }`}>
                            {getTrendInfo(indicators.trend).text}
                          </span>
                        </div>
                      </div>

                      <div className={`p-3 rounded-lg border ${
                        indicators.rsi >= 70 ? 'bg-red-500/10 border-red-500/30' :
                        indicators.rsi <= 30 ? 'bg-green-500/10 border-green-500/30' :
                        'bg-gray-500/10 border-gray-500/30'
                      }`}>
                        <div className="text-xs text-gray-400">RSI (14)</div>
                        <div className="flex items-center gap-2">
                          <span className={`text-xl font-bold font-mono ${
                            indicators.rsi >= 70 ? 'text-red-400' :
                            indicators.rsi <= 30 ? 'text-green-400' : 'text-white'
                          }`}>
                            {indicators.rsi}
                          </span>
                          <span className={`text-xs ${
                            indicators.rsi >= 70 ? 'text-red-400' :
                            indicators.rsi <= 30 ? 'text-green-400' : 'text-gray-500'
                          }`}>
                            {getRSIStatus(indicators.rsi).text}
                          </span>
                        </div>
                      </div>

                      <div className={`p-3 rounded-lg border ${
                        indicators.volumeRatio >= 1.5 ? 'bg-blue-500/10 border-blue-500/30' : 'bg-gray-500/10 border-gray-500/30'
                      }`}>
                        <div className="text-xs text-gray-400">Volume</div>
                        <div className="flex items-center gap-2">
                          <span className={`text-xl font-bold font-mono ${indicators.volumeRatio >= 1.5 ? 'text-blue-400' : 'text-white'}`}>
                            {indicators.volumeRatio}x
                          </span>
                          <span className="text-xs text-gray-500">vs avg</span>
                        </div>
                      </div>

                      <div className="p-3 rounded-lg border bg-gray-500/10 border-gray-500/30">
                        <div className="text-xs text-gray-400">Volatility (ATR)</div>
                        <div className="flex items-center gap-2">
                          <span className={`text-xl font-bold font-mono ${indicators.atrPercent >= 3 ? 'text-orange-400' : 'text-white'}`}>
                            {indicators.atrPercent}%
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Price Changes */}
                    <div className="grid grid-cols-2 gap-3">
                      <div className={`p-3 rounded-lg border ${
                        indicators.priceChange1h >= 0 ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'
                      }`}>
                        <div className="text-xs text-gray-400">1h Change</div>
                        <span className={`text-xl font-bold font-mono ${indicators.priceChange1h >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {indicators.priceChange1h >= 0 ? '+' : ''}{indicators.priceChange1h}%
                        </span>
                      </div>
                      <div className={`p-3 rounded-lg border ${
                        indicators.priceChange24h >= 0 ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'
                      }`}>
                        <div className="text-xs text-gray-400">24h Change</div>
                        <span className={`text-xl font-bold font-mono ${indicators.priceChange24h >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {indicators.priceChange24h >= 0 ? '+' : ''}{indicators.priceChange24h}%
                        </span>
                      </div>
                    </div>

                    {/* EMA Stack */}
                    <div className="p-3 rounded-lg border bg-gray-500/10 border-gray-500/30">
                      <div className="text-xs text-gray-400 mb-2">EMA Stack</div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm">Price: <span className="font-mono text-white">${indicators.currentPrice < 1 ? indicators.currentPrice.toFixed(6) : indicators.currentPrice.toFixed(2)}</span></span>
                        <span className="text-gray-600">→</span>
                        <span className="text-sm">EMA9: <span className="font-mono text-blue-400">${indicators.ema9 < 1 ? indicators.ema9.toFixed(6) : indicators.ema9.toFixed(2)}</span></span>
                        <span className="text-gray-600">→</span>
                        <span className="text-sm">EMA21: <span className="font-mono text-purple-400">${indicators.ema21 < 1 ? indicators.ema21.toFixed(6) : indicators.ema21.toFixed(2)}</span></span>
                        <span className="text-gray-600">→</span>
                        <span className="text-sm">EMA50: <span className="font-mono text-orange-400">${indicators.ema50 < 1 ? indicators.ema50.toFixed(6) : indicators.ema50.toFixed(2)}</span></span>
                      </div>
                      <div className="mt-2 text-xs">
                        {indicators.currentPrice > indicators.ema9 && indicators.ema9 > indicators.ema21 ? (
                          <span className="text-green-400">{"✓ Bullish alignment (Price > EMA9 > EMA21)"}</span>
                        ) : indicators.currentPrice < indicators.ema9 && indicators.ema9 < indicators.ema21 ? (
                          <span className="text-red-400">{"✗ Bearish alignment (Price < EMA9 < EMA21)"}</span>
                        ) : (
                          <span className="text-gray-500">{"○ Mixed alignment"}</span>
                        )}
                      </div>
                    </div>

                    {/* MACD */}
                    <div className="p-3 rounded-lg border bg-gray-500/10 border-gray-500/30">
                      <div className="text-xs text-gray-400 mb-2">MACD</div>
                      <div className="flex items-center gap-4">
                        <div>
                          <span className="text-xs text-gray-500">MACD:</span>
                          <span className={`ml-1 font-mono ${indicators.macd.macd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {indicators.macd.macd.toFixed(4)}
                          </span>
                        </div>
                        <div>
                          <span className="text-xs text-gray-500">Signal:</span>
                          <span className="ml-1 font-mono text-gray-300">{indicators.macd.signal.toFixed(4)}</span>
                        </div>
                        <div>
                          <span className="text-xs text-gray-500">Histogram:</span>
                          <span className={`ml-1 font-mono ${indicators.macd.histogram >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {indicators.macd.histogram.toFixed(4)}
                          </span>
                        </div>
                      </div>
                      <div className="mt-2 text-xs">
                        {indicators.macd.histogram > 0 && indicators.macd.macd > indicators.macd.signal ? (
                          <span className="text-green-400">✓ Bullish momentum (MACD above signal)</span>
                        ) : indicators.macd.histogram < 0 ? (
                          <span className="text-red-400">✗ Bearish momentum (MACD below signal)</span>
                        ) : (
                          <span className="text-gray-500">○ Neutral</span>
                        )}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="text-center text-gray-500 py-4">No indicator data available</div>
                )}
              </div>

              {/* Trade Details */}
              <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 p-4">
                <div className="text-sm text-gray-400 mb-3">Trade Details</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <div className="text-xs text-gray-500">Price</div>
                    <div className="font-mono font-bold">${selectedTrade.price < 1 ? selectedTrade.price.toFixed(6) : selectedTrade.price.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500">Quantity</div>
                    <div className="font-mono font-bold">{selectedTrade.quantity.toFixed(6)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500">Amount</div>
                    <div className="font-mono font-bold">${(selectedTrade.amount_usdt || selectedTrade.price * selectedTrade.quantity).toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500">Portfolio</div>
                    <div className="font-bold text-blue-400">{selectedTrade.portfolio}</div>
                  </div>
                </div>
              </div>

              {/* Reason */}
              <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 p-4">
                <div className="text-sm text-gray-400 mb-2">Trade Reason</div>
                <div className="text-white bg-gray-900/50 rounded-lg p-3 font-mono text-sm">
                  {selectedTrade.reason || 'No reason provided'}
                </div>
              </div>

              {/* Legitimacy Check */}
              {indicators && (
                <div className={`rounded-xl border p-4 ${
                  (() => {
                    let score = 0;
                    const isBuy = selectedTrade.action === 'BUY';

                    // RSI check
                    if (isBuy && indicators.rsi <= 40) score++;
                    if (!isBuy && indicators.rsi >= 60) score++;

                    // Trend check
                    if (isBuy && indicators.trend.includes('bullish')) score++;
                    if (!isBuy && indicators.trend.includes('bearish')) score++;

                    // Volume check
                    if (indicators.volumeRatio >= 1.2) score++;

                    // MACD check
                    if (isBuy && indicators.macd.histogram > 0) score++;
                    if (!isBuy && indicators.macd.histogram < 0) score++;

                    if (score >= 3) return 'bg-green-500/10 border-green-500/30';
                    if (score >= 2) return 'bg-yellow-500/10 border-yellow-500/30';
                    return 'bg-red-500/10 border-red-500/30';
                  })()
                }`}>
                  <div className="text-sm font-bold mb-2 flex items-center gap-2">
                    {(() => {
                      let score = 0;
                      const isBuy = selectedTrade.action === 'BUY';
                      if (isBuy && indicators.rsi <= 40) score++;
                      if (!isBuy && indicators.rsi >= 60) score++;
                      if (isBuy && indicators.trend.includes('bullish')) score++;
                      if (!isBuy && indicators.trend.includes('bearish')) score++;
                      if (indicators.volumeRatio >= 1.2) score++;
                      if (isBuy && indicators.macd.histogram > 0) score++;
                      if (!isBuy && indicators.macd.histogram < 0) score++;

                      if (score >= 3) return <><span className="text-green-400">✓</span> Trade Looks Legit</>;
                      if (score >= 2) return <><span className="text-yellow-400">⚠</span> Trade is Questionable</>;
                      return <><span className="text-red-400">✗</span> Trade Looks Risky</>;
                    })()}
                  </div>
                  <div className="text-xs text-gray-400 space-y-1">
                    {(() => {
                      const checks = [];
                      const isBuy = selectedTrade.action === 'BUY';

                      // RSI
                      if (isBuy) {
                        if (indicators.rsi <= 30) checks.push({ ok: true, text: 'RSI oversold - good buy zone' });
                        else if (indicators.rsi <= 40) checks.push({ ok: true, text: 'RSI in lower range' });
                        else if (indicators.rsi >= 70) checks.push({ ok: false, text: 'RSI overbought - risky buy' });
                        else checks.push({ ok: null, text: 'RSI neutral' });
                      } else {
                        if (indicators.rsi >= 70) checks.push({ ok: true, text: 'RSI overbought - good sell zone' });
                        else if (indicators.rsi >= 60) checks.push({ ok: true, text: 'RSI in upper range' });
                        else if (indicators.rsi <= 30) checks.push({ ok: false, text: 'RSI oversold - might be selling too low' });
                        else checks.push({ ok: null, text: 'RSI neutral' });
                      }

                      // Trend
                      if (isBuy && indicators.trend.includes('bullish')) checks.push({ ok: true, text: 'Buying with the trend' });
                      else if (isBuy && indicators.trend.includes('bearish')) checks.push({ ok: false, text: 'Buying against the trend' });
                      else if (!isBuy && indicators.trend.includes('bearish')) checks.push({ ok: true, text: 'Selling with the trend' });
                      else if (!isBuy && indicators.trend.includes('bullish')) checks.push({ ok: false, text: 'Selling against the trend' });
                      else checks.push({ ok: null, text: 'No clear trend' });

                      // Volume
                      if (indicators.volumeRatio >= 1.5) checks.push({ ok: true, text: 'High volume confirmation' });
                      else if (indicators.volumeRatio >= 1.0) checks.push({ ok: null, text: 'Normal volume' });
                      else checks.push({ ok: false, text: 'Low volume - weak move' });

                      // MACD
                      if (isBuy && indicators.macd.histogram > 0) checks.push({ ok: true, text: 'MACD bullish momentum' });
                      else if (isBuy && indicators.macd.histogram < 0) checks.push({ ok: false, text: 'MACD bearish - counter-trend buy' });
                      else if (!isBuy && indicators.macd.histogram < 0) checks.push({ ok: true, text: 'MACD bearish momentum' });
                      else if (!isBuy && indicators.macd.histogram > 0) checks.push({ ok: false, text: 'MACD bullish - might be selling too early' });
                      else checks.push({ ok: null, text: 'MACD neutral' });

                      return checks.map((c, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span>{c.ok === true ? '✓' : c.ok === false ? '✗' : '○'}</span>
                          <span className={c.ok === true ? 'text-green-400' : c.ok === false ? 'text-red-400' : 'text-gray-500'}>
                            {c.text}
                          </span>
                        </div>
                      ));
                    })()}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
