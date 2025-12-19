"""
Risk Manager - Gestion du risque et des positions
"""
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
import json
import os

from config.settings import trading_config
from utils.logger import logger


@dataclass
class Position:
    """Représente une position ouverte"""
    symbol: str
    side: str  # 'long' ou 'short'
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    trailing_stop: Optional[float] = None
    highest_price: float = 0  # Pour trailing stop
    pnl: float = 0
    pnl_percent: float = 0


@dataclass
class TradeRecord:
    """Historique d'un trade"""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_percent: float
    entry_time: datetime
    exit_time: datetime
    reason: str  # 'take_profit', 'stop_loss', 'trailing_stop', 'signal'


class RiskManager:
    """
    Gestionnaire de risque

    Règles:
    1. Max 2% du capital par trade
    2. Stop loss obligatoire
    3. Take profit défini
    4. Max 3 positions simultanées
    5. Pas de trade si drawdown > 10%
    """

    def __init__(self):
        self.config = trading_config
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeRecord] = []
        self.initial_capital: float = 0
        self.current_capital: float = 0
        self.max_positions = 3
        self.max_drawdown_percent = 10
        self.daily_loss_limit = 5  # % max loss par jour

        # Stats
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0

        # Load history
        self._load_state()

    def can_open_position(self, symbol: str, capital: float) -> Tuple[bool, str]:
        """
        Vérifie si on peut ouvrir une nouvelle position

        Returns:
            (can_trade, reason)
        """
        # Vérifier le nombre de positions
        if len(self.positions) >= self.max_positions:
            return False, f"Max positions reached ({self.max_positions})"

        # Vérifier si position déjà ouverte sur ce symbol
        if symbol in self.positions:
            return False, f"Position already open on {symbol}"

        # Vérifier le drawdown
        if self.initial_capital > 0:
            drawdown = (self.initial_capital - capital) / self.initial_capital * 100
            if drawdown > self.max_drawdown_percent:
                return False, f"Max drawdown exceeded ({drawdown:.1f}%)"

        # Vérifier la perte journalière
        daily_pnl = self._calculate_daily_pnl()
        if daily_pnl < -self.daily_loss_limit:
            return False, f"Daily loss limit reached ({daily_pnl:.1f}%)"

        return True, "OK"

    def calculate_position_size(self, capital: float, entry_price: float,
                                stop_loss_price: float, confidence: int = 70) -> float:
        """
        Calcule la taille de position basée sur le risque

        Formule: Position = (Capital * Risk%) / (Entry - StopLoss)

        Args:
            capital: Capital disponible en USDT
            entry_price: Prix d'entrée prévu
            stop_loss_price: Prix du stop loss
            confidence: Confiance du signal (0-100)

        Returns:
            Montant en USDT à investir
        """
        # Risk de base: 2% du capital
        base_risk = self.config.max_risk_percent / 100

        # Ajuster le risque selon la confiance
        # 50% confidence = 0.5x risk, 100% confidence = 1.5x risk
        confidence_multiplier = 0.5 + (confidence / 100)
        adjusted_risk = base_risk * confidence_multiplier

        # Distance au stop loss en %
        stop_distance = abs(entry_price - stop_loss_price) / entry_price

        if stop_distance == 0:
            stop_distance = self.config.stop_loss_percent / 100

        # Taille de position
        position_usdt = (capital * adjusted_risk) / stop_distance

        # Cap à 20% du capital max par position
        max_position = capital * 0.20
        position_usdt = min(position_usdt, max_position)

        # Minimum trade amount
        position_usdt = max(position_usdt, self.config.trade_amount_usdt)

        logger.info(f"Position size: ${position_usdt:.2f} (Risk: {adjusted_risk*100:.1f}%, SL distance: {stop_distance*100:.1f}%)")

        return position_usdt

    def open_position(self, symbol: str, side: str, entry_price: float,
                      quantity: float) -> Position:
        """Ouvre une nouvelle position avec SL/TP"""

        # Calculer SL et TP
        if side == 'long':
            stop_loss = entry_price * (1 - self.config.stop_loss_percent / 100)
            take_profit = entry_price * (1 + self.config.take_profit_percent / 100)
        else:  # short
            stop_loss = entry_price * (1 + self.config.stop_loss_percent / 100)
            take_profit = entry_price * (1 - self.config.take_profit_percent / 100)

        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            highest_price=entry_price
        )

        self.positions[symbol] = position
        self._save_state()

        logger.info(f"Position opened: {side.upper()} {quantity} {symbol} @ ${entry_price:.2f}")
        logger.info(f"  Stop Loss: ${stop_loss:.2f} | Take Profit: ${take_profit:.2f}")

        return position

    def update_position(self, symbol: str, current_price: float) -> Optional[str]:
        """
        Met à jour une position et vérifie SL/TP

        Returns:
            'take_profit', 'stop_loss', 'trailing_stop' ou None
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Calculer PnL
        if pos.side == 'long':
            pos.pnl = (current_price - pos.entry_price) * pos.quantity
            pos.pnl_percent = (current_price - pos.entry_price) / pos.entry_price * 100
        else:
            pos.pnl = (pos.entry_price - current_price) * pos.quantity
            pos.pnl_percent = (pos.entry_price - current_price) / pos.entry_price * 100

        # Update highest price pour trailing stop
        if current_price > pos.highest_price:
            pos.highest_price = current_price

            # Activer trailing stop si en profit > 2%
            if pos.pnl_percent > 2 and pos.trailing_stop is None:
                pos.trailing_stop = current_price * (1 - self.config.trailing_stop_percent / 100)
                logger.info(f"Trailing stop activated at ${pos.trailing_stop:.2f}")

            # Mettre à jour trailing stop
            elif pos.trailing_stop:
                new_trailing = current_price * (1 - self.config.trailing_stop_percent / 100)
                if new_trailing > pos.trailing_stop:
                    pos.trailing_stop = new_trailing

        # Vérifier Take Profit
        if pos.side == 'long' and current_price >= pos.take_profit:
            return 'take_profit'
        elif pos.side == 'short' and current_price <= pos.take_profit:
            return 'take_profit'

        # Vérifier Stop Loss
        if pos.side == 'long' and current_price <= pos.stop_loss:
            return 'stop_loss'
        elif pos.side == 'short' and current_price >= pos.stop_loss:
            return 'stop_loss'

        # Vérifier Trailing Stop
        if pos.trailing_stop:
            if pos.side == 'long' and current_price <= pos.trailing_stop:
                return 'trailing_stop'

        return None

    def close_position(self, symbol: str, exit_price: float, reason: str) -> Optional[TradeRecord]:
        """Ferme une position et enregistre le trade"""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Calculer PnL final
        if pos.side == 'long':
            pnl = (exit_price - pos.entry_price) * pos.quantity
            pnl_percent = (exit_price - pos.entry_price) / pos.entry_price * 100
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity
            pnl_percent = (pos.entry_price - exit_price) / pos.entry_price * 100

        # Créer le record
        record = TradeRecord(
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            pnl=pnl,
            pnl_percent=pnl_percent,
            entry_time=pos.entry_time,
            exit_time=datetime.now(),
            reason=reason
        )

        # Mettre à jour les stats
        self.trade_history.append(record)
        self.total_trades += 1
        self.total_pnl += pnl

        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        # Supprimer la position
        del self.positions[symbol]
        self._save_state()

        # Log
        emoji = "✅" if pnl > 0 else "❌"
        logger.info(f"{emoji} Position closed: {symbol} | PnL: ${pnl:.2f} ({pnl_percent:+.1f}%) | Reason: {reason}")

        return record

    def get_stats(self) -> Dict:
        """Retourne les statistiques de trading"""
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'total_pnl': self.total_pnl,
            'open_positions': len(self.positions),
            'positions': list(self.positions.keys())
        }

    def _calculate_daily_pnl(self) -> float:
        """Calcule le PnL du jour"""
        today = datetime.now().date()
        daily_pnl = sum(
            t.pnl for t in self.trade_history
            if t.exit_time.date() == today
        )
        return (daily_pnl / self.initial_capital * 100) if self.initial_capital > 0 else 0

    def _save_state(self):
        """Sauvegarde l'état"""
        state = {
            'positions': {k: vars(v) for k, v in self.positions.items()},
            'stats': {
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades,
                'total_pnl': self.total_pnl
            }
        }

        # Convertir datetime en string
        for pos in state['positions'].values():
            if isinstance(pos.get('entry_time'), datetime):
                pos['entry_time'] = pos['entry_time'].isoformat()

        try:
            with open('data/risk_state.json', 'w') as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save risk state: {e}")

    def _load_state(self):
        """Charge l'état précédent"""
        try:
            if os.path.exists('data/risk_state.json'):
                with open('data/risk_state.json', 'r') as f:
                    state = json.load(f)
                    stats = state.get('stats', {})
                    self.total_trades = stats.get('total_trades', 0)
                    self.winning_trades = stats.get('winning_trades', 0)
                    self.losing_trades = stats.get('losing_trades', 0)
                    self.total_pnl = stats.get('total_pnl', 0)
        except Exception as e:
            logger.warning(f"Failed to load risk state: {e}")


# Import manquant
from typing import Tuple
