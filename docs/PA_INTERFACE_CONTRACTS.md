# PA Interface Contracts

**Author:** Juan (Platform Adapter team)  
**Audience:** Jake (Normalizer / Dispatcher), Pete (oversight)  
**Date:** January 2026  
**Version:** r2  
**Source files:** `platform_adapter/src/platform_adapter/interfaces/pa_outputs.py`, `pa_inputs.py`  

---

## Purpose

This document defines the **exact data shapes** that PA emits (outputs) and accepts (inputs). These are the contracts between PA and the rest of the system:

- **Jake's Normalizer** consumes PA outputs → needs to know every field PA emits
- **Jake's Dispatcher** produces PA inputs → needs to know every command PA accepts

PA is a thin pipe. It doesn't derive, aggregate, or transform. Every output event is an **immutable broker fact**. Every input command is a **validated instruction** that PA translates to an IB API call.

---

## Table of Contents

**Part 1 — Outputs (PA → Normalizer)**
1. [QuoteEvent](#1-quoteevent)
2. [BarEvent](#2-barevent)
3. [OrderUpdateEvent](#3-orderupdateevent)
4. [FillEvent](#4-fillevent)
5. [PositionEvent](#5-positionevent)
6. [AccountValueEvent](#6-accountvalueevent)
7. [ConnectionEvent](#7-connectionevent)
8. [KillStateEvent](#8-killstateevent) *(r2)*
9. [FailsafeStageEvent](#9-failsafestageevent) *(r2)*
10. [PacingStateEvent](#10-pacingstateevent) *(r2)*
11. [ReconciliationReportEvent](#11-reconciliationreportevent) *(r2)*

**Part 2 — Inputs (Dispatcher → PA)**
12. [PlaceOrderCommand](#12-placeordercommand)
13. [CancelOrderCommand](#13-cancelordercommand)
14. [ModifyOrderCommand](#14-modifyordercommand)
15. [FlattenCommand](#15-flattencommand)
16. [SubscribeMarketDataCommand](#16-subscribemarketdatacommand)
17. [UnsubscribeMarketDataCommand](#17-unsubscribemarketdatacommand)
18. [HistoricalDataCommand](#18-historicaldatacommand)
19. [SoftKillCommand](#19-softkillcommand) *(r2)*
20. [HardKillCommand](#20-hardkillcommand) *(r2)*
21. [ResumeNormalCommand](#21-resumenormalcommand) *(r2)*
22. [SetLockoutCommand](#22-setlockoutcommand) *(r2)*
23. [HeartbeatCommand](#23-heartbeatcommand) *(r2)*
24. [ReconcileCommand](#24-reconcilecommand) *(r2)*
25. [SwitchModeCommand](#25-switchmodecommand) *(r2)*

**Part 3 — Stream Architecture**
26. [PAOutputStream (how to consume events)](#26-paoutputstream)
27. [PAInputStream (how to send commands)](#27-painputstream)

---

# Part 1 — Output Events (PA → Downstream)

All output events are **frozen dataclasses** (immutable). PA emits them and never modifies them. Every event represents a broker fact — something IB told PA.

---

## 1. QuoteEvent

Real-time quote snapshot from broker. Emitted when `reqMktData` delivers tick updates.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | `str` | ✅ | Instrument symbol (e.g. `"AAPL"`, `"ES"`) |
| `timestamp` | `datetime` | ✅ | When broker emitted this tick |
| `bid` | `float \| None` | | Best bid price |
| `ask` | `float \| None` | | Best ask price |
| `bid_size` | `int \| None` | | Bid depth (number of contracts/shares) |
| `ask_size` | `int \| None` | | Ask depth |
| `last` | `float \| None` | | Last trade price |
| `last_size` | `int \| None` | | Last trade size |
| `volume` | `int \| None` | | Session cumulative volume |

**Notes:**
- Not every field is populated on every tick — IB sends partial updates.
- `bid`/`ask` may be `None` for instruments without a book (e.g., some indices).
- `volume` is cumulative for the session, not per-tick.

---

## 2. BarEvent

OHLCV bar from broker — either historical or real-time 5-second bars.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | `str` | ✅ | Instrument symbol |
| `timestamp` | `datetime` | ✅ | Bar **open** time (not close) |
| `open` | `float` | ✅ | Open price |
| `high` | `float` | ✅ | High price |
| `low` | `float` | ✅ | Low price |
| `close` | `float` | ✅ | Close price |
| `volume` | `int` | ✅ | Volume in bar |
| `count` | `int` | | Trade count in bar (0 if unavailable) |
| `wap` | `float` | | Weighted average price (0.0 if unavailable) |

**Notes:**
- `timestamp` is bar **open** time — IB convention.
- `count` = 0 for some data types (e.g., MIDPOINT).
- `wap` = 0.0 when IB doesn't provide it.
- Same event type for historical bars (`reqHistoricalData`) and real-time 5s bars (`reqRealTimeBars`).

---

## 3. OrderUpdateEvent

Order status change from broker. Emitted whenever an order's status changes.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `order_id` | `int` | ✅ | PA-assigned order ID |
| `symbol` | `str` | ✅ | Instrument symbol |
| `status` | `str` | ✅ | Current status (see values below) |
| `action` | `str` | ✅ | `"BUY"` or `"SELL"` |
| `quantity` | `int` | ✅ | Total order quantity |
| `order_type` | `str` | ✅ | `"MKT"`, `"LMT"`, `"STP"`, `"STP LMT"` |
| `filled` | `int` | ✅ | Shares/contracts filled so far |
| `remaining` | `int` | ✅ | Shares/contracts remaining |
| `avg_fill_price` | `float` | ✅ | Average fill price (0.0 if no fills yet) |
| `timestamp` | `datetime` | ✅ | When this update was received |
| `limit_price` | `float \| None` | | Limit price (if LMT or STP LMT) |
| `stop_price` | `float \| None` | | Stop price (if STP or STP LMT) |

**Status values (`OrderStatusValue` enum):**

| Value | Meaning |
|-------|---------|
| `PendingSubmit` | Order sent, awaiting broker acknowledgment |
| `PendingCancel` | Cancel sent, awaiting confirmation |
| `PreSubmitted` | Order accepted by IB, not yet at exchange |
| `Submitted` | Order live at exchange |
| `Filled` | Completely filled |
| `Cancelled` | Successfully cancelled |
| `Inactive` | Rejected or expired |
| `ApiCancelled` | Cancelled by API (not user action) |

---

## 4. FillEvent

Individual execution/fill report from broker. One order can generate multiple `FillEvent`s (partial fills).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `order_id` | `int` | ✅ | PA order ID this fill belongs to |
| `exec_id` | `str` | ✅ | Broker execution ID (globally unique) |
| `symbol` | `str` | ✅ | Instrument symbol |
| `side` | `str` | ✅ | `"BOT"` (bought) or `"SLD"` (sold) |
| `shares` | `int` | ✅ | Shares/contracts in this fill |
| `price` | `float` | ✅ | Execution price |
| `timestamp` | `datetime` | ✅ | Execution timestamp |
| `commission` | `float` | | Commission charged (0.0 if unknown yet) |

**Notes:**
- `side` uses IB convention: `"BOT"` not `"BUY"`, `"SLD"` not `"SELL"`.
- `commission` may be 0.0 initially — IB sometimes sends commission in a separate `commissionReport` callback shortly after the fill.
- `exec_id` is unique across all fills — use it to deduplicate.

---

## 5. PositionEvent

Position snapshot from broker. Emitted when positions change or on initial subscription.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | `str` | ✅ | Instrument symbol |
| `quantity` | `int` | ✅ | Signed quantity: `+` long, `−` short, `0` flat |
| `avg_cost` | `float` | ✅ | Average cost per unit |
| `account` | `str` | ✅ | Broker account ID |
| `sec_type` | `str` | | Security type (default `"STK"`) |
| `exchange` | `str` | | Exchange (default `"SMART"`) |
| `currency` | `str` | | Currency code (default `"USD"`) |

**Notes:**
- `quantity` is signed: positive = long, negative = short, zero = flat.
- `avg_cost` is total cost per unit (includes commission for stocks).
- Emitted on subscription start (initial snapshot) and on every change.

---

## 6. AccountValueEvent

Account value update from broker (balances, margin, equity, etc.).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | `str` | ✅ | Value key (see common keys below) |
| `value` | `str` | ✅ | Value as string (broker sends strings) |
| `currency` | `str` | ✅ | Currency code (e.g. `"USD"`, `"BASE"`) |
| `account` | `str` | ✅ | Broker account ID |

**Common keys:**

| Key | Description |
|-----|-------------|
| `NetLiquidation` | Net liquidation value |
| `TotalCashValue` | Total cash balance |
| `BuyingPower` | Available buying power |
| `GrossPositionValue` | Total position value |
| `InitMarginReq` | Current initial margin requirement |
| `MaintMarginReq` | Current maintenance margin requirement |
| `AvailableFunds` | Funds available for new trades |
| `ExcessLiquidity` | Excess liquidity (cushion before margin call) |
| `Cushion` | Margin cushion as percentage |
| `UnrealizedPnL` | Unrealized P&L |
| `RealizedPnL` | Realized P&L |

**Notes:**
- `value` is always a string — downstream must parse to float/int as needed.
- IB sends many more keys than listed; these are the most useful.

---

## 7. ConnectionEvent

Connection lifecycle event. Emitted on connect, disconnect, reconnect, error.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | `ConnectionStatus` | ✅ | Current connection state |
| `message` | `str` | | Human-readable description |

**ConnectionStatus values:**

| Value | Meaning |
|-------|---------|
| `connected` | Successfully connected to IB |
| `disconnected` | Lost connection |
| `reconnecting` | Attempting to reconnect |
| `error` | Connection error (see message) |

---

## 8. KillStateEvent *(r2)*

Kill state transition event. Emitted whenever the kill state machine changes state.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `from_state` | `str` | ✅ | Previous state (`"NORMAL"`, `"SOFT_KILL"`, `"HARD_KILL"`, `"LOCKOUT"`) |
| `to_state` | `str` | ✅ | New state |
| `reason` | `str` | ✅ | Why the transition happened |
| `source` | `str` | ✅ | Who triggered it: `"exec"`, `"failsafe"`, `"human"`, `"system"` |
| `timestamp` | `datetime` | ✅ | When transition occurred |

---

## 9. FailsafeStageEvent *(r2)*

Failsafe heartbeat monitor stage change. Emitted when the dead-man's-switch escalates.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `stage` | `int` | ✅ | `0`=NORMAL, `1`=WARN, `2`=FREEZE, `3`=FLATTEN |
| `seconds_since_heartbeat` | `float` | ✅ | Seconds since last heartbeat from Exec |
| `message` | `str` | ✅ | Human-readable stage description |
| `timestamp` | `datetime` | ✅ | When stage changed |

**Stage escalation:**

| Stage | Seconds | Behavior |
|-------|---------|----------|
| 0 — NORMAL | 0–30 | Everything OK |
| 1 — WARN | 30+ | Warning logged, event emitted |
| 2 — FREEZE | 60+ | New orders blocked |
| 3 — FLATTEN | 120+ | Cancel all orders + flatten all positions |

---

## 10. PacingStateEvent *(r2)*

Pacing recovery state change. Emitted when PA enters or exits pacing recovery mode.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `in_recovery` | `bool` | ✅ | `True` = in recovery, `False` = recovered |
| `error_code` | `int` | ✅ | IB error code that triggered recovery (0 if ending) |
| `cooldown_sec` | `float` | ✅ | Current cooldown period in seconds |
| `violation_count` | `int` | ✅ | Consecutive pacing violations |
| `message` | `str` | ✅ | Human-readable description |
| `timestamp` | `datetime` | ✅ | When state changed |

---

## 11. ReconciliationReportEvent *(r2)*

Reconciliation completed event. Emitted after PA compares local state vs broker truth.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `bool` | ✅ | Whether reconciliation completed without errors |
| `duration_sec` | `float` | ✅ | How long reconciliation took |
| `positions_broker` | `int` | ✅ | Number of positions from broker |
| `positions_local` | `int` | ✅ | Number of positions in local state |
| `orders_broker` | `int` | ✅ | Number of open orders from broker |
| `orders_local` | `int` | ✅ | Number of orders in local state |
| `orders_orphaned` | `int` | ✅ | Orders in local state not found at broker |
| `positions_mismatches` | `int` | ✅ | Position count/price mismatches |
| `actions_taken` | `List[str]` | ✅ | List of actions taken (e.g. `"synced position ES"`) |
| `message` | `str` | ✅ | Summary message |
| `timestamp` | `datetime` | ✅ | When reconciliation completed |

---

# Part 2 — Input Commands (Upstream → PA)

All input commands are **frozen dataclasses** with `__post_init__` validation. PA validates the command shape, then translates to IB API calls. Results come back asynchronously through output events.

**Rule:** Only the Dispatcher sends commands to PA. No other component touches PA directly.

---

## 12. PlaceOrderCommand

Place a new order with the broker.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `symbol` | `str` | ✅ | | Instrument symbol |
| `action` | `str` | ✅ | | `"BUY"` or `"SELL"` |
| `quantity` | `int` | ✅ | | Number of shares/contracts (must be > 0) |
| `order_type` | `str` | | `"MKT"` | `"MKT"`, `"LMT"`, `"STP"`, `"STP LMT"` |
| `limit_price` | `float \| None` | | `None` | Required for `"LMT"` and `"STP LMT"` |
| `stop_price` | `float \| None` | | `None` | Required for `"STP"` and `"STP LMT"` |
| `sec_type` | `str` | | `"STK"` | Security type |
| `exchange` | `str` | | `"SMART"` | Exchange |
| `currency` | `str` | | `"USD"` | Currency |
| `tif` | `str` | | `"DAY"` | Time-in-force |
| `outside_rth` | `bool` | | `False` | Allow outside regular trading hours |

**Validation rules:**
- `action` must be `"BUY"` or `"SELL"`
- `quantity` must be > 0
- `"LMT"` / `"STP LMT"` requires `limit_price`
- `"STP"` / `"STP LMT"` requires `stop_price`

**Returns:** `int` — the PA order ID assigned to this order

**Result events:** `OrderUpdateEvent` (status changes), `FillEvent` (executions)

---

## 13. CancelOrderCommand

Cancel an existing order.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `order_id` | `int` | ✅ | PA order ID to cancel |

**Returns:** `bool` — `True` if cancel request was sent

**Result events:** `OrderUpdateEvent` with status `Cancelled` or `PendingCancel`

---

## 14. ModifyOrderCommand

Modify an existing order. At least one of `quantity`, `limit_price`, or `stop_price` must be provided.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `order_id` | `int` | ✅ | | PA order ID to modify |
| `quantity` | `int \| None` | | `None` | New quantity (must be > 0 if provided) |
| `limit_price` | `float \| None` | | `None` | New limit price |
| `stop_price` | `float \| None` | | `None` | New stop price |

**Validation rules:**
- At least one field must be non-None
- `quantity` must be > 0 if provided

**Returns:** `bool` — `True` if modify request was sent

**Result events:** `OrderUpdateEvent` with updated fields

---

## 15. FlattenCommand

Close all positions for a symbol by sending a market order in the opposite direction.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `symbol` | `str` | ✅ | | Instrument to flatten |
| `sec_type` | `str` | | `"STK"` | Security type |
| `exchange` | `str` | | `"SMART"` | Exchange |
| `currency` | `str` | | `"USD"` | Currency |

**Returns:** `int | None` — order ID of the closing order, or `None` if already flat

**Result events:** `OrderUpdateEvent`, `FillEvent`, then `PositionEvent` showing flat

---

## 16. SubscribeMarketDataCommand

Subscribe to real-time streaming market data for a symbol.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `symbol` | `str` | ✅ | | Instrument symbol |
| `sec_type` | `str` | | `"STK"` | Security type |
| `exchange` | `str` | | `"SMART"` | Exchange |
| `currency` | `str` | | `"USD"` | Currency |
| `snapshot` | `bool` | | `False` | `True` = one-time snapshot, `False` = streaming |

**Returns:** `int` — request ID for this subscription

**Result events:** Continuous `QuoteEvent` stream until unsubscribed

---

## 17. UnsubscribeMarketDataCommand

Stop streaming market data for a symbol.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | `str` | ✅ | Instrument symbol to unsubscribe |

**Returns:** `None`

---

## 18. HistoricalDataCommand

Request historical bars for a time range.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `symbol` | `str` | ✅ | | Instrument symbol |
| `duration` | `str` | | `"1 D"` | IB duration string (`"1 D"`, `"1 W"`, `"1 M"`, `"1 Y"`) |
| `bar_size` | `str` | | `"1 min"` | IB bar size (see Discovery doc Section 5) |
| `what_to_show` | `str` | | `"TRADES"` | Data type: `"TRADES"`, `"MIDPOINT"`, `"BID"`, `"ASK"` |
| `use_rth` | `bool` | | `True` | `True` = regular hours only, `False` = all hours |
| `end_datetime` | `str` | | `""` | End time (empty = now) |
| `sec_type` | `str` | | `"STK"` | Security type |
| `exchange` | `str` | | `"SMART"` | Exchange |
| `currency` | `str` | | `"USD"` | Currency |

**Returns:** `int` — request ID

**Result events:** Multiple `BarEvent`s (one per bar)

---

## 19. SoftKillCommand *(r2)*

Activate SoftKill — blocks opening/adding positions, allows reducing/closing/cancelling.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `reason` | `str` | | `""` | Why SoftKill is being activated |

**Returns:** `bool`

**Result events:** `KillStateEvent` (NORMAL → SOFT_KILL)

---

## 20. HardKillCommand *(r2)*

Nuclear option — cancel ALL orders, flatten ALL positions, then enter LOCKOUT.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `reason` | `str` | | `""` | Why HardKill is being activated |

**Returns:** `bool`

**Result events:** `KillStateEvent` (any → HARD_KILL → LOCKOUT), plus `OrderUpdateEvent` (cancels) and `FillEvent` (flatten fills)

---

## 21. ResumeNormalCommand *(r2)*

Resume normal operations from SoftKill or Failsafe Freeze.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `reason` | `str` | | `""` | Why resuming |

**Returns:** `bool`

**Result events:** `KillStateEvent` (SOFT_KILL/FREEZE → NORMAL)

**⚠️ Cannot resume from LOCKOUT** — only human reset can clear LOCKOUT.

---

## 22. SetLockoutCommand *(r2)*

Force LOCKOUT — everything blocked until human intervenes.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `reason` | `str` | | `""` | Why lockout is being set |

**Returns:** `bool`

**Result events:** `KillStateEvent` (any → LOCKOUT)

---

## 23. HeartbeatCommand *(r2)*

Exec/Strategy layer sends this periodically to prove it's alive. If PA stops receiving heartbeats, the failsafe escalates through WARN → FREEZE → FLATTEN.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| *(no fields)* | | | Command has no parameters |

**Returns:** `None`

**Expected cadence:** Every 10 seconds (configurable). If PA doesn't receive one within 30 seconds, failsafe Stage 1 (WARN) triggers.

---

## 24. ReconcileCommand *(r2)*

Request a manual reconciliation — PA queries IB for positions and orders, compares with local state, and fixes discrepancies.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| *(no fields)* | | | Command has no parameters |

**Returns:** `None`

**Result events:** `ReconciliationReportEvent` when complete

---

## 25. SwitchModeCommand *(r2)*

Switch between Live and Paper trading mode. PA disconnects from the current session, reconnects on the appropriate port, and runs a full reconciliation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mode` | `str` | ✅ | `"live"` or `"paper"` |

**Validation:** `mode` must be `"live"` or `"paper"`

**Returns:** `bool`

**Result events:** `ConnectionEvent` (disconnect → reconnect), then `ReconciliationReportEvent`

---

# Part 3 — Stream Architecture

## 26. PAOutputStream

The `PAOutputStream` class is PA's event bus. Downstream consumers register callbacks, and PA fires events through them.

### Registration Pattern

Jake — to consume PA events, register callbacks on the stream:

```python
stream = PAOutputStream()

# Register handlers
stream.on_quote(normalizer.handle_quote)       # QuoteEvent → Normalizer
stream.on_bar(normalizer.handle_bar)            # BarEvent → Normalizer
stream.on_order_update(dispatcher.handle_order) # OrderUpdateEvent → Dispatcher
stream.on_fill(dispatcher.handle_fill)          # FillEvent → Dispatcher
stream.on_position(risk.handle_position)        # PositionEvent → Risk Governor
stream.on_account_value(risk.handle_account)    # AccountValueEvent → Risk Governor
stream.on_connection(monitor.handle_conn)       # ConnectionEvent → Observability

# r2 events
stream.on_kill_state(monitor.handle_kill)       # KillStateEvent → Observability
stream.on_failsafe(monitor.handle_failsafe)     # FailsafeStageEvent → Observability
stream.on_pacing(monitor.handle_pacing)         # PacingStateEvent → Observability
stream.on_reconciliation(monitor.handle_recon)  # ReconciliationReportEvent → Observability
```

### Available Registration Methods

| Method | Event Type | Typical Consumer |
|--------|-----------|-----------------|
| `on_quote(callback)` | `QuoteEvent` | Normalizer |
| `on_bar(callback)` | `BarEvent` | Normalizer |
| `on_order_update(callback)` | `OrderUpdateEvent` | Dispatcher / Observability |
| `on_fill(callback)` | `FillEvent` | Dispatcher / Observability |
| `on_position(callback)` | `PositionEvent` | Risk Governor |
| `on_account_value(callback)` | `AccountValueEvent` | Risk Governor |
| `on_connection(callback)` | `ConnectionEvent` | Monitor |
| `on_kill_state(callback)` | `KillStateEvent` | Monitor |
| `on_failsafe(callback)` | `FailsafeStageEvent` | Monitor |
| `on_pacing(callback)` | `PacingStateEvent` | Monitor |
| `on_reconciliation(callback)` | `ReconciliationReportEvent` | Monitor |

### Emit Behavior
- PA calls `emit_*` methods internally — consumers never call these.
- Each listener callback is wrapped in `try/except` — **PA never crashes because a downstream listener throws**.
- Multiple listeners per event type are supported.

---

## 27. PAInputStream

The `PAInputStream` is a **Protocol** (interface) that PA implements. The Dispatcher calls these methods to send commands to PA.

### Available Command Methods

| Method | Command Type | Returns | Result Events |
|--------|-------------|---------|---------------|
| `handle_place_order(cmd)` | `PlaceOrderCommand` | `int` (order_id) | `OrderUpdateEvent`, `FillEvent` |
| `handle_cancel_order(cmd)` | `CancelOrderCommand` | `bool` | `OrderUpdateEvent` |
| `handle_modify_order(cmd)` | `ModifyOrderCommand` | `bool` | `OrderUpdateEvent` |
| `handle_flatten(cmd)` | `FlattenCommand` | `int \| None` | `OrderUpdateEvent`, `FillEvent`, `PositionEvent` |
| `handle_subscribe_market_data(cmd)` | `SubscribeMarketDataCommand` | `int` (req_id) | `QuoteEvent` stream |
| `handle_unsubscribe_market_data(cmd)` | `UnsubscribeMarketDataCommand` | `None` | — |
| `handle_historical_data(cmd)` | `HistoricalDataCommand` | `int` (req_id) | `BarEvent` batch |
| `set_softkill(cmd)` | `SoftKillCommand` | `bool` | `KillStateEvent` |
| `hardkill(cmd)` | `HardKillCommand` | `bool` | `KillStateEvent`, `OrderUpdateEvent`, `FillEvent` |
| `resume_normal(cmd)` | `ResumeNormalCommand` | `bool` | `KillStateEvent` |
| `set_lockout(cmd)` | `SetLockoutCommand` | `bool` | `KillStateEvent` |
| `heartbeat_from_exec(cmd)` | `HeartbeatCommand` | `None` | — |
| `reconcile_state(cmd)` | `ReconcileCommand` | `None` | `ReconciliationReportEvent` |
| `switch_mode(cmd)` | `SwitchModeCommand` | `bool` | `ConnectionEvent`, `ReconciliationReportEvent` |

### Fire-and-Forget Pattern
- Every method returns **immediately** (synchronous return value is just an ack/id).
- Actual results come back **asynchronously** through `PAOutputStream` events.
- The Dispatcher should correlate commands with result events using `order_id` or `req_id`.

---

## Quick Reference: Data Flow

```
┌──────────────┐     Commands (14 types)     ┌────────────┐
│  Dispatcher   │ ──────────────────────────► │     PA     │
│  (Jake)       │                             │   (Juan)   │
└──────────────┘                              │            │
                                              │  thin pipe │
┌──────────────┐     Events (11 types)        │  to IB     │
│  Normalizer   │ ◄────────────────────────── │            │
│  (Jake)       │                             └────────────┘
└──────────────┘                                    ▲ ▼
                                              ┌────────────┐
                                              │  IB Gateway │
                                              │  (broker)   │
                                              └────────────┘
```

**14 commands in → PA → IB API calls**  
**IB callbacks → PA → 11 event types out**

---

*Source code: `platform_adapter/src/platform_adapter/interfaces/pa_outputs.py` (456 lines) and `pa_inputs.py` (334 lines). All types are importable from `platform_adapter.interfaces`.*
