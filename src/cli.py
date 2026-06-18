# kalshi_weather_quant/src/cli.py
"""CLI entry point for Kalshi Weather Quant Trading."""

import asyncio
import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.config import kalshi_config, trading_config, weather_config
from src.state import StateManager
from src.formulas import QuantEngine
from src.backtesting import BacktestEngine, load_trades_csv
from src.experiments import ExperimentRegistry, parse_key_value_pairs
from src.api.client import KalshiRestClient
from src.strategies.weather import WeatherTradingStrategy
from src.tui.app import KalshiQuantApp

console = Console()


@click.group()
@click.option("--env", default=".env", help="Path to .env file")
@click.pass_context
def cli(ctx, env):
    """Kalshi Weather Quant Trading CLI"""
    if os.path.exists(env):
        from dotenv import load_dotenv

        load_dotenv(env)
    ctx.ensure_object(dict)
    ctx.obj["quant"] = QuantEngine()
    state_commands = {"dashboard", "analyze", "trade", "positions", "portfolio"}
    if ctx.invoked_subcommand in state_commands:
        ctx.obj["state"] = StateManager()


@cli.command()
@click.pass_context
def dashboard(ctx):
    """Launch the TUI dashboard."""
    state = ctx.obj["state"]
    app = KalshiQuantApp(state_manager=state)
    app.run()


@cli.command()
@click.option("--ticker", required=True, help="Market ticker to analyze")
@click.option(
    "--model-prob", type=float, required=True, help="Your model probability (0-1)"
)
@click.option("--side", type=click.Choice(["yes", "no"]), default="yes")
@click.pass_context
def analyze(ctx, ticker, model_prob, side):
    """Analyze a specific market opportunity."""
    state = ctx.obj["state"]
    quant = ctx.obj["quant"]

    market_bid = 25.0
    market_ask = 30.0

    from datetime import datetime, timedelta

    resolution_date = datetime.utcnow() + timedelta(days=7)

    portfolio = asyncio.run(state.get_portfolio_state())
    bankroll = portfolio.bankroll if portfolio else trading_config.initial_bankroll

    screen = quant.screen_opportunity(
        model_prob=model_prob,
        market_bid=market_bid,
        market_ask=market_ask,
        resolution_date=resolution_date,
        bankroll=bankroll,
        ensemble_spread=0.1,
        side=side,
    )

    table = Table(title=f"Analysis: {ticker} ({side.upper()})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    edge = screen["edge"]
    table.add_row("Model Probability", f"{edge.model_probability:.2%}")
    table.add_row("Market Probability", f"{edge.market_probability:.2%}")
    table.add_row("Raw Edge", f"{edge.raw_edge:.2%}")
    table.add_row("Fee-Adjusted Edge", f"{edge.fee_adjusted_edge:.2%}")
    table.add_row("Expected Value", f"${edge.expected_value:.4f}")
    table.add_row("Tradeable", "YES" if edge.is_tradeable else "NO")

    kelly = screen["kelly"]
    table.add_row("Full Kelly", f"{kelly.full_kelly_fraction:.2%}")
    table.add_row("Fractional Kelly", f"{kelly.fractional_kelly_fraction:.2%}")
    table.add_row("Recommended Bet", f"${kelly.recommended_bet_dollars:,.2f}")

    iy = screen["iy"]
    table.add_row("Annualized Yield", f"{iy.annualized_yield:.0%}")
    table.add_row("Days to Resolution", str(iy.days_to_resolution))

    table.add_row("Risk of Ruin", f"{screen['ror']:.4%}")
    table.add_row("PASS SCREEN", "YES" if screen["passes_screen"] else "NO")

    console.print(table)

    if screen["passes_screen"]:
        console.print(
            Panel(
                "[bold green]RECOMMENDATION: ENTER[/bold green]", border_style="green"
            )
        )
    else:
        console.print(
            Panel("[bold red]RECOMMENDATION: PASS[/bold red]", border_style="red")
        )


@cli.command()
@click.option("--live/--dry", default=False, help="Live trading or dry run")
@click.option("--interval", default=300, help="Scan interval in seconds")
@click.pass_context
def trade(ctx, live, interval):
    """Run the weather trading strategy."""
    state = ctx.obj["state"]

    if live and not kalshi_config.api_key:
        console.print("[red]Error: KALSHI_API_KEY required for live trading[/red]")
        sys.exit(1)

    client = KalshiRestClient()
    strategy = WeatherTradingStrategy(state, client)

    mode = "LIVE" if live else "DRY RUN"
    console.print(
        Panel(
            f"[bold]Starting Weather Strategy - {mode}[/bold]\nInterval: {interval}s",
            border_style="yellow" if live else "blue",
        )
    )

    try:
        asyncio.run(strategy.run_continuous(interval))
    except KeyboardInterrupt:
        console.print("[yellow]Shutting down...[/yellow]")
        asyncio.run(strategy.stop())


@cli.command()
@click.pass_context
def positions(ctx):
    """List all open positions."""
    state = ctx.obj["state"]
    positions = asyncio.run(state.get_open_positions())

    if not positions:
        console.print("[yellow]No open positions[/yellow]")
        return

    table = Table(title="Open Positions")
    table.add_column("ID", style="dim")
    table.add_column("Ticker", style="cyan")
    table.add_column("Side")
    table.add_column("Entry")
    table.add_column("Qty")
    table.add_column("Edge")
    table.add_column("Location")

    for pos in positions:
        table.add_row(
            str(pos.id),
            pos.ticker,
            pos.side.upper(),
            f"{pos.entry_price:.2f}",
            str(pos.quantity),
            f"{pos.edge_at_entry:.2%}",
            pos.location or "N/A",
        )

    console.print(table)


@cli.command()
@click.pass_context
def portfolio(ctx):
    """Show portfolio summary."""
    state = ctx.obj["state"]
    portfolio = asyncio.run(state.get_portfolio_state())

    if not portfolio:
        console.print("[red]No portfolio data[/red]")
        return

    table = Table(title="Portfolio Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Bankroll", f"${portfolio.bankroll:,.2f}")
    table.add_row("Available Cash", f"${portfolio.available_cash:,.2f}")
    table.add_row("Total Exposure", f"${portfolio.total_exposure:,.2f}")
    table.add_row("Open Positions", str(portfolio.open_positions_count))
    table.add_row("MTD P&L", f"${portfolio.mtd_pnl:,.2f}")
    table.add_row("YTD P&L", f"${portfolio.ytd_pnl:,.2f}")
    table.add_row("Max Drawdown", f"{portfolio.max_drawdown:.2%}")

    console.print(table)


def _format_ratio(value: float) -> str:
    if value == float("inf"):
        return "inf"
    return f"{value:.2f}"


@cli.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--bankroll",
    type=float,
    default=trading_config.initial_bankroll,
    show_default=True,
    help="Initial bankroll for replay metrics.",
)
@click.option(
    "--json-out",
    type=click.Path(dir_okay=False, writable=True),
    help="Write a dashboard-ready JSON summary to this path.",
)
def backtest(path, bankroll, json_out):
    """Run an offline backtest from a CSV trade ledger."""
    trades = load_trades_csv(path)
    summary = BacktestEngine().run(trades, initial_bankroll=bankroll)

    table = Table(title=f"Backtest: {path}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Trades", str(summary.total_trades))
    table.add_row("Win Rate", f"{summary.win_rate:.2%}")
    table.add_row("Net P&L", f"${summary.net_pnl:,.2f}")
    table.add_row("Return", f"{summary.return_pct:.2%}")
    table.add_row("Max Drawdown", f"{summary.max_drawdown:.2%}")
    table.add_row("Profit Factor", _format_ratio(summary.profit_factor))
    table.add_row("Average Edge", f"{summary.average_edge:.2%}")
    table.add_row("Average Confidence", f"{summary.average_confidence:.2%}")
    table.add_row("Sharpe-like", f"{summary.sharpe_like:.2f}")
    table.add_row("Fees", f"${summary.total_fees:,.2f}")
    table.add_row("Ending Bankroll", f"${summary.ending_bankroll:,.2f}")

    console.print(table)

    if json_out:
        output_path = Path(json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(summary.to_dict(), handle, indent=2, allow_nan=False)
            handle.write("\n")
        console.print(f"[green]Wrote dashboard summary to {output_path}[/green]")


@cli.group()
def experiments():
    """Manage offline experiment registry records."""


@experiments.command("create")
@click.option("--registry", default="data/experiments.jsonl", show_default=True)
@click.option("--strategy", required=True, help="Strategy name for the run.")
@click.option("--param", multiple=True, help="Run parameter formatted as key=value.")
@click.option("--data-ref", multiple=True, help="Input data or snapshot reference.")
@click.option("--artifact", multiple=True, help="Result artifact path.")
@click.option("--git-commit", default=None, help="Code commit reference.")
@click.option("--model-version", default="", help="Model version or identifier.")
@click.option("--run-id", default=None, help="Stable run id. Generated if omitted.")
@click.option("--notes", default="", help="Short run note.")
def experiment_create(
    registry,
    strategy,
    param,
    data_ref,
    artifact,
    git_commit,
    model_version,
    run_id,
    notes,
):
    """Create an experiment record."""
    record = ExperimentRegistry(registry).create(
        strategy_name=strategy,
        parameters=parse_key_value_pairs(param),
        data_references=data_ref,
        artifact_paths=artifact,
        git_commit=git_commit,
        model_version=model_version,
        run_id=run_id,
        notes=notes,
    )
    console.print(f"[green]Created experiment {record.run_id}[/green]")


@experiments.command("list")
@click.option("--registry", default="data/experiments.jsonl", show_default=True)
def experiment_list(registry):
    """List recorded experiments."""
    records = ExperimentRegistry(registry).list()
    table = Table(title=f"Experiments: {registry}")
    table.add_column("Run ID", style="cyan")
    table.add_column("Strategy")
    table.add_column("Status")
    table.add_column("Artifacts")
    table.add_column("Git")

    for record in records:
        table.add_row(
            record.run_id,
            record.strategy_name,
            record.status,
            str(len(record.artifact_paths)),
            record.git_commit[:12],
        )

    console.print(table)


@experiments.command("show")
@click.argument("run_id")
@click.option("--registry", default="data/experiments.jsonl", show_default=True)
def experiment_show(run_id, registry):
    """Show one experiment record as JSON."""
    record = ExperimentRegistry(registry).get(run_id)
    console.print_json(data=record.to_dict())


@experiments.command("add-artifact")
@click.argument("run_id")
@click.argument("artifact_path")
@click.option("--registry", default="data/experiments.jsonl", show_default=True)
def experiment_add_artifact(run_id, artifact_path, registry):
    """Append an artifact link to an experiment record."""
    record = ExperimentRegistry(registry).add_artifact(run_id, artifact_path)
    console.print(f"[green]Linked artifact to {record.run_id}[/green]")


@cli.command()
@click.option("--lat", type=float, required=True)
@click.option("--lon", type=float, required=True)
@click.option(
    "--event-type", type=click.Choice(["rain", "temp", "wind", "snow"]), required=True
)
@click.option("--threshold", type=float, default=0.0)
def weather(lat, lon, event_type, threshold):
    """Fetch and display weather forecast data."""
    from src.weather.data import WeatherModelEngine

    engine = WeatherModelEngine()

    async def fetch():
        forecast = await engine.fetch_all_sources(
            location=f"{lat},{lon}",
            lat=lat,
            lon=lon,
            event_type=event_type,
            threshold=threshold,
        )

        table = Table(title=f"Weather Forecast: {lat},{lon}")
        table.add_column("Model", style="cyan")
        table.add_column("Probability", style="green")
        table.add_column("Weight", style="yellow")

        weights = {
            "ECMWF": weather_config.ecmwf_weight,
            "GEFS": weather_config.gefs_weight,
            "Analog": weather_config.analog_weight,
            "Microclimate": weather_config.microclimate_weight,
            "NWS Delta": weather_config.nws_delta_weight,
        }

        table.add_row(
            "ECMWF (NWS)", f"{forecast.ecmwf_prob:.2%}", f"{weights['ECMWF']:.0%}"
        )
        table.add_row(
            "GEFS (OpenMeteo)", f"{forecast.gefs_prob:.2%}", f"{weights['GEFS']:.0%}"
        )
        table.add_row(
            "Analog", f"{forecast.analog_prob:.2%}", f"{weights['Analog']:.0%}"
        )
        table.add_row(
            "Microclimate",
            f"{forecast.microclimate_prob:.2%}",
            f"{weights['Microclimate']:.0%}",
        )
        table.add_row(
            "NWS Delta", f"{forecast.nws_delta:.2%}", f"{weights['NWS Delta']:.0%}"
        )

        quant = QuantEngine()
        blended, confidence = quant.blend_weather_probabilities(
            forecast.ecmwf_prob,
            forecast.gefs_prob,
            forecast.analog_prob,
            forecast.microclimate_prob,
            forecast.nws_delta,
            forecast.ensemble_spread,
        )

        table.add_row("[bold]BLENDED[/bold]", f"[bold]{blended:.2%}[/bold]", "")
        table.add_row("Confidence", f"{confidence:.2%}", "")
        table.add_row("Ensemble Spread", f"{forecast.ensemble_spread:.2%}", "")

        console.print(table)
        console.print(f"[dim]Sources: {', '.join(forecast.sources)}[/dim]")

        await engine.close()

    asyncio.run(fetch())


@cli.command()
def formulas():
    """Display all quant formulas used."""
    text = Text()
    text.append("KALSHI WEATHER QUANT FORMULAS\n\n", style="bold underline")

    formulas_list = [
        (
            "1. Fee-Adjusted Edge",
            "fee_adj = p_model / (1 + 0.03 * p_model)\nedge = p_model - max(p_market, fee_adj)",
        ),
        ("2. Kelly Criterion", "f* = (p*(b+1) - 1) / b\nwhere b = (1/p_market) - 1"),
        ("3. Annualized Yield (IY)", "IY = (1 / price)^(365 / days) - 1"),
        ("4. Liquidity Spread (LAS)", "LAS = (Ask - Bid) / Mid"),
        ("5. Bayesian Update", "p_posterior = p_prior * likelihood / evidence"),
        (
            "6. Weather Blend",
            "p_blend = 0.30*ECMWF + 0.25*GEFS + 0.20*Analog + 0.15*Micro + 0.10*NWS_delta",
        ),
        ("7. Risk of Ruin", "RoR = ((1-edge)/(1+edge))^(bankroll/bet_size)"),
    ]

    for name, formula in formulas_list:
        text.append(f"\n{name}\n", style="bold cyan")
        text.append(f"{formula}\n", style="dim")

    console.print(Panel(text, title="Quant Formula Reference"))


if __name__ == "__main__":
    cli()
