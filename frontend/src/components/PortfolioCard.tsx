'use client';

import { Portfolio } from '@/lib/types';

interface PortfolioCardProps {
  portfolio: Portfolio;
  prices: Record<string, number>;
}

export function PortfolioCard({ portfolio, prices }: PortfolioCardProps) {
  // Calculate portfolio value
  const calculateValue = () => {
    let total = portfolio.balance['USDT'] || 0;

    for (const [symbol, position] of Object.entries(portfolio.positions)) {
      const price = prices[symbol] || position.current_price;
      total += position.quantity * price;
    }

    return total;
  };

  const totalValue = calculateValue();
  const pnl = totalValue - portfolio.initial_capital;
  const pnlPercent = ((pnl / portfolio.initial_capital) * 100);
  const isPositive = pnl >= 0;

  const positionCount = Object.keys(portfolio.positions).length;
  const tradeCount = portfolio.trades.length;

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden hover:border-gray-600 transition-colors">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <div className="flex justify-between items-start">
          <div>
            <h3 className="font-semibold text-white">{portfolio.name}</h3>
            <p className="text-xs text-gray-400">{portfolio.strategy_id}</p>
          </div>
          <span className={`px-2 py-0.5 rounded text-xs ${
            portfolio.active ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
          }`}>
            {portfolio.active ? 'Active' : 'Paused'}
          </span>
        </div>
      </div>

      {/* Value */}
      <div className="p-4">
        <div className="flex justify-between items-baseline mb-2">
          <span className="text-gray-400 text-sm">Value</span>
          <span className="text-white font-mono text-lg">${totalValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
        </div>

        <div className="flex justify-between items-baseline">
          <span className="text-gray-400 text-sm">P&L</span>
          <span className={`font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isPositive ? '+' : ''}{pnlPercent.toFixed(2)}%
            <span className="text-xs ml-1">
              (${isPositive ? '+' : ''}{pnl.toFixed(2)})
            </span>
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-gray-900/50 flex justify-between text-xs text-gray-400">
        <span>{positionCount} position{positionCount !== 1 ? 's' : ''}</span>
        <span>{tradeCount} trade{tradeCount !== 1 ? 's' : ''}</span>
      </div>

      {/* Active positions preview */}
      {positionCount > 0 && (
        <div className="px-4 py-2 border-t border-gray-700">
          <div className="flex flex-wrap gap-1">
            {Object.entries(portfolio.positions).slice(0, 5).map(([symbol, pos]) => {
              const pnlPct = pos.pnl_percent ?? 0;
              return (
                <span
                  key={symbol}
                  className={`text-xs px-2 py-0.5 rounded ${
                    pnlPct >= 0 ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                  }`}
                >
                  {symbol.replace('/USDT', '')} {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}%
                </span>
              );
            })}
            {positionCount > 5 && (
              <span className="text-xs text-gray-500">+{positionCount - 5} more</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
