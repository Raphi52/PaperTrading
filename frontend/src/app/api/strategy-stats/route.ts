import { NextResponse } from 'next/server';
import path from 'path';
import fs from 'fs';

// Get strategy performance stats from portfolios.json trades
export async function GET() {
  try {
    const dataDir = path.join(process.cwd(), '..', 'data');
    const portfoliosPath = path.join(dataDir, 'portfolios.json');

    // Read portfolios
    const portfoliosData = JSON.parse(fs.readFileSync(portfoliosPath, 'utf-8'));
    const portfolios = portfoliosData.portfolios || {};

    // Calculate stats per strategy
    const stats: Record<string, any> = {};

    // Seven days ago
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    for (const [id, p] of Object.entries(portfolios) as [string, any][]) {
      const strategyId = p.strategy_id || 'manual';

      // Initialize strategy stats if not exists
      if (!stats[strategyId]) {
        stats[strategyId] = {
          strategy_id: strategyId,
          portfolios: 0,
          total_trades: 0,
          wins: 0,
          losses: 0,
          win_rate: 0,
          pnl: 0,
          exit_reasons: {},
          active: false
        };
      }

      stats[strategyId].portfolios++;
      if (p.active !== false) {
        stats[strategyId].active = true;
      }

      // Process trades from this portfolio
      const trades = p.trades || [];
      for (const trade of trades) {
        // Only count SELL/COVER trades (completed trades with P&L)
        if (trade.action !== 'SELL' && trade.action !== 'COVER') continue;

        // Check if within last 7 days
        const tradeDate = new Date(trade.timestamp);
        if (tradeDate < sevenDaysAgo) continue;

        stats[strategyId].total_trades++;
        const pnl = trade.pnl || 0;
        stats[strategyId].pnl += pnl;

        if (pnl > 0) {
          stats[strategyId].wins++;
        } else if (pnl < 0) {
          stats[strategyId].losses++;
        }

        // Parse exit reason
        const reason = trade.reason || '';
        let exitType = 'Other';
        if (reason.includes('TP') || reason.includes('TAKE PROFIT') || reason.includes('take profit')) exitType = 'TP';
        else if (reason.includes('SL') || reason.includes('STOP LOSS') || reason.includes('stop loss')) exitType = 'SL';
        else if (reason.includes('TIME') || reason.includes('HOLD') || reason.includes('hold')) exitType = 'TIME';
        else if (reason.includes('TRAIL')) exitType = 'TRAIL';
        else if (reason.includes('EMA') || reason.includes('RSI') || reason.includes('STOCH') || reason.includes('Overbought') || reason.includes('Oversold')) exitType = 'SIGNAL';

        stats[strategyId].exit_reasons[exitType] = (stats[strategyId].exit_reasons[exitType] || 0) + 1;
      }
    }

    // Calculate win rates
    for (const s of Object.values(stats)) {
      if ((s as any).total_trades > 0) {
        (s as any).win_rate = ((s as any).wins / (s as any).total_trades) * 100;
      }
    }

    // Sort by P&L
    const sortedStats = Object.values(stats).sort((a: any, b: any) => b.pnl - a.pnl);

    return NextResponse.json(sortedStats);
  } catch (error) {
    console.error('Strategy stats error:', error);
    return NextResponse.json({ error: 'Failed to get strategy stats' }, { status: 500 });
  }
}
