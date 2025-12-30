'use client';

import { useEffect, useState } from 'react';

interface Settings {
  binance_api_key_masked: string;
  binance_secret_masked: string;
  has_binance_keys: boolean;
  binance_testnet: boolean;
  etherscan_api_key: string;
  helius_api_key: string;
  telegram_bot_token: string;
  telegram_chat_id: string;
  alert_types: string[];
  refresh_rate: number;
  wallets: {
    solana: { has_key: boolean; public_key: string; enabled: boolean };
    ethereum: { has_key: boolean; public_key: string; rpc_url: string; enabled: boolean };
    bsc: { has_key: boolean; public_key: string; rpc_url: string; enabled: boolean };
  };
  real_trading: {
    enabled: boolean;
    master_password_hash: string;
    global_daily_loss_limit: number;
    emergency_stop_triggered: boolean;
  };
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Form states
  const [binanceApiKey, setBinanceApiKey] = useState('');
  const [binanceSecret, setBinanceSecret] = useState('');
  const [telegramToken, setTelegramToken] = useState('');
  const [telegramChatId, setTelegramChatId] = useState('');
  const [dailyLossLimit, setDailyLossLimit] = useState(500);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      setSettings(data);
      setTelegramToken(data.telegram_bot_token || '');
      setTelegramChatId(data.telegram_chat_id || '');
      setDailyLossLimit(data.real_trading?.global_daily_loss_limit || 500);
    } catch (e) {
      console.error('Failed to fetch settings:', e);
    }
    setLoading(false);
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 3000);
  };

  const updateSettings = async (action: string, data: Record<string, any>) => {
    setSaving(true);
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, ...data })
      });
      const result = await res.json();
      if (result.success) {
        setSettings(result.settings);
        showMessage('success', 'Settings saved!');
      } else {
        showMessage('error', result.error || 'Failed to save');
      }
    } catch (e) {
      showMessage('error', 'Network error');
    }
    setSaving(false);
  };

  const handleEmergencyStop = async () => {
    if (confirm('Are you sure you want to trigger EMERGENCY STOP? This will immediately disable all real trading.')) {
      await updateSettings('emergency_stop', {});
    }
  };

  const handleResetEmergency = async () => {
    if (confirm('Reset emergency stop? Make sure you have resolved the issue before re-enabling trading.')) {
      await updateSettings('reset_emergency', {});
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <div className="text-white text-xl">Loading settings...</div>
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-[#0a0a0f] text-white">
      {/* Header */}
      <header className="bg-gradient-to-r from-[#0f0f1a] to-[#1a1a2e] border-b border-gray-800 sticky top-0 z-50">
        <div className="max-w-[1200px] mx-auto px-4 py-3">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-8">
              <a href="/" className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                Trading Bot
              </a>
              <nav className="flex items-center gap-1">
                <a href="/" className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5">
                  Dashboard
                </a>
                <a href="/?tab=portfolios" className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5">
                  Portfolios
                </a>
                <a href="/positions" className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5">
                  Positions
                </a>
                <a href="/trades" className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-gray-400 hover:text-white hover:bg-white/5">
                  Trades
                </a>
                <a href="/settings" className="px-4 py-2 rounded-lg text-sm font-medium transition-all text-white bg-white/10">
                  Settings
                </a>
              </nav>
            </div>
          </div>
        </div>
      </header>

      {/* Message Toast */}
      {message && (
        <div className={`fixed top-20 right-4 z-50 px-4 py-3 rounded-lg shadow-lg ${
          message.type === 'success' ? 'bg-green-500' : 'bg-red-500'
        } text-white font-medium`}>
          {message.text}
        </div>
      )}

      <div className="max-w-[1200px] mx-auto p-6 space-y-6">
        <h1 className="text-3xl font-bold mb-8">Settings</h1>

        {/* Real Trading Mode - MAIN SECTION */}
        <div className={`rounded-2xl border-2 p-6 ${
          settings?.real_trading?.emergency_stop_triggered
            ? 'bg-red-900/20 border-red-500'
            : settings?.real_trading?.enabled
              ? 'bg-green-900/20 border-green-500'
              : 'bg-gray-800/30 border-gray-700'
        }`}>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold flex items-center gap-3">
                {settings?.real_trading?.enabled ? (
                  <span className="text-green-400">REAL TRADING MODE</span>
                ) : (
                  <span className="text-gray-400">Paper Trading Mode</span>
                )}
                {settings?.real_trading?.emergency_stop_triggered && (
                  <span className="px-3 py-1 bg-red-500 text-white text-sm rounded-full animate-pulse">
                    EMERGENCY STOP
                  </span>
                )}
              </h2>
              <p className="text-gray-400 mt-1">
                {settings?.real_trading?.enabled
                  ? 'Real money is being used for trades!'
                  : 'Trading with virtual money only'}
              </p>
            </div>

            {/* Toggle Switch */}
            <div className="flex items-center gap-4">
              {settings?.real_trading?.emergency_stop_triggered ? (
                <button
                  onClick={handleResetEmergency}
                  className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 rounded-lg font-medium transition-colors"
                >
                  Reset Emergency Stop
                </button>
              ) : (
                <>
                  <button
                    onClick={() => updateSettings('update_real_trading', { enabled: !settings?.real_trading?.enabled })}
                    disabled={saving || !settings?.has_binance_keys}
                    className={`relative w-20 h-10 rounded-full transition-colors ${
                      settings?.real_trading?.enabled ? 'bg-green-500' : 'bg-gray-600'
                    } ${(!settings?.has_binance_keys) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    <div className={`absolute top-1 w-8 h-8 bg-white rounded-full shadow-lg transition-transform ${
                      settings?.real_trading?.enabled ? 'translate-x-11' : 'translate-x-1'
                    }`} />
                  </button>
                  {settings?.real_trading?.enabled && (
                    <button
                      onClick={handleEmergencyStop}
                      className="px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg font-bold transition-colors animate-pulse"
                    >
                      EMERGENCY STOP
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {!settings?.has_binance_keys && (
            <div className="bg-yellow-500/20 border border-yellow-500/50 rounded-lg p-4 mb-4">
              <p className="text-yellow-400 font-medium">
                Configure Binance API keys below to enable real trading
              </p>
            </div>
          )}

          {/* Daily Loss Limit */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">Global Daily Loss Limit (USD)</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={dailyLossLimit}
                  onChange={(e) => setDailyLossLimit(parseInt(e.target.value) || 0)}
                  className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500"
                />
                <button
                  onClick={() => updateSettings('update_real_trading', { global_daily_loss_limit: dailyLossLimit })}
                  disabled={saving}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg font-medium transition-colors disabled:opacity-50"
                >
                  Save
                </button>
              </div>
              <p className="text-xs text-gray-500 mt-1">Trading stops automatically when this limit is reached</p>
            </div>
          </div>
        </div>

        {/* Binance API */}
        <div className="bg-gray-800/30 rounded-2xl border border-gray-700 p-6">
          <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
            <span className="text-yellow-400">Binance</span> API Configuration
            {settings?.has_binance_keys && (
              <span className="px-2 py-1 bg-green-500/20 text-green-400 text-xs rounded-full">Connected</span>
            )}
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">API Key</label>
              <input
                type="password"
                placeholder={settings?.has_binance_keys ? settings.binance_api_key_masked : 'Enter API Key'}
                value={binanceApiKey}
                onChange={(e) => setBinanceApiKey(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-2">Secret Key</label>
              <input
                type="password"
                placeholder={settings?.has_binance_keys ? settings.binance_secret_masked : 'Enter Secret Key'}
                value={binanceSecret}
                onChange={(e) => setBinanceSecret(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings?.binance_testnet || false}
                  onChange={(e) => updateSettings('update_binance', { testnet: e.target.checked })}
                  className="w-5 h-5 rounded bg-gray-900 border-gray-700 text-blue-500 focus:ring-blue-500"
                />
                <span className="text-sm">Use Testnet (recommended for testing)</span>
              </label>
            </div>
            <button
              onClick={() => {
                if (binanceApiKey || binanceSecret) {
                  updateSettings('update_binance', {
                    api_key: binanceApiKey || undefined,
                    secret: binanceSecret || undefined
                  });
                  setBinanceApiKey('');
                  setBinanceSecret('');
                }
              }}
              disabled={saving || (!binanceApiKey && !binanceSecret)}
              className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              Save Binance Keys
            </button>
          </div>
        </div>

        {/* Wallets */}
        <div className="bg-gray-800/30 rounded-2xl border border-gray-700 p-6">
          <h2 className="text-xl font-bold mb-4">DEX Wallets</h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Solana */}
            <div className={`p-4 rounded-xl border ${
              settings?.wallets?.solana?.enabled ? 'bg-purple-500/10 border-purple-500/50' : 'bg-gray-900/50 border-gray-700'
            }`}>
              <div className="flex items-center justify-between mb-3">
                <span className="font-bold text-purple-400">Solana</span>
                <button
                  onClick={() => updateSettings('update_wallet', { chain: 'solana', enabled: !settings?.wallets?.solana?.enabled })}
                  disabled={saving || !settings?.wallets?.solana?.has_key}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    settings?.wallets?.solana?.enabled
                      ? 'bg-purple-500 text-white'
                      : 'bg-gray-700 text-gray-400'
                  } ${!settings?.wallets?.solana?.has_key ? 'opacity-50' : ''}`}
                >
                  {settings?.wallets?.solana?.enabled ? 'Enabled' : 'Disabled'}
                </button>
              </div>
              <div className="text-xs text-gray-500 mb-2">
                {settings?.wallets?.solana?.has_key ? (
                  <span className="text-green-400">Key configured</span>
                ) : (
                  <span className="text-yellow-400">No key configured</span>
                )}
              </div>
              {settings?.wallets?.solana?.public_key && (
                <div className="text-xs text-gray-400 font-mono truncate">
                  {settings.wallets.solana.public_key}
                </div>
              )}
            </div>

            {/* Ethereum */}
            <div className={`p-4 rounded-xl border ${
              settings?.wallets?.ethereum?.enabled ? 'bg-blue-500/10 border-blue-500/50' : 'bg-gray-900/50 border-gray-700'
            }`}>
              <div className="flex items-center justify-between mb-3">
                <span className="font-bold text-blue-400">Ethereum</span>
                <button
                  onClick={() => updateSettings('update_wallet', { chain: 'ethereum', enabled: !settings?.wallets?.ethereum?.enabled })}
                  disabled={saving || !settings?.wallets?.ethereum?.has_key}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    settings?.wallets?.ethereum?.enabled
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-700 text-gray-400'
                  } ${!settings?.wallets?.ethereum?.has_key ? 'opacity-50' : ''}`}
                >
                  {settings?.wallets?.ethereum?.enabled ? 'Enabled' : 'Disabled'}
                </button>
              </div>
              <div className="text-xs text-gray-500 mb-2">
                {settings?.wallets?.ethereum?.has_key ? (
                  <span className="text-green-400">Key configured</span>
                ) : (
                  <span className="text-yellow-400">No key configured</span>
                )}
              </div>
              {settings?.wallets?.ethereum?.public_key && (
                <div className="text-xs text-gray-400 font-mono truncate">
                  {settings.wallets.ethereum.public_key}
                </div>
              )}
            </div>

            {/* BSC */}
            <div className={`p-4 rounded-xl border ${
              settings?.wallets?.bsc?.enabled ? 'bg-yellow-500/10 border-yellow-500/50' : 'bg-gray-900/50 border-gray-700'
            }`}>
              <div className="flex items-center justify-between mb-3">
                <span className="font-bold text-yellow-400">BSC</span>
                <button
                  onClick={() => updateSettings('update_wallet', { chain: 'bsc', enabled: !settings?.wallets?.bsc?.enabled })}
                  disabled={saving || !settings?.wallets?.bsc?.has_key}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    settings?.wallets?.bsc?.enabled
                      ? 'bg-yellow-500 text-black'
                      : 'bg-gray-700 text-gray-400'
                  } ${!settings?.wallets?.bsc?.has_key ? 'opacity-50' : ''}`}
                >
                  {settings?.wallets?.bsc?.enabled ? 'Enabled' : 'Disabled'}
                </button>
              </div>
              <div className="text-xs text-gray-500 mb-2">
                {settings?.wallets?.bsc?.has_key ? (
                  <span className="text-green-400">Key configured</span>
                ) : (
                  <span className="text-yellow-400">No key configured</span>
                )}
              </div>
              {settings?.wallets?.bsc?.public_key && (
                <div className="text-xs text-gray-400 font-mono truncate">
                  {settings.wallets.bsc.public_key}
                </div>
              )}
            </div>
          </div>

          <p className="text-xs text-gray-500 mt-4">
            Wallet private keys must be configured via the Python backend for security.
          </p>
        </div>

        {/* Telegram Alerts */}
        <div className="bg-gray-800/30 rounded-2xl border border-gray-700 p-6">
          <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
            <span className="text-blue-400">Telegram</span> Alerts
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">Bot Token</label>
              <input
                type="password"
                placeholder="Enter Bot Token"
                value={telegramToken}
                onChange={(e) => setTelegramToken(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-2">Chat ID</label>
              <input
                type="text"
                placeholder="Enter Chat ID"
                value={telegramChatId}
                onChange={(e) => setTelegramChatId(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <button
            onClick={() => updateSettings('update_telegram', {
              bot_token: telegramToken,
              chat_id: telegramChatId
            })}
            disabled={saving}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            Save Telegram Settings
          </button>
        </div>

        {/* Danger Zone */}
        <div className="bg-red-900/20 rounded-2xl border border-red-500/50 p-6">
          <h2 className="text-xl font-bold mb-4 text-red-400">Danger Zone</h2>

          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-gray-900/50 rounded-lg">
              <div>
                <div className="font-medium">Emergency Stop All Trading</div>
                <div className="text-sm text-gray-400">Immediately stops all real trading activity</div>
              </div>
              <button
                onClick={handleEmergencyStop}
                disabled={saving || !settings?.real_trading?.enabled}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 rounded-lg font-medium transition-colors disabled:opacity-50"
              >
                EMERGENCY STOP
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
