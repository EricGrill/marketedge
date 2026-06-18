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
