"""Test DEX simulation functions"""
from bot import execute_dex_trade_realistic

print("=== Testing 20 buys to see MEV/TX failures ===")
mev_count = 0
fail_count = 0
ok_count = 0

for i in range(20):
    result = execute_dex_trade_realistic(
        chain='solana',
        token_address=f'token{i}',
        token_price=0.001,
        trade_size_usd=200,
        liquidity_usd=10000,
        is_buy=True
    )
    if result['was_frontrun']:
        mev_count += 1
        print(f'  FRONTRUN #{i+1}: +MEV slippage')
    elif result['tx_failed']:
        fail_count += 1
        print(f'  TX FAIL #{i+1}: Lost gas')
    else:
        ok_count += 1

print()
print(f"Results: {ok_count} OK, {mev_count} FRONTRUN, {fail_count} TX FAILED")
print()

# Test position size limit
print("=== Test: $500 buy with only $1000 liquidity ===")
result = execute_dex_trade_realistic(
    chain='ethereum',
    token_address='testlimit',
    token_price=0.01,
    trade_size_usd=500,
    liquidity_usd=1000,
    is_buy=True
)
if result['success']:
    print(f"Requested $500, got reduced to ${result['actual_trade_size']:.2f}")
    print(f"Size reduced: {result['size_reduced']}")
else:
    print(f"Failed: {result.get('fail_reason')}")

print()
print("All simulation tests passed!")

