import json

from click.testing import CliRunner

import src.cli as cli_module
from src.cli import cli


def test_backtest_cli_runs_without_state_database():
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open("trades.csv", "w") as handle:
            handle.write(
                "\n".join(
                    [
                        "timestamp,ticker,side,entry_price,exit_price,quantity,"
                        "model_probability,confidence,entry_fee,exit_fee",
                        "2026-06-18T14:00:00,HIGHNY-26JUN18-B88.5,yes,40,100,"
                        "10,0.62,0.8,0.3,0.2",
                    ]
                )
            )

        result = runner.invoke(cli, ["backtest", "trades.csv", "--bankroll", "1000"])

    assert result.exit_code == 0
    assert "Backtest:" in result.output
    assert "Trades" in result.output
    assert "$5.50" in result.output


def test_backtest_cli_writes_dashboard_json():
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open("trades.csv", "w") as handle:
            handle.write(
                "\n".join(
                    [
                        "timestamp,ticker,side,entry_price,exit_price,quantity,"
                        "model_probability,confidence,entry_fee,exit_fee",
                        "2026-06-18T14:00:00,HIGHNY-26JUN18-B88.5,yes,40,100,"
                        "10,0.62,0.8,0.3,0.2",
                        "2026-06-18T14:05:00,RAINMIA-26JUN18-YES,yes,64,100,"
                        "8,0.72,0.7,0.2,0.1",
                    ]
                )
            )

        result = runner.invoke(
            cli,
            [
                "backtest",
                "trades.csv",
                "--bankroll",
                "1000",
                "--json-out",
                "web/data/backtest-summary.json",
            ],
        )

        with open("web/data/backtest-summary.json", encoding="utf-8") as handle:
            payload = json.load(handle)

    assert result.exit_code == 0
    assert "Wrote dashboard summary" in result.output
    assert payload["total_trades"] == 2
    assert payload["net_pnl"] > 0
    assert payload["profit_factor"] is None
    assert len(payload["equity_curve"]) == 2


def test_experiment_cli_creates_lists_and_shows_runs():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "experiments",
                "create",
                "--registry",
                "experiments.jsonl",
                "--strategy",
                "wx-meanrev",
                "--param",
                "edge=0.04",
                "--data-ref",
                "data/snapshots/wx.jsonl",
                "--artifact",
                "web/data/backtest-summary.json",
                "--git-commit",
                "abc123",
                "--run-id",
                "run-1",
            ],
        )
        list_result = runner.invoke(
            cli, ["experiments", "list", "--registry", "experiments.jsonl"]
        )
        add_artifact_result = runner.invoke(
            cli,
            [
                "experiments",
                "add-artifact",
                "run-1",
                "web/data/calibration-summary.json",
                "--registry",
                "experiments.jsonl",
            ],
        )
        show_result = runner.invoke(
            cli,
            ["experiments", "show", "run-1", "--registry", "experiments.jsonl"],
        )
        payload = json.loads(show_result.output)

    assert result.exit_code == 0
    assert "Created experiment run-1" in result.output
    assert list_result.exit_code == 0
    assert "wx-meanrev" in list_result.output
    assert add_artifact_result.exit_code == 0
    assert "Linked artifact to run-1" in add_artifact_result.output
    assert show_result.exit_code == 0
    assert payload["artifact_paths"] == [
        "web/data/backtest-summary.json",
        "web/data/calibration-summary.json",
    ]


def test_experiment_cli_compares_runs_with_artifacts():
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open("a.json", "w", encoding="utf-8") as handle:
            json.dump({"return_pct": 0.10, "net_pnl": 100, "sharpe_like": 1.2}, handle)
        with open("b.json", "w", encoding="utf-8") as handle:
            json.dump({"return_pct": 0.15, "net_pnl": 150, "sharpe_like": 1.5}, handle)

        for run_id, artifact in [("run-a", "a.json"), ("run-b", "b.json")]:
            result = runner.invoke(
                cli,
                [
                    "experiments",
                    "create",
                    "--registry",
                    "experiments.jsonl",
                    "--strategy",
                    "wx-meanrev",
                    "--artifact",
                    artifact,
                    "--run-id",
                    run_id,
                ],
            )
            assert result.exit_code == 0

        compare_result = runner.invoke(
            cli,
            [
                "experiments",
                "compare",
                "run-a",
                "run-b",
                "--registry",
                "experiments.jsonl",
                "--json-out",
                "compare.json",
            ],
        )
        with open("compare.json", encoding="utf-8") as handle:
            payload = json.load(handle)

    assert compare_result.exit_code == 0
    assert "Experiment Compare" in compare_result.output
    assert round(payload["metric_deltas"]["run-b"]["return_pct"], 6) == 0.05


def test_doctor_cli_strict_fails_on_warnings():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "doctor",
                "--env-file",
                ".env",
                "--db-path",
                "state.db",
                "--dashboard-path",
                "missing.json",
                "--strict",
            ],
        )

    assert result.exit_code == 1
    assert "Market Edge Doctor" in result.output
    assert "WARN" in result.output


def test_opportunities_cli_writes_rankings_json():
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open("candidates.csv", "w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    [
                        "ticker,model_probability,yes_bid,yes_ask,confidence,volume",
                        "HIGHNY-TEST-B88.5,0.85,39,40,0.9,100000",
                    ]
                )
            )
        result = runner.invoke(
            cli,
            ["opportunities", "candidates.csv", "--json-out", "rankings.json"],
        )
        with open("rankings.json", encoding="utf-8") as handle:
            payload = json.load(handle)

    assert result.exit_code == 0
    assert "Opportunities" in result.output
    assert payload[0]["action"] == "BUY_YES"


def test_analyze_cli_requires_explicit_quotes_without_fetch():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["analyze", "--ticker", "TEST", "--model-prob", "0.6"],
        )

    assert result.exit_code != 0
    assert "missing YES quote inputs" in result.output


def test_analyze_cli_uses_explicit_yes_and_no_quotes():
    runner = CliRunner()
    with runner.isolated_filesystem():
        yes_result = runner.invoke(
            cli,
            [
                "analyze",
                "--ticker",
                "TEST",
                "--model-prob",
                "0.7",
                "--yes-bid",
                "39",
                "--yes-ask",
                "41",
                "--resolution-date",
                "2026-06-18T20:00:00Z",
            ],
        )
        no_result = runner.invoke(
            cli,
            [
                "analyze",
                "--ticker",
                "TEST",
                "--model-prob",
                "0.3",
                "--side",
                "no",
                "--no-bid",
                "59",
                "--no-ask",
                "61",
                "--days-to-resolution",
                "10",
            ],
        )

    assert yes_result.exit_code == 0
    assert "39.0¢ / 41.0¢" in yes_result.output
    assert no_result.exit_code == 0
    assert "59.0¢ / 61.0¢" in no_result.output


def test_collect_snapshots_cli_writes_state(monkeypatch):
    class FakeClient:
        async def get_market(self, ticker):
            return {
                "market": {
                    "ticker": ticker,
                    "title": "NYC Daily High above 88.5F",
                    "volume": 10,
                    "open_interest": 20,
                }
            }

        async def get_market_orderbook(self, ticker, depth=10):
            return {
                "orderbook": {"yes_bid": 39, "yes_ask": 41, "no_bid": 59, "no_ask": 61}
            }

    monkeypatch.setattr(cli_module, "KalshiRestClient", FakeClient)
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "collect-snapshots",
                "--db-path",
                "state.db",
                "--ticker",
                "HIGHNY-TEST-B88.5",
            ],
        )

    assert result.exit_code == 0
    assert "Collected 1/1 market snapshots" in result.output


def test_strategies_cli_lists_and_runs_weather_strategy():
    runner = CliRunner()
    with runner.isolated_filesystem():
        list_result = runner.invoke(
            cli,
            ["strategies", "list", "--config", "strategy-config.json"],
        )
        run_result = runner.invoke(
            cli,
            [
                "strategies",
                "run",
                "weather",
                "--config",
                "strategy-config.json",
                "--json-out",
                "weather-run.json",
            ],
        )
        with open("weather-run.json", encoding="utf-8") as handle:
            payload = json.load(handle)

    assert list_result.exit_code == 0
    assert "weather" in list_result.output
    assert run_result.exit_code == 0
    assert payload["strategy_id"] == "weather"
    assert payload["status"] == "completed"


def test_paper_cli_records_and_lists_positions():
    runner = CliRunner()
    with runner.isolated_filesystem():
        order_result = runner.invoke(
            cli,
            [
                "paper",
                "order",
                "--ledger",
                "paper.jsonl",
                "--ticker",
                "RAIN-NYC-TEST",
                "--side",
                "yes",
                "--action",
                "buy",
                "--quantity",
                "10",
                "--price",
                "40",
            ],
        )
        positions_result = runner.invoke(
            cli,
            ["paper", "positions", "--ledger", "paper.jsonl"],
        )

    assert order_result.exit_code == 0
    assert "Recorded paper order" in order_result.output
    assert positions_result.exit_code == 0
    assert "RAIN-NYC-TEST" in positions_result.output


def test_dashboard_data_cli_writes_payload():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "dashboard-data",
                "--db-path",
                "marketedge.db",
                "--out",
                "web/data/dashboard.json",
            ],
        )
        with open("web/data/dashboard.json", encoding="utf-8") as handle:
            payload = json.load(handle)

    assert result.exit_code == 0
    assert "Wrote dashboard data" in result.output
    assert payload["account"]["bankroll"] == 10_000


def test_db_cli_initializes_schema_and_records_audit_events():
    runner = CliRunner()
    with runner.isolated_filesystem():
        init_result = runner.invoke(
            cli,
            ["db", "init", "--db-path", "marketedge.db"],
        )
        migrations_result = runner.invoke(
            cli,
            ["db", "migrations", "--db-path", "marketedge.db"],
        )
        record_result = runner.invoke(
            cli,
            [
                "db",
                "audit-record",
                "--db-path",
                "marketedge.db",
                "--event-type",
                "decision",
                "--subject",
                "paper-trade",
                "--ticker",
                "RAIN-NYC-TEST",
                "--payload",
                "action=buy",
            ],
        )
        audit_result = runner.invoke(
            cli,
            ["db", "audit", "--db-path", "marketedge.db"],
        )

    assert init_result.exit_code == 0
    assert "Initialized Market Edge database" in init_result.output
    assert "0001_state_and_audit" in init_result.output
    assert migrations_result.exit_code == 0
    assert "Schema Migrations" in migrations_result.output
    assert record_result.exit_code == 0
    assert "Recorded audit event" in record_result.output
    assert audit_result.exit_code == 0
    assert "paper-trade" in audit_result.output
    assert "RAIN-NYC-TEST" in audit_result.output


# --- CHA-2390: strategy lookup/state errors must be clean CLI errors ---


def test_strategies_run_disabled_reports_clean_error(tmp_path):
    """A disabled strategy must produce a CLI error, not a traceback."""
    config_path = tmp_path / "strategy-config.json"
    config_path.write_text(json.dumps({"relative-value": {"enabled": False}}))

    runner = CliRunner()
    result = runner.invoke(
        cli, ["strategies", "run", "relative-value", "--config", str(config_path)]
    )

    assert result.exit_code != 0
    assert "Error: strategy disabled: relative-value" in result.output
    assert "Traceback" not in result.output


def test_strategies_run_unknown_id_reports_clean_error(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "strategies",
            "run",
            "no-such-strategy",
            "--config",
            str(tmp_path / "strategy-config.json"),
        ],
    )

    assert result.exit_code != 0
    assert "Error: strategy not found: no-such-strategy" in result.output
    assert "Traceback" not in result.output


def test_strategies_inspect_enable_disable_unknown_id_report_clean_errors(tmp_path):
    runner = CliRunner()
    config_path = str(tmp_path / "strategy-config.json")
    for command in ("inspect", "enable", "disable"):
        result = runner.invoke(
            cli, ["strategies", command, "no-such-strategy", "--config", config_path]
        )
        assert result.exit_code != 0, command
        assert "Error: strategy not found: no-such-strategy" in result.output, command
        assert "Traceback" not in result.output, command
