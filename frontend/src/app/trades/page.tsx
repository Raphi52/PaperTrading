'use client';

import { useEffect, useState, useMemo } from 'react';
import { api } from '@/lib/api';
import { Portfolio } from '@/lib/types';

interface Trade {
  symbol: string;
  action: 'BUY' | 'SELL';
  price: number;
  quantity: number;
  timestamp: string;
  reason?: string;
  pnl?: number;
  amount_usdt?: number;
  portfolio: string;
  portfolioId: string;
}

export default function TradesPage() {
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<'date' | 'pnl_high' | 'pnl_low' | 'symbol'>('date');
  const [filterAction, setFilterAction] = useState<'all' | 'BUY' | 'SELL'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
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

  const allTrades = useMemo(() => {
    return portfolios.flatMap(p =>
      (p.trades || []).map(t => ({ ...t, portfolio: p.name, portfolioId: p.id }))
    );
  }, [portfolios]);

  const filteredAndSortedTrades = useMemo(() => {
    let trades = [...allTrades];

    // Filter by action
    if (filterAction !== 'all') {
      trades = trades.filter(t => t.action === filterAction);
    }

    // Filter by search
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      trades = trades.filter(t =>
        t.symbol.toLowerCase().includes(query) ||
        t.portfolio.toLowerCase().includes(query) ||
        (t.reason || '').toLowerCase().includes(query)
      );
    }

    // Sort
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
  }, [allTrades, sortBy, filterAction, searchQuery]);

  const totalPages = Math.ceil(filteredAndSortedTrades.length / TRADES_PER_PAGE);
  const paginatedTrades = filteredAndSortedTrades.slice(
    (currentPage - 1) * TRADES_PER_PAGE,
    currentPage * TRADES_PER_PAGE
  );

  // Stats
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
            <div className="flex items-center gap-4">
              <a href="/" className="text-gray-400 hover:text-white transition-colors">
                ← Back
              </a>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                All Trades
              </h1>
            </div>
            <span className="px-3 py-1.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400 border border-green-500/30">
              {stats.totalTrades} trades
            </span>
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
            placeholder="Search symbol, portfolio, reason..."
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
            className="flex-1 min-w-[200px] bg-gray-800/50 border border-gray-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />

          {/* Action Filter */}
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

          {/* Sort */}
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
              <button
                onClick={() => setCurrentPage(1)}
                disabled={currentPage === 1}
                className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors"
              >
                First
              </button>
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors"
              >
                Prev
              </button>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors"
              >
                Next
              </button>
              <button
                onClick={() => setCurrentPage(totalPages)}
                disabled={currentPage === totalPages}
                className="px-3 py-1.5 bg-gray-800 rounded-lg text-sm disabled:opacity-30 hover:bg-gray-700 transition-colors"
              >
                Last
              </button>
            </div>
          </div>
        )}

        {/* Trades Table */}
        <div className="bg-gray-800/30 rounded-xl border border-gray-700/50 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-700/50 text-left text-xs text-gray-500 uppercase tracking-wider">
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
                    <tr key={i} className="hover:bg-gray-800/30 transition-colors">
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
    </main>
  );
}
