import { NextResponse } from 'next/server';

// Calculate RSI
function calculateRSI(closes: number[], period: number = 14): number {
  if (closes.length < period + 1) return 50;

  let gains = 0;
  let losses = 0;

  for (let i = closes.length - period; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }

  const avgGain = gains / period;
  const avgLoss = losses / period;

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

// Calculate EMA
function calculateEMA(prices: number[], period: number): number[] {
  const ema: number[] = [];
  const multiplier = 2 / (period + 1);

  // Start with SMA
  let sum = 0;
  for (let i = 0; i < period && i < prices.length; i++) {
    sum += prices[i];
  }
  ema.push(sum / Math.min(period, prices.length));

  // Calculate EMA
  for (let i = period; i < prices.length; i++) {
    ema.push((prices[i] - ema[ema.length - 1]) * multiplier + ema[ema.length - 1]);
  }

  return ema;
}

// Calculate MACD
function calculateMACD(closes: number[]): { macd: number; signal: number; histogram: number } {
  if (closes.length < 26) return { macd: 0, signal: 0, histogram: 0 };

  const ema12 = calculateEMA(closes, 12);
  const ema26 = calculateEMA(closes, 26);

  const macdLine: number[] = [];
  const offset = ema26.length - ema12.length;

  for (let i = 0; i < ema26.length; i++) {
    const ema12Idx = i - offset;
    if (ema12Idx >= 0 && ema12Idx < ema12.length) {
      macdLine.push(ema12[ema12Idx] - ema26[i]);
    }
  }

  const signalLine = calculateEMA(macdLine, 9);

  const macd = macdLine[macdLine.length - 1] || 0;
  const signal = signalLine[signalLine.length - 1] || 0;

  return { macd, signal, histogram: macd - signal };
}

// Calculate Bollinger Bands
function calculateBB(closes: number[], period: number = 20): { upper: number; middle: number; lower: number; width: number } {
  if (closes.length < period) {
    const avg = closes.reduce((a, b) => a + b, 0) / closes.length;
    return { upper: avg, middle: avg, lower: avg, width: 0 };
  }

  const slice = closes.slice(-period);
  const sma = slice.reduce((a, b) => a + b, 0) / period;
  const variance = slice.reduce((sum, val) => sum + Math.pow(val - sma, 2), 0) / period;
  const stdDev = Math.sqrt(variance);

  return {
    upper: sma + 2 * stdDev,
    middle: sma,
    lower: sma - 2 * stdDev,
    width: ((sma + 2 * stdDev) - (sma - 2 * stdDev)) / sma * 100
  };
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get('symbol');
  const timestamp = searchParams.get('timestamp'); // Trade timestamp

  if (!symbol) {
    return NextResponse.json({ error: 'Missing symbol' }, { status: 400 });
  }

  try {
    const binanceSymbol = symbol.replace('/', '');
    const tradeTime = timestamp ? parseInt(timestamp) : Date.now();

    // Fetch 100 candles before the trade for indicator calculation
    const startTime = tradeTime - (100 * 60 * 60 * 1000); // 100 hours before
    const url = `https://api.binance.com/api/v3/klines?symbol=${binanceSymbol}&interval=1h&startTime=${startTime}&endTime=${tradeTime}&limit=100`;

    const response = await fetch(url, { next: { revalidate: 300 } });

    if (!response.ok) {
      throw new Error('Binance API error');
    }

    const data = await response.json();

    if (data.length === 0) {
      return NextResponse.json({
        rsi: 50,
        ema9: 0,
        ema21: 0,
        ema50: 0,
        macd: { macd: 0, signal: 0, histogram: 0 },
        bb: { upper: 0, middle: 0, lower: 0, width: 0 },
        volume24h: 0,
        avgVolume: 0,
        volumeRatio: 1,
        priceChange1h: 0,
        priceChange24h: 0,
        trend: 'neutral'
      });
    }

    const closes = data.map((k: any[]) => parseFloat(k[4]));
    const volumes = data.map((k: any[]) => parseFloat(k[5]));
    const highs = data.map((k: any[]) => parseFloat(k[2]));
    const lows = data.map((k: any[]) => parseFloat(k[3]));

    // Calculate indicators
    const rsi = calculateRSI(closes);
    const ema9 = calculateEMA(closes, 9);
    const ema21 = calculateEMA(closes, 21);
    const ema50 = calculateEMA(closes, 50);
    const macd = calculateMACD(closes);
    const bb = calculateBB(closes);

    // Volume analysis
    const volume24h = volumes.slice(-24).reduce((a, b) => a + b, 0);
    const avgVolume = volumes.reduce((a, b) => a + b, 0) / volumes.length;
    const currentVolume = volumes[volumes.length - 1];
    const volumeRatio = avgVolume > 0 ? currentVolume / avgVolume : 1;

    // Price changes
    const currentPrice = closes[closes.length - 1];
    const price1hAgo = closes[closes.length - 2] || currentPrice;
    const price24hAgo = closes[closes.length - 24] || closes[0];
    const priceChange1h = ((currentPrice - price1hAgo) / price1hAgo) * 100;
    const priceChange24h = ((currentPrice - price24hAgo) / price24hAgo) * 100;

    // Determine trend
    const ema9Val = ema9[ema9.length - 1] || currentPrice;
    const ema21Val = ema21[ema21.length - 1] || currentPrice;
    const ema50Val = ema50[ema50.length - 1] || currentPrice;

    let trend = 'neutral';
    if (currentPrice > ema9Val && ema9Val > ema21Val && ema21Val > ema50Val) {
      trend = 'strong_bullish';
    } else if (currentPrice > ema9Val && ema9Val > ema21Val) {
      trend = 'bullish';
    } else if (currentPrice < ema9Val && ema9Val < ema21Val && ema21Val < ema50Val) {
      trend = 'strong_bearish';
    } else if (currentPrice < ema9Val && ema9Val < ema21Val) {
      trend = 'bearish';
    }

    // ATR for volatility
    let atr = 0;
    for (let i = Math.max(1, closes.length - 14); i < closes.length; i++) {
      const tr = Math.max(
        highs[i] - lows[i],
        Math.abs(highs[i] - closes[i - 1]),
        Math.abs(lows[i] - closes[i - 1])
      );
      atr += tr;
    }
    atr = atr / Math.min(14, closes.length - 1);
    const atrPercent = (atr / currentPrice) * 100;

    return NextResponse.json({
      rsi: Math.round(rsi * 10) / 10,
      ema9: ema9Val,
      ema21: ema21Val,
      ema50: ema50Val,
      macd,
      bb,
      volume24h,
      avgVolume,
      volumeRatio: Math.round(volumeRatio * 100) / 100,
      priceChange1h: Math.round(priceChange1h * 100) / 100,
      priceChange24h: Math.round(priceChange24h * 100) / 100,
      trend,
      atrPercent: Math.round(atrPercent * 100) / 100,
      currentPrice
    });
  } catch (error) {
    console.error('Error calculating indicators:', error);
    return NextResponse.json({ error: 'Failed to calculate indicators' }, { status: 500 });
  }
}

export const dynamic = 'force-dynamic';
