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

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<StrategyStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<'pnl' | 'win_rate' | 'trades' | 'name'>('pnl');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [filterCategory, setFilterCategory] = useState<string>('All');
  const [showOnlyActive, setShowOnlyActive] = useState(false);

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
              <tr key={s.strategy_id} className={`border-t border-gray-800 hover:bg-[#252540] ${i % 2 === 0 ? 'bg-[#1a1a2e]' : 'bg-[#161625]'}`}>
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
    </div>
  );
}
