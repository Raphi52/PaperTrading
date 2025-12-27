import { NextResponse } from 'next/server';

// Fetch prices from Binance
export async function GET() {
  try {
    const response = await fetch('https://api.binance.com/api/v3/ticker/price', {
      next: { revalidate: 5 } // Cache for 5 seconds
    });

    if (!response.ok) {
      throw new Error('Binance API error');
    }

    const data = await response.json();
    const prices: Record<string, number> = {};

    for (const item of data) {
      if (item.symbol.endsWith('USDT')) {
        const symbol = item.symbol.replace('USDT', '/USDT');
        prices[symbol] = parseFloat(item.price);
      }
    }

    return NextResponse.json(prices);
  } catch (error) {
    console.error('Error fetching prices:', error);
    return NextResponse.json({}, { status: 500 });
  }
}

export const dynamic = 'force-dynamic';
