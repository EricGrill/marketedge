# marketedge/src/cli.py
"""CLI entry point for Market Edge."""

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.config import kalshi_config, trading_config, weather_config
from src.state import SCHEMA_VERSION, StateManager
from src.formulas import QuantEngine
from src.backtesting import BacktestEngine, load_trades_csv
from src.experiments import (
    ExperimentRegistry,
    ExperimentRegistryError,
    parse_key_value_pairs,
)
from src.doctor import has_failures, has_warnings, run_health_checks
from src.dashboard import build_dashboard_payload, write_dashboard_payload
from src.data_collection import collect_market_snapshots, fetch_market_quotes
from src.calibration import (
    CalibrationScorer,
    export_calibration_summary,
    fit_persisted_weights,
    load_forecasts_csv,
    load_forecasts_jsonl,
    score_persisted_forecasts,
)
from src.opportunities import OpportunityScanner, load_candidates
from src.paper import PaperLedgerError, PaperTradingLedger
from src.settlements import load_settlements_csv, load_settlements_jsonl
from src.strategy_registry import StrategyConfigStore, StrategyManager, StrategyRegistry
from src.api.client import KalshiRestClient
from src.strategies.weather import WeatherTradingStrategy
from src.tui.app import KalshiQuantApp
from src.logging_config import configure_logging
from src.safety import (
    ALLOW_LIVE_ENV,
    KILL_SWITCH_ENV,
    evaluate_live_trading_gate,
)
from src.utils import parse_timestamp, utcnow

console = Console()


@click.group()
@click.option("--env", default=".env", help="Path to .env file")
@click.pass_context
def cli(ctx, env):
    """Market Edge research and dry-run trading CLI."""
    configure_logging()
    if os.path.exists(env):
        from dotenv import load_dotenv

        load_dotenv(env)
    ctx.ensure_object(dict)
    ctx.obj["quant"] = QuantEngine()
    state_commands = {
        "dashboard",
        "analyze",
        "trade",
        "positions",
        "portfolio",
        "dashboard-data",
        "collect-snapshots",
        "calibration-score",
        "strategies",
    }
    if ctx.invoked_subcommand in state_commands:
        ctx.obj["state"] = StateManager()


@cli.command()
@click.pass_context
def dashboard(ctx):
    """Launch the TUI dashboard."""
    state = ctx.obj["state"]
    app = KalshiQuantApp(state_manager=state)
    app.run()


@cli.group()
def db():
    """Manage local SQLite persistence and audit trail."""


@db.command("init")
@click.option("--db-path", default=None, help="SQLite database path to initialize.")
def db_init(db_path):
    """Initialize the SQLite database and schema ledger."""
    state = StateManager(db_path)
    migrations = asyncio.run(state.list_schema_migrations())
    latest = migrations[-1].version if migrations else "none"
    console.print(f"[green]Initialized Market Edge database: {state.db_path}[/green]")
    console.print(f"[dim]Schema version: {latest}[/dim]")


@db.command("migrations")
@click.option("--db-path", default=None, help="SQLite database path to inspect.")
def db_migrations(db_path):
    """List recorded schema migrations."""
    state = StateManager(db_path)
    migrations = asyncio.run(state.list_schema_migrations())
    table = Table(title=f"Schema Migrations: {state.db_path}")
    table.add_column("Version", style="cyan")
    table.add_column("Applied At")
    table.add_column("Description")

    for migration in migrations:
        table.add_row(
            migration.version,
            migration.applied_at.isoformat(timespec="seconds"),
            migration.description,
        )

    if not migrations:
        table.add_row("none", "", "")

    console.print(table)


@db.command("audit-record")
@click.option("--db-path", default=None, help="SQLite database path to update.")
@click.option("--event-type", required=True, help="Audit event type.")
@click.option("--subject", required=True, help="Strategy, workflow, or actor subject.")
@click.option("--ticker", default=None, help="Optional market ticker.")
@click.option("--payload", multiple=True, help="Metadata formatted as key=value.")
def db_audit_record(db_path, event_type, subject, ticker, payload):
    """Append an audit event to the local SQLite trail."""
    try:
        parsed_payload = parse_key_value_pairs(payload)
    except ExperimentRegistryError as exc:
        raise click.ClickException(str(exc)) from exc

    state = StateManager(db_path)
    event_id = asyncio.run(
        state.record_audit_event(
            event_type=event_type,
            subject=subject,
            ticker=ticker,
            payload=parsed_payload,
        )
    )
    console.print(f"[green]Recorded audit event {event_id} ({SCHEMA_VERSION})[/green]")


@db.command("audit")
@click.option("--db-path", default=None, help="SQLite database path to inspect.")
@click.option("--limit", default=25, show_default=True, help="Maximum events to show.")
def db_audit(db_path, limit):
    """List recent audit events."""
    state = StateManager(db_path)
    events = asyncio.run(state.list_audit_events(limit=limit))
    table = Table(title=f"Audit Events: {state.db_path}")
    table.add_column("ID", style="dim")
    table.add_column("Created")
    table.add_column("Type", style="cyan")
    table.add_column("Subject")
    table.add_column("Ticker")
    table.add_column("Payload")

    for event in events:
        table.add_row(
            str(event.id),
            event.created_at.isoformat(timespec="seconds"),
            event.event_type,
            event.subject,
            event.ticker or "",
            event.payload_json,
        )

    if not events:
        table.add_row("", "", "none", "", "", "")

    console.print(table)


@cli.command()
@click.option("--ticker", required=True, help="Market ticker to analyze")
@click.option(
    "--model-prob", type=float, required=True, help="Your model probability (0-1)"
)
@click.option("--side", type=click.Choice(["yes", "no"]), default="yes")
@click.option("--bid", type=float, default=None, help="Generic bid quote in cents.")
@click.option("--ask", type=float, default=None, help="Generic ask quote in cents.")
@click.option("--yes-bid", type=float, default=None, help="YES bid quote in cents.")
@click.option("--yes-ask", type=float, default=None, help="YES ask quote in cents.")
@click.option("--no-bid", type=float, default=None, help="NO bid quote in cents.")
@click.option("--no-ask", type=float, default=None, help="NO ask quote in cents.")
@click.option(
    "--resolution-date",
    default=None,
    help="ISO-8601 market resolution date. Used for annualized yield.",
)
@click.option(
    "--days-to-resolution",
    type=float,
    default=7.0,
    show_default=True,
    help="Fallback days to resolution when no date is provided or fetched.",
)
@click.option(
    "--fetch",
    is_flag=True,
    help="Fetch current market/orderbook quotes by ticker using Kalshi credentials.",
)
@click.pass_context
def analyze(
    ctx,
    ticker,
    model_prob,
    side,
    bid,
    ask,
    yes_bid,
    yes_ask,
    no_bid,
    no_ask,
    resolution_date,
    days_to_resolution,
    fetch,
):
    """Analyze a specific market opportunity."""
    state = ctx.obj["state"]
    quant = ctx.obj["quant"]

    fetched_market = {}
    if fetch:
        if not kalshi_config.api_key or not kalshi_config.api_secret:
            raise click.ClickException(
                "--fetch requires KALSHI_API_KEY and KALSHI_API_SECRET"
            )
        fetched_market = asyncio.run(fetch_market_quotes(KalshiRestClient(), ticker))
        yes_bid = yes_bid if yes_bid is not None else fetched_market.get("yes_bid")
        yes_ask = yes_ask if yes_ask is not None else fetched_market.get("yes_ask")
        no_bid = no_bid if no_bid is not None else fetched_market.get("no_bid")
        no_ask = no_ask if no_ask is not None else fetched_market.get("no_ask")
        bid = bid if bid is not None else fetched_market.get("bid")
        ask = ask if ask is not None else fetched_market.get("ask")

    market_bid, market_ask = _quote_pair_for_side(
        side=side,
        bid=bid,
        ask=ask,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=no_bid,
        no_ask=no_ask,
    )
    parsed_resolution = _resolution_for_analyze(
        resolution_date=resolution_date,
        days_to_resolution=days_to_resolution,
        fetched_market=fetched_market,
    )

    portfolio = asyncio.run(state.get_portfolio_state())
    bankroll = portfolio.bankroll if portfolio else trading_config.initial_bankroll

    screen = quant.screen_opportunity(
        model_prob=model_prob,
        market_bid=market_bid,
        market_ask=market_ask,
        resolution_date=parsed_resolution,
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
    table.add_row("Bid / Ask", f"{market_bid:.1f}¢ / {market_ask:.1f}¢")
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
@click.option("--ticker", multiple=True, help="Ticker to collect; repeatable.")
@click.option("--weather-scan", is_flag=True, help="Scan open weather markets.")
@click.option(
    "--limit", default=50, show_default=True, help="Maximum markets per pass."
)
@click.option(
    "--interval",
    type=float,
    default=0.0,
    show_default=True,
    help="Seconds between polling passes.",
)
@click.option(
    "--iterations",
    type=int,
    default=1,
    show_default=True,
    help="Number of bounded polling passes.",
)
@click.option("--db-path", default=None, help="SQLite database path to write.")
def collect_snapshots(ticker, weather_scan, limit, interval, iterations, db_path):
    """Collect durable market snapshots into local SQLite state."""
    if not ticker and not weather_scan:
        raise click.ClickException("provide --ticker or --weather-scan")
    state = StateManager(db_path)
    result = asyncio.run(
        collect_market_snapshots(
            state,
            KalshiRestClient(),
            tickers=ticker,
            weather_scan=weather_scan,
            limit=limit,
            interval_seconds=interval,
            iterations=iterations,
        )
    )
    console.print(
        f"[green]Collected {result.written}/{result.attempted} market snapshots[/green]"
    )
    for error in result.errors:
        console.print(f"[yellow]{error}[/yellow]")


@cli.command("calibration-score")
@click.option("--forecasts", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--settlements", required=True, type=click.Path(exists=True, dir_okay=False)
)
@click.option(
    "--format",
    "file_format",
    type=click.Choice(["csv", "jsonl"]),
    default="csv",
    show_default=True,
)
@click.option(
    "--db-path", default=None, help="SQLite database path for stored forecasts."
)
@click.option("--json-out", type=click.Path(dir_okay=False, writable=True))
def calibration_score(forecasts, settlements, file_format, db_path, json_out):
    """Score forecast calibration from files or persisted forecast state."""
    resolver = (
        load_settlements_jsonl(settlements)
        if file_format == "jsonl"
        else load_settlements_csv(settlements)
    )
    if forecasts:
        forecast_rows = (
            load_forecasts_jsonl(forecasts)
            if file_format == "jsonl"
            else load_forecasts_csv(forecasts)
        )
        summary = CalibrationScorer().score(forecast_rows, resolver)
    else:
        summary = asyncio.run(
            score_persisted_forecasts(StateManager(db_path), resolver)
        )

    table = Table(title="Calibration")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Forecasts", str(summary.total_forecasts))
    table.add_row("Brier", f"{summary.brier_score:.4f}")
    table.add_row("Log Loss", f"{summary.log_loss:.4f}")
    table.add_row("Observed Rate", f"{summary.observed_rate:.2%}")
    table.add_row("Groups", str(len(summary.groups)))
    console.print(table)
    if json_out:
        output = export_calibration_summary(summary, json_out)
        console.print(f"[green]Wrote calibration summary to {output}[/green]")


@cli.command("calibration-fit-weights")
@click.option(
    "--settlements", required=True, type=click.Path(exists=True, dir_okay=False)
)
@click.option(
    "--format",
    "file_format",
    type=click.Choice(["csv", "jsonl"]),
    default="csv",
    show_default=True,
)
@click.option(
    "--db-path", default=None, help="SQLite database path for stored forecasts."
)
@click.option("--json-out", type=click.Path(dir_okay=False, writable=True))
def calibration_fit_weights(settlements, file_format, db_path, json_out):
    """Propose (dry-run) weather-blend weights learned from settled forecasts."""
    resolver = (
        load_settlements_jsonl(settlements)
        if file_format == "jsonl"
        else load_settlements_csv(settlements)
    )
    result = asyncio.run(fit_persisted_weights(StateManager(db_path), resolver))

    if result.sample_count == 0:
        console.print(
            "[yellow]No settled forecasts to fit against; weights unchanged.[/yellow]"
        )
        return

    table = Table(title="Proposed blend weights (dry run)")
    table.add_column("Source", style="cyan")
    table.add_column("Current", justify="right")
    table.add_column("Fitted", justify="right", style="green")
    for name in result.source_names:
        table.add_row(
            name,
            f"{result.baseline_weights[name]:.3f}",
            f"{result.fitted_weights[name]:.3f}",
        )
    console.print(table)
    console.print(
        f"Brier: {result.baseline_brier:.4f} (current) -> "
        f"{result.fitted_brier:.4f} (fitted) over {result.sample_count} forecasts"
    )
    if result.improved:
        console.print("[green]Fitted weights improve calibration.[/green]")
    else:
        console.print("[yellow]No improvement over current weights.[/yellow]")
    console.print("[yellow]Dry run — weather_config weights are unchanged.[/yellow]")
    if json_out:
        path = Path(json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.to_dict(), indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        console.print(f"[green]Wrote proposed weights to {path}[/green]")


@cli.group()
def strategies():
    """List, configure, and run registered strategies."""


@strategies.command("list")
@click.option(
    "--config", "config_path", default="data/strategy-config.json", show_default=True
)
@click.pass_context
def strategies_list(ctx, config_path):
    """List registered strategies and last-run status."""
    state = ctx.obj["state"]
    statuses = asyncio.run(
        StrategyManager(
            state,
            registry=StrategyRegistry(),
            config_store=StrategyConfigStore(config_path),
        ).list_status()
    )
    table = Table(title="Strategies")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Enabled")
    table.add_column("Last Status")
    table.add_column("Signals")
    for item in statuses:
        last_run = item["last_run"] or {}
        table.add_row(
            item["strategy_id"],
            item["display_name"],
            "yes" if item["enabled"] else "no",
            last_run.get("status", ""),
            str(last_run.get("signal_count", "")),
        )
    console.print(table)


@strategies.command("inspect")
@click.argument("strategy_id")
@click.option(
    "--config", "config_path", default="data/strategy-config.json", show_default=True
)
def strategies_inspect(strategy_id, config_path):
    """Show one strategy metadata/config as JSON."""
    registry = StrategyRegistry()
    strategy = registry.get(strategy_id)
    config = StrategyConfigStore(config_path).get_strategy_config(
        strategy_id, strategy.default_config()
    )
    console.print_json(
        data={
            **strategy.metadata.to_dict(),
            "default_config": strategy.default_config(),
            "config": config,
        }
    )


@strategies.command("enable")
@click.argument("strategy_id")
@click.option(
    "--config", "config_path", default="data/strategy-config.json", show_default=True
)
def strategies_enable(strategy_id, config_path):
    """Enable a registered strategy."""
    StrategyRegistry().get(strategy_id)
    StrategyConfigStore(config_path).set_enabled(strategy_id, True)
    console.print(f"[green]Enabled {strategy_id}[/green]")


@strategies.command("disable")
@click.argument("strategy_id")
@click.option(
    "--config", "config_path", default="data/strategy-config.json", show_default=True
)
def strategies_disable(strategy_id, config_path):
    """Disable a registered strategy."""
    StrategyRegistry().get(strategy_id)
    StrategyConfigStore(config_path).set_enabled(strategy_id, False)
    console.print(f"[green]Disabled {strategy_id}[/green]")


@strategies.command("run")
@click.argument("strategy_id")
@click.option(
    "--config", "config_path", default="data/strategy-config.json", show_default=True
)
@click.option(
    "--live",
    is_flag=True,
    help="Mark the run as live-intended; no orders are placed here.",
)
@click.option("--json-out", type=click.Path(dir_okay=False, writable=True))
@click.pass_context
def strategies_run(ctx, strategy_id, config_path, live, json_out):
    """Run a registered strategy through the local manager."""
    state = ctx.obj["state"]
    result = asyncio.run(
        StrategyManager(
            state,
            registry=StrategyRegistry(),
            config_store=StrategyConfigStore(config_path),
        ).run(strategy_id, dry_run=not live)
    )
    console.print(
        f"[green]Ran {strategy_id}: {result['status']} "
        f"({len(result['opportunities'])} signals)[/green]"
    )
    if json_out:
        output_path = Path(json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
        console.print(f"[green]Wrote strategy run to {output_path}[/green]")


@cli.command()
@click.option(
    "--live/--dry",
    default=False,
    help="Live trading or dry run (dry run is the default and is always safe)",
)
@click.option("--interval", default=300, help="Scan interval in seconds")
@click.option(
    "--confirm-live",
    is_flag=True,
    default=False,
    help="Operator confirmation required to place real orders in live mode",
)
@click.pass_context
def trade(ctx, live, interval, confirm_live):
    """Run the weather trading strategy.

    Defaults to a dry run that never places real orders. Live mode fails closed:
    it runs only when the global kill switch is disengaged, MARKETEDGE_ALLOW_LIVE
    is set, both Kalshi credentials are present, and --confirm-live is passed.
    """
    state = ctx.obj["state"]

    decision = evaluate_live_trading_gate(
        live=live,
        api_key=kalshi_config.api_key,
        api_secret=kalshi_config.api_secret,
        confirmed=confirm_live,
        allow_live_env=os.getenv(ALLOW_LIVE_ENV),
        kill_switch_env=os.getenv(KILL_SWITCH_ENV),
    )
    if not decision.allowed:
        console.print(f"[red]Live trading blocked: {decision.reason}[/red]")
        sys.exit(1)

    client = KalshiRestClient()
    strategy = WeatherTradingStrategy(
        state,
        client,
        use_sample_markets_if_empty=not live,
        execute_orders=live,
    )

    mode = "LIVE" if live else "DRY RUN"
    console.print(
        Panel(
            f"[bold]Starting Weather Strategy - {mode}[/bold]\nInterval: {interval}s",
            border_style="yellow" if live else "blue",
        )
    )

    async def run_strategy():
        try:
            await strategy.run_continuous(interval)
        finally:
            await strategy.stop()

    try:
        asyncio.run(run_strategy())
    except KeyboardInterrupt:
        console.print("[yellow]Shutting down...[/yellow]")


@cli.command()
@click.option("--env-file", default=".env", show_default=True)
@click.option("--db-path", default=None, help="SQLite database path to validate.")
@click.option(
    "--dashboard-path",
    default="web/data/backtest-summary.json",
    show_default=True,
    help="Dashboard backtest artifact to validate.",
)
@click.option("--strict", is_flag=True, help="Treat warnings as failures.")
def doctor(env_file, db_path, dashboard_path, strict):
    """Validate local setup and operator readiness."""
    checks = run_health_checks(env_file, db_path, dashboard_path)
    table = Table(title="Market Edge Doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Message")
    table.add_column("Remediation", style="yellow")

    status_style = {"ok": "green", "warn": "yellow", "fail": "red"}
    for check in checks:
        table.add_row(
            check.name,
            f"[{status_style[check.status]}]{check.status.upper()}[/{status_style[check.status]}]",
            check.message,
            check.remediation,
        )
    console.print(table)

    if has_failures(checks) or (strict and has_warnings(checks)):
        sys.exit(1)


@cli.command("dashboard-data")
@click.option("--out", default="web/data/dashboard.json", show_default=True)
@click.option("--db-path", default=None, help="SQLite database path to export.")
@click.option(
    "--paper-ledger",
    default="data/paper-ledger.jsonl",
    show_default=True,
    help="Optional paper trading ledger to include.",
)
@click.option(
    "--backtest-summary",
    default="web/data/backtest-summary.json",
    show_default=True,
    help="Optional generated backtest summary to include.",
)
def dashboard_data(out, db_path, paper_ledger, backtest_summary):
    """Write dashboard-ready JSON from local state."""
    state = StateManager(db_path)
    payload = asyncio.run(
        build_dashboard_payload(
            state,
            paper_ledger_path=paper_ledger,
            backtest_summary_path=backtest_summary,
        )
    )
    output_path = write_dashboard_payload(payload, out)
    console.print(f"[green]Wrote dashboard data to {output_path}[/green]")


@cli.command()
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--bankroll",
    type=float,
    default=trading_config.initial_bankroll,
    show_default=True,
)
@click.option("--json-out", type=click.Path(dir_okay=False, writable=True))
@click.option("--limit", type=int, default=20, show_default=True)
def opportunities(path, bankroll, json_out, limit):
    """Rank offline opportunity candidates by edge, risk, and liquidity."""
    results = OpportunityScanner().rank(load_candidates(path), bankroll=bankroll)
    table = Table(title=f"Opportunities: {path}")
    table.add_column("Rank", style="dim")
    table.add_column("Ticker", style="cyan")
    table.add_column("Side")
    table.add_column("Action")
    table.add_column("Score")
    table.add_column("Edge")
    table.add_column("EV")
    table.add_column("Size")
    table.add_column("Reasons")

    for index, result in enumerate(results[:limit], start=1):
        table.add_row(
            str(index),
            result.ticker,
            result.side.upper(),
            result.action,
            f"{result.score:.2f}",
            f"{result.fee_adjusted_edge:.2%}",
            f"{result.expected_value:.3f}",
            f"${result.recommended_bet_dollars:,.2f}",
            ", ".join(result.reason_codes),
        )
    console.print(table)

    if json_out:
        output_path = Path(json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump([result.to_dict() for result in results], handle, indent=2)
            handle.write("\n")
        console.print(f"[green]Wrote opportunity rankings to {output_path}[/green]")


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


@experiments.command("compare")
@click.argument("run_ids", nargs=-1)
@click.option("--registry", default="data/experiments.jsonl", show_default=True)
@click.option("--json-out", type=click.Path(dir_okay=False, writable=True))
def experiment_compare(run_ids, registry, json_out):
    """Compare two or more experiment records."""
    if len(run_ids) < 2:
        raise click.ClickException("compare requires at least two run IDs")

    comparison = ExperimentRegistry(registry).compare(run_ids)
    table = Table(title=f"Experiment Compare: {comparison['baseline_run_id']} baseline")
    table.add_column("Run ID", style="cyan")
    table.add_column("Strategy")
    table.add_column("Model")
    table.add_column("Return")
    table.add_column("Net P&L")
    table.add_column("Sharpe")
    table.add_column("Warnings", style="yellow")

    for run in comparison["runs"]:
        metrics = run["metrics"]
        table.add_row(
            run["run_id"],
            run["strategy_name"],
            run["model_version"],
            _format_optional_percent(metrics.get("return_pct")),
            _format_optional_dollars(metrics.get("net_pnl")),
            _format_optional_ratio(metrics.get("sharpe_like")),
            "; ".join(run["warnings"]),
        )
    console.print(table)

    if json_out:
        output_path = Path(json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(comparison, handle, indent=2, allow_nan=False)
            handle.write("\n")
        console.print(f"[green]Wrote experiment comparison to {output_path}[/green]")


@experiments.command("add-artifact")
@click.argument("run_id")
@click.argument("artifact_path")
@click.option("--registry", default="data/experiments.jsonl", show_default=True)
def experiment_add_artifact(run_id, artifact_path, registry):
    """Append an artifact link to an experiment record."""
    record = ExperimentRegistry(registry).add_artifact(run_id, artifact_path)
    console.print(f"[green]Linked artifact to {record.run_id}[/green]")


@cli.group()
def paper():
    """Manage no-account paper trading ledger events."""


@paper.command("order")
@click.option("--ledger", default="data/paper-ledger.jsonl", show_default=True)
@click.option("--ticker", required=True)
@click.option("--side", type=click.Choice(["yes", "no"]), required=True)
@click.option("--action", type=click.Choice(["buy", "sell"]), required=True)
@click.option("--quantity", type=int, required=True)
@click.option("--price", type=float, required=True, help="Limit/fill price in cents.")
@click.option("--fee", type=float, default=0.0, show_default=True)
@click.option("--note", default="")
def paper_order(ledger, ticker, side, action, quantity, price, fee, note):
    """Record a dry-run paper order as an immediate fill."""
    try:
        event = PaperTradingLedger(ledger).record_order(
            ticker=ticker,
            side=side,
            action=action,
            quantity=quantity,
            price=price,
            fee=fee,
            note=note,
        )
    except PaperLedgerError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"[green]Recorded paper order {event.event_id}[/green]")


@paper.command("settle")
@click.option("--ledger", default="data/paper-ledger.jsonl", show_default=True)
@click.option("--ticker", required=True)
@click.option("--winning-side", type=click.Choice(["yes", "no"]), required=True)
@click.option("--note", default="")
def paper_settle(ledger, ticker, winning_side, note):
    """Settle all open paper positions for one ticker."""
    event = PaperTradingLedger(ledger).settle(
        ticker=ticker,
        winning_side=winning_side,
        note=note,
    )
    console.print(f"[green]Recorded paper settlement {event.event_id}[/green]")


@paper.command("positions")
@click.option("--ledger", default="data/paper-ledger.jsonl", show_default=True)
def paper_positions(ledger):
    """Show open paper positions and realized P&L."""
    summary = PaperTradingLedger(ledger).summary()
    table = Table(title=f"Paper Positions: {ledger}")
    table.add_column("Ticker", style="cyan")
    table.add_column("Side")
    table.add_column("Qty")
    table.add_column("Avg")
    table.add_column("Cost")
    table.add_column("Realized")

    for position in summary["open_positions"]:
        table.add_row(
            position["ticker"],
            position["side"].upper(),
            str(position["quantity"]),
            f"{position['average_price']:.2f}¢",
            f"${position['cost_basis']:,.2f}",
            f"${position['realized_pnl']:,.2f}",
        )
    console.print(table)
    console.print(
        f"[dim]Events: {summary['event_count']} | Realized P&L: ${summary['realized_pnl']:,.2f} | Fees: ${summary['fees']:,.2f}[/dim]"
    )


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
    text.append("MARKET EDGE FORMULAS\n\n", style="bold underline")

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


def _format_optional_percent(value):
    if isinstance(value, (int, float)):
        return f"{value:.2%}"
    return "N/A"


def _format_optional_dollars(value):
    if isinstance(value, (int, float)):
        return f"${value:,.2f}"
    return "N/A"


def _format_optional_ratio(value):
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return "N/A"


def _quote_pair_for_side(
    *,
    side: str,
    bid: float | None,
    ask: float | None,
    yes_bid: float | None,
    yes_ask: float | None,
    no_bid: float | None,
    no_ask: float | None,
) -> tuple[float, float]:
    if side == "yes":
        market_bid = yes_bid if yes_bid is not None else bid
        market_ask = yes_ask if yes_ask is not None else ask
        label = "YES"
    else:
        market_bid = no_bid if no_bid is not None else bid
        market_ask = no_ask if no_ask is not None else ask
        label = "NO"
    if market_bid is None or market_ask is None:
        raise click.ClickException(
            f"missing {label} quote inputs; provide --{side}-bid/--{side}-ask, "
            "--bid/--ask, or use --fetch with credentials"
        )
    if not 0 <= market_bid <= 100 or not 0 <= market_ask <= 100:
        raise click.ClickException("quotes must be between 0 and 100 cents")
    if market_bid > market_ask:
        raise click.ClickException("bid cannot be greater than ask")
    return float(market_bid), float(market_ask)


def _resolution_for_analyze(
    *,
    resolution_date: str | None,
    days_to_resolution: float,
    fetched_market: dict,
):
    if resolution_date:
        return parse_timestamp(resolution_date)
    for key in ("resolution_date", "close_date", "expiration_date", "settle_time"):
        value = fetched_market.get(key)
        if value:
            return parse_timestamp(str(value))
    if days_to_resolution <= 0:
        raise click.ClickException("--days-to-resolution must be positive")
    return utcnow() + timedelta(days=days_to_resolution)


if __name__ == "__main__":
    cli()
