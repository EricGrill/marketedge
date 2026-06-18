import json

from click.testing import CliRunner

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
