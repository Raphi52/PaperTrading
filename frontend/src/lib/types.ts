// Types matching Python portfolios.json structure

export interface Portfolio {
  id?: string;
  name: string;
  strategy_id: string;
  config: PortfolioConfig;
  balance: Record<string, number>;
  initial_capital: number;
  positions: Record<string, Position>;
  trades: Trade[];
  active: boolean;
  created_at?: string;
  trading_mode?: string;
  market_type?: string;
}

export interface PortfolioConfig {
  cryptos: string[];
  allocation_percent: number;
  max_positions?: number;
  auto_trade?: boolean;
}

export interface Position {
  symbol: string;
  entry_price: number;
  quantity: number;
  entry_time: string;
  current_price: number;
  highest_price?: number;
  pnl_percent?: number;
}

export interface Trade {
  timestamp: string;
  action: 'BUY' | 'SELL';
  symbol: string;
  price: number;
  quantity: number;
  amount_usdt?: number;
  pnl: number;
  pnl_pct?: number;
  fee?: number;
  reason?: string;
}

export interface GlobalStats {
  total_portfolios: number;
  active_portfolios: number;
  total_value: number;
  total_pnl: number;
  total_pnl_percent: number;
  total_trades: number;
  winning_portfolios: number;
  total_positions: number;
}

export interface PriceData {
  symbol: string;
  price: number;
  change_24h?: number;
}

export type WsMessage =
  | { type: 'Prices'; data: Record<string, number> }
  | { type: 'Trade'; data: Trade }
  | { type: 'PortfolioUpdate'; data: Portfolio }
  | { type: 'Stats'; data: GlobalStats }
  | { type: 'Error'; data: string };
