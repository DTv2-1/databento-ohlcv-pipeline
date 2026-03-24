iteration: 2026-03-03.7  
audience: JK / Pete / Juan  
purpose: define PAr2 inbound commands + outbound events (market + execution truth)  
notes: JSON examples; Juan may implement as dataclasses/pydantic; exact IB fields map later.

___

Juan — this document defines the exact input/output message shapes for PAr2.  
You will implement PAr2 so it accepts PACommand objects from Dispatcher and emits PAEvent objects (market bars + execution truth events).  
Please treat this as the contract: if you need to change fields based on IB reality, propose the changes and we will update the contract together.  
Deliverable is a PAr2 implementation that matches these message shapes, plus a short note listing any deviations required by IB.


___

**SniperZero v1 Locked Runtime Flow (LAW)**  
`PAr2` → `Normalizer` → `Aggregator` → `MFE` → `Pattern` → `C2` → `Policy` → `RiskGov` → `Dispatcher` → `PAr2`  
`JournalDB` is a listener/recorder (append-only history). It is not in the decision flow and must not be a runtime dependency for live decisions.

**PAr2 Implementation Dependencies (LAW)**  
PAr2 must implement against our contracts: **PipelineContext v0** (runtime package), **PA Wire Contract v0** (PACommand/PAEvent shapes), and the **JournalDB listening model v0** (what events must be emitted for durable recording). These are required for correct downstream behavior and replay/debug; implementers must propose changes to the contracts before deviating.

___

## 0) Law (non-negotiable)

- Commands are instructions, not truth.
- PAr2 appends execution truth (events + reconciliation snapshots) into PipelineContext.exec.
- Downstream modules act on truth, not on “we sent a command.”

## 1) Inbound to PAr2 (from Dispatcher): PACommand

### 1.1 Common envelope

PACommand:
- command_id: string (unique)
- ts_utc_ms: int
- trading_mode: "LIVE" | "PAPER"
- symbol: string
- channel: "order_place" | "order_modify" | "order_cancel" | "misc"
- priority: "EXIT" | "NORMAL"
- action: "PLACE" | "MODIFY" | "CANCEL"
- intent_type: "OPEN" | "ADD" | "CLOSE" | "FLATTEN" | "PLACE_STOP" | "MODIFY_STOP" | "SOFTKILL" | "HARDKILL"
- constraints:
    - tighten_only: bool (true/false, never 1/0)
- order_spec: object (broker-mapped fields allowed)

### 1.2 Example: OPEN (market)

```json
{
  "command_id": "cmd_000123",
  "ts_utc_ms": 1767474200123,
  "trading_mode": "PAPER",
  "symbol": "ES",
  "channel": "order_place",
  "priority": "NORMAL",
  "action": "PLACE",
  "intent_type": "OPEN",
  "constraints": {"tighten_only": false},
  "order_spec": {
    "side": "BUY",
    "order_kind": "MKT",
    "qty": 1
  }
}
```

### 1.3 Example: CLOSE (priority exit)

```json
{
  "command_id": "cmd_000124",
  "ts_utc_ms": 1767474200456,
  "trading_mode": "PAPER",
  "symbol": "ES",
  "channel": "order_place",
  "priority": "EXIT",
  "action": "PLACE",
  "intent_type": "CLOSE",
  "constraints": {"tighten_only": false},
  "order_spec": {
    "side": "SELL",
    "order_kind": "MKT",
    "qty": 1
  }
}
```

### 1.4 Example: MODIFY_STOP (tighten-only)

```json
{
  "command_id": "cmd_000125",
  "ts_utc_ms": 1767474200789,
  "trading_mode": "PAPER",
  "symbol": "ES",
  "channel": "order_modify",
  "priority": "NORMAL",
  "action": "MODIFY",
  "intent_type": "MODIFY_STOP",
  "constraints": {"tighten_only": true},
  "order_spec": {
    "broker_order_id": 987654,
    "new_stop_price": 5123.25
  }
}
```

### 1.5 Example: HARDKILL

Rule:
HARDKILL must immediately trigger FAILSAFE_STAGE_CHANGED and HARDKILL_EXECUTED events.

```json
{
  "command_id": "cmd_000126",
  "ts_utc_ms": 1767474200999,
  "trading_mode": "PAPER",
  "symbol": "ALL",
  "channel": "misc",
  "priority": "EXIT",
  "action": "PLACE",
  "intent_type": "HARDKILL",
  "constraints": {"tighten_only": false},
  "order_spec": {
    "reason": "OPERATOR_PANIC"
  }
}
```

## 2) Outbound from PAr2: PAEvent (execution truth + market feed)

PAEvent objects emitted here are the same objects recorded in
PipelineContext.exec.events.pa_events and JournalDB.

### 2.1 Common envelope

PAEvent:
- event_id: string
- ts_utc_ms: int
- trading_mode: "LIVE" | "PAPER"
- type: string (see categories below)
- symbol: string (optional for account/global events)
- payload: object (type-specific)
- session_id
- cycle_id

### 2.2 Market data events (into Normalizer)

Type: MARKET_BAR (base timeframe feed only)  
> Note:
> These represent the configured base feed (e.g., 1s or 15s).
> Aggregator constructs higher-timeframe bars from this feed.

Payload:
- tf: "1s" | "15s" | etc
- bar_state: "UPDATE" | "CLOSE"
- ohlcv: {o,h,l,c,v}
- source: "TRADES" | "MID" | "BID" | "ASK" (if known)

Example:  
```json
{
  "event_id": "evt_100001",
  "ts_utc_ms": 1767474200123,
  "trading_mode": "PAPER",
  "type": "MARKET_BAR",
  "symbol": "ES",
  "payload": {
    "tf": "1s",
    "bar_state": "CLOSE",
    "ohlcv": {"o": 5124.0, "h": 5124.25, "l": 5123.75, "c": 5124.0, "v": 120},
    "source": "TRADES"
  }
}
```

### 2.3 Order lifecycle events (truth into PipelineContext.exec)

LAW: command_id must appear in all lifecycle events derived from a PACommand.
This allows Dispatcher and JournalDB to correlate command → broker order → fills.

Types:
- ORDER_SUBMITTED
- ORDER_ACCEPTED
- ORDER_REJECTED
- ORDER_STATUS
- FILL

Example: ORDER_REJECTED  
```json
{
  "event_id": "evt_200010",
  "ts_utc_ms": 1767474200457,
  "trading_mode": "PAPER",
  "type": "ORDER_REJECTED",
  "symbol": "ES",
  "payload": {
    "command_id": "cmd_000124",
    "broker_order_id": null,
    "ib_error_code": 321,
    "message": "Read-only API mode"
  }
}
```

Example: FILL  
```json
{
  "event_id": "evt_200020",
  "ts_utc_ms": 1767474200560,
  "trading_mode": "PAPER",
  "type": "FILL",
  "symbol": "ES",
  "payload": {
    "command_id": "cmd_000124",
    "broker_order_id": 987655,
    "side": "SELL",
    "qty": 1,
    "price": 5123.75,
    "fill_ts_utc_ms": 1767474200559
  }
}
```

### 2.4 Position snapshot events (truth)

Type: POSITION_SNAPSHOT  
Payload:
- positions: list of {symbol, qty, avg_price, unrealized_pnl (optional)}

Example:  
```json
{
  "event_id": "evt_300001",
  "ts_utc_ms": 1767474200600,
  "trading_mode": "PAPER",
  "type": "POSITION_SNAPSHOT",
  "payload": {
    "positions": [{"symbol": "ES", "qty": 0, "avg_price": 0}]
  }
}
```

### 2.5 Reconciliation report (truth)

Type: RECONCILIATION_REPORT  
Payload:
- report_id
- positions_snapshot
- open_orders_snapshot
- account_snapshot (optional)
- actions_taken (config: adopted/canceled, default to cancel)
     **Specific Values:**
	   - **Unknown open orders → CANCEL**
	   - **Unexpected open position → CLOSE, forced flatten + lockout**
- notes (optional)

### 2.6 Pacing + recovery events

Types:
- PACING_WARNING
- PACING_COOLDOWN_STARTED
- PACING_COOLDOWN_ENDED

Payload includes:
- channel
- current_rate_estimate
- cooldown_until_ts (if applicable)
- ib_error_code/message (if applicable)

### 2.7 Kill + failsafe state events

Types:
- SOFTKILL_ENABLED / SOFTKILL_DISABLED
- FAILSAFE_STAGE_CHANGED (NORMAL/FREEZE/AUTOEXIT)
- HARDKILL_EXECUTED
- LOCKOUT_ENABLED / LOCKOUT_DISABLED

Rule:
When FAILSAFE_STAGE_CHANGED transitions to AUTOEXIT, PAr2 must also emit LOCKOUT_ENABLED
(unless failsafe.autoexit_implies_lockout is explicitly false; default true).

## 3) Routing rules (who consumes what)

- Normalizer consumes `MARKET_*` events (and may log selected execution events).
- Dispatcher consumes execution truth events (`ORDER_*`, `FILL`, `POSITION_SNAPSHOT`, `PACING_*`, `KILL_*`, `RECONCILIATION_REPORT`).
- JournalDB records all PAEvents (append-only), with optional downsampling for `MARKET_*` depending on storage policy.

## 4) Priority EXIT guarantee (must be enforced)

- PAr2 must service priority="EXIT" commands before NORMAL commands.
- EXIT commands bypass stop-modify throttling.
- Under pacing recovery, EXIT remains allowed; non-critical commands may be delayed.

## 5) Versioning

- pa_wire_contract_version: "PAWire.v0"
- Backward compatible additions only in v0 (new optional fields).
- Breaking changes require v1 and explicit operator approval.




