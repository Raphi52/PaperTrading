"""
Security Module - Real Trading Protection
==========================================

Handles:
- Private key encryption (AES-256)
- Master password hashing (bcrypt)
- API key validation
- Wallet validation
"""

import os
import json
import base64
import hashlib
import secrets
from typing import Dict, Tuple, Optional
from datetime import datetime

# Try to import cryptography, fall back to simple encryption if not available
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

# Try to import bcrypt, fall back to hashlib if not available
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False

import requests


class SecurityManager:
    """Manages security for real trading operations"""

    def __init__(self, settings_path: str = "data/settings.json"):
        self.settings_path = settings_path
        self._salt = None

    # ==================== PASSWORD HASHING ====================

    def hash_password(self, password: str) -> str:
        """
        Hash a master password using bcrypt (or SHA-256 fallback).
        Returns the hash string to store.
        """
        if BCRYPT_AVAILABLE:
            salt = bcrypt.gensalt(rounds=12)
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
        else:
            # Fallback: SHA-256 with salt
            salt = secrets.token_hex(16)
            combined = f"{salt}:{password}"
            hashed = hashlib.sha256(combined.encode()).hexdigest()
            return f"sha256:{salt}:{hashed}"

    def verify_password(self, password: str, stored_hash: str) -> bool:
        """
        Verify a password against a stored hash.
        Returns True if password matches.
        """
        if not stored_hash:
            return False

        if BCRYPT_AVAILABLE and not stored_hash.startswith('sha256:'):
            try:
                return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
            except Exception:
                return False
        elif stored_hash.startswith('sha256:'):
            # Fallback verification
            parts = stored_hash.split(':')
            if len(parts) != 3:
                return False
            _, salt, expected_hash = parts
            combined = f"{salt}:{password}"
            actual_hash = hashlib.sha256(combined.encode()).hexdigest()
            return actual_hash == expected_hash
        return False

    # ==================== KEY ENCRYPTION ====================

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive an encryption key from password using PBKDF2"""
        if CRYPTO_AVAILABLE:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=480000,
            )
            return base64.urlsafe_b64encode(kdf.derive(password.encode()))
        else:
            # Fallback: simple key derivation
            combined = password.encode() + salt
            return base64.urlsafe_b64encode(hashlib.sha256(combined).digest())

    def encrypt_private_key(self, private_key: str, password: str) -> str:
        """
        Encrypt a private key using AES-256 (Fernet).
        Returns base64-encoded encrypted string with salt prefix.
        """
        salt = secrets.token_bytes(16)
        key = self._derive_key(password, salt)

        if CRYPTO_AVAILABLE:
            f = Fernet(key)
            encrypted = f.encrypt(private_key.encode())
            # Prefix with salt for decryption
            result = base64.urlsafe_b64encode(salt + encrypted)
            return result.decode('utf-8')
        else:
            # Fallback: XOR encryption (NOT secure, just for basic obfuscation)
            key_bytes = key[:32]
            data = private_key.encode()
            encrypted = bytes(a ^ b for a, b in zip(data, (key_bytes * (len(data) // 32 + 1))[:len(data)]))
            result = base64.urlsafe_b64encode(salt + encrypted)
            return f"xor:{result.decode('utf-8')}"

    def decrypt_private_key(self, encrypted: str, password: str) -> Optional[str]:
        """
        Decrypt a private key.
        Returns the original private key or None if decryption fails.
        """
        try:
            if encrypted.startswith('xor:'):
                # Fallback decryption
                data = base64.urlsafe_b64decode(encrypted[4:])
                salt = data[:16]
                encrypted_data = data[16:]
                key = self._derive_key(password, salt)[:32]
                decrypted = bytes(a ^ b for a, b in zip(encrypted_data, (key * (len(encrypted_data) // 32 + 1))[:len(encrypted_data)]))
                return decrypted.decode('utf-8')
            else:
                data = base64.urlsafe_b64decode(encrypted)
                salt = data[:16]
                encrypted_data = data[16:]
                key = self._derive_key(password, salt)

                if CRYPTO_AVAILABLE:
                    f = Fernet(key)
                    decrypted = f.decrypt(encrypted_data)
                    return decrypted.decode('utf-8')
                return None
        except Exception as e:
            print(f"Decryption error: {e}")
            return None

    # ==================== API VALIDATION ====================

    def validate_binance_api(self, api_key: str, secret: str, testnet: bool = True) -> Dict:
        """
        Validate Binance API credentials.
        Returns: {valid: bool, permissions: list, balance_usdt: float, error: str}
        """
        result = {
            'valid': False,
            'permissions': [],
            'balance_usdt': 0,
            'error': None
        }

        if not api_key or not secret:
            result['error'] = "API key or secret is empty"
            return result

        try:
            import hmac
            import time

            # Choose endpoint
            if testnet:
                base_url = "https://testnet.binance.vision"
            else:
                base_url = "https://api.binance.com"

            # Create signature for account info request
            timestamp = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature = hmac.new(
                secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            # Make request
            url = f"{base_url}/api/v3/account?{query_string}&signature={signature}"
            headers = {"X-MBX-APIKEY": api_key}

            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                result['valid'] = True

                # Get permissions
                result['permissions'] = data.get('permissions', [])

                # Get USDT balance
                for balance in data.get('balances', []):
                    if balance['asset'] == 'USDT':
                        result['balance_usdt'] = float(balance['free']) + float(balance['locked'])
                        break

            elif response.status_code == 401:
                result['error'] = "Invalid API key"
            elif response.status_code == 418 or response.status_code == 429:
                result['error'] = "Rate limited - try again later"
            else:
                error_data = response.json() if response.text else {}
                result['error'] = error_data.get('msg', f"HTTP {response.status_code}")

        except requests.exceptions.Timeout:
            result['error'] = "Connection timeout"
        except requests.exceptions.ConnectionError:
            result['error'] = "Connection failed"
        except Exception as e:
            result['error'] = str(e)

        return result

    def validate_solana_wallet(self, private_key: str) -> Dict:
        """
        Validate a Solana wallet private key.
        Returns: {valid: bool, public_key: str, balance_sol: float, error: str}
        """
        result = {
            'valid': False,
            'public_key': None,
            'balance_sol': 0,
            'error': None
        }

        try:
            # Try to import solana libraries
            from solders.keypair import Keypair
            from solana.rpc.api import Client

            # Parse private key (base58 or bytes)
            if len(private_key) == 88:  # Base58 encoded
                keypair = Keypair.from_base58_string(private_key)
            elif len(private_key) == 64:  # Hex encoded
                keypair = Keypair.from_bytes(bytes.fromhex(private_key))
            else:
                # Try as JSON array (Phantom export format)
                try:
                    key_bytes = bytes(json.loads(private_key))
                    keypair = Keypair.from_bytes(key_bytes)
                except:
                    result['error'] = "Invalid private key format"
                    return result

            result['public_key'] = str(keypair.pubkey())
            result['valid'] = True

            # Try to get balance
            try:
                client = Client("https://api.mainnet-beta.solana.com")
                balance_resp = client.get_balance(keypair.pubkey())
                if balance_resp.value is not None:
                    result['balance_sol'] = balance_resp.value / 1e9
            except:
                pass  # Balance check is optional

        except ImportError:
            result['error'] = "Solana libraries not installed (pip install solana solders)"
        except Exception as e:
            result['error'] = str(e)

        return result

    def validate_evm_wallet(self, private_key: str, chain: str = "ethereum") -> Dict:
        """
        Validate an EVM wallet private key (Ethereum, BSC, etc).
        Returns: {valid: bool, public_key: str, balance: float, error: str}
        """
        result = {
            'valid': False,
            'public_key': None,
            'balance': 0,
            'error': None
        }

        # RPC endpoints
        rpc_urls = {
            'ethereum': 'https://eth.llamarpc.com',
            'bsc': 'https://bsc-dataseed.binance.org',
            'polygon': 'https://polygon-rpc.com',
            'arbitrum': 'https://arb1.arbitrum.io/rpc'
        }

        try:
            from web3 import Web3

            # Ensure key has 0x prefix
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key

            # Validate key format
            if len(private_key) != 66:
                result['error'] = "Invalid private key length (should be 64 hex chars)"
                return result

            # Get account from private key
            w3 = Web3()
            account = w3.eth.account.from_key(private_key)
            result['public_key'] = account.address
            result['valid'] = True

            # Try to get balance
            try:
                rpc_url = rpc_urls.get(chain, rpc_urls['ethereum'])
                w3 = Web3(Web3.HTTPProvider(rpc_url))
                if w3.is_connected():
                    balance_wei = w3.eth.get_balance(account.address)
                    result['balance'] = float(w3.from_wei(balance_wei, 'ether'))
            except:
                pass  # Balance check is optional

        except ImportError:
            result['error'] = "Web3 not installed (pip install web3)"
        except Exception as e:
            result['error'] = str(e)

        return result

    # ==================== SETTINGS HELPERS ====================

    def is_real_trading_enabled(self) -> bool:
        """Check if real trading is globally enabled"""
        try:
            with open(self.settings_path, 'r') as f:
                settings = json.load(f)
            return settings.get('real_trading', {}).get('enabled', False)
        except:
            return False

    def get_master_password_hash(self) -> Optional[str]:
        """Get stored master password hash"""
        try:
            with open(self.settings_path, 'r') as f:
                settings = json.load(f)
            return settings.get('real_trading', {}).get('master_password_hash')
        except:
            return None

    def set_master_password(self, password: str) -> bool:
        """Set the master password (hashes and stores it)"""
        try:
            with open(self.settings_path, 'r') as f:
                settings = json.load(f)

            if 'real_trading' not in settings:
                settings['real_trading'] = {}

            settings['real_trading']['master_password_hash'] = self.hash_password(password)

            with open(self.settings_path, 'w') as f:
                json.dump(settings, f, indent=2)

            return True
        except Exception as e:
            print(f"Error setting master password: {e}")
            return False

    def verify_master_password(self, password: str) -> bool:
        """Verify the master password"""
        stored_hash = self.get_master_password_hash()
        if not stored_hash:
            return False
        return self.verify_password(password, stored_hash)


# Singleton instance
security_manager = SecurityManager()


# ==================== UTILITY FUNCTIONS ====================

def validate_api_keys(api_key: str, secret: str, testnet: bool = True) -> Dict:
    """Wrapper for Binance API validation"""
    return security_manager.validate_binance_api(api_key, secret, testnet)


def validate_wallet(chain: str, private_key: str) -> Dict:
    """Wrapper for wallet validation"""
    if chain == 'solana':
        return security_manager.validate_solana_wallet(private_key)
    else:
        return security_manager.validate_evm_wallet(private_key, chain)


def encrypt_key(private_key: str, password: str) -> str:
    """Wrapper for key encryption"""
    return security_manager.encrypt_private_key(private_key, password)


def decrypt_key(encrypted: str, password: str) -> Optional[str]:
    """Wrapper for key decryption"""
    return security_manager.decrypt_private_key(encrypted, password)
