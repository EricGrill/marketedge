"""Pre-order risk policy and audit-friendly decision objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, cast

from src.config import trading_config
from src.formulas import QuantEngine
from src.state import StateManager


@dataclass(frozen=True)
class OrderIntent:
    """Proposed order before it is allowed to reach an exchange client."""

    ticker: str
    side: str
    action: str
    quantity: int
    limit_price: float
    strategy_id: str
    correlation_group: str = ""
    region: str = "unknown"
    event_type: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def notional(self) -> float:
        return self.quantity * self.limit_price / 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "side": self.side,
            "action": self.action,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "notional": self.notional,
            "strategy_id": self.strategy_id,
            "correlation_group": self.correlation_group,
            "region": self.region,
            "event_type": self.event_type,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RiskPolicyConfig:
    """Configurable limits enforced before order placement."""

    max_position_pct: float = trading_config.max_position_pct
    max_correlated_pct: float = trading_config.max_correlated_pct
    max_total_notional_pct: float = 0.60
    max_daily_loss_pct: float = 0.05
    kill_switch: bool = False


@dataclass(frozen=True)
class RiskDecision:
    """Result of a pre-order policy evaluation."""

    allowed: bool
    reason_codes: List[str]
    intent: OrderIntent
    bankroll: float
    current_exposure: float
    projected_exposure: float
    correlated_exposure: float
    daily_loss: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason_codes": self.reason_codes,
            "intent": self.intent.to_dict(),
            "bankroll": self.bankroll,
            "current_exposure": self.current_exposure,
            "projected_exposure": self.projected_exposure,
            "correlated_exposure": self.correlated_exposure,
            "daily_loss": self.daily_loss,
        }


class PreOrderRiskPolicy:
    """Evaluate every order intent against local risk controls."""

    def __init__(
        self,
        config: RiskPolicyConfig | None = None,
        quant_engine: QuantEngine | None = None,
    ):
        self.config = config or RiskPolicyConfig()
        self.quant = quant_engine or QuantEngine()

    async def evaluate(
        self,
        state: StateManager,
        intent: OrderIntent,
    ) -> RiskDecision:
        portfolio = await state.get_portfolio_state()
        open_positions = await state.get_open_positions()
        # PortfolioState is a SQLAlchemy model; attribute reads type as Column[Any].
        # Cast the numeric fields to their real runtime type (float).
        bankroll = (
            cast(float, portfolio.bankroll)
            if portfolio
            else trading_config.initial_bankroll
        )
        current_exposure = cast(float, portfolio.total_exposure) if portfolio else 0.0
        projected_exposure = current_exposure + intent.notional
        daily_loss = abs(min(cast(float, portfolio.mtd_pnl) if portfolio else 0.0, 0.0))
        correlated_exposure = self._correlated_exposure(open_positions, intent)

        reasons: List[str] = []
        if self.config.kill_switch:
            reasons.append("KILL_SWITCH")
        if bankroll <= 0:
            reasons.append("NO_BANKROLL")
        elif intent.notional > bankroll * self.config.max_position_pct:
            reasons.append("MAX_POSITION_SIZE")
        if bankroll > 0 and projected_exposure > (
            bankroll * self.config.max_total_notional_pct
        ):
            reasons.append("MAX_TOTAL_NOTIONAL")
        if bankroll > 0 and daily_loss > bankroll * self.config.max_daily_loss_pct:
            reasons.append("MAX_DAILY_LOSS")
        if correlated_exposure > self.config.max_correlated_pct:
            reasons.append("MAX_CORRELATED_EXPOSURE")
        if intent.quantity <= 0:
            reasons.append("INVALID_QUANTITY")
        if not 0 <= intent.limit_price <= 100:
            reasons.append("INVALID_PRICE")

        if not reasons:
            reasons.append("APPROVED")

        return RiskDecision(
            allowed=reasons == ["APPROVED"],
            reason_codes=reasons,
            intent=intent,
            bankroll=bankroll,
            current_exposure=current_exposure,
            projected_exposure=projected_exposure,
            correlated_exposure=correlated_exposure,
            daily_loss=daily_loss,
        )

    def _correlated_exposure(
        self, positions: Iterable[Any], intent: OrderIntent
    ) -> float:
        position_payloads = []
        for position in positions:
            exposure = _position_exposure(position)
            position_payloads.append(
                {
                    "ticker": position.ticker,
                    "size": exposure,
                    "region": position.location or "unknown",
                    "event_type": position.weather_event_type or "unknown",
                }
            )
        if not position_payloads:
            return 0.0
        return self.quant.correlation_exposure(
            position_payloads,
            {
                "ticker": intent.ticker,
                "size": intent.notional,
                "region": intent.region,
                "event_type": intent.event_type,
            },
        )


def _position_exposure(position: Any) -> float:
    entry_price = float(position.entry_price or 0.0)
    quantity = int(position.quantity or 0)
    if entry_price <= 1.0:
        return entry_price * quantity
    return entry_price * quantity / 100.0
