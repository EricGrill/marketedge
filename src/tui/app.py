# marketedge/src/tui/app.py
"""Textual TUI for Market Edge."""

import asyncio
import logging

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
            self.bankroll = portfolio.bankroll
            self.available = portfolio.available_cash
            self.exposure = portfolio.total_exposure
            self.open_count = portfolio.open_positions_count
            self.mtd_pnl = portfolio.mtd_pnl


class PositionsTable(Static):
    """Display open positions table."""

    def compose(self) -> ComposeResult:
        yield Label("[b]OPEN POSITIONS[/b]", classes="title")
        table = DataTable(id="positions-table")
        table.add_columns(
            "Ticker", "Side", "Entry", "Qty", "Edge", "IY", "Location", "Age"
        )
        yield table

    async def refresh_data(self, state_manager: StateManager):
        table = self.query_one("#positions-table", DataTable)
        table.clear()

        positions = await state_manager.get_open_positions()
        for pos in positions:
            age = (utcnow() - pos.created_at).days
            table.add_row(
                pos.ticker,
                pos.side.upper(),
                f"{pos.entry_price:.2f}",
                str(pos.quantity),
                f"{pos.edge_at_entry:.2%}",
                f"{pos.iy_annualized:.0%}",
                pos.location or "N/A",
                f"{age}d",
            )


class SignalsTable(Static):
    """Display recent trade signals."""

    signals = reactive([], init=False)

    def compose(self) -> ComposeResult:
        yield Label("[b]RECENT SIGNALS[/b]", classes="title")
        table = DataTable(id="signals-table")
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
            self.scanning = True
            self.query_one("#scanner-log", Log).write_line(
                "[SCANNER] Starting market scan..."
            )
        elif event.button.id == "stop-btn":
            self.scanning = False
            self.query_one("#scanner-log", Log).write_line("[SCANNER] Stopped.")

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
        self._refresh_task = None
        self._signals_history = []

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
        scanner = self.query_one("#scanner", MarketScannerWidget)
        scanner.add_log("[SCANNER] Manual scan triggered via hotkey")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-settings":
            self.query_one("#scanner", MarketScannerWidget).add_log(
                "[SETTINGS] Saved (mock)"
            )

    def add_signal(self, signal: dict):
        """Add a trade signal to history."""
        signal["time"] = utcnow().strftime("%H:%M:%S")
        self._signals_history.append(signal)
        signals_widget = self.query_one("#signals", SignalsTable)
        signals_widget.signals = self._signals_history

    async def on_unmount(self):
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
