import json

import pytest

from src.experiments import (
    ExperimentRegistry,
    ExperimentRegistryError,
    parse_key_value_pairs,
)


def test_experiment_registry_creates_lists_and_loads_runs(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments.jsonl")

    record = registry.create(
        strategy_name="wx-meanrev",
        parameters={"edge": "0.04"},
        data_references=["data/snapshots/wx.jsonl"],
        artifact_paths=["web/data/backtest-summary.json"],
        git_commit="abc123",
        model_version="v1",
        run_id="run-1",
    )

    records = registry.list()

    assert record.run_id == "run-1"
    assert len(records) == 1
    assert registry.get("run-1").strategy_name == "wx-meanrev"
    assert registry.get("run-1").data_references == ["data/snapshots/wx.jsonl"]


def test_experiment_registry_links_artifacts_append_only(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments.jsonl")
    registry.create(
        strategy_name="wx-meanrev",
        git_commit="abc123",
        run_id="run-1",
    )

    updated = registry.add_artifact("run-1", "web/data/backtest-summary.json")

    assert updated.status == "artifact-linked"
    assert updated.finished_at is not None
    assert updated.artifact_paths == ["web/data/backtest-summary.json"]
    assert len(registry.list()) == 2
    assert registry.get("run-1").artifact_paths == ["web/data/backtest-summary.json"]


def test_experiment_registry_reports_missing_runs(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments.jsonl")

    with pytest.raises(ExperimentRegistryError, match="experiment not found"):
        registry.get("missing")


def test_parse_key_value_pairs_rejects_unstructured_values():
    assert parse_key_value_pairs(["edge=0.04", "kelly=0.25"]) == {
        "edge": "0.04",
        "kelly": "0.25",
    }
    with pytest.raises(ExperimentRegistryError, match="key=value"):
        parse_key_value_pairs(["bad"])


def test_experiment_registry_writes_jsonl_records(tmp_path):
    path = tmp_path / "experiments.jsonl"
    registry = ExperimentRegistry(path)

    registry.create(strategy_name="wx-meanrev", git_commit="abc123", run_id="run-1")

    payload = json.loads(path.read_text().strip())

    assert payload["run_id"] == "run-1"
    assert payload["strategy_name"] == "wx-meanrev"
