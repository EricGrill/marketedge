"""First-class strategy registry, config, and run management."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Protocol
from uuid import uuid4

from src.market_adapters import normalize_market
from src.state import StateManager
from src.strategies.advanced import (
    CalibrationWeightedEnsembleStrategy,
    CatalystCalendarStrategy,
    LiquidityMicrostructureOverlay,
    RelativeValueStrategy,
    StrategyOpportunity,
)
from src.utils import utcnow


class RegisteredStrategy(Protocol):
    metadata: "StrategyMetadata"

    def default_config(self) -> Dict[str, Any]:
        raise NotImplementedError

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    async def run(self, context: "StrategyContext") -> "StrategyRunResult":
        raise NotImplementedError


@dataclass(frozen=True)
class StrategyMetadata:
    """Stable registry metadata for an executable strategy."""

    strategy_id: str
    display_name: str
    description: str
    category: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
        }


@dataclass(frozen=True)
class StrategyContext:
    """Runtime context passed to registered strategies."""

    state: StateManager
    config: Dict[str, Any]
    dry_run: bool = True


@dataclass(frozen=True)
class StrategyRunResult:
    """Result persisted after a strategy run."""

    status: str
    opportunities: List[StrategyOpportunity] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    artifact_paths: List[str] = field(default_factory=list)
    explanation: Dict[str, Any] = field(default_factory=dict)


class StrategyConfigStore:
    """Small JSON config store for enabled flags and per-strategy options."""

    def __init__(self, path: str | Path = "data/strategy-config.json"):
        self.path = Path(path)

    def load(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, config: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    def get_strategy_config(
        self, strategy_id: str, defaults: Dict[str, Any]
    ) -> Dict[str, Any]:
        config = self.load().get(strategy_id, {})
        return {**defaults, **config}

    def set_enabled(self, strategy_id: str, enabled: bool) -> Dict[str, Any]:
        config = self.load()
        item = dict(config.get(strategy_id, {}))
        item["enabled"] = enabled
        config[strategy_id] = item
        self.save(config)
        return item


class StrategyRegistry:
    """Register and inspect built-in/local strategies."""

    def __init__(self, strategies: Iterable[RegisteredStrategy] | None = None):
        self._strategies: Dict[str, RegisteredStrategy] = {}
        for strategy in strategies or builtin_strategies():
            self.register(strategy)

    def register(self, strategy: RegisteredStrategy) -> None:
        self._strategies[strategy.metadata.strategy_id] = strategy

    def get(self, strategy_id: str) -> RegisteredStrategy:
        try:
            return self._strategies[strategy_id]
        except KeyError as exc:
            raise ValueError(f"strategy not found: {strategy_id}") from exc

    def list(self) -> List[RegisteredStrategy]:
        return [self._strategies[key] for key in sorted(self._strategies)]


class StrategyManager:
    """Run registered strategies and persist run records."""

    def __init__(
        self,
        state: StateManager,
        registry: StrategyRegistry | None = None,
        config_store: StrategyConfigStore | None = None,
    ):
        self.state = state
        self.registry = registry or StrategyRegistry()
        self.config_store = config_store or StrategyConfigStore()

    async def list_status(self) -> List[Dict[str, Any]]:
        runs = await self.state.list_strategy_runs(limit=200)
        latest_by_strategy: Dict[str, Any] = {}
        for run in runs:
            latest_by_strategy.setdefault(str(run.strategy_id), run)

        statuses = []
        config = self.config_store.load()
        for strategy in self.registry.list():
            defaults = strategy.default_config()
            strategy_config = {
                **defaults,
                **config.get(strategy.metadata.strategy_id, {}),
            }
            last_run = latest_by_strategy.get(strategy.metadata.strategy_id)
            statuses.append(
                {
                    **strategy.metadata.to_dict(),
                    "enabled": bool(strategy_config.get("enabled", True)),
                    "config": strategy_config,
                    "last_run": _run_to_dict(last_run) if last_run else None,
                }
            )
        return statuses

    async def run(
        self,
        strategy_id: str,
        *,
        dry_run: bool = True,
        overrides: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        strategy = self.registry.get(strategy_id)
        config = self.config_store.get_strategy_config(
            strategy_id, strategy.default_config()
        )
        config.update(overrides or {})
        config = strategy.validate_config(config)
        if not config.get("enabled", True):
            raise ValueError(f"strategy disabled: {strategy_id}")

        run_id = f"{strategy_id}-{uuid4().hex[:10]}"
        await self.state.start_strategy_run(strategy_id, run_id, config)
        result = await strategy.run(
            StrategyContext(state=self.state, config=config, dry_run=dry_run)
        )
        await self.state.finish_strategy_run(
            run_id,
            status=result.status,
            warnings=result.warnings,
            signal_count=len(result.opportunities),
            artifact_paths=result.artifact_paths,
            explanation=result.explanation,
        )
        await self.state.record_audit_event(
            event_type="strategy_run",
            subject=strategy_id,
            payload={
                "run_id": run_id,
                "dry_run": dry_run,
                "status": result.status,
                "signal_count": len(result.opportunities),
            },
        )
        return {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "status": result.status,
            "opportunities": [item.to_dict() for item in result.opportunities],
            "warnings": result.warnings,
            "artifact_paths": result.artifact_paths,
            "explanation": result.explanation,
        }


class LatestSnapshotStrategy:
    """Base helper for strategies that read latest normalized snapshots."""

    metadata = StrategyMetadata(
        strategy_id="latest-snapshot",
        display_name="Latest Snapshot",
        description="Base strategy helper",
        category="internal",
    )

    def default_config(self) -> Dict[str, Any]:
        return {"enabled": True, "limit": 100}

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        parsed = dict(config)
        parsed["limit"] = int(parsed.get("limit", 100))
        if parsed["limit"] <= 0:
            raise ValueError("limit must be positive")
        return parsed

    async def _markets(self, context: StrategyContext):
        snapshots = await context.state.get_latest_market_snapshots(
            limit=context.config.get("limit", 100)
        )
        return [
            market
            for market in (
                normalize_market(
                    {
                        "ticker": snapshot.ticker,
                        "title": snapshot.title or snapshot.ticker,
                        "yes_bid": snapshot.yes_bid,
                        "yes_ask": snapshot.yes_ask,
                        "no_bid": snapshot.no_bid,
                        "no_ask": snapshot.no_ask,
                        "last_price": snapshot.last_price,
                        "volume": snapshot.volume_24h,
                        "open_interest": snapshot.open_interest,
                        "source": snapshot.source or "state",
                    }
                )
                for snapshot in snapshots
            )
            if market
        ]


class WeatherBuiltinStrategy(LatestSnapshotStrategy):
    metadata = StrategyMetadata(
        strategy_id="weather",
        display_name="Weather Strategy",
        description="Weather market screening using local snapshots and explanations.",
        category="weather",
    )

    async def run(self, context: StrategyContext) -> StrategyRunResult:
        markets = await self._markets(context)
        opportunities = [
            StrategyOpportunity(
                strategy_id=self.metadata.strategy_id,
                ticker=market.ticker,
                action="explain",
                edge=0.0,
                confidence=1.0,
                reason_codes=["WEATHER_MARKET_NORMALIZED"],
                metadata={"market": market.to_dict()},
            )
            for market in markets
            if market.category == "weather"
        ]
        return StrategyRunResult(
            status="completed",
            opportunities=opportunities,
            explanation={"market_count": len(markets), "dry_run": context.dry_run},
        )


class RelativeValueBuiltinStrategy(LatestSnapshotStrategy):
    metadata = StrategyMetadata(
        strategy_id="relative-value",
        display_name="Relative Value",
        description="Find threshold, outcome-set, and regional pricing inconsistencies.",
        category="cross-market",
    )

    async def run(self, context: StrategyContext) -> StrategyRunResult:
        markets = await self._markets(context)
        opportunities = RelativeValueStrategy(
            tolerance=float(context.config.get("tolerance", 0.02))
        ).evaluate(markets)
        return StrategyRunResult(
            status="completed",
            opportunities=opportunities,
            explanation={"market_count": len(markets), "dry_run": context.dry_run},
        )

    def default_config(self) -> Dict[str, Any]:
        return {**super().default_config(), "tolerance": 0.02}


class CatalystBuiltinStrategy(LatestSnapshotStrategy):
    metadata = StrategyMetadata(
        strategy_id="catalyst-calendar",
        display_name="Catalyst Calendar",
        description="Tag markets that are inside local catalyst windows.",
        category="calendar",
    )

    async def run(self, context: StrategyContext) -> StrategyRunResult:
        markets = await self._markets(context)
        strategy = CatalystCalendarStrategy()
        opportunities = strategy.evaluate(markets, as_of=utcnow())
        return StrategyRunResult(
            status="completed",
            opportunities=opportunities,
            warnings=[] if opportunities else ["no catalyst calendar records loaded"],
            explanation={"market_count": len(markets), "dry_run": context.dry_run},
        )


class EnsembleBuiltinStrategy(LatestSnapshotStrategy):
    metadata = StrategyMetadata(
        strategy_id="calibration-ensemble",
        display_name="Calibration Ensemble",
        description="Blend probability sources with calibration-weighted diagnostics.",
        category="model",
    )

    async def run(self, context: StrategyContext) -> StrategyRunResult:
        return StrategyRunResult(
            status="completed",
            warnings=["no probability sources supplied to registry dry-run"],
            explanation={
                "engine": CalibrationWeightedEnsembleStrategy.strategy_id,
                "dry_run": context.dry_run,
            },
        )


class LiquidityBuiltinStrategy(LatestSnapshotStrategy):
    metadata = StrategyMetadata(
        strategy_id="liquidity-overlay",
        display_name="Liquidity Overlay",
        description="Execution-quality guardrail for spread, depth, staleness, and slippage.",
        category="execution",
    )

    async def run(self, context: StrategyContext) -> StrategyRunResult:
        markets = await self._markets(context)
        return StrategyRunResult(
            status="completed",
            warnings=["orderbook depth required for actionable overlay decisions"],
            explanation={
                "engine": LiquidityMicrostructureOverlay.strategy_id,
                "market_count": len(markets),
                "dry_run": context.dry_run,
            },
        )


def builtin_strategies() -> List[RegisteredStrategy]:
    return [
        WeatherBuiltinStrategy(),
        RelativeValueBuiltinStrategy(),
        CatalystBuiltinStrategy(),
        EnsembleBuiltinStrategy(),
        LiquidityBuiltinStrategy(),
    ]


def _run_to_dict(run) -> Dict[str, Any]:
    return {
        "run_id": run.run_id,
        "strategy_id": run.strategy_id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "warnings": json.loads(run.warnings_json or "[]"),
        "signal_count": run.signal_count,
        "artifact_paths": json.loads(run.artifact_paths_json or "[]"),
        "explanation": json.loads(run.explanation_json or "{}"),
    }
