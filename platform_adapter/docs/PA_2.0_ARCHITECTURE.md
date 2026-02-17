# PA 2.0 — Architecture & Interface Contracts

## What PA Does (exactly 2 things)

1. **Pull & stream broker FACTS** → `PAOutputStream`  
   Prices, bars, order updates, fills, positions, account values, connection status.

2. **Receive commands from OE** → translate → send to broker  
   Place, cancel, modify, flatten, subscribe, unsubscribe, historical data.

## What PA Does NOT Do

- ❌ No local state cache (StateManager quarantined)
- ❌ No reconciliation logic
- ❌ No strategy / decision-making
- ❌ No derived math (P&L, market value — that's MIC's job)
- ❌ No `time.sleep()` hacks after orders
- ❌ No dead code models

---

## MIC Interface Contracts

### PA Outputs (`pa_outputs.py`)

| Event | Fields (required bold) | When Emitted |
|-------|----------------------|--------------|
| `QuoteEvent` | **symbol**, **timestamp**, bid, ask, bid_size, ask_size, last, last_size, volume | Real-time tick from broker |
| `BarEvent` | **symbol**, **timestamp**, **O**, **H**, **L**, **C**, **volume**, count, wap | Historical data response |
| `OrderUpdateEvent` | **order_id**, **symbol**, **status**, **action**, **quantity**, **order_type**, **filled**, **remaining**, **avg_fill_price**, **timestamp**, limit_price, stop_price | Order status change |
| `FillEvent` | **order_id**, **exec_id**, **symbol**, **side**, **shares**, **price**, **timestamp**, commission | Execution report |
| `PositionEvent` | **symbol**, **quantity**, **avg_cost**, **account**, sec_type, exchange, currency | Position snapshot/update |
| `AccountValueEvent` | **key**, **value**, **currency**, **account** | Account value update |
| `ConnectionEvent` | **status**, message | Connect/disconnect/error |

All events are `frozen=True` dataclasses (immutable broker facts).

### PA Inputs (`pa_inputs.py`)

| Command | Fields (required bold) | Validation |
|---------|----------------------|------------|
| `PlaceOrderCommand` | **symbol**, **action**, **quantity**, order_type, limit_price, stop_price, sec_type, exchange, currency, tif, outside_rth | action ∈ {BUY,SELL}, qty > 0, LMT→limit_price, STP→stop_price |
| `CancelOrderCommand` | **order_id** | — |
| `ModifyOrderCommand` | **order_id**, quantity, limit_price, stop_price | At least one field to change, qty > 0 |
| `FlattenCommand` | **symbol**, sec_type, exchange, currency | — |
| `SubscribeMarketDataCommand` | **symbol**, sec_type, exchange, currency, snapshot | — |
| `UnsubscribeMarketDataCommand` | **symbol** | — |
| `HistoricalDataCommand` | **symbol**, duration, bar_size, what_to_show, use_rth, end_datetime, sec_type, exchange, currency | — |

All commands are `frozen=True` with `__post_init__` validation.

---

## Data Flow

```
                    ┌─────────────┐
   OE/Strategy ──→  │  PA 2.0     │ ──→ PAOutputStream
   (commands)       │  thin pipe  │      (broker facts)
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │  IB Gateway │
                    └─────────────┘
```

**Left side (inputs):** OE sends `PlaceOrderCommand`, `CancelOrderCommand`, etc.  
**Right side (outputs):** PA emits `QuoteEvent`, `FillEvent`, `PositionEvent`, etc.  
**PA is the bridge.** Zero logic. Pure translation.

---

## File Structure (PA 2.0)

```
platform_adapter/
├── main.py                          # PA 2.0 facade (thin pipe)
├── src/platform_adapter/
│   ├── interfaces/                  # MIC contracts (NEW)
│   │   ├── __init__.py
│   │   ├── pa_outputs.py            # Output events + PAOutputStream
│   │   └── pa_inputs.py             # Input commands + PAInputStream protocol
│   ├── core/
│   │   └── connection_manager.py    # TCP connection to IB (unchanged)
│   ├── adapters/
│   │   ├── market_data_adapter.py   # Market data streaming (unchanged)
│   │   ├── order_execution_adapter.py # Order lifecycle (unchanged)
│   │   └── account_manager.py       # Account/positions (unchanged)
│   ├── models/
│   │   ├── contract.py              # Contract DTO (unchanged)
│   │   ├── order.py                 # Order DTO (unchanged)
│   │   └── position.py              # Position DTO (cleaned: stubs removed)
│   ├── utils/
│   │   ├── rate_limiter.py          # Token bucket (unchanged)
│   │   └── logger.py                # Loguru setup (unchanged)
│   ├── config/
│   │   └── settings.py              # YAML config (unchanged)
│   └── _quarantine/                 # Removed from core (kept for reference)
│       ├── state_manager.py         # Local cache + reconciliation
│       ├── account_model.py         # Dead code AccountValue duplicate
│       └── main_v1.py               # Old PA 1.0 facade
└── tests/
    ├── test_models.py               # Model unit tests
    ├── test_utils.py                # Utility tests
    ├── test_interfaces.py           # MIC contract tests (NEW)
    └── test_integration_connection.py # Integration tests
```

---

## What Changed (PA 1.0 → PA 2.0)

| Component | PA 1.0 | PA 2.0 |
|-----------|--------|--------|
| `main.py` | 587 lines, StateManager wiring, `time.sleep()`, reconciliation | ~380 lines, thin pipe, command handlers, stream wiring |
| `StateManager` | 497 lines in `core/` | Quarantined to `_quarantine/` |
| `Position.market_value` | Stub returning `None` | Removed (MIC's job) |
| `Position.unrealized_pnl` | Stub returning `None` | Removed (MIC's job) |
| `models/account.py` | Dead code duplicate | Quarantined |
| Interface contracts | None | `interfaces/pa_outputs.py` + `pa_inputs.py` |
| `PAOutputStream` | N/A | Event bus for downstream consumers |
| `PAInputStream` | N/A | Protocol for OE commands |
