"""Local experiment registry for reproducible strategy research."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List
from uuid import uuid4

from src.utils import parse_timestamp, utcnow

COMPARISON_METRICS = (
    "total_trades",
    "win_rate",
    "net_pnl",
    "return_pct",
    "max_drawdown",
    "profit_factor",
    "average_edge",
    "average_confidence",
    "sharpe_like",
)


class ExperimentRegistryError(ValueError):
    """Raised when an experiment record cannot be loaded or found."""


@dataclass(frozen=True)
class ExperimentRecord:
    """Reproducibility metadata for one strategy run."""

    run_id: str
    strategy_name: str
    parameters: Dict[str, Any]
    data_references: List[str]
    artifact_paths: List[str]
    git_commit: str
    model_version: str = ""
    status: str = "created"
    started_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "strategy_name": self.strategy_name,
            "parameters": self.parameters,
            "data_references": self.data_references,
            "artifact_paths": self.artifact_paths,
            "git_commit": self.git_commit,
            "model_version": self.model_version,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ExperimentRecord":
        return cls(
            run_id=str(payload["run_id"]),
            strategy_name=str(payload["strategy_name"]),
            parameters=dict(payload.get("parameters") or {}),
            data_references=list(payload.get("data_references") or []),
            artifact_paths=list(payload.get("artifact_paths") or []),
            git_commit=str(payload.get("git_commit") or ""),
            model_version=str(payload.get("model_version") or ""),
            status=str(payload.get("status") or "created"),
            started_at=_parse_datetime(str(payload["started_at"])),
            finished_at=(
                _parse_datetime(str(payload["finished_at"]))
                if payload.get("finished_at")
                else None
            ),
            notes=str(payload.get("notes") or ""),
        )


class ExperimentRegistry:
    """Append-only JSONL experiment registry."""

    def __init__(self, path: str | Path = "data/experiments.jsonl"):
        self.path = Path(path)

    def create(
        self,
        strategy_name: str,
        parameters: Dict[str, Any] | None = None,
        data_references: Iterable[str] | None = None,
        artifact_paths: Iterable[str] | None = None,
        git_commit: str | None = None,
        model_version: str = "",
        run_id: str | None = None,
        notes: str = "",
    ) -> ExperimentRecord:
        record = ExperimentRecord(
            run_id=run_id or _default_run_id(strategy_name),
            strategy_name=strategy_name,
            parameters=parameters or {},
            data_references=list(data_references or []),
            artifact_paths=list(artifact_paths or []),
            git_commit=git_commit or detect_git_commit(),
            model_version=model_version,
            notes=notes,
        )
        self.append(record)
        return record

    def append(self, record: ExperimentRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(record.to_dict(), handle, sort_keys=True)
            handle.write("\n")

    def list(self) -> List[ExperimentRecord]:
        if not self.path.exists():
            return []

        records: List[ExperimentRecord] = []
        with self.path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(ExperimentRecord.from_dict(json.loads(line)))
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise ExperimentRegistryError(
                        f"invalid experiment record on line {line_number}"
                    ) from exc
        return records

    def get(self, run_id: str) -> ExperimentRecord:
        for record in reversed(self.list()):
            if record.run_id == run_id:
                return record
        raise ExperimentRegistryError(f"experiment not found: {run_id}")

    def add_artifact(self, run_id: str, artifact_path: str) -> ExperimentRecord:
        record = self.get(run_id)
        updated = replace(
            record,
            artifact_paths=[*record.artifact_paths, artifact_path],
            finished_at=utcnow(),
            status="artifact-linked",
        )
        self.append(updated)
        return updated

    def compare(self, run_ids: Iterable[str]) -> Dict[str, Any]:
        records = [self.get(run_id) for run_id in run_ids]
        if len(records) < 2:
            raise ExperimentRegistryError("compare requires at least two run IDs")

        runs = [_comparison_run(record) for record in records]
        baseline = runs[0]
        metric_deltas = {}
        for run in runs[1:]:
            deltas = {}
            for metric in COMPARISON_METRICS:
                before = baseline["metrics"].get(metric)
                after = run["metrics"].get(metric)
                if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                    deltas[metric] = after - before
            metric_deltas[run["run_id"]] = deltas

        parameter_keys = sorted(
            {key for record in records for key in record.parameters.keys()}
        )
        return {
            "baseline_run_id": baseline["run_id"],
            "runs": runs,
            "metric_deltas": metric_deltas,
            "parameter_keys": parameter_keys,
        }


def detect_git_commit(cwd: str | Path = ".") -> str:
    """Return the current git commit, or an empty string outside git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(cwd),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def parse_key_value_pairs(values: Iterable[str]) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ExperimentRegistryError(
                f"parameter must be formatted as key=value: {value}"
            )
        key, item = value.split("=", 1)
        parsed[key] = item
    return parsed


def _comparison_run(record: ExperimentRecord) -> Dict[str, Any]:
    metrics, warnings = _load_artifact_metrics(record.artifact_paths)
    return {
        "run_id": record.run_id,
        "strategy_name": record.strategy_name,
        "parameters": record.parameters,
        "data_references": record.data_references,
        "artifact_paths": record.artifact_paths,
        "artifact_count": len(record.artifact_paths),
        "git_commit": record.git_commit,
        "model_version": record.model_version,
        "status": record.status,
        "started_at": record.started_at.isoformat(),
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
        "notes": record.notes,
        "metrics": metrics,
        "warnings": warnings,
    }


def _load_artifact_metrics(paths: Iterable[str]) -> tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    for artifact in paths:
        path = Path(artifact)
        if not path.exists():
            warnings.append(f"artifact not found: {artifact}")
            continue
        if path.suffix.lower() != ".json":
            warnings.append(f"artifact is not JSON: {artifact}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            warnings.append(f"artifact is invalid JSON: {artifact}")
            continue
        metrics = {
            metric: payload.get(metric)
            for metric in COMPARISON_METRICS
            if metric in payload
        }
        if metrics:
            return metrics, warnings
        warnings.append(f"artifact has no comparison metrics: {artifact}")
    return {}, warnings


def _default_run_id(strategy_name: str) -> str:
    safe_strategy = "".join(
        char.lower() if char.isalnum() else "-" for char in strategy_name
    ).strip("-")
    return f"{safe_strategy or 'experiment'}-{uuid4().hex[:10]}"


def _parse_datetime(value: str) -> datetime:
    return parse_timestamp(value)
