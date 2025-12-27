'use client';

interface PricesTickerProps {
  prices: Record<string, number>;
}

const TOP_CRYPTOS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT'];

export function PricesTicker({ prices }: PricesTickerProps) {
  const formatPrice = (symbol: string, price: number) => {
    if (price >= 1000) return price.toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (price >= 1) return price.toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (price >= 0.01) return price.toFixed(4);
    return price.toFixed(6);
  };

  const getSymbolIcon = (symbol: string) => {
    const base = symbol.split('/')[0];
    const icons: Record<string, string> = {
      BTC: '₿',
      ETH: 'Ξ',
      SOL: '◎',
      BNB: '⬡',
      XRP: '✕',
      DOGE: 'Ð',
      ADA: '₳',
      AVAX: '🔺',
    };
    return icons[base] || '●';
  };

  return (
    <div className="bg-gray-800/50 border-b border-gray-700 overflow-hidden">
      <div className="flex gap-6 py-2 px-4 animate-scroll">
        {TOP_CRYPTOS.map((symbol) => {
          const price = prices[symbol];
          if (!price) return null;
          const base = symbol.split('/')[0];

          return (
            <div key={symbol} className="flex items-center gap-2 text-sm whitespace-nowrap">
              <span className="text-yellow-500">{getSymbolIcon(symbol)}</span>
              <span className="text-gray-400">{base}</span>
              <span className="text-white font-mono">${formatPrice(symbol, price)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
