# Order Lifecycle State Machine — Design

Date: 2026-06-22
Status: Approved for planning

## Problem

`WeatherTradingStrategy.execute_signal` fires `place_order` and forgets it. There
is no record of an order's outcome, so:

- A **rejected** order is logged but the strategy still proceeds as if nothing
  is outstanding.
- A **partial fill** is invisible: the recorded position is sized to the
  *requested* quantity, not the quantity actually filled — a phantom position.
- A **stuck/working** order has no timeout; nothing ever closes it out.

There is also no audit trail of order state over time, which the structured
logging work (improvement #2) was a prerequisite for.

## Goals

- Track every order through an explicit, validated lifecycle.
- Persist the lifecycle as an append-only, replayable audit trail.
- Size recorded positions to the **actually filled** quantity.
- Detect timeouts in a dry-run world that has no live order-status feed.
- Keep the core pure and unit-testable in isolation.

## Non-Goals (YAGNI)

- Cancel/replace (amend) flows.
- Multi-leg or basket orders.
- Live order-status polling. `KalshiRestClient.get_orders` / `cancel_order`
  already exist and can feed `record_fill` / `cancel` later without changing
  this design.

## Approach

Event-sourced ledger, mirroring the existing `src/paper.py`
(`PaperTradingLedger`): the ledger is an append-only JSONL of **events**, and an
order's current state is derived by folding its event stream. No mutable rows;
fully replayable and auditable. Persistence lives at `data/orders.jsonl`, which
is already covered by `.gitignore` (`data/*.jsonl`).

The state machine is a pure, I/O-free fold so it can be exhaustively unit
tested. The `OrderLedger` class is a thin I/O wrapper that appends events and
re-reads/folds, exactly like `PaperTradingLedger`.

## Components

### `src/orders.py` (new)

#### `OrderState` (enum)

`PENDING`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED`, `EXPIRED`.

Terminal states: `FILLED`, `CANCELLED`, `REJECTED`, `EXPIRED`.

#### `OrderEvent` (frozen dataclass)

One appended JSONL line:

- `order_id: str`
- `event_type: str` — one of `submitted`, `fill`, `rejected`, `cancelled`, `expired`
- `quantity: int` — for `submitted` = requested qty; for `fill` = qty of *this*
  fill; otherwise 0
- `price: float | None` — effective price for a `fill` (cents), else `None`
- `timestamp: datetime` — UTC-aware via `src.utils.utcnow`
- `detail: str` — free text (e.g. rejection reason); default `""`
- identity fields carried on the `submitted` event only: `ticker`, `side`,
  `action`, `order_type`, `limit_price`

#### `OrderRecord` (frozen dataclass) — folded view

- identity: `order_id`, `ticker`, `side`, `action`, `order_type`, `limit_price`
- `requested_quantity: int`
- `filled_quantity: int`
- `average_fill_price: float | None` — quantity-weighted over fills
- `state: OrderState`
- `created_at: datetime`, `updated_at: datetime`
- `reason: str` — last non-fill detail (rejection/cancel/expire reason)

#### Pure core

`apply_event(record: OrderRecord | None, event: OrderEvent) -> OrderRecord`

- A `submitted` event for an unknown order creates the initial `PENDING` record.
- A transition table validates `event_type` against the current `state`:

  ```
  PENDING          --fill (cumulative < requested)--> PARTIALLY_FILLED
  PENDING          --fill (cumulative >= requested)--> FILLED
  PENDING          --rejected/cancelled/expired-----> REJECTED/CANCELLED/EXPIRED
  PARTIALLY_FILLED --fill (cumulative < requested)--> PARTIALLY_FILLED
  PARTIALLY_FILLED --fill (cumulative >= requested)--> FILLED
  PARTIALLY_FILLED --cancelled/expired------------->  CANCELLED/EXPIRED
  <terminal>       --any-----------------------------> raises OrderLedgerError
  ```

- Fills accumulate `filled_quantity`; `average_fill_price` is recomputed as the
  quantity-weighted mean of fill prices. A fill whose cumulative quantity
  exceeds `requested_quantity` is an error (`OrderLedgerError`).
- Invalid transitions raise `OrderLedgerError`.

`OrderLedgerError(ValueError)` — consistent with `PaperLedgerError`,
`ExecutionModelError`, etc.

#### `OrderLedger` (class) — thin I/O wrapper

Constructor: `OrderLedger(path: str | Path = "data/orders.jsonl")` — same shape
as `PaperTradingLedger`.

Methods (each appends an event, then returns the folded `OrderRecord`):

- `submit(order_id, ticker, side, action, order_type, requested_quantity, limit_price=None, *, at=None) -> OrderRecord`
- `record_fill(order_id, quantity, price, *, at=None) -> OrderRecord`
- `reject(order_id, reason="", *, at=None) -> OrderRecord`
- `cancel(order_id, reason="", *, at=None) -> OrderRecord`
- `expire(order_id, reason="", *, at=None) -> OrderRecord`

Queries (fold the whole ledger):

- `get(order_id) -> OrderRecord | None`
- `open_orders() -> list[OrderRecord]` — records in non-terminal states
- `reconcile_timeouts(ttl_seconds, *, now=None) -> list[OrderRecord]` — appends
  an `expired` event for every open order whose `created_at` is older than
  `ttl_seconds`; returns the newly expired records. `now`/`at` parameters are
  injectable for deterministic tests.

### `src/config.py`

Add one field to `TradingConfig`:

```python
order_ttl_seconds: int = 300  # working order timeout for reconcile passes
```

### `src/strategies/weather.py`

`WeatherTradingStrategy.__init__` gains an `OrderLedger` (default
`OrderLedger()`, injectable for tests).

`execute_signal` flow becomes:

1. `submit(order_id=client_order_id, ticker, side, action, order_type="limit",
   requested_quantity=signal.quantity, limit_price=int(signal.entry_price))`.
2. `order = await self.kalshi.place_order(...)`.
3. If `order.get("error")`: `ledger.reject(order_id, reason=str(order))`, log,
   return `{"success": False, ...}` — **no position recorded**.
4. Else derive `(filled_quantity, avg_price)` from the response (the current
   mock returns a full fill; `ExecutionResult` supplies partials when the
   execution model is wired in). `ledger.record_fill(order_id, filled_quantity,
   avg_price)`.
5. Record the position sized to `filled_quantity` (skip if `filled_quantity == 0`).

`run_continuous` calls
`ledger.reconcile_timeouts(trading_config.order_ttl_seconds)` once per loop
iteration so working orders that never fill get expired.

A small helper `_extract_fill(order_response) -> tuple[int, float | None]`
isolates the parsing of the venue/mock response so it can be tested and later
swapped for `ExecutionResult`.

## Data Flow

```
signal --> execute_signal
             |
             v
        ledger.submit  --> append "submitted"  (PENDING)
             |
             v
        kalshi.place_order
          /            \
      error?            ok
        |                |
   ledger.reject    _extract_fill -> ledger.record_fill --> (PARTIALLY_FILLED | FILLED)
   (REJECTED)            |
   no position           v
                    record position sized to filled_quantity

run_continuous loop --> ledger.reconcile_timeouts(ttl) --> open & stale -> EXPIRED
```

## Error Handling

- Invalid transitions and unknown-order operations raise `OrderLedgerError`.
- Over-fill (cumulative filled > requested) raises `OrderLedgerError`.
- Strategy treats a rejected order as a no-op for position state (logs at
  ERROR via the logger added in improvement #2).
- A malformed ledger line surfaces as `OrderLedgerError` on read (matching
  `PaperTradingLedger` behavior).

## Testing — `tests/test_orders.py`

Pure core:
- Valid sequences: submit → fill(full) → FILLED; submit → fill(partial) →
  PARTIALLY_FILLED → fill(rest) → FILLED.
- Every invalid transition raises (fill after REJECTED/FILLED/CANCELLED/EXPIRED;
  reject after FILLED; etc.).
- Partial-fill accumulation and quantity-weighted `average_fill_price`.
- Over-fill raises.

Ledger I/O:
- `reject` / `cancel` / `expire` produce the right terminal state.
- `open_orders` excludes terminal orders.
- `reconcile_timeouts` expires stale open orders and leaves fresh ones
  (deterministic via injected `now`).
- Persistence round-trip: a second `OrderLedger` over the same path reconstructs
  identical state by folding.

Strategy integration (fake `KalshiRestClient`):
- Rejection response → order ends `REJECTED`, no position recorded.
- Partial-fill response → position quantity equals filled quantity, order ends
  `PARTIALLY_FILLED`.

## Verification

The repo gate must pass:

```
.venv/bin/black --check src tests
.venv/bin/flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503
.venv/bin/pytest tests/ -q
node --check web/app.js
```
