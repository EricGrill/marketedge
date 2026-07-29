# marketedge/src/tui/app.py
"""Textual TUI for Market Edge."""

import asyncio
import logging
from typing import Any, List, Optional, cast

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Grid
from textual.widgets import (
    Header,
    Footer,
    Static,
    DataTable,
    Log,
    Button,
    Input,
    Label,
    TabbedContent,
    TabPane,
)
from textual.reactive import reactive
from textual.binding import Binding

from src.state import StateManager
from src.formulas import QuantEngine
from src.config import trading_config
from src.opportunities import OpportunityCandidate, OpportunityScanner
from src.utils import utcnow

logger = logging.getLogger(__name__)


class PortfolioWidget(Static):
    """Display portfolio summary."""

    # init=False: these watchers query child Labels that do not exist until the
    # Grid below is mounted. Firing them during compose/mount raises NoMatches,
    # so we suppress the initialization call and let refresh_data drive updates.
    bankroll = reactive(10000.0, init=False)
    available = reactive(10000.0, init=False)
    exposure = reactive(0.0, init=False)
    open_count = reactive(0, init=False)
    mtd_pnl = reactive(0.0, init=False)

    def compose(self) -> ComposeResult:
        yield Label("[b]PORTFOLIO[/b]", classes="title")
        yield Grid(
            Label("Bankroll:", classes="label"),
            Label(f"${self.bankroll:,.2f}", id="bankroll-val", classes="value"),
            Label("Available:", classes="label"),
            Label(f"${self.available:,.2f}", id="available-val", classes="value"),
            Label("Exposure:", classes="label"),
            Label(f"${self.exposure:,.2f}", id="exposure-val", classes="value"),
            Label("Open Pos:", classes="label"),
            Label(str(self.open_count), id="open-count-val", classes="value"),
            Label("MTD P&L:", classes="label"),
            Label(f"${self.mtd_pnl:,.2f}", id="mtd-pnl-val", classes="value"),
            classes="portfolio-grid",
        )

    def watch_bankroll(self, value: float):
        self.query_one("#bankroll-val", Label).update(f"${value:,.2f}")

    def watch_available(self, value: float):
        self.query_one("#available-val", Label).update(f"${value:,.2f}")

    def watch_exposure(self, value: float):
        self.query_one("#exposure-val", Label).update(f"${value:,.2f}")

    def watch_open_count(self, value: int):
        self.query_one("#open-count-val", Label).update(str(value))

    def watch_mtd_pnl(self, value: float):
        label = self.query_one("#mtd-pnl-val", Label)
        color = "green" if value >= 0 else "red"
        label.update(f"[{color}]${value:,.2f}[/{color}]")

    async def refresh_data(self, state_manager: StateManager):
        portfolio = await state_manager.get_portfolio_state()
        if portfolio:
            self.bankroll = portfolio.bankroll or 0.0
            self.available = portfolio.available_cash or 0.0
            self.exposure = portfolio.total_exposure or 0.0
            self.open_count = portfolio.open_positions_count or 0
            self.mtd_pnl = portfolio.mtd_pnl or 0.0


class PositionsTable(Static):
    """Display open positions table."""

    def compose(self) -> ComposeResult:
        yield Label("[b]OPEN POSITIONS[/b]", classes="title")
        table: DataTable = DataTable(id="positions-table")
        table.add_columns(
            "Ticker", "Side", "Entry", "Qty", "Edge", "IY", "Location", "Age"
        )
        yield table

    async def refresh_data(self, state_manager: StateManager):
        table = self.query_one("#positions-table", DataTable)
        table.clear()

        positions = await state_manager.get_open_positions()
        for pos in positions:
            age = (utcnow() - (pos.created_at or utcnow())).days
            table.add_row(
                pos.ticker,
                (pos.side or "").upper(),
                f"{pos.entry_price:.2f}",
                str(pos.quantity),
                f"{pos.edge_at_entry:.2%}",
                f"{pos.iy_annualized:.0%}",
                pos.location or "N/A",
                f"{age}d",
            )


class SignalsTable(Static):
    """Display recent trade signals."""

    signals: reactive[list] = reactive([], init=False)

    def compose(self) -> ComposeResult:
        yield Label("[b]RECENT SIGNALS[/b]", classes="title")
        table: DataTable = DataTable(id="signals-table")
        table.add_columns("Time", "Ticker", "Side", "Price", "Edge", "IY", "Action")
        yield table

    def watch_signals(self, signals: list):
        table = self.query_one("#signals-table", DataTable)
        table.clear()
        for sig in signals[-20:]:  # Last 20
            table.add_row(
                sig.get("time", ""),
                sig.get("ticker", ""),
                sig.get("side", "").upper(),
                f"{sig.get('price', 0):.1f}¢",
                f"{sig.get('edge', 0):.2%}",
                f"{sig.get('iy', 0):.0%}",
                sig.get("action", ""),
            )


class MarketScannerWidget(Static):
    """Market scanner control panel."""

    scanning = reactive(False)

    def compose(self) -> ComposeResult:
        yield Label("[b]MARKET SCANNER[/b]", classes="title")
        yield Horizontal(
            Button("Start Scan", id="scan-btn", variant="primary"),
            Button("Stop", id="stop-btn", variant="error"),
            Input(placeholder="Min Edge %", id="min-edge", value="3"),
            Input(placeholder="Min IY %", id="min-iy", value="50"),
            classes="scanner-controls",
        )
        yield Log(id="scanner-log", highlight=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scan-btn":
            cast("KalshiQuantApp", self.app).start_scanner()
            event.stop()
        elif event.button.id == "stop-btn":
            cast("KalshiQuantApp", self.app).stop_scanner()
            event.stop()

    def add_log(self, message: str):
        self.query_one("#scanner-log", Log).write_line(message)


class RiskWidget(Static):
    """Risk metrics display."""

    # init=False: see PortfolioWidget — watchers query child Labels mounted below.
    ror = reactive(0.0, init=False)
    max_dd = reactive(0.0, init=False)
    var95 = reactive(0.0, init=False)

    def compose(self) -> ComposeResult:
        yield Label("[b]RISK METRICS[/b]", classes="title")
        yield Grid(
            Label("RoR:", classes="label"),
            Label(f"{self.ror:.2%}", id="ror-val", classes="value"),
            Label("Max DD:", classes="label"),
            Label(f"{self.max_dd:.2%}", id="max-dd-val", classes="value"),
            Label("VaR 95%:", classes="label"),
            Label(f"${self.var95:,.2f}", id="var-val", classes="value"),
            classes="risk-grid",
        )

    def watch_ror(self, value: float):
        label = self.query_one("#ror-val", Label)
        color = "green" if value < 0.01 else "yellow" if value < 0.05 else "red"
        label.update(f"[{color}]{value:.2%}[/{color}]")

    def watch_max_dd(self, value: float):
        self.query_one("#max-dd-val", Label).update(f"{value:.2%}")

    def watch_var95(self, value: float):
        self.query_one("#var-val", Label).update(f"${value:,.2f}")


class KalshiQuantApp(App):
    """Main TUI application."""

    CSS = """
    Screen {
        align: center middle;
    }

    .title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin: 1 0;
    }

    .portfolio-grid, .risk-grid {
        grid-size: 2;
        grid-columns: 15 20;
        grid-rows: auto;
        padding: 1;
    }

    .label {
        text-style: bold;
        color: $text-muted;
    }

    .value {
        text-align: right;
        color: $text;
    }

    .scanner-controls {
        height: auto;
        margin: 1 0;
    }

    #scanner-log {
        height: 15;
        border: solid $primary;
    }

    DataTable {
        height: 1fr;
        border: solid $primary;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("s", "scan", "Scan Now", show=True),
    ]

    def __init__(self, state_manager: StateManager, **kwargs):
        super().__init__(**kwargs)
        self.state = state_manager
        self.quant = QuantEngine()
        self._refresh_task: Optional[asyncio.Task] = None
        self._scan_task: Optional[asyncio.Task] = None
        self._signals_history: List[Any] = []
        self._scanner_settings = {
            "min_edge": trading_config.min_edge_pct,
            "min_iy": trading_config.min_iy_annualized,
        }

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent():
            with TabPane("Dashboard", id="dashboard"):
                with Horizontal():
                    with Vertical(classes="left-panel"):
                        yield PortfolioWidget(id="portfolio")
                        yield RiskWidget(id="risk")
                        yield MarketScannerWidget(id="scanner")
                    with Vertical(classes="right-panel"):
                        yield PositionsTable(id="positions")
                        yield SignalsTable(id="signals")

            with TabPane("Positions", id="positions-tab"):
                yield PositionsTable(id="positions-detail")

            with TabPane("Settings", id="settings"):
                yield Label("[b]TRADING CONFIGURATION[/b]", classes="title")
                yield Grid(
                    Label("Kelly Fraction:"),
                    Input(value=str(trading_config.kelly_fraction), id="kelly-input"),
                    Label("Max Position %:"),
                    Input(
                        value=str(trading_config.max_position_pct), id="max-pos-input"
                    ),
                    Label("Min Edge %:"),
                    Input(value=str(trading_config.min_edge_pct), id="min-edge-input"),
                    Label("Min IY %:"),
                    Input(
                        value=str(trading_config.min_iy_annualized), id="min-iy-input"
                    ),
                    classes="settings-grid",
                )
                yield Button("Save Settings", id="save-settings", variant="primary")

        yield Footer()

    async def on_mount(self):
        """Start background refresh."""
        # NB: do not name this loop `_auto_refresh` — Textual's DOMNode reserves
        # `self._auto_refresh` as an instance attribute (the auto_refresh interval),
        # which would shadow the method and make `self._auto_refresh()` call None.
        self._refresh_task = asyncio.create_task(self._auto_refresh_loop())

    async def _auto_refresh_loop(self):
        """Auto-refresh dashboard every 5 seconds."""
        while True:
            try:
                await self._refresh_dashboard()
                await asyncio.sleep(5)
            except Exception:
                logger.exception("Refresh error")
                await asyncio.sleep(5)

    async def _refresh_dashboard(self):
        """Refresh all dashboard widgets."""
        portfolio_widget = self.query_one("#portfolio", PortfolioWidget)
        await portfolio_widget.refresh_data(self.state)

        positions_widget = self.query_one("#positions", PositionsTable)
        await positions_widget.refresh_data(self.state)

        # Update risk metrics
        risk_widget = self.query_one("#risk", RiskWidget)
        portfolio = await self.state.get_portfolio_state()
        if portfolio:
            # Calculate risk metrics
            bankroll = portfolio.bankroll
            exposure = portfolio.total_exposure
            if bankroll > 0:
                risk_widget.ror = min(1.0, exposure / bankroll * 0.1)
                risk_widget.max_dd = portfolio.max_drawdown
                risk_widget.var95 = exposure * 0.05

    def action_refresh(self):
        """Manual refresh action."""
        asyncio.create_task(self._refresh_dashboard())

    def action_scan(self):
        """Trigger scan action."""
        self.start_scanner(manual=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-settings":
            self.save_settings()
            event.stop()

    def start_scanner(self, manual: bool = False):
        """Start a bounded local scan from stored market snapshots."""
        scanner = self.query_one("#scanner", MarketScannerWidget)
        if self._scan_task and not self._scan_task.done():
            scanner.add_log("[SCANNER] Scan already running")
            return
        try:
            self._scanner_settings.update(self._scanner_control_settings())
        except ValueError as exc:
            scanner.add_log(f"[SCANNER] Invalid settings: {exc}")
            return
        scanner.scanning = True
        scanner.add_log(
            "[SCANNER] Manual scan triggered"
            if manual
            else "[SCANNER] Starting local scan"
        )
        self._scan_task = asyncio.create_task(self._run_local_scan())

    def stop_scanner(self):
        """Cancel any active scan task."""
        scanner = self.query_one("#scanner", MarketScannerWidget)
        if self._scan_task and not self._scan_task.done():
            self._scan_task.cancel()
        scanner.scanning = False
        scanner.add_log("[SCANNER] Stopped.")

    def save_settings(self):
        """Validate and stage runtime settings."""
        scanner = self.query_one("#scanner", MarketScannerWidget)
        try:
            min_edge = _parse_percent_input(
                self.query_one("#min-edge-input", Input).value,
                "Min Edge %",
            )
            min_iy = _parse_percent_input(
                self.query_one("#min-iy-input", Input).value,
                "Min IY %",
            )
            self._scanner_settings.update({"min_edge": min_edge, "min_iy": min_iy})
            scanner.add_log("[SETTINGS] Saved runtime settings")
        except ValueError as exc:
            scanner.add_log(f"[SETTINGS] Invalid settings: {exc}")

    async def _run_local_scan(self):
        scanner = self.query_one("#scanner", MarketScannerWidget)
        try:
            snapshots = await self.state.get_latest_market_snapshots(limit=100)
            if not snapshots:
                scanner.add_log("[SCANNER] No local market snapshots available")
                return
            candidates = [_candidate_from_snapshot(snapshot) for snapshot in snapshots]
            results = OpportunityScanner(self.quant).rank(candidates)
            min_edge = self._scanner_settings["min_edge"]
            min_iy = self._scanner_settings["min_iy"]
            filtered = [
                result
                for result in results
                if abs(result.fee_adjusted_edge) >= min_edge
                and result.annualized_yield >= min_iy
            ]
            if not filtered:
                scanner.add_log("[SCANNER] No signals matched current thresholds")
                return
            for result in filtered[:20]:
                self.add_signal(
                    {
                        "ticker": result.ticker,
                        "side": result.side,
                        "price": result.entry_price,
                        "edge": result.fee_adjusted_edge,
                        "iy": result.annualized_yield,
                        "action": result.action,
                    }
                )
            scanner.add_log(f"[SCANNER] Added {len(filtered[:20])} local signals")
        except asyncio.CancelledError:
            scanner.add_log("[SCANNER] Cancelled active scan")
            raise
        except Exception as exc:
            logger.exception("Local scan failed")
            scanner.add_log(f"[SCANNER] Error: {exc}")
        finally:
            scanner.scanning = False

    def _scanner_control_settings(self) -> dict:
        return {
            "min_edge": _parse_percent_input(
                self.query_one("#min-edge", Input).value,
                "Min Edge %",
            ),
            "min_iy": _parse_percent_input(
                self.query_one("#min-iy", Input).value,
                "Min IY %",
            ),
        }

    def add_signal(self, signal: dict):
        """Add a trade signal to history."""
        signal["time"] = utcnow().strftime("%H:%M:%S")
        self._signals_history.append(signal)
        signals_widget = self.query_one("#signals", SignalsTable)
        signals_widget.signals = self._signals_history

    async def on_unmount(self):
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass


def _parse_percent_input(raw: str, label: str) -> float:
    value = float(raw)
    if value < 0:
        raise ValueError(f"{label} cannot be negative")
    return value / 100.0 if value > 1 else value


def _candidate_from_snapshot(snapshot) -> OpportunityCandidate:
    midpoint = (
        ((snapshot.yes_bid or 0) + (snapshot.yes_ask or 0)) / 200.0
        if snapshot.yes_bid is not None and snapshot.yes_ask is not None
        else 0.5
    )
    return OpportunityCandidate(
        ticker=snapshot.ticker,
        title=snapshot.title or snapshot.ticker,
        model_probability=max(0.01, min(0.99, midpoint)),
        yes_bid=snapshot.yes_bid or snapshot.bid or 0.0,
        yes_ask=snapshot.yes_ask or snapshot.ask or 0.0,
        no_bid=snapshot.no_bid,
        no_ask=snapshot.no_ask,
        confidence=0.5,
        volume=snapshot.volume_24h or 0,
        open_interest=snapshot.open_interest or 0,
    )
