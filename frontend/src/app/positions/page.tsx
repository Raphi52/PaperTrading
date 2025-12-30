'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { api } from '@/lib/api';
import { Portfolio, Position } from '@/lib/types';

interface ExtendedPosition extends Position {
  portfolioId: string;
  portfolioName: string;
  strategyId: string;
  value: number;
  pnlDollar: number;
  holdTime: string;
}

export default function PositionsPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<'pnl' | 'value' | 'symbol' | 'time'>('pnl');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [filterPnl, setFilterPnl] = useState<'all' | 'profit' | 'loss'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPosition, setSelectedPosition] = useState<ExtendedPosition | null>(null);

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      const [portfoliosData, pricesData] = await Promise.all([
        api.getPortfolios(),
        api.getPrices(),
      ]);
      setPortfolios(portfoliosData);
      setPrices(pricesData);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Calculate hold time
  const getHoldTime = (entryTime: string): string => {
    const entry = new Date(entryTime);
    const now = new Date();
    const diffMs = now.getTime() - entry.getTime();
    const hours = Math.floor(diffMs / (1000 * 60 * 60));
    const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

    if (hours > 24) {
      const days = Math.floor(hours / 24);
      return `${days}d ${hours % 24}h`;
    }
    return `${hours}h ${minutes}m`;
  };

  // Aggregate all positions
  const allPositions = useMemo(() => {
    const positions: ExtendedPosition[] = [];

    portfolios.forEach(p => {
      Object.entries(p.positions || {}).forEach(([symbol, pos]) => {
        const currentPrice = prices[symbol] || pos.current_price || pos.entry_price;
        const pnlPct = pos.entry_price > 0
          ? ((currentPrice - pos.entry_price) / pos.entry_price) * 100
          : 0;
        const value = pos.quantity * currentPrice;
        const pnlDollar = pos.quantity * (currentPrice - pos.entry_price);

        positions.push({
          ...pos,
          symbol,
          current_price: currentPrice,
          pnl_percent: pnlPct,
          portfolioId: p.id || '',
          portfolioName: p.name,
          strategyId: p.strategy_id,
          value,
          pnlDollar,
          holdTime: getHoldTime(pos.entry_time),
        });
      });
    });

    return positions;
  }, [portfolios, prices]);

  // Filter and sort
  const filteredPositions = useMemo(() => {
    let result = [...allPositions];

    // Search filter
    if (searchQuery) {
      const query = searchQuery.toUpperCase();
      result = result.filter(p =>
        p.symbol.includes(query) ||
        p.portfolioName.toUpperCase().includes(query)
      );
    }

    // P&L filter
    if (filterPnl === 'profit') {
      result = result.filter(p => (p.pnl_percent || 0) > 0);
    } else if (filterPnl === 'loss') {
      result = result.filter(p => (p.pnl_percent || 0) < 0);
    }

    // Sort
    result.sort((a, b) => {
      let comparison = 0;
      switch (sortBy) {
        case 'pnl':
          comparison = (a.pnl_percent || 0) - (b.pnl_percent || 0);
          break;
        case 'value':
          comparison = a.value - b.value;
          break;
        case 'symbol':
          comparison = a.symbol.localeCompare(b.symbol);
          break;
        case 'time':
          comparison = new Date(a.entry_time).getTime() - new Date(b.entry_time).getTime();
          break;
      }
      return sortDir === 'desc' ? -comparison : comparison;
    });

    return result;
  }, [allPositions, searchQuery, filterPnl, sortBy, sortDir]);

  // Stats
  const stats = useMemo(() => {
    const totalValue = allPositions.reduce((sum, p) => sum + p.value, 0);
    const totalPnl = allPositions.reduce((sum, p) => sum + p.pnlDollar, 0);
    const avgPnlPct = allPositions.length > 0
      ? allPositions.reduce((sum, p) => sum + (p.pnl_percent || 0), 0) / allPositions.length
      : 0;
    const profitCount = allPositions.filter(p => (p.pnl_percent || 0) > 0).length;
    const best = allPositions.reduce((max, p) => (p.pnl_percent || 0) > (max?.pnl_percent || -Infinity) ? p : max, null as ExtendedPosition | null);
    const worst = allPositions.reduce((min, p) => (p.pnl_percent || 0) < (min?.pnl_percent || Infinity) ? p : min, null as ExtendedPosition | null);

    return { totalValue, totalPnl, avgPnlPct, profitCount, best, worst };
  }, [allPositions]);

  const toggleSort = (field: typeof sortBy) => {
    if (sortBy === field) {
      setSortDir(sortDir === 'desc' ? 'asc' : 'desc');
    } else {
      setSortBy(field);
      setSortDir('desc');
    }
  };

  const formatPrice = (price: number) => {
    if (price >= 1000) return price.toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (price >= 1) return price.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return price.toLocaleString(undefined, { maximumFractionDigits: 6 });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] text-white flex items-center justify-center">
        <div className="text-xl text-gray-400 animate-pulse">Loading positions...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-[#0a0a0f]/95 backdrop-blur-sm border-b border-gray-800">
        <div className="max-w-[1600px] mx-auto px-4 py-3">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-8">
              <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                Trading Bot
              </h1>
              <nav className="flex items-center gap-1">
                <a
                  href="/"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5"
                >
                  Dashboard
                </a>
                <a
                  href="/positions"
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-white bg-white/10"
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

      {/* Stats Bar */}
      <div className="bg-gradient-to-r from-[#1a1a2e] via-[#16213e] to-[#1a1a2e] border-b border-gray-800">
        <div className="max-w-[1600px] mx-auto px-4 py-5">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {/* Total Positions */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Open Positions</div>
              <div className="text-2xl md:text-3xl font-bold text-purple-400">{allPositions.length}</div>
              <div className="text-sm text-gray-500">{stats.profitCount} in profit</div>
            </div>

            {/* Total Value */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Total Value</div>
              <div className="text-2xl md:text-3xl font-bold">${stats.totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
            </div>

            {/* Total P&L */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Unrealized P&L</div>
              <div className={`text-2xl md:text-3xl font-bold ${stats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.totalPnl >= 0 ? '+' : ''}${stats.totalPnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
            </div>

            {/* Avg P&L */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Avg P&L %</div>
              <div className={`text-2xl md:text-3xl font-bold ${stats.avgPnlPct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {stats.avgPnlPct >= 0 ? '+' : ''}{stats.avgPnlPct.toFixed(2)}%
              </div>
            </div>

            {/* Best */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Best Position</div>
              <div className="text-lg font-bold text-green-400">
                {stats.best ? `+${(stats.best.pnl_percent || 0).toFixed(1)}%` : '-'}
              </div>
              <div className="text-sm text-gray-500 truncate">{stats.best?.symbol || '-'}</div>
            </div>

            {/* Worst */}
            <div className="bg-black/20 rounded-xl p-4 border border-gray-800">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Worst Position</div>
              <div className="text-lg font-bold text-red-400">
                {stats.worst ? `${(stats.worst.pnl_percent || 0).toFixed(1)}%` : '-'}
              </div>
              <div className="text-sm text-gray-500 truncate">{stats.worst?.symbol || '-'}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <main className="max-w-[1600px] mx-auto px-4 py-6">
        {/* Filters */}
        <div className="flex flex-wrap gap-4 mb-6">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <input
              type="text"
              placeholder="Search symbol or portfolio..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-4 py-2.5 bg-[#1a1a2e] border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
              >
                x
              </button>
            )}
          </div>

          {/* P&L Filter */}
          <div className="flex gap-1 bg-[#1a1a2e] rounded-lg p-1 border border-gray-700">
            {(['all', 'profit', 'loss'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilterPnl(f)}
                className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
                  filterPnl === f
                    ? f === 'profit' ? 'bg-green-500/20 text-green-400'
                    : f === 'loss' ? 'bg-red-500/20 text-red-400'
                    : 'bg-white/10 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {f === 'all' ? 'All' : f === 'profit' ? 'Profit' : 'Loss'}
              </button>
            ))}
          </div>

          {/* Sort */}
          <div className="flex gap-1 bg-[#1a1a2e] rounded-lg p-1 border border-gray-700">
            {(['pnl', 'value', 'symbol', 'time'] as const).map((s) => (
              <button
                key={s}
                onClick={() => toggleSort(s)}
                className={`px-3 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-1 ${
                  sortBy === s ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'
                }`}
              >
                {s === 'pnl' ? 'P&L' : s === 'value' ? 'Value' : s === 'symbol' ? 'Symbol' : 'Time'}
                {sortBy === s && (
                  <span className="text-xs">{sortDir === 'desc' ? '↓' : '↑'}</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Positions Table */}
        {filteredPositions.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            {allPositions.length === 0
              ? 'No open positions'
              : 'No positions match your filters'}
          </div>
        ) : (
          <div className="bg-[#1a1a2e] rounded-xl border border-gray-700 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700 text-left">
                    <th className="px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium">Symbol</th>
                    <th className="px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium">Portfolio</th>
                    <th className="px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium text-right">Entry</th>
                    <th className="px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium text-right">Current</th>
                    <th className="px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium text-right">Qty</th>
                    <th className="px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium text-right">Value</th>
                    <th className="px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium text-right">P&L %</th>
                    <th className="px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium text-right">P&L $</th>
                    <th className="px-4 py-3 text-xs text-gray-500 uppercase tracking-wider font-medium text-right">Hold Time</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPositions.map((pos, idx) => (
                    <tr
                      key={`${pos.portfolioId}-${pos.symbol}-${idx}`}
                      onClick={() => setSelectedPosition(pos)}
                      className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium text-white">{pos.symbol.replace('/USDT', '')}</div>
                        <div className="text-xs text-gray-500">{pos.strategyId}</div>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400 max-w-[150px] truncate">
                        {pos.portfolioName}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        ${formatPrice(pos.entry_price)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        ${formatPrice(pos.current_price)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm text-gray-400">
                        {pos.quantity < 0.01 ? pos.quantity.toFixed(6) : pos.quantity.toFixed(4)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-sm">
                        ${pos.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-mono font-medium ${(pos.pnl_percent || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {(pos.pnl_percent || 0) >= 0 ? '+' : ''}{(pos.pnl_percent || 0).toFixed(2)}%
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-mono text-sm ${pos.pnlDollar >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          {pos.pnlDollar >= 0 ? '+' : ''}${pos.pnlDollar.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-sm text-gray-400">
                        {pos.holdTime}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* Position Detail Modal */}
      {selectedPosition && (
        <div
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedPosition(null)}
        >
          <div
            className="bg-[#1a1a2e] rounded-2xl border border-gray-700 w-full max-w-lg overflow-hidden"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="p-6 border-b border-gray-700">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-2xl font-bold">{selectedPosition.symbol}</h2>
                  <div className="text-gray-400 text-sm mt-1">{selectedPosition.portfolioName}</div>
                </div>
                <button
                  onClick={() => setSelectedPosition(null)}
                  className="text-gray-500 hover:text-white text-2xl leading-none"
                >
                  &times;
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="p-6 space-y-4">
              {/* P&L Banner */}
              <div className={`p-4 rounded-xl ${(selectedPosition.pnl_percent || 0) >= 0 ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
                <div className="flex justify-between items-center">
                  <div>
                    <div className="text-sm text-gray-400">Unrealized P&L</div>
                    <div className={`text-3xl font-bold ${(selectedPosition.pnl_percent || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(selectedPosition.pnl_percent || 0) >= 0 ? '+' : ''}{(selectedPosition.pnl_percent || 0).toFixed(2)}%
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-gray-400">Amount</div>
                    <div className={`text-xl font-bold ${selectedPosition.pnlDollar >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {selectedPosition.pnlDollar >= 0 ? '+' : ''}${selectedPosition.pnlDollar.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </div>
                  </div>
                </div>
              </div>

              {/* Details Grid */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Entry Price</div>
                  <div className="text-lg font-mono">${formatPrice(selectedPosition.entry_price)}</div>
                </div>
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Current Price</div>
                  <div className="text-lg font-mono">${formatPrice(selectedPosition.current_price)}</div>
                </div>
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Quantity</div>
                  <div className="text-lg font-mono">{selectedPosition.quantity}</div>
                </div>
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Value</div>
                  <div className="text-lg font-mono">${selectedPosition.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
                </div>
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Hold Time</div>
                  <div className="text-lg">{selectedPosition.holdTime}</div>
                </div>
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Strategy</div>
                  <div className="text-lg truncate">{selectedPosition.strategyId}</div>
                </div>
              </div>

              {/* Entry Time */}
              <div className="bg-black/20 rounded-lg p-3">
                <div className="text-xs text-gray-500 uppercase">Entry Time</div>
                <div className="text-sm text-gray-300">
                  {new Date(selectedPosition.entry_time).toLocaleString()}
                </div>
              </div>

              {/* Highest Price */}
              {selectedPosition.highest_price && (
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Highest Price</div>
                  <div className="text-lg font-mono text-yellow-400">
                    ${formatPrice(selectedPosition.highest_price)}
                    <span className="text-sm text-gray-500 ml-2">
                      (Peak: +{(((selectedPosition.highest_price - selectedPosition.entry_price) / selectedPosition.entry_price) * 100).toFixed(2)}%)
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
