from datetime import datetime, timedelta

import pytest

from src.calibration import (
    CalibrationScorer,
    ForecastInput,
    export_calibration_summary,
    load_forecasts_csv,
    load_forecasts_jsonl,
    score_persisted_forecasts,
)
from src.settlements import SettlementOutcome, SettlementResolver
from src.state import StateManager


def _settlements() -> SettlementResolver:
    return SettlementResolver(
        [
            SettlementOutcome(
                ticker="YES-1",
                settled_at=datetime(2026, 6, 18, 20, 0),
                winning_side="yes",
                yes_settlement_price=100,
            ),
            SettlementOutcome(
                ticker="NO-1",
                settled_at=datetime(2026, 6, 18, 20, 0),
                winning_side="no",
                yes_settlement_price=0,
            ),
        ]
    )


def test_calibration_scores_perfect_forecasts():
    start = datetime(2026, 6, 18, 12, 0)
    forecasts = [
        ForecastInput(timestamp=start, ticker="YES-1", model_probability=1.0),
        ForecastInput(
            timestamp=start + timedelta(minutes=5),
            ticker="NO-1",
            model_probability=0.0,
        ),
    ]

    summary = CalibrationScorer().score(forecasts, _settlements())

    assert summary.total_forecasts == 2
    assert summary.brier_score == 0
    assert summary.log_loss == pytest.approx(0, abs=1e-12)
    assert summary.observed_rate == 0.5
    assert summary.to_dict()["buckets"][0]["observed_rate"] == 0


def test_calibration_scores_poor_forecasts():
    start = datetime(2026, 6, 18, 12, 0)
    forecasts = [
        ForecastInput(timestamp=start, ticker="YES-1", model_probability=0.0),
        ForecastInput(
            timestamp=start + timedelta(minutes=5),
            ticker="NO-1",
            model_probability=1.0,
        ),
    ]

    summary = CalibrationScorer().score(forecasts, _settlements())

    assert summary.brier_score == 1
    assert summary.log_loss > 10


def test_calibration_returns_bucketed_observed_vs_predicted_rates():
    start = datetime(2026, 6, 18, 12, 0)
    forecasts = [
        ForecastInput(
            timestamp=start,
            ticker="YES-1",
            model_probability=0.62,
            strategy="wx-v1",
            market_category="weather",
            event_type="temperature",
        ),
        ForecastInput(
            timestamp=start + timedelta(minutes=5),
            ticker="NO-1",
            model_probability=0.64,
            strategy="wx-v1",
            market_category="weather",
            event_type="temperature",
        ),
    ]

    summary = CalibrationScorer(bucket_size=0.1).score(forecasts, _settlements())

    assert summary.window_start == start
    assert summary.window_end == start + timedelta(minutes=5)
    assert len(summary.buckets) == 1
    assert summary.buckets[0].lower == pytest.approx(0.6)
    assert summary.buckets[0].upper == pytest.approx(0.7)
    assert summary.buckets[0].average_probability == pytest.approx(0.63)
    assert summary.buckets[0].observed_rate == 0.5
    assert summary.groups[0].strategy == "wx-v1"
    assert summary.groups[0].market_category == "weather"
    assert summary.groups[0].event_type == "temperature"
    assert summary.to_dict()["groups"][0]["total_forecasts"] == 2


def test_load_forecasts_csv_parses_records_and_metadata(tmp_path):
    path = tmp_path / "forecasts.csv"
    path.write_text(
        "\n".join(
            [
                "timestamp,ticker,model_probability,strategy,market_category,event_type,run_id",
                "2026-06-18T12:00:00,YES-1,0.62,wx-v1,weather,temperature,run-1",
            ]
        )
    )

    forecasts = load_forecasts_csv(path)

    assert forecasts[0].ticker == "YES-1"
    assert forecasts[0].strategy == "wx-v1"
    assert forecasts[0].metadata == {"run_id": "run-1"}


def test_load_forecasts_jsonl_parses_records(tmp_path):
    path = tmp_path / "forecasts.jsonl"
    path.write_text(
        '{"timestamp":"2026-06-18T12:00:00","ticker":"YES-1",'
        '"model_probability":0.62,"strategy":"wx-v1"}\n'
    )

    forecasts = load_forecasts_jsonl(path)

    assert forecasts[0].ticker == "YES-1"
    assert forecasts[0].model_probability == 0.62


@pytest.mark.asyncio
async def test_persisted_weather_forecast_scores_and_exports(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    await state.add_weather_forecast(
        {
            "location": "NYC",
            "event_type": "temperature",
            "forecast_cycle": datetime(2026, 6, 18, 12, 0),
            "ecmwf_prob": 0.7,
            "gefs_prob": 0.7,
            "analog_prob": 0.7,
            "microclimate_prob": 0.7,
            "nws_delta": 0.7,
            "blended_probability": 0.7,
            "confidence": 0.8,
            "market_ticker": "YES-1",
            "market_price": 40,
            "strategy": "weather",
            "model_version": "weather-heuristic-v1",
            "market_category": "weather",
            "source_metadata": {"sources": ["fixture"]},
            "feature_metadata": {"threshold": 88.5},
        }
    )

    summary = await score_persisted_forecasts(state, _settlements())
    output = export_calibration_summary(summary, tmp_path / "calibration.json")

    assert summary.total_forecasts == 1
    assert summary.groups[0].strategy == "weather"
    assert output.exists()
