import { Portfolio, GlobalStats } from './types';

class ApiClient {
  async getPortfolios(): Promise<Portfolio[]> {
    const response = await fetch('/api/portfolios');
    if (!response.ok) throw new Error('Failed to fetch portfolios');
    return response.json();
  }

  async getPrices(): Promise<Record<string, number>> {
    const response = await fetch('/api/prices');
    if (!response.ok) throw new Error('Failed to fetch prices');
    return response.json();
  }

  async getStats(): Promise<GlobalStats> {
    const response = await fetch('/api/stats');
    if (!response.ok) throw new Error('Failed to fetch stats');
    return response.json();
  }
}

export const api = new ApiClient();

// Placeholder WebSocket - not needed for now
export function createWebSocket(onMessage: (data: unknown) => void): WebSocket {
  // Return a dummy WebSocket that does nothing
  const ws = new WebSocket('ws://localhost:9999');
  ws.onerror = () => {}; // Ignore errors
  return ws;
}
