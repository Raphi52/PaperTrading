import { NextResponse } from 'next/server';
import fs from 'fs';

const BOT_PATH = 'C:\\Users\\viral\\Desktop\\PaperTrading\\bot.py';

export async function GET() {
  try {
    const content = fs.readFileSync(BOT_PATH, 'utf-8');

    // Find STRATEGIES dict
    const match = content.match(/^STRATEGIES\s*=\s*\{/m);
    if (!match) {
      return NextResponse.json({});
    }

    const startIdx = match.index! + match[0].length - 1;

    // Find matching closing brace
    let braceCount = 1;
    let endIdx = startIdx + 1;
    while (braceCount > 0 && endIdx < content.length) {
      if (content[endIdx] === '{') braceCount++;
      if (content[endIdx] === '}') braceCount--;
      endIdx++;
    }

    const strategiesStr = content.substring(startIdx, endIdx);

    // Parse strategies to extract TP/SL
    const strategies: Record<string, { take_profit: number; stop_loss: number }> = {};

    // Match each strategy definition
    const strategyRegex = /"([^"]+)":\s*\{([^}]+)\}/g;
    let stratMatch;

    while ((stratMatch = strategyRegex.exec(strategiesStr)) !== null) {
      const stratName = stratMatch[1];
      const stratContent = stratMatch[2];

      const tpMatch = stratContent.match(/["']?take_profit["']?\s*:\s*(\d+)/);
      const slMatch = stratContent.match(/["']?stop_loss["']?\s*:\s*(\d+)/);

      strategies[stratName] = {
        take_profit: tpMatch ? parseInt(tpMatch[1]) : 20,
        stop_loss: slMatch ? parseInt(slMatch[1]) : 10,
      };
    }

    return NextResponse.json(strategies);
  } catch (error) {
    console.error('Error reading strategies:', error);
    return NextResponse.json({});
  }
}

export const dynamic = 'force-dynamic';
