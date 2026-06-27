# marketedge/src/safety.py
"""Live-trading safety gate.

Market Edge defaults to dry-run, no-account, local-first operation. Placing real
orders against a funded exchange account must never happen by accident, so live
mode fails closed: every gate below has to be satisfied at once, and any one of
them missing blocks live trading with a specific, actionable reason.

The gate is a pure function so it can be exhaustively unit tested without a CLI,
network, or environment. The CLI is the only caller that reads the process
environment and translates a blocked decision into a non-zero exit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Operator must explicitly opt in to live trading via the environment.
ALLOW_LIVE_ENV = "MARKETEDGE_ALLOW_LIVE"
# Fast stop path: when engaged, live trading is blocked regardless of opt-in.
KILL_SWITCH_ENV = "MARKETEDGE_KILL_SWITCH"

_TRUTHY = {"1", "true", "yes", "on"}


def is_truthy(value: Optional[str]) -> bool:
    """Return True for the small set of affirmative environment-flag spellings."""
    return value is not None and value.strip().lower() in _TRUTHY


@dataclass(frozen=True)
class LiveTradingDecision:
    """Outcome of evaluating whether live trading may proceed."""

    allowed: bool
    reason: str


def evaluate_live_trading_gate(
    *,
    live: bool,
    api_key: str,
    api_secret: str,
    confirmed: bool,
    allow_live_env: Optional[str],
    kill_switch_env: Optional[str] = None,
) -> LiveTradingDecision:
    """Decide whether live trading may run. Fails closed for live mode.

    Dry-run is always allowed. Live mode requires, all at once:

    * the global kill switch disengaged,
    * explicit live enablement via ``MARKETEDGE_ALLOW_LIVE``,
    * both Kalshi API credentials present, and
    * an explicit operator confirmation (``--confirm-live``).

    The checks are ordered so the returned reason names the *first* unmet gate,
    giving the operator a single clear next step.
    """
    if not live:
        return LiveTradingDecision(True, "dry-run mode: no live orders are placed")

    if is_truthy(kill_switch_env):
        return LiveTradingDecision(
            False,
            f"global kill switch engaged ({KILL_SWITCH_ENV}); unset it to allow live trading",
        )
    if not is_truthy(allow_live_env):
        return LiveTradingDecision(
            False,
            f"live trading is not enabled; set {ALLOW_LIVE_ENV}=true to opt in",
        )
    if not api_key:
        return LiveTradingDecision(False, "KALSHI_API_KEY is required for live trading")
    if not api_secret:
        return LiveTradingDecision(
            False, "KALSHI_API_SECRET is required for live trading"
        )
    if not confirmed:
        return LiveTradingDecision(
            False,
            "operator confirmation required; re-run with --confirm-live to place real orders",
        )
    return LiveTradingDecision(True, "live trading enabled: all safety gates satisfied")
