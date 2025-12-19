"""
Take Profit Ladder - Vente par paliers
=======================================

Permet de vendre une position en plusieurs tranches:
- 25% a +2%
- 25% a +5%
- 25% a +10%
- 25% trailing stop

Evite de tout vendre trop tot ou trop tard.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from enum import Enum
import json


class LadderType(Enum):
    """Types de ladder predefinis"""
    CONSERVATIVE = "conservative"  # Prendre profits tot
    BALANCED = "balanced"          # Equilibre
    AGGRESSIVE = "aggressive"      # Laisser courir
    MOONBAG = "moonbag"            # Garder une partie pour le moon
    CUSTOM = "custom"


@dataclass
class LadderStep:
    """Une etape du ladder"""
    percent_to_sell: float      # % de la position a vendre (ex: 25)
    trigger_profit_pct: float   # % de profit pour declencher (ex: 5.0)
    is_trailing: bool = False   # Si True, utilise trailing au lieu de TP fixe
    trailing_distance: float = 1.0  # Distance du trailing en %
    executed: bool = False
    executed_at: Optional[datetime] = None
    executed_price: Optional[float] = None
    pnl: float = 0


@dataclass
class TPLadder:
    """Configuration complete d'un TP Ladder"""
    name: str
    steps: List[LadderStep]
    total_sold_pct: float = 0
    remaining_pct: float = 100
    highest_profit_pct: float = 0

    def get_next_step(self) -> Optional[LadderStep]:
        """Retourne la prochaine etape non executee"""
        for step in self.steps:
            if not step.executed:
                return step
        return None

    def get_executed_steps(self) -> List[LadderStep]:
        """Retourne les etapes executees"""
        return [s for s in self.steps if s.executed]

    def is_complete(self) -> bool:
        """Verifie si tous les steps sont executes"""
        return all(s.executed for s in self.steps)


# ==================== LADDERS PREDEFINIS ====================

def create_conservative_ladder() -> TPLadder:
    """Ladder conservateur - prendre profits rapidement"""
    return TPLadder(
        name="Conservative",
        steps=[
            LadderStep(percent_to_sell=30, trigger_profit_pct=2.0),
            LadderStep(percent_to_sell=30, trigger_profit_pct=4.0),
            LadderStep(percent_to_sell=25, trigger_profit_pct=6.0),
            LadderStep(percent_to_sell=15, trigger_profit_pct=8.0, is_trailing=True, trailing_distance=1.5),
        ]
    )


def create_balanced_ladder() -> TPLadder:
    """Ladder equilibre - standard"""
    return TPLadder(
        name="Balanced",
        steps=[
            LadderStep(percent_to_sell=25, trigger_profit_pct=3.0),
            LadderStep(percent_to_sell=25, trigger_profit_pct=6.0),
            LadderStep(percent_to_sell=25, trigger_profit_pct=10.0),
            LadderStep(percent_to_sell=25, trigger_profit_pct=15.0, is_trailing=True, trailing_distance=2.0),
        ]
    )


def create_aggressive_ladder() -> TPLadder:
    """Ladder agressif - laisser courir"""
    return TPLadder(
        name="Aggressive",
        steps=[
            LadderStep(percent_to_sell=20, trigger_profit_pct=5.0),
            LadderStep(percent_to_sell=20, trigger_profit_pct=10.0),
            LadderStep(percent_to_sell=30, trigger_profit_pct=20.0),
            LadderStep(percent_to_sell=30, trigger_profit_pct=30.0, is_trailing=True, trailing_distance=3.0),
        ]
    )


def create_moonbag_ladder() -> TPLadder:
    """Ladder moonbag - garder une partie pour le moon"""
    return TPLadder(
        name="Moonbag",
        steps=[
            LadderStep(percent_to_sell=25, trigger_profit_pct=3.0),
            LadderStep(percent_to_sell=25, trigger_profit_pct=10.0),
            LadderStep(percent_to_sell=30, trigger_profit_pct=25.0),
            LadderStep(percent_to_sell=10, trigger_profit_pct=50.0),
            # 10% reste en "moonbag" - jamais vendu automatiquement
        ]
    )


def create_degen_ladder() -> TPLadder:
    """Ladder degen - pour le scalping rapide"""
    return TPLadder(
        name="Degen",
        steps=[
            LadderStep(percent_to_sell=50, trigger_profit_pct=1.5),
            LadderStep(percent_to_sell=30, trigger_profit_pct=3.0),
            LadderStep(percent_to_sell=20, trigger_profit_pct=5.0, is_trailing=True, trailing_distance=1.0),
        ]
    )


def create_custom_ladder(steps: List[Tuple[float, float]]) -> TPLadder:
    """
    Cree un ladder personnalise

    Args:
        steps: Liste de tuples (percent_to_sell, trigger_profit_pct)
               ex: [(25, 2), (25, 5), (25, 10), (25, 20)]
    """
    ladder_steps = []
    for i, (pct, trigger) in enumerate(steps):
        is_last = i == len(steps) - 1
        ladder_steps.append(LadderStep(
            percent_to_sell=pct,
            trigger_profit_pct=trigger,
            is_trailing=is_last,
            trailing_distance=trigger * 0.2  # 20% du trigger comme trailing
        ))

    return TPLadder(name="Custom", steps=ladder_steps)


# ==================== LADDER PRESETS ====================

LADDER_PRESETS = {
    LadderType.CONSERVATIVE: create_conservative_ladder,
    LadderType.BALANCED: create_balanced_ladder,
    LadderType.AGGRESSIVE: create_aggressive_ladder,
    LadderType.MOONBAG: create_moonbag_ladder,
}


def get_ladder(ladder_type: LadderType) -> TPLadder:
    """Retourne un ladder selon le type"""
    if ladder_type in LADDER_PRESETS:
        return LADDER_PRESETS[ladder_type]()
    return create_balanced_ladder()


# ==================== LADDER MANAGER ====================

class LadderManager:
    """Gestionnaire de TP Ladders pour les positions"""

    def __init__(self):
        self.ladders: Dict[str, TPLadder] = {}  # symbol -> ladder
        self.trailing_highs: Dict[str, float] = {}  # symbol -> highest price seen

    def create_ladder_for_position(self, symbol: str,
                                   ladder_type: LadderType = LadderType.BALANCED) -> TPLadder:
        """Cree un ladder pour une position"""
        ladder = get_ladder(ladder_type)
        self.ladders[symbol] = ladder
        self.trailing_highs[symbol] = 0
        return ladder

    def set_custom_ladder(self, symbol: str, steps: List[Tuple[float, float]]):
        """Definit un ladder personnalise"""
        ladder = create_custom_ladder(steps)
        self.ladders[symbol] = ladder
        self.trailing_highs[symbol] = 0

    def check_ladder(self, symbol: str, entry_price: float,
                     current_price: float) -> List[LadderStep]:
        """
        Verifie si des steps du ladder doivent etre executes

        Returns:
            Liste des steps a executer
        """
        if symbol not in self.ladders:
            return []

        ladder = self.ladders[symbol]
        profit_pct = (current_price - entry_price) / entry_price * 100

        # Update highest profit
        ladder.highest_profit_pct = max(ladder.highest_profit_pct, profit_pct)

        # Update trailing high
        if symbol not in self.trailing_highs:
            self.trailing_highs[symbol] = current_price
        else:
            self.trailing_highs[symbol] = max(self.trailing_highs[symbol], current_price)

        steps_to_execute = []

        for step in ladder.steps:
            if step.executed:
                continue

            should_execute = False

            if step.is_trailing:
                # Check trailing stop
                trailing_high = self.trailing_highs[symbol]
                trailing_trigger = trailing_high * (1 - step.trailing_distance / 100)

                # Trailing s'active seulement si on a atteint le profit minimum
                if profit_pct >= step.trigger_profit_pct and current_price <= trailing_trigger:
                    should_execute = True
            else:
                # Check fixed TP
                if profit_pct >= step.trigger_profit_pct:
                    should_execute = True

            if should_execute:
                steps_to_execute.append(step)

        return steps_to_execute

    def execute_step(self, symbol: str, step: LadderStep, price: float, pnl: float):
        """Marque un step comme execute"""
        step.executed = True
        step.executed_at = datetime.now()
        step.executed_price = price
        step.pnl = pnl

        if symbol in self.ladders:
            ladder = self.ladders[symbol]
            ladder.total_sold_pct += step.percent_to_sell
            ladder.remaining_pct = 100 - ladder.total_sold_pct

    def get_ladder_status(self, symbol: str) -> Dict:
        """Retourne le statut du ladder"""
        if symbol not in self.ladders:
            return {"error": "No ladder for symbol"}

        ladder = self.ladders[symbol]
        return {
            "name": ladder.name,
            "total_sold_pct": ladder.total_sold_pct,
            "remaining_pct": ladder.remaining_pct,
            "highest_profit_pct": ladder.highest_profit_pct,
            "is_complete": ladder.is_complete(),
            "steps": [
                {
                    "sell_pct": s.percent_to_sell,
                    "trigger": s.trigger_profit_pct,
                    "is_trailing": s.is_trailing,
                    "executed": s.executed,
                    "pnl": s.pnl
                }
                for s in ladder.steps
            ]
        }

    def remove_ladder(self, symbol: str):
        """Supprime le ladder d'une position fermee"""
        if symbol in self.ladders:
            del self.ladders[symbol]
        if symbol in self.trailing_highs:
            del self.trailing_highs[symbol]

    def get_remaining_quantity(self, symbol: str, original_quantity: float) -> float:
        """Retourne la quantite restante apres les ventes partielles"""
        if symbol not in self.ladders:
            return original_quantity

        ladder = self.ladders[symbol]
        return original_quantity * (ladder.remaining_pct / 100)

    def get_quantity_to_sell(self, symbol: str, original_quantity: float,
                             step: LadderStep) -> float:
        """Retourne la quantite a vendre pour un step"""
        return original_quantity * (step.percent_to_sell / 100)


# Instance globale
ladder_manager = LadderManager()


# ==================== EXEMPLES D'UTILISATION ====================

def example_usage():
    """Exemple d'utilisation du TP Ladder"""

    # 1. Creer un ladder pour une position
    manager = LadderManager()
    manager.create_ladder_for_position("BTC", LadderType.BALANCED)

    # 2. Simuler des mises a jour de prix
    entry_price = 100.0
    original_qty = 1.0

    prices = [100, 102, 103, 105, 108, 110, 115, 120, 118, 115]

    for current_price in prices:
        steps = manager.check_ladder("BTC", entry_price, current_price)

        for step in steps:
            qty_to_sell = manager.get_quantity_to_sell("BTC", original_qty, step)
            pnl = (current_price - entry_price) * qty_to_sell

            print(f"Price: ${current_price} | Selling {step.percent_to_sell}% | "
                  f"Qty: {qty_to_sell:.4f} | PnL: ${pnl:.2f}")

            manager.execute_step("BTC", step, current_price, pnl)

    # 3. Afficher le statut final
    status = manager.get_ladder_status("BTC")
    print(f"\nFinal status: {json.dumps(status, indent=2, default=str)}")


if __name__ == "__main__":
    example_usage()
