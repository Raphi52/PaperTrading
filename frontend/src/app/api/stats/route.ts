import { NextResponse } from 'next/server';
import fs from 'fs';

const PORTFOLIOS_PATH = 'C:\\Users\\viral\\Desktop\\PaperTrading\\data\\portfolios.json';

export async function GET() {
  try {
    const data = fs.readFileSync(PORTFOLIOS_PATH, 'utf-8');
    const json = JSON.parse(data);
    const portfolios = Object.values(json.portfolios || {}) as any[];

    let totalValue = 0;
    let totalInitial = 0;
    let totalTrades = 0;
    let totalPositions = 0;
    let winningPortfolios = 0;
    let activePortfolios = 0;

    for (const p of portfolios) {
      const initial = p.initial_capital || 10000;
      const usdt = p.balance?.USDT || 0;

      // Calculate position values (approximate with stored current_price)
      let posValue = 0;
      for (const pos of Object.values(p.positions || {}) as any[]) {
        posValue += (pos.quantity || 0) * (pos.current_price || pos.entry_price || 0);
      }

      const value = usdt + posValue;
      totalValue += value;
      totalInitial += initial;
      totalTrades += (p.trades || []).length;
      totalPositions += Object.keys(p.positions || {}).length;

      if (value > initial) winningPortfolios++;
      if (p.active) activePortfolios++;
    }

    const totalPnl = totalValue - totalInitial;
    const totalPnlPercent = totalInitial > 0 ? (totalPnl / totalInitial) * 100 : 0;

    return NextResponse.json({
      total_portfolios: portfolios.length,
      active_portfolios: activePortfolios,
      total_value: totalValue,
      total_pnl: totalPnl,
      total_pnl_percent: totalPnlPercent,
      total_trades: totalTrades,
      winning_portfolios: winningPortfolios,
      total_positions: totalPositions,
    });
  } catch (error) {
    console.error('Error calculating stats:', error);
    return NextResponse.json({
      total_portfolios: 0,
      active_portfolios: 0,
      total_value: 0,
      total_pnl: 0,
      total_pnl_percent: 0,
      total_trades: 0,
      winning_portfolios: 0,
      total_positions: 0,
    });
  }
}

export const dynamic = 'force-dynamic';
