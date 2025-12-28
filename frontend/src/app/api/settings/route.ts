import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

const SETTINGS_PATH = path.join(process.cwd(), '..', 'data', 'settings.json');

function loadSettings() {
  try {
    const data = fs.readFileSync(SETTINGS_PATH, 'utf-8');
    return JSON.parse(data);
  } catch (e) {
    return {
      binance_api_key: '',
      binance_secret: '',
      binance_testnet: true,
      etherscan_api_key: '',
      helius_api_key: '',
      telegram_bot_token: '',
      telegram_chat_id: '',
      alert_types: ['Pump Detected', 'Position Closed'],
      refresh_rate: 10,
      wallets: {
        solana: { private_key_encrypted: '', public_key: '', enabled: false },
        ethereum: { private_key_encrypted: '', public_key: '', rpc_url: 'https://eth.llamarpc.com', enabled: false },
        bsc: { private_key_encrypted: '', public_key: '', rpc_url: 'https://bsc-dataseed.binance.org', enabled: false }
      },
      real_trading: {
        enabled: false,
        master_password_hash: '',
        global_daily_loss_limit: 500,
        emergency_stop_triggered: false
      }
    };
  }
}

function saveSettings(settings: Record<string, any>) {
  fs.writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2));
}

// Mask sensitive data for frontend display
function maskSensitiveData(settings: Record<string, any>) {
  const masked = { ...settings };

  // Mask API keys (show first 4 and last 4 chars)
  const maskKey = (key: string) => {
    if (!key || key.length < 10) return key ? '****' : '';
    return key.slice(0, 4) + '****' + key.slice(-4);
  };

  masked.binance_api_key_masked = maskKey(settings.binance_api_key);
  masked.binance_secret_masked = maskKey(settings.binance_secret);
  masked.has_binance_keys = !!(settings.binance_api_key && settings.binance_secret);

  // Check wallet status without exposing keys
  if (masked.wallets) {
    masked.wallets = {
      solana: {
        has_key: !!settings.wallets?.solana?.private_key_encrypted,
        public_key: settings.wallets?.solana?.public_key || '',
        enabled: settings.wallets?.solana?.enabled || false
      },
      ethereum: {
        has_key: !!settings.wallets?.ethereum?.private_key_encrypted,
        public_key: settings.wallets?.ethereum?.public_key || '',
        rpc_url: settings.wallets?.ethereum?.rpc_url || '',
        enabled: settings.wallets?.ethereum?.enabled || false
      },
      bsc: {
        has_key: !!settings.wallets?.bsc?.private_key_encrypted,
        public_key: settings.wallets?.bsc?.public_key || '',
        rpc_url: settings.wallets?.bsc?.rpc_url || '',
        enabled: settings.wallets?.bsc?.enabled || false
      }
    };
  }

  // Don't expose actual keys
  delete masked.binance_api_key;
  delete masked.binance_secret;

  return masked;
}

export async function GET() {
  try {
    const settings = loadSettings();
    const masked = maskSensitiveData(settings);
    return NextResponse.json(masked);
  } catch (error) {
    console.error('Error loading settings:', error);
    return NextResponse.json({ error: 'Failed to load settings' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const currentSettings = loadSettings();

    // Handle different update types
    const { action, ...data } = body;

    switch (action) {
      case 'update_binance':
        if (data.api_key) currentSettings.binance_api_key = data.api_key;
        if (data.secret) currentSettings.binance_secret = data.secret;
        if (typeof data.testnet === 'boolean') currentSettings.binance_testnet = data.testnet;
        break;

      case 'update_telegram':
        if (data.bot_token !== undefined) currentSettings.telegram_bot_token = data.bot_token;
        if (data.chat_id !== undefined) currentSettings.telegram_chat_id = data.chat_id;
        if (data.alert_types) currentSettings.alert_types = data.alert_types;
        break;

      case 'update_wallet':
        const { chain, public_key, rpc_url, enabled } = data;
        if (chain && currentSettings.wallets[chain]) {
          if (public_key !== undefined) currentSettings.wallets[chain].public_key = public_key;
          if (rpc_url !== undefined) currentSettings.wallets[chain].rpc_url = rpc_url;
          if (typeof enabled === 'boolean') currentSettings.wallets[chain].enabled = enabled;
        }
        break;

      case 'update_real_trading':
        if (typeof data.enabled === 'boolean') {
          currentSettings.real_trading.enabled = data.enabled;
        }
        if (data.global_daily_loss_limit !== undefined) {
          currentSettings.real_trading.global_daily_loss_limit = data.global_daily_loss_limit;
        }
        break;

      case 'emergency_stop':
        currentSettings.real_trading.emergency_stop_triggered = true;
        currentSettings.real_trading.enabled = false;
        break;

      case 'reset_emergency':
        currentSettings.real_trading.emergency_stop_triggered = false;
        break;

      case 'update_refresh_rate':
        if (data.refresh_rate) currentSettings.refresh_rate = data.refresh_rate;
        break;

      default:
        return NextResponse.json({ error: 'Unknown action' }, { status: 400 });
    }

    saveSettings(currentSettings);
    const masked = maskSensitiveData(currentSettings);
    return NextResponse.json({ success: true, settings: masked });
  } catch (error) {
    console.error('Error updating settings:', error);
    return NextResponse.json({ error: 'Failed to update settings' }, { status: 500 });
  }
}

export const dynamic = 'force-dynamic';
