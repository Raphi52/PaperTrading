import { NextResponse } from 'next/server';
import fs from 'fs';

const HISTORY_PATH = 'C:\\Users\\viral\\Desktop\\PaperTrading\\data\\portfolio_history.json';

export async function GET() {
  try {
    const data = fs.readFileSync(HISTORY_PATH, 'utf-8');
    const json = JSON.parse(data);
    return NextResponse.json(json);
  } catch (error) {
    console.error('Error reading history:', error);
    return NextResponse.json({ portfolios: {} }, { status: 500 });
  }
}

export const dynamic = 'force-dynamic';
