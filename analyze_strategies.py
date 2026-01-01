import json

with open('data/portfolios.json') as f:
    data = json.load(f)

print("=== Portfolios avec 0 trades ===\n")
zero_trades = []
low_trades = []

for pid, p in data['portfolios'].items():
    trades = p.get('trades', [])
    strategy = p.get('strategy_id', 'unknown')
    name = p.get('name', 'Unknown')
    active = p.get('active', False)
    auto = p.get('config', {}).get('auto_trade', False)

    if len(trades) == 0:
        zero_trades.append({
            'name': name,
            'strategy': strategy,
            'active': active,
            'auto': auto,
            'balance': p.get('balance', {}).get('USDT', 0)
        })
    elif len(trades) < 5:
        low_trades.append({
            'name': name,
            'strategy': strategy,
            'trades': len(trades),
            'active': active
        })

print(f"Found {len(zero_trades)} portfolios with 0 trades:\n")
for p in sorted(zero_trades, key=lambda x: x['name']):
    status = "[ON]" if p['active'] and p['auto'] else "[OFF]"
    print(f"  {status} {p['name']}")
    print(f"      Strategy: {p['strategy']}")
    print(f"      Active: {p['active']}, Auto: {p['auto']}, Balance: ${p['balance']:.0f}")
    print()

print(f"\n=== Portfolios avec < 5 trades ===\n")
for p in sorted(low_trades, key=lambda x: x['trades']):
    print(f"  {p['name']}: {p['trades']} trades (strategy: {p['strategy']})")
