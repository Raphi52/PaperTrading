'use client';

import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';
import { PieChart, Pie, Cell, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

interface Trade {
  timestamp: string;
  action: string;
  symbol: string;
  pnl: number;
  reason: string;
  portfolio: string;
}

interface DailyStats {
  date: string;
  pnl: number;
  trades: number;
  wins: number;
  losses: number;
}

interface HourlyStats {
  hour: number;
  pnl: number;
  trades: number;
}

const COLORS = ['#22c55e', '#ef4444', '#eab308', '#3b82f6', '#8b5cf6', '#ec4899'];

export default function AnalyticsPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<7 | 14 | 30>(7);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch('/api/portfolios');
        const data = await res.json();
        const portfolios = data.portfolios || {};

        // Extract all trades
        const allTrades: Trade[] = [];
        const cutoffDate = new Date();
        cutoffDate.setDate(cutoffDate.getDate() - period);

        for (const [id, p] of Object.entries(portfolios) as [string, any][]) {
          const portfolioTrades = p.trades || [];
          for (const t of portfolioTrades) {
            if (t.action === 'SELL' || t.action === 'COVER') {
              const tradeDate = new Date(t.timestamp);
              if (tradeDate >= cutoffDate) {
                allTrades.push({
                  ...t,
                  portfolio: p.name || id
                });
              }
            }
          }
        }

        setTrades(allTrades);
      } catch (e) {
        console.error('Failed to fetch data:', e);
      }
      setLoading(false);
    };
    fetchData();
  }, [period]);

  // Calculate daily stats
  const dailyStats = useMemo(() => {
    const stats: Record<string, DailyStats> = {};

    for (const t of trades) {
      const date = t.timestamp.split('T')[0];
      if (!stats[date]) {
        stats[date] = { date, pnl: 0, trades: 0, wins: 0, losses: 0 };
      }
      stats[date].pnl += t.pnl || 0;
      stats[date].trades++;
      if ((t.pnl || 0) > 0) stats[date].wins++;
      else if ((t.pnl || 0) < 0) stats[date].losses++;
    }

    return Object.values(stats).sort((a, b) => a.date.localeCompare(b.date));
  }, [trades]);

  // Calculate hourly stats
  const hourlyStats = useMemo(() => {
    const stats: HourlyStats[] = Array.from({ length: 24 }, (_, i) => ({
      hour: i,
      pnl: 0,
      trades: 0
    }));

    for (const t of trades) {
      const hour = new Date(t.timestamp).getUTCHours();
      stats[hour].pnl += t.pnl || 0;
      stats[hour].trades++;
    }

    return stats;
  }, [trades]);

  // Calculate exit reasons
  const exitReasons = useMemo(() => {
    const reasons: Record<string, number> = {};

    for (const t of trades) {
      const reason = t.reason || '';
      let exitType = 'Other';
      if (reason.includes('TP') || reason.includes('TAKE PROFIT')) exitType = 'Take Profit';
      else if (reason.includes('SL') || reason.includes('STOP LOSS')) exitType = 'Stop Loss';
      else if (reason.includes('TIME') || reason.includes('HOLD')) exitType = 'Time Exit';
      else if (reason.includes('TRAIL')) exitType = 'Trailing Stop';
      else if (reason.includes('EMA') || reason.includes('RSI') || reason.includes('STOCH')) exitType = 'Signal Exit';

      reasons[exitType] = (reasons[exitType] || 0) + 1;
    }

    return Object.entries(reasons).map(([name, value]) => ({ name, value }));
  }, [trades]);

  // Calculate top/worst symbols
  const symbolStats = useMemo(() => {
    const stats: Record<string, { pnl: number; trades: number }> = {};

    for (const t of trades) {
      const symbol = t.symbol || 'Unknown';
      if (!stats[symbol]) stats[symbol] = { pnl: 0, trades: 0 };
      stats[symbol].pnl += t.pnl || 0;
      stats[symbol].trades++;
    }

    const sorted = Object.entries(stats)
      .map(([symbol, data]) => ({ symbol, ...data }))
      .sort((a, b) => b.pnl - a.pnl);

    return {
      top: sorted.slice(0, 5),
      worst: sorted.slice(-5).reverse()
    };
  }, [trades]);

  // Totals
  const totals = useMemo(() => {
    const totalPnl = trades.reduce((sum, t) => sum + (t.pnl || 0), 0);
    const wins = trades.filter(t => (t.pnl || 0) > 0).length;
    const losses = trades.filter(t => (t.pnl || 0) < 0).length;
    const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 0;
    const avgWin = wins > 0 ? trades.filter(t => (t.pnl || 0) > 0).reduce((s, t) => s + t.pnl, 0) / wins : 0;
    const avgLoss = losses > 0 ? trades.filter(t => (t.pnl || 0) < 0).reduce((s, t) => s + t.pnl, 0) / losses : 0;
    return { totalPnl, trades: trades.length, wins, losses, winRate, avgWin, avgLoss };
  }, [trades]);

  // Cumulative P&L for chart
  const cumulativePnl = useMemo(() => {
    let cumulative = 0;
    return dailyStats.map(d => {
      cumulative += d.pnl;
      return { ...d, cumulative };
    });
  }, [dailyStats]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="text-white text-xl animate-pulse">Loading analytics...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold">Analytics</h1>
          <div className="flex gap-2">
            {[7, 14, 30].map(p => (
              <button
                key={p}
                onClick={() => setPeriod(p as 7 | 14 | 30)}
                className={`px-3 py-1 rounded text-sm ${period === p ? 'bg-blue-600' : 'bg-[#1a1a2e] hover:bg-[#252540]'}`}
              >
                {p}d
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/" className="px-3 py-1.5 bg-[#1a1a2e] hover:bg-[#252540] rounded text-sm">Dashboard</Link>
          <Link href="/trades" className="px-3 py-1.5 bg-[#1a1a2e] hover:bg-[#252540] rounded text-sm">Trades</Link>
          <Link href="/positions" className="px-3 py-1.5 bg-[#1a1a2e] hover:bg-[#252540] rounded text-sm">Positions</Link>
          <Link href="/strategies" className="px-3 py-1.5 bg-[#1a1a2e] hover:bg-[#252540] rounded text-sm">Strategies</Link>
          <Link href="/settings" className="px-3 py-1.5 bg-[#1a1a2e] hover:bg-[#252540] rounded text-sm">Settings</Link>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-7 gap-4 mb-6">
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Total P&L</div>
          <div className={`text-2xl font-bold ${totals.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${totals.totalPnl >= 0 ? '+' : ''}{totals.totalPnl.toFixed(2)}
          </div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Total Trades</div>
          <div className="text-2xl font-bold">{totals.trades}</div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Win Rate</div>
          <div className={`text-2xl font-bold ${totals.winRate >= 50 ? 'text-green-400' : 'text-yellow-400'}`}>
            {totals.winRate.toFixed(1)}%
          </div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Wins</div>
          <div className="text-2xl font-bold text-green-400">{totals.wins}</div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Losses</div>
          <div className="text-2xl font-bold text-red-400">{totals.losses}</div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Avg Win</div>
          <div className="text-2xl font-bold text-green-400">${totals.avgWin.toFixed(2)}</div>
        </div>
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <div className="text-gray-400 text-sm">Avg Loss</div>
          <div className="text-2xl font-bold text-red-400">${totals.avgLoss.toFixed(2)}</div>
        </div>
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        {/* Cumulative P&L Chart */}
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Cumulative P&L</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={cumulativePnl}>
                <defs>
                  <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={d => d.slice(5)} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={v => `$${v}`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #374151' }}
                  formatter={(value) => [`$${(value as number || 0).toFixed(2)}`, 'Cumulative P&L']}
                />
                <Area type="monotone" dataKey="cumulative" stroke="#22c55e" fill="url(#pnlGradient)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Exit Reasons Pie Chart */}
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Exit Reasons</h3>
          <div className="h-64 flex items-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={exitReasons}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                >
                  {exitReasons.map((entry, index) => (
                    <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        {/* Hourly Performance */}
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">P&L by Hour (UTC)</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={hourlyStats}>
                <XAxis dataKey="hour" tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={h => `${h}:00`} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={v => `$${v}`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #374151' }}
                  formatter={(value) => [`$${(value as number || 0).toFixed(2)}`, 'P&L']}
                />
                <Bar dataKey="pnl">
                  {hourlyStats.map((entry, index) => (
                    <Cell key={index} fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Daily P&L */}
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Daily P&L</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dailyStats}>
                <XAxis dataKey="date" tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={d => d.slice(5)} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={v => `$${v}`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #374151' }}
                  formatter={(value) => [`$${(value as number || 0).toFixed(2)}`, 'P&L']}
                />
                <Bar dataKey="pnl">
                  {dailyStats.map((entry, index) => (
                    <Cell key={index} fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Top/Worst Performers */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4 text-green-400">Top Performers</h3>
          <table className="w-full">
            <thead>
              <tr className="text-gray-400 text-sm">
                <th className="text-left pb-2">Symbol</th>
                <th className="text-right pb-2">Trades</th>
                <th className="text-right pb-2">P&L</th>
              </tr>
            </thead>
            <tbody>
              {symbolStats.top.map(s => (
                <tr key={s.symbol} className="border-t border-gray-800">
                  <td className="py-2 font-mono">{s.symbol}</td>
                  <td className="py-2 text-right text-gray-400">{s.trades}</td>
                  <td className="py-2 text-right text-green-400 font-bold">+${s.pnl.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="bg-[#1a1a2e] rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4 text-red-400">Worst Performers</h3>
          <table className="w-full">
            <thead>
              <tr className="text-gray-400 text-sm">
                <th className="text-left pb-2">Symbol</th>
                <th className="text-right pb-2">Trades</th>
                <th className="text-right pb-2">P&L</th>
              </tr>
            </thead>
            <tbody>
              {symbolStats.worst.map(s => (
                <tr key={s.symbol} className="border-t border-gray-800">
                  <td className="py-2 font-mono">{s.symbol}</td>
                  <td className="py-2 text-right text-gray-400">{s.trades}</td>
                  <td className="py-2 text-right text-red-400 font-bold">${s.pnl.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
