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
