import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get('symbol'); // e.g., "BTC/USDT"
  const since = searchParams.get('since'); // timestamp in ms

  if (!symbol) {
    return NextResponse.json({ error: 'Missing symbol' }, { status: 400 });
  }

  try {
    // Convert symbol format: "BTC/USDT" -> "BTCUSDT"
    const binanceSymbol = symbol.replace('/', '');

    // Calculate interval based on time since entry
    const sinceMs = since ? parseInt(since) : Date.now() - 24 * 60 * 60 * 1000;
    const hoursAgo = (Date.now() - sinceMs) / (1000 * 60 * 60);

    // Choose interval: 1m for <2h, 5m for <12h, 15m for <2d, 1h for <7d, 4h otherwise
    let interval = '1h';
    let limit = 100;
    if (hoursAgo < 2) {
      interval = '1m';
      limit = 120;
    } else if (hoursAgo < 12) {
      interval = '5m';
      limit = 144;
    } else if (hoursAgo < 48) {
      interval = '15m';
      limit = 192;
    } else if (hoursAgo < 168) {
      interval = '1h';
      limit = 168;
    } else {
      interval = '4h';
      limit = 180;
    }

    const url = `https://api.binance.com/api/v3/klines?symbol=${binanceSymbol}&interval=${interval}&startTime=${sinceMs}&limit=${limit}`;

    const response = await fetch(url, { next: { revalidate: 60 } });

    if (!response.ok) {
      throw new Error('Binance API error');
    }

    const data = await response.json();

    // Transform to OHLC format
    const candles = data.map((k: any[]) => ({
      time: k[0], // Open time
      open: parseFloat(k[1]),
      high: parseFloat(k[2]),
      low: parseFloat(k[3]),
      close: parseFloat(k[4]),
      volume: parseFloat(k[5]),
    }));

    return NextResponse.json(candles);
  } catch (error) {
    console.error('Error fetching klines:', error);
    return NextResponse.json([], { status: 500 });
  }
}

export const dynamic = 'force-dynamic';
