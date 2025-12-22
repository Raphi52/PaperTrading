"""
Real Trade Executor
====================

Unified interface for executing real trades on:
- Binance (via CCXT)
- DEX (Solana, Ethereum, BSC)

Includes:
- Pre-trade validation via RiskGuard
- Execution with error handling
- Post-trade logging
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from core.risk_guard import RiskGuard, TradeValidation
from core.security import SecurityManager, decrypt_key


@dataclass
class ExecutionResult:
    """Result of a trade execution"""
    success: bool
    order_id: Optional[str] = None
    symbol: str = ""
    action: str = ""
    requested_amount: float = 0
    executed_amount: float = 0
    execution_price: float = 0
    fees: float = 0
    pnl: float = 0
    error: Optional[str] = None
    warnings: list = None
    exchange_response: dict = None
    timestamp: str = ""

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.timestamp == "":
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'order_id': self.order_id,
            'symbol': self.symbol,
            'action': self.action,
            'requested_amount': self.requested_amount,
            'executed_amount': self.executed_amount,
            'execution_price': self.execution_price,
            'fees': self.fees,
            'pnl': self.pnl,
            'error': self.error,
            'warnings': self.warnings,
            'timestamp': self.timestamp
        }


class RealExecutor:
    """Executes real trades with full validation and logging"""

    def __init__(self, portfolio: dict, settings: dict, master_password: str = None):
        """
        Initialize the executor for a specific portfolio.

        Args:
            portfolio: The portfolio dict
            settings: Global settings from data/settings.json
            master_password: Master password for decrypting private keys
        """
        self.portfolio = portfolio
        self.settings = settings
        self.master_password = master_password
        self.risk_guard = RiskGuard(portfolio, settings)
        self.security = SecurityManager()

        # Determine market type
        self.market_type = portfolio.get('market_type', 'binance')
        self.trading_mode = portfolio.get('trading_mode', 'paper')

    def execute_trade(self, action: str, symbol: str, amount_usd: float,
                      entry_price: float = 0) -> ExecutionResult:
        """
        Execute a real trade with full validation.

        Args:
            action: 'BUY' or 'SELL'
            symbol: Trading pair (e.g., 'BTC/USDT' or token address)
            amount_usd: Trade size in USD
            entry_price: Entry price for PnL calculation (SELL only)

        Returns:
            ExecutionResult with success status and details
        """
        # 1. Verify trading mode
        if self.trading_mode != 'real':
            return ExecutionResult(
                success=False,
                error="Portfolio is not in real trading mode",
                symbol=symbol,
                action=action
            )

        # 2. Pre-validation via RiskGuard
        validation = self.risk_guard.can_execute_trade(amount_usd, action == 'BUY')
        if not validation.allowed:
            return ExecutionResult(
                success=False,
                error=validation.reason,
                warnings=validation.warnings,
                symbol=symbol,
                action=action,
                requested_amount=amount_usd
            )

        # 3. Route to appropriate exchange
        try:
            if self.market_type == 'binance':
                result = self._execute_binance(action, symbol, amount_usd, entry_price)
            elif self.market_type.startswith('dex_'):
                chain = self.market_type.replace('dex_', '')
                result = self._execute_dex(action, symbol, amount_usd, chain, entry_price)
            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unknown market type: {self.market_type}",
                    symbol=symbol,
                    action=action
                )

            # 4. Record result in RiskGuard
            if result.success:
                self.risk_guard.record_trade_result(
                    pnl=result.pnl,
                    trade_info=result.to_dict()
                )

            # 5. Add any pre-trade warnings
            if validation.warnings:
                result.warnings.extend(validation.warnings)

            return result

        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Execution error: {str(e)}",
                symbol=symbol,
                action=action,
                requested_amount=amount_usd
            )

    def _execute_binance(self, action: str, symbol: str, amount_usd: float,
                         entry_price: float = 0) -> ExecutionResult:
        """Execute trade on Binance via CCXT"""
        try:
            from core.exchange import Exchange

            # Get API credentials
            api_key = self.settings.get('binance_api_key', '')
            api_secret = self.settings.get('binance_secret', '')
            testnet = self.settings.get('binance_testnet', True)

            if not api_key or not api_secret:
                return ExecutionResult(
                    success=False,
                    error="Binance API credentials not configured",
                    symbol=symbol,
                    action=action
                )

            # Initialize exchange
            exchange = Exchange(name='binance', testnet=testnet)

            if action == 'BUY':
                result = exchange.create_market_buy(symbol, amount_usd)

                if result.get('success'):
                    return ExecutionResult(
                        success=True,
                        order_id=result.get('order_id'),
                        symbol=symbol,
                        action='BUY',
                        requested_amount=amount_usd,
                        executed_amount=result.get('cost', amount_usd),
                        execution_price=result.get('price', 0),
                        fees=result.get('cost', 0) * 0.001,  # ~0.1% Binance fee
                        exchange_response=result
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=result.get('error', 'Unknown error'),
                        symbol=symbol,
                        action='BUY',
                        requested_amount=amount_usd
                    )

            elif action == 'SELL':
                # Get quantity from portfolio position
                positions = self.portfolio.get('positions', {})
                position = positions.get(symbol, {})
                quantity = position.get('quantity', 0)

                if quantity <= 0:
                    return ExecutionResult(
                        success=False,
                        error=f"No position to sell for {symbol}",
                        symbol=symbol,
                        action='SELL'
                    )

                result = exchange.create_market_sell(symbol, quantity=quantity)

                if result.get('success'):
                    # Calculate PnL
                    exit_price = result.get('price', 0)
                    revenue = result.get('revenue', quantity * exit_price)
                    fees = revenue * 0.001
                    pnl = (exit_price - entry_price) * quantity - fees if entry_price > 0 else 0

                    return ExecutionResult(
                        success=True,
                        order_id=result.get('order_id'),
                        symbol=symbol,
                        action='SELL',
                        requested_amount=amount_usd,
                        executed_amount=revenue,
                        execution_price=exit_price,
                        fees=fees,
                        pnl=pnl,
                        exchange_response=result
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=result.get('error', 'Unknown error'),
                        symbol=symbol,
                        action='SELL'
                    )

        except ImportError:
            return ExecutionResult(
                success=False,
                error="CCXT library not available",
                symbol=symbol,
                action=action
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                symbol=symbol,
                action=action
            )

    def _execute_dex(self, action: str, symbol: str, amount_usd: float,
                     chain: str, entry_price: float = 0) -> ExecutionResult:
        """Execute trade on DEX (Solana, Ethereum, BSC)"""

        # Get wallet configuration
        wallets = self.settings.get('wallets', {})
        wallet_config = wallets.get(chain, {})

        if not wallet_config.get('enabled'):
            return ExecutionResult(
                success=False,
                error=f"Wallet for {chain} not enabled",
                symbol=symbol,
                action=action
            )

        encrypted_key = wallet_config.get('private_key_encrypted', '')
        if not encrypted_key:
            return ExecutionResult(
                success=False,
                error=f"No private key configured for {chain}",
                symbol=symbol,
                action=action
            )

        # Decrypt private key
        if not self.master_password:
            return ExecutionResult(
                success=False,
                error="Master password required for DEX trading",
                symbol=symbol,
                action=action
            )

        private_key = decrypt_key(encrypted_key, self.master_password)
        if not private_key:
            return ExecutionResult(
                success=False,
                error="Failed to decrypt private key - wrong password?",
                symbol=symbol,
                action=action
            )

        # Route to chain-specific executor
        try:
            if chain == 'solana':
                return self._execute_solana(action, symbol, amount_usd, private_key, entry_price)
            elif chain in ['ethereum', 'bsc', 'polygon', 'arbitrum']:
                rpc_url = wallet_config.get('rpc_url', '')
                return self._execute_evm(action, symbol, amount_usd, private_key, chain, rpc_url, entry_price)
            else:
                return ExecutionResult(
                    success=False,
                    error=f"Unsupported chain: {chain}",
                    symbol=symbol,
                    action=action
                )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"DEX execution error: {str(e)}",
                symbol=symbol,
                action=action
            )

    def _execute_solana(self, action: str, symbol: str, amount_usd: float,
                        private_key: str, entry_price: float = 0) -> ExecutionResult:
        """Execute trade on Solana via Jupiter"""
        try:
            from core.jupiter import JupiterSwapper, JupiterClient

            # Get token address from position or symbol
            token_address = None
            positions = self.portfolio.get('positions', {})

            # Check if symbol is in positions (for SELL)
            if symbol in positions:
                token_address = positions[symbol].get('address', '')

            # If no address found, try to extract from symbol (for sniper tokens)
            if not token_address:
                # Check if it's a known token or we have it stored somewhere
                for pos_symbol, pos_data in positions.items():
                    if symbol in pos_symbol or pos_symbol in symbol:
                        token_address = pos_data.get('address', '')
                        break

            if not token_address:
                return ExecutionResult(
                    success=False,
                    error=f"No token address found for {symbol}. Need contract address for DEX trading.",
                    symbol=symbol,
                    action=action
                )

            # Initialize Jupiter swapper
            swapper = JupiterSwapper(private_key)

            if not swapper.keypair:
                return ExecutionResult(
                    success=False,
                    error="Invalid wallet private key format",
                    symbol=symbol,
                    action=action
                )

            # Check SOL balance for fees
            balances = swapper.get_balances()
            sol_balance = balances.get('sol', 0)

            if sol_balance < 0.01:
                return ExecutionResult(
                    success=False,
                    error=f"Insufficient SOL for fees (have {sol_balance:.4f} SOL, need 0.01)",
                    symbol=symbol,
                    action=action
                )

            # Get SOL price for USD conversion
            client = JupiterClient()
            sol_price = client.get_token_price("So11111111111111111111111111111111111111112") or 100

            if action.upper() == 'BUY':
                # Convert USD to SOL
                amount_sol = amount_usd / sol_price

                # Check if we have enough SOL
                if amount_sol > (sol_balance - 0.01):  # Keep 0.01 for fees
                    amount_sol = sol_balance - 0.01
                    if amount_sol <= 0:
                        return ExecutionResult(
                            success=False,
                            error=f"Not enough SOL. Have {sol_balance:.4f}, need at least 0.02",
                            symbol=symbol,
                            action=action
                        )

                # Execute buy via Jupiter
                result = swapper.buy_token(
                    token_mint=token_address,
                    amount_sol=amount_sol,
                    slippage_pct=1.0  # 1% slippage
                )

                if result.success:
                    return ExecutionResult(
                        success=True,
                        order_id=result.signature,
                        symbol=symbol,
                        action='BUY',
                        requested_amount=amount_usd,
                        executed_amount=amount_sol * sol_price,
                        execution_price=result.price if result.price else 0,
                        fees=result.fees_sol * sol_price,
                        exchange_response={
                            'signature': result.signature,
                            'explorer': f"https://solscan.io/tx/{result.signature}",
                            'input_sol': result.input_amount,
                            'output_tokens': result.output_amount
                        }
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=result.error or "Jupiter swap failed",
                        symbol=symbol,
                        action='BUY'
                    )

            elif action.upper() == 'SELL':
                # Get position quantity
                position = positions.get(symbol, {})
                token_amount = position.get('quantity', 0)

                if token_amount <= 0:
                    return ExecutionResult(
                        success=False,
                        error=f"No tokens to sell for {symbol}",
                        symbol=symbol,
                        action='SELL'
                    )

                # Execute sell via Jupiter (sell all)
                result = swapper.sell_token(
                    token_mint=token_address,
                    sell_all=True,
                    slippage_pct=1.5  # 1.5% slippage for sells (often less liquid)
                )

                if result.success:
                    # Calculate PnL
                    received_sol = result.output_amount
                    received_usd = received_sol * sol_price
                    entry_value = entry_price * token_amount if entry_price > 0 else 0
                    pnl = received_usd - entry_value

                    return ExecutionResult(
                        success=True,
                        order_id=result.signature,
                        symbol=symbol,
                        action='SELL',
                        requested_amount=token_amount,
                        executed_amount=received_usd,
                        execution_price=result.price if result.price else 0,
                        fees=result.fees_sol * sol_price,
                        pnl=pnl,
                        exchange_response={
                            'signature': result.signature,
                            'explorer': f"https://solscan.io/tx/{result.signature}",
                            'input_tokens': result.input_amount,
                            'output_sol': result.output_amount
                        }
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=result.error or "Jupiter swap failed",
                        symbol=symbol,
                        action='SELL'
                    )

            return ExecutionResult(
                success=False,
                error=f"Unknown action: {action}",
                symbol=symbol,
                action=action
            )

        except ImportError as e:
            return ExecutionResult(
                success=False,
                error=f"Missing dependencies: {e}. Install with: pip install solana solders",
                symbol=symbol,
                action=action
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"Solana/Jupiter error: {str(e)}",
                symbol=symbol,
                action=action
            )

    def _execute_evm(self, action: str, symbol: str, amount_usd: float,
                     private_key: str, chain: str, rpc_url: str,
                     entry_price: float = 0) -> ExecutionResult:
        """Execute trade on EVM chain - routes to appropriate DEX"""

        # Route BSC to PancakeSwap, others to Uniswap
        if chain == 'bsc':
            return self._execute_bsc(action, symbol, amount_usd, private_key, rpc_url, entry_price)
        else:
            return self._execute_uniswap(action, symbol, amount_usd, private_key, chain, rpc_url, entry_price)

    def _execute_bsc(self, action: str, symbol: str, amount_usd: float,
                     private_key: str, rpc_url: str,
                     entry_price: float = 0) -> ExecutionResult:
        """Execute trade on BSC via PancakeSwap"""
        try:
            from core.pancakeswap import PancakeSwapper, get_bnb_price

            # Get token address from position or symbol
            token_address = None
            positions = self.portfolio.get('positions', {})

            if symbol in positions:
                token_address = positions[symbol].get('address', '')

            if not token_address:
                for pos_symbol, pos_data in positions.items():
                    if symbol in pos_symbol or pos_symbol in symbol:
                        token_address = pos_data.get('address', '')
                        break

            if not token_address:
                return ExecutionResult(
                    success=False,
                    error=f"No token address found for {symbol}. Need contract address for DEX trading.",
                    symbol=symbol,
                    action=action
                )

            # Initialize PancakeSwap swapper
            swapper = PancakeSwapper(private_key, rpc_url)

            if not swapper.account:
                return ExecutionResult(
                    success=False,
                    error="Invalid wallet private key format",
                    symbol=symbol,
                    action=action
                )

            if not swapper.client.is_connected():
                return ExecutionResult(
                    success=False,
                    error="Failed to connect to BSC RPC",
                    symbol=symbol,
                    action=action
                )

            # Check BNB balance for fees
            balances = swapper.get_balances()
            bnb_balance = balances.get('bnb', 0)

            if bnb_balance < 0.005:
                return ExecutionResult(
                    success=False,
                    error=f"Insufficient BNB for fees (have {bnb_balance:.4f}, need 0.005)",
                    symbol=symbol,
                    action=action
                )

            # Get BNB price for USD conversion
            bnb_price = get_bnb_price() or 300  # Fallback price

            if action.upper() == 'BUY':
                # Convert USD to BNB
                amount_bnb = amount_usd / bnb_price

                # Check if we have enough BNB
                if amount_bnb > (bnb_balance - 0.005):
                    amount_bnb = bnb_balance - 0.005
                    if amount_bnb <= 0:
                        return ExecutionResult(
                            success=False,
                            error=f"Not enough BNB. Have {bnb_balance:.4f}, need at least 0.01",
                            symbol=symbol,
                            action=action
                        )

                # Execute buy via PancakeSwap
                result = swapper.buy_token(
                    token_address=token_address,
                    amount_bnb=amount_bnb,
                    slippage_pct=0.5
                )

                if result.success:
                    return ExecutionResult(
                        success=True,
                        order_id=result.tx_hash,
                        symbol=symbol,
                        action='BUY',
                        requested_amount=amount_usd,
                        executed_amount=amount_bnb * bnb_price,
                        execution_price=result.price if result.price else 0,
                        fees=result.total_fee_bnb * bnb_price,
                        exchange_response={
                            'tx_hash': result.tx_hash,
                            'explorer': f"https://bscscan.com/tx/{result.tx_hash}",
                            'input_bnb': result.input_amount,
                            'output_tokens': result.output_amount,
                            'gas_used': result.gas_used,
                            'gas_price_gwei': result.gas_price_gwei
                        }
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=result.error or "PancakeSwap swap failed",
                        symbol=symbol,
                        action='BUY'
                    )

            elif action.upper() == 'SELL':
                position = positions.get(symbol, {})
                token_amount = position.get('quantity', 0)

                if token_amount <= 0:
                    return ExecutionResult(
                        success=False,
                        error=f"No tokens to sell for {symbol}",
                        symbol=symbol,
                        action='SELL'
                    )

                result = swapper.sell_token(
                    token_address=token_address,
                    sell_all=True,
                    slippage_pct=1.0
                )

                if result.success:
                    received_bnb = result.output_amount
                    received_usd = received_bnb * bnb_price
                    entry_value = entry_price * token_amount if entry_price > 0 else 0
                    pnl = received_usd - entry_value

                    return ExecutionResult(
                        success=True,
                        order_id=result.tx_hash,
                        symbol=symbol,
                        action='SELL',
                        requested_amount=token_amount,
                        executed_amount=received_usd,
                        execution_price=result.price if result.price else 0,
                        fees=result.total_fee_bnb * bnb_price,
                        pnl=pnl,
                        exchange_response={
                            'tx_hash': result.tx_hash,
                            'explorer': f"https://bscscan.com/tx/{result.tx_hash}",
                            'input_tokens': result.input_amount,
                            'output_bnb': result.output_amount,
                            'gas_used': result.gas_used,
                            'gas_price_gwei': result.gas_price_gwei
                        }
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=result.error or "PancakeSwap swap failed",
                        symbol=symbol,
                        action='SELL'
                    )

            return ExecutionResult(
                success=False,
                error=f"Unknown action: {action}",
                symbol=symbol,
                action=action
            )

        except ImportError as e:
            return ExecutionResult(
                success=False,
                error=f"Missing dependencies: {e}. Install with: pip install web3",
                symbol=symbol,
                action=action
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"BSC/PancakeSwap error: {str(e)}",
                symbol=symbol,
                action=action
            )

    def _execute_uniswap(self, action: str, symbol: str, amount_usd: float,
                         private_key: str, chain: str, rpc_url: str,
                         entry_price: float = 0) -> ExecutionResult:
        """Execute trade on EVM chain (Ethereum, Polygon, Arbitrum) via Uniswap"""
        try:
            from core.uniswap import UniswapSwapper, get_eth_price

            # Get token address from position or symbol
            token_address = None
            positions = self.portfolio.get('positions', {})

            if symbol in positions:
                token_address = positions[symbol].get('address', '')

            if not token_address:
                for pos_symbol, pos_data in positions.items():
                    if symbol in pos_symbol or pos_symbol in symbol:
                        token_address = pos_data.get('address', '')
                        break

            if not token_address:
                return ExecutionResult(
                    success=False,
                    error=f"No token address found for {symbol}. Need contract address for DEX trading.",
                    symbol=symbol,
                    action=action
                )

            # Initialize Uniswap swapper
            swapper = UniswapSwapper(private_key, rpc_url, chain)

            if not swapper.account:
                return ExecutionResult(
                    success=False,
                    error="Invalid wallet private key format",
                    symbol=symbol,
                    action=action
                )

            if not swapper.client.is_connected():
                return ExecutionResult(
                    success=False,
                    error=f"Failed to connect to {chain} RPC",
                    symbol=symbol,
                    action=action
                )

            # Check native token balance for fees
            balances = swapper.get_balances()
            eth_balance = balances.get('eth', 0)

            min_balance = {'ethereum': 0.01, 'polygon': 0.1, 'arbitrum': 0.001, 'base': 0.001, 'optimism': 0.001}
            min_eth = min_balance.get(chain, 0.01)

            if eth_balance < min_eth:
                native_token = 'MATIC' if chain == 'polygon' else 'ETH'
                return ExecutionResult(
                    success=False,
                    error=f"Insufficient {native_token} for fees (have {eth_balance:.4f}, need {min_eth})",
                    symbol=symbol,
                    action=action
                )

            # Get ETH price for USD conversion
            eth_price = get_eth_price() or 2000  # Fallback price

            explorers = {
                'ethereum': 'https://etherscan.io/tx/',
                'polygon': 'https://polygonscan.com/tx/',
                'arbitrum': 'https://arbiscan.io/tx/',
                'base': 'https://basescan.org/tx/',
                'optimism': 'https://optimistic.etherscan.io/tx/',
            }
            explorer = explorers.get(chain, explorers['ethereum'])

            if action.upper() == 'BUY':
                amount_eth = amount_usd / eth_price

                if amount_eth > (eth_balance - min_eth):
                    amount_eth = eth_balance - min_eth
                    if amount_eth <= 0:
                        return ExecutionResult(
                            success=False,
                            error=f"Not enough ETH. Have {eth_balance:.4f}, need at least {min_eth * 2:.4f}",
                            symbol=symbol,
                            action=action
                        )

                result = swapper.buy_token(
                    token_address=token_address,
                    amount_eth=amount_eth,
                    slippage_pct=0.5
                )

                if result.success:
                    return ExecutionResult(
                        success=True,
                        order_id=result.tx_hash,
                        symbol=symbol,
                        action='BUY',
                        requested_amount=amount_usd,
                        executed_amount=amount_eth * eth_price,
                        execution_price=result.price if result.price else 0,
                        fees=result.total_fee_eth * eth_price,
                        exchange_response={
                            'tx_hash': result.tx_hash,
                            'explorer': f"{explorer}{result.tx_hash}",
                            'input_eth': result.input_amount,
                            'output_tokens': result.output_amount,
                            'gas_used': result.gas_used,
                            'gas_price_gwei': result.gas_price_gwei
                        }
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=result.error or "Uniswap swap failed",
                        symbol=symbol,
                        action='BUY'
                    )

            elif action.upper() == 'SELL':
                position = positions.get(symbol, {})
                token_amount = position.get('quantity', 0)

                if token_amount <= 0:
                    return ExecutionResult(
                        success=False,
                        error=f"No tokens to sell for {symbol}",
                        symbol=symbol,
                        action='SELL'
                    )

                result = swapper.sell_token(
                    token_address=token_address,
                    sell_all=True,
                    slippage_pct=1.0
                )

                if result.success:
                    received_eth = result.output_amount
                    received_usd = received_eth * eth_price
                    entry_value = entry_price * token_amount if entry_price > 0 else 0
                    pnl = received_usd - entry_value

                    return ExecutionResult(
                        success=True,
                        order_id=result.tx_hash,
                        symbol=symbol,
                        action='SELL',
                        requested_amount=token_amount,
                        executed_amount=received_usd,
                        execution_price=result.price if result.price else 0,
                        fees=result.total_fee_eth * eth_price,
                        pnl=pnl,
                        exchange_response={
                            'tx_hash': result.tx_hash,
                            'explorer': f"{explorer}{result.tx_hash}",
                            'input_tokens': result.input_amount,
                            'output_eth': result.output_amount,
                            'gas_used': result.gas_used,
                            'gas_price_gwei': result.gas_price_gwei
                        }
                    )
                else:
                    return ExecutionResult(
                        success=False,
                        error=result.error or "Uniswap swap failed",
                        symbol=symbol,
                        action='SELL'
                    )

            return ExecutionResult(
                success=False,
                error=f"Unknown action: {action}",
                symbol=symbol,
                action=action
            )

        except ImportError as e:
            return ExecutionResult(
                success=False,
                error=f"Missing dependencies: {e}. Install with: pip install web3",
                symbol=symbol,
                action=action
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=f"EVM/Uniswap error: {str(e)}",
                symbol=symbol,
                action=action
            )


# ==================== HELPER FUNCTIONS ====================

def execute_real_trade(portfolio: dict, action: str, symbol: str,
                       price: float, amount_usdt: float = None,
                       settings: dict = None, master_password: str = None) -> dict:
    """
    Wrapper function for executing real trades.
    Can be called from bot.py.

    Returns:
        dict with trade result
    """
    if settings is None:
        try:
            with open('data/settings.json', 'r') as f:
                settings = json.load(f)
        except:
            settings = {}

    if amount_usdt is None:
        amount_usdt = portfolio.get('config', {}).get('allocation_percent', 10) / 100
        amount_usdt *= portfolio.get('balance', {}).get('USDT', 0)

    executor = RealExecutor(portfolio, settings, master_password)
    result = executor.execute_trade(action, symbol, amount_usdt, entry_price=price)

    return result.to_dict()


def is_real_trading_ready(portfolio: dict, settings: dict = None) -> Tuple[bool, str]:
    """
    Check if a portfolio is ready for real trading.

    Returns:
        (ready: bool, reason: str)
    """
    if settings is None:
        try:
            with open('data/settings.json', 'r') as f:
                settings = json.load(f)
        except:
            return False, "Cannot load settings"

    # Check trading mode
    if portfolio.get('trading_mode') != 'real':
        return False, "Portfolio not in real trading mode"

    # Check global enable
    if not settings.get('real_trading', {}).get('enabled', False):
        return False, "Real trading not enabled globally"

    # Check market type
    market_type = portfolio.get('market_type', 'binance')

    if market_type == 'binance':
        if not settings.get('binance_api_key') or not settings.get('binance_secret'):
            return False, "Binance API keys not configured"
    elif market_type.startswith('dex_'):
        chain = market_type.replace('dex_', '')
        wallet = settings.get('wallets', {}).get(chain, {})
        if not wallet.get('enabled'):
            return False, f"Wallet for {chain} not enabled"
        if not wallet.get('private_key_encrypted'):
            return False, f"Private key for {chain} not configured"

    return True, "Ready for real trading"
