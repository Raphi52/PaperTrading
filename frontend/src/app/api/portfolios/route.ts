import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

// Path to Python project's portfolios.json
const PORTFOLIOS_PATH = 'C:\\Users\\viral\\Desktop\\PaperTrading\\data\\portfolios.json';

export async function GET() {
  try {
    const data = fs.readFileSync(PORTFOLIOS_PATH, 'utf-8');
    const json = JSON.parse(data);
    const portfolios = Object.values(json.portfolios || {});
    return NextResponse.json(portfolios);
  } catch (error) {
    console.error('Error reading portfolios:', error);
    return NextResponse.json([], { status: 500 });
  }
}

// Disable caching to always get fresh data
export const dynamic = 'force-dynamic';
