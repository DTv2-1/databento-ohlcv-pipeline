# IB TWS API — Discovery Document

**Author:** Juan (Platform Adapter team)  
**Audience:** Jake (Normalizer / Dispatcher), Pete (oversight)  
**Date:** January 2026  
**Version:** 1.0  

---

## Purpose

This document describes **exactly what the Interactive Brokers TWS API can and cannot do** — native timeframes, available commands, rate limits, data shapes, emergency mechanisms, and known gotchas. Jake needs this to build the Normalizer (flattening raw IB data into our internal schema) and the Dispatcher (sending commands back through PA to IB). Pete needs this for acceptance criteria.

PA is a **thin pipe** — it wraps these IB capabilities, adds rate-limiting/pacing recovery, and exposes them through typed interface contracts. PA does not add, derive, or transform data. What IB sends, PA relays.

---

## Table of Contents

1. [Connection & Authentication](#1-connection--authentication)
2. [Market Data — Real-Time](#2-market-data--real-time)
3. [Market Data — Historical Bars](#3-market-data--historical-bars)
4. [Market Data — Tick-by-Tick](#4-market-data--tick-by-tick)
5. [Native Bar Sizes & Timeframes](#5-native-bar-sizes--timeframes)
6. [What the Aggregator Must Handle](#6-what-the-aggregator-must-handle)
7. [Order Types & Commands](#7-order-types--commands)
8. [Account & Position Queries](#8-account--position-queries)
9. [Rate Limits & Pacing Rules](#9-rate-limits--pacing-rules)
10. [Emergency Mechanisms](#10-emergency-mechanisms)
11. [Known Limitations & Gotchas](#11-known-limitations--gotchas)
12. [Error Codes Reference](#12-error-codes-reference)
13. [Raw Data Shapes from IB](#13-raw-data-shapes-from-ib)
14. [Contract Types & Instruments](#14-contract-types--instruments)
15. [Summary: CAN vs CANNOT](#15-summary-can-vs-cannot)

---

## 1. Connection & Authentication

### How It Works
- IB uses a **TCP socket protocol** — PA connects to TWS or IB Gateway running on the same machine (or network).
- **No REST API, no WebSocket** — it's a raw socket with IB's proprietary message format.
- The Python `ibapi` library abstracts the socket protocol into a request/callback pattern.

### Ports

| Mode | TWS Port | Gateway Port |
|------|----------|-------------|
| **Live Trading** | 7496 | 4001 |
| **Paper Trading** | 7497 | 4002 |

### Authentication
- **Manual login required** — a human must type credentials into TWS or IB Gateway GUI.
- **No headless auth** — there's no API call to authenticate programmatically.
- **2FA** — IB requires 2FA; can be bypassed with "Trusted IPs" or "SLS" device.
- **Auto-restart** — from Gateway v974+ the app can auto-restart daily, but the first login of the week (Sunday) requires manual re-auth.

### Connection Lifecycle
1. PA calls `app.connect(host, port, clientId)`
2. IB sends `nextValidId(orderId)` callback → connection is ready
3. PA must **wait for `nextValidId`** before sending any requests
4. Up to **32 simultaneous API clients** per TWS/Gateway instance (each needs unique `clientId`)
5. **One login per username** at a time (multiple usernames = multiple sessions)

### What PA Does
- Manages connect/disconnect/reconnect lifecycle
- Emits `ConnectionEvent` on status changes
- Tracks connection state internally
- Auto-reconnects on drop with backoff

### ⚠️ Cannot Do
- ❌ Programmatic login (always needs human for initial auth)
- ❌ Headless deployment without GUI (Gateway needs X11 or VNC at minimum)
- ❌ Keep session alive indefinitely (IB forces daily restart window)

---

## 2. Market Data — Real-Time

### Streaming Quotes (`reqMktData`)

**What it provides:**
- Bid price/size, Ask price/size, Last price/size, Volume
- **NOT true tick-by-tick** — IB aggregates into snapshots

**Update frequency:**
- Stocks: snapshots every **250ms** (4 updates/sec)
- Options: snapshots every **100ms** (10 updates/sec)
- These are IB's aggregated snapshots, not raw exchange ticks

**Tick types returned:**
| Tick ID | Field |
|---------|-------|
| 1 | Bid Price |
| 2 | Ask Price |
| 4 | Last Price |
| 0 | Bid Size |
| 3 | Ask Size |
| 5 | Last Size |
| 8 | Volume |
| 9 | Close (previous) |
| 14 | Open |
| 6 | High |
| 7 | Low |

**Subscription limit:**
- Default: **100 market data lines** (each symbol = 1 line)
- Booster packs: +100 lines for ~$30/month each
- Formula: max requests/sec = (market_data_lines / 2)

### Real-Time 5-Second Bars (`reqRealTimeBars`)

**What it provides:**
- OHLCV bars at exactly **5-second intervals**
- Fields: open, high, low, close, volume, wap (weighted avg price), count (trade count)
- `whatToShow`: TRADES, MIDPOINT, BID, ASK

**⚠️ CRITICAL: The ONLY native real-time bar size from IB is 5 seconds.**

There is no `reqRealTimeBars` for 1s, 10s, 15s, 30s, 1min, etc. Only 5 seconds.

**What PA Does:**
- Wraps `reqMktData` → emits `QuoteEvent`
- Wraps `reqRealTimeBars` → emits `BarEvent` (5s bars)

### ⚠️ Cannot Do
- ❌ Native real-time bars at any interval other than 5 seconds
- ❌ True tick-by-tick from `reqMktData` (it's aggregated snapshots)
- ❌ Unlimited simultaneous subscriptions (capped by market data lines)

---

## 3. Market Data — Historical Bars

### `reqHistoricalData`

**What it provides:**
- OHLCV bars for a requested time range and bar size
- Fields: date, open, high, low, close, volume, count, wap
- Can request bars up to months/years back (availability varies by instrument)

**Parameters:**

| Parameter | Description | Example |
|-----------|-------------|---------|
| `endDateTime` | End of the requested period (empty = now) | `"20260115 16:00:00 US/Eastern"` |
| `durationStr` | How far back from end | `"1 D"`, `"1 W"`, `"1 M"`, `"1 Y"` |
| `barSizeSetting` | Bar size | `"1 min"`, `"5 mins"`, `"1 hour"` |
| `whatToShow` | Data type | `"TRADES"`, `"MIDPOINT"`, `"BID"`, `"ASK"` |
| `useRTH` | Regular trading hours only | `1` (RTH) or `0` (all hours) |
| `keepUpToDate` | Live-updating bars | `True` or `False` |

**Duration strings:** `S` (seconds), `D` (days), `W` (weeks), `M` (months), `Y` (years)

**`keepUpToDate=True`** → IB sends updated bars as they form in real-time. This is how you can get streaming bars at any native bar size (not just 5s). The last bar is a partial bar that updates until the interval completes.

**What PA Does:**
- Wraps `reqHistoricalData` → emits `BarEvent` per bar
- Manages pacing rules (see Section 9)

### ⚠️ Cannot Do
- ❌ Request unlimited history (availability depends on instrument and bar size)
- ❌ Avoid pacing limits (60 requests per 10 minutes is hard)
- ❌ Get 1-second bars older than ~1 day (IB restriction)

---

## 4. Market Data — Tick-by-Tick

### `reqTickByTickData`

**What it provides:**
- Individual ticks (trades or quotes), not aggregated
- Types: `Last`, `AllLast`, `BidAsk`, `MidPoint`

| Type | Fields |
|------|--------|
| `Last` | time, price, size, exchange, specialConditions |
| `AllLast` | same as Last but includes off-exchange |
| `BidAsk` | time, bidPrice, askPrice, bidSize, askSize |
| `MidPoint` | time, midPoint |

**This is the highest resolution data IB provides** — individual trade/quote events.

### ⚠️ Cannot Do
- ❌ Get tick-by-tick for all instruments (some don't support it)
- ❌ Get historical tick-by-tick (only real-time)
- ❌ Combine with `reqRealTimeBars` for same instrument simultaneously (IB blocks this)

---

## 5. Native Bar Sizes & Timeframes

### Historical Bar Sizes (from `reqHistoricalData`)

These are the **exact bar sizes IB supports natively**:

| Bar Size | IB String | Max Duration per Request |
|----------|-----------|-------------------------|
| 1 second | `"1 secs"` | 1,800 S (30 min) |
| 5 seconds | `"5 secs"` | 3,600 S (1 hour) |
| 10 seconds | `"10 secs"` | 14,400 S (4 hours) |
| 15 seconds | `"15 secs"` | 14,400 S (4 hours) |
| 30 seconds | `"30 secs"` | 28,800 S (8 hours) |
| 1 minute | `"1 min"` | 1 D |
| 2 minutes | `"2 mins"` | 2 D |
| 3 minutes | `"3 mins"` | 1 W |
| 5 minutes | `"5 mins"` | 1 W |
| 10 minutes | `"10 mins"` | 1 W |
| 15 minutes | `"15 mins"` | 1 W |
| 20 minutes | `"20 mins"` | 1 W |
| 30 minutes | `"30 mins"` | 1 W |
| 1 hour | `"1 hour"` | 1 M |
| 2 hours | `"2 hours"` | 1 M |
| 3 hours | `"3 hours"` | 1 M |
| 4 hours | `"4 hours"` | 1 M |
| 8 hours | `"8 hours"` | 1 M |
| 1 day | `"1 day"` | 1 Y |
| 1 week | `"1 week"` | 1 Y |
| 1 month | `"1 month"` | 1 Y |

### Real-Time Bar Sizes

| Source | Bar Size | Notes |
|--------|----------|-------|
| `reqRealTimeBars` | **5 seconds ONLY** | Dedicated real-time stream |
| `reqHistoricalData` with `keepUpToDate=True` | Any native bar size | Live-updating, last bar is partial |
| `reqMktData` | N/A (raw ticks/snapshots) | Must aggregate yourself |
| `reqTickByTickData` | N/A (individual ticks) | Must aggregate yourself |

---

## 6. What the Aggregator Must Handle

Jake — this is what your Aggregator needs to do. **IB cannot natively produce these timeframes in real-time:**

### Timeframes NOT native to IB (examples)

If the Kitchen needs bars at non-IB intervals (e.g., 7s, 45s, 2.5min, 4min, 7min, etc.), the Aggregator must build them from the smallest available native bars or from tick data.

### Aggregator Strategy Options

| Strategy | Source | Pro | Con |
|----------|--------|-----|-----|
| **Aggregate from 5s bars** | `reqRealTimeBars` → 5s bars → resample to 15s, 30s, 1min, etc. | Simplest, continuous stream | Can only build multiples of 5s |
| **Aggregate from ticks** | `reqTickByTickData` → build any bar size | Maximum flexibility | More complex, higher processing |
| **Use native bars + keepUpToDate** | `reqHistoricalData(keepUpToDate=True)` at desired bar size | IB does the work | Only works for IB's native sizes |
| **Hybrid** | 5s bars for sub-minute, `keepUpToDate` for 1min+ | Best of both | More code |

### Recommended Approach (from meeting)
Per Jake's architecture, the Aggregator sits between the Normalizer and the Kitchen. The existing resampling code (from the data pipeline) can be integrated. PA delivers raw 5s bars or ticks → Normalizer flattens → Aggregator resamples to whatever the Kitchen wants.

---

## 7. Order Types & Commands

### Supported Order Types

| Order Type | IB String | Description | PA Support |
|------------|-----------|-------------|------------|
| Market | `"MKT"` | Execute at market price immediately | ✅ |
| Limit | `"LMT"` | Execute at limit price or better | ✅ |
| Stop | `"STP"` | Triggers market order when stop price hit | ✅ |
| Stop Limit | `"STP LMT"` | Triggers limit order when stop price hit | ✅ |
| Trailing Stop | `"TRAIL"` | Stop follows price by amount/% | ✅ (future) |
| Trailing Stop Limit | `"TRAIL LIMIT"` | Trailing stop that triggers limit | ✅ (future) |
| Market on Close | `"MOC"` | Execute at close auction | ✅ (future) |
| Limit on Close | `"LOC"` | Limit order for close auction | ✅ (future) |
| Market if Touched | `"MIT"` | Like stop but for entry | ✅ (future) |
| Limit if Touched | `"LIT"` | MIT that triggers limit | ✅ (future) |

### Order Actions

| Action | Description |
|--------|-------------|
| `"BUY"` | Buy to open or cover |
| `"SELL"` | Sell to close or short |

### Time in Force

| TIF | Description |
|-----|-------------|
| `"DAY"` | Good for the day |
| `"GTC"` | Good till cancelled |
| `"IOC"` | Immediate or cancel |
| `"FOK"` | Fill or kill |
| `"GTD"` | Good till date |
| `"OPG"` | At the opening |

### Order Lifecycle (what IB sends back)

```
PlaceOrder → PendingSubmit → PreSubmitted → Submitted → Filled
                                                      → PartiallyFilled
                                         → Cancelled
                           → Inactive (rejected)
```

### Order Commands PA Supports

| Command | IB Call | Returns |
|---------|---------|---------|
| Place Order | `placeOrder(orderId, contract, order)` | Order updates via callbacks |
| Cancel Order | `cancelOrder(orderId, "")` | Cancel confirmation via callback |
| Modify Order | `placeOrder(orderId, contract, modifiedOrder)` | Same orderId, modified fields |
| Cancel All | `reqGlobalCancel()` | Cancels ALL active orders |
| Get Open Orders | `reqOpenOrders()` | List of all open orders |
| Flatten | PA sends market order to close position | Custom PA logic |

### ⚠️ Cannot Do
- ❌ Bracket orders as atomic unit (PA must place parent + child separately)
- ❌ Guaranteed fill price (market orders fill at market)
- ❌ Cancel a filled order (obviously)
- ❌ Modify a cancelled/filled order

---

## 8. Account & Position Queries

### Account Summary (`reqAccountSummary`)

**Available fields (tags):**

| Tag | Description |
|-----|-------------|
| `AccountType` | Account type identifier |
| `NetLiquidation` | Net liquidation value |
| `TotalCashValue` | Total cash |
| `SettledCash` | Settled cash |
| `AccruedCash` | Accrued cash |
| `BuyingPower` | Buying power |
| `EquityWithLoanValue` | Equity with loan value |
| `GrossPositionValue` | Gross position value |
| `InitMarginReq` | Initial margin requirement |
| `MaintMarginReq` | Maintenance margin requirement |
| `AvailableFunds` | Available funds |
| `ExcessLiquidity` | Excess liquidity |
| `Cushion` | Margin cushion (% before margin call) |
| `FullInitMarginReq` | Full initial margin |
| `FullMaintMarginReq` | Full maintenance margin |
| `LookAheadInitMarginReq` | Look-ahead initial margin |
| `LookAheadMaintMarginReq` | Look-ahead maintenance margin |

**⚠️ Limit: max 2 simultaneous `reqAccountSummary` subscriptions**
**⚠️ Updates every ~3 minutes (not real-time)**

### Account Updates (`reqAccountUpdates`)
- Real-time account value + portfolio updates
- Pushed on change (more responsive than summary)
- Only for the logged-in account

### Positions (`reqPositions`)
- Returns all positions across all accounts
- Fields: account, contract, position (signed qty), avgCost
- Subscription-based — updates on change

### P&L (`reqPnL` / `reqPnLSingle`)
- Real-time P&L for account or single position
- Fields: dailyPnL, unrealizedPnL, realizedPnL, value

### ⚠️ Cannot Do
- ❌ Get real-time margin updates faster than ~3 min (for summary)
- ❌ More than 2 simultaneous account summary subscriptions
- ❌ Access other accounts unless configured as advisor/sub-account

---

## 9. Rate Limits & Pacing Rules

### Message Rate Limit

| Direction | Limit |
|-----------|-------|
| Client → IB (outbound) | **50 messages/second** |
| IB → Client (inbound) | **No limit** |

- **Violation (error 100):** "Max rate of messages per second has been exceeded"
- **3 consecutive violations = automatic disconnection**

### Historical Data Pacing

| Rule | Limit |
|------|-------|
| General | **60 requests per 600 seconds** (10-minute window) |
| Small bars (≤ 30s) | **Stricter** — IB enforces additional throttling |
| Identical requests | **15-second minimum** between identical requests |
| Violation (error 162) | Pacing violation → temporary ban |

### What PA Does About Pacing
PA implements **PacingRecovery** (r2 feature):
1. Detects pacing violation (error 162)
2. Enters recovery mode with exponential backoff
3. Emits `PacingStateEvent` so downstream knows
4. Queues requests and drains at safe rate
5. Resumes normal after cooldown

### Market Data Request Rate
- Formula: `max_requests_per_second = market_data_lines / 2`
- Default 100 lines → 50 requests/sec (matches message rate limit)

---

## 10. Emergency Mechanisms

### `reqGlobalCancel()`
- **Cancels ALL active orders** across all instruments and accounts
- No parameters, no confirmation — just fires
- PA exposes this via `HardKillCommand`

### PA Kill States (r2)

| State | Behavior | Trigger |
|-------|----------|---------|
| **NORMAL** | All operations allowed | Default / `ResumeNormalCommand` |
| **SOFT_KILL** | Blocks OPEN/ADD orders; allows REDUCE/CLOSE/CANCEL | `SoftKillCommand` from Exec |
| **HARD_KILL** | Cancel all orders → flatten all positions → LOCKOUT | `HardKillCommand` from Exec |
| **LOCKOUT** | Everything blocked until human reset | After HardKill or manual `SetLockoutCommand` |

### PA Failsafe (Heartbeat Monitor)

If the Exec/Strategy layer stops sending heartbeats, PA escalates automatically:

| Stage | Seconds Without Heartbeat | Action |
|-------|---------------------------|--------|
| 0 — NORMAL | 0–30s | Everything OK |
| 1 — WARN | 30s | Log warning, emit `FailsafeStageEvent` |
| 2 — FREEZE | 60s | Block new orders, emit event |
| 3 — FLATTEN | 120s | Cancel all + flatten all positions |

This is PA's **dead man's switch** — if the upstream system crashes, PA will protect capital automatically.

### ⚠️ IB Cannot Do
- ❌ IB has no native "kill switch" beyond `reqGlobalCancel` (which only cancels orders, doesn't flatten)
- ❌ IB doesn't know about our positions — the flatten logic is PA's responsibility
- ❌ No automatic IB-side loss limit (that's our Risk Governor's job)

---

## 11. Known Limitations & Gotchas

### Connection
- **Daily restart window** — IB Gateway restarts daily (configurable time). Auto-restart from v974+ but Sunday needs manual login.
- **2FA on every restart** — unless using Trusted IPs or SLS device
- **No headless** — GUI required (use VNC/X11 for remote servers)

### Data
- **Stock quotes are 250ms snapshots**, not true ticks. For true tick-by-tick, use `reqTickByTickData`.
- **Historical 1s bars** — limited to very recent data (~1 day)
- **Bar timestamps** — IB returns bar **open** time, not close time
- **Volume** — may be 0 for some instruments/data types (e.g., FX midpoint)
- **No historical tick-by-tick** — tick data is real-time only

### Orders
- **Order ID must be unique** — IB provides `nextValidId`, PA must track and increment
- **Modify = re-place** — to modify an order, you call `placeOrder` again with the same orderId but new parameters
- **Paper trading fills differ** — paper trading simulates fills, behavior won't match live exactly
- **`outsideRth` flag** — must explicitly set to trade outside regular hours

### Account
- **Account summary updates every ~3 minutes** — don't rely on it for real-time margin checks
- **One user session at a time** — can't login from two places simultaneously

### Market Data
- **Subscription required** — need active market data subscription for each exchange
- **Forex is free**, US stocks cost $10-30/month per exchange
- **Market data lines limited** — default 100, expandable with booster packs

---

## 12. Error Codes Reference

### Critical Errors

| Code | Message | Action |
|------|---------|--------|
| 100 | Max rate of messages exceeded | Back off immediately; 3x = disconnect |
| 162 | Historical data pacing violation | PA enters pacing recovery |
| 200 | No security definition found | Bad symbol/contract spec |
| 201 | Order rejected | Check order parameters |
| 202 | Order cancelled | Confirmation of cancel |
| 321 | Error validating request | Bad request parameters |
| 502 | Couldn't connect to TWS | TWS not running or wrong port |
| 504 | Not connected | Send request before connected |

### Informational (Not Errors)

| Code | Message | Meaning |
|------|---------|---------|
| 2104 | Market data farm connection OK | Connected to data feed |
| 2106 | HMDS data farm connection OK | Connected to historical data |
| 2158 | Sec-def data farm connection OK | Connected to security definitions |

### Error Code Ranges

| Range | Category |
|-------|----------|
| < 1000 | System errors |
| 1000–1999 | Warning messages |
| 2000+ | Notification/info messages |

---

## 13. Raw Data Shapes from IB

Jake — this is what the raw data looks like before PA wraps it into typed events. Your Normalizer needs to handle these shapes.

### `tickPrice` callback (from `reqMktData`)
```python
tickPrice(reqId: int, tickType: int, price: float, attrib: TickAttrib)
# tickType is a numeric ID (1=bid, 2=ask, 4=last, etc.)
# attrib has: canAutoExecute, pastLimit, preOpen
```

### `realtimeBar` callback (from `reqRealTimeBars`)
```python
realtimeBar(reqId: int, time: int, open: float, high: float, low: float, 
            close: float, volume: int, wap: float, count: int)
# time is UNIX timestamp
# wap = weighted average price
# count = number of trades in bar
```

### `historicalData` callback (from `reqHistoricalData`)
```python
historicalData(reqId: int, bar: BarData)
# bar.date = "20260115  09:30:00" (string format)
# bar.open, bar.high, bar.low, bar.close, bar.volume, bar.barCount, bar.wap
```

### `orderStatus` callback
```python
orderStatus(orderId: int, status: str, filled: float, remaining: float, 
            avgFillPrice: float, permId: int, parentId: int, 
            lastFillPrice: float, clientId: int, whyHeld: str, mktCapPrice: float)
```

### `execDetails` callback
```python
execDetails(reqId: int, contract: Contract, execution: Execution)
# execution.execId, execution.time, execution.shares, execution.price
# execution.side ("BOT" or "SLD"), execution.commission
```

**PA wraps all of these into typed, immutable dataclass events** (see Interface Contracts doc).

---

## 14. Contract Types & Instruments

### Supported Security Types

| `secType` | Description | Example |
|-----------|-------------|---------|
| `"STK"` | Stocks/ETFs | AAPL, SPY, QQQ |
| `"FUT"` | Futures | ES, NQ, GC, CL |
| `"OPT"` | Options | AAPL calls/puts |
| `"CASH"` | Forex pairs | EUR.USD, AUD.JPY |
| `"IND"` | Indices | SPX (no trading, data only) |
| `"CFD"` | CFDs | Where available |
| `"BOND"` | Bonds | US Treasuries, corp bonds |

### Contract Specification

Every request to IB requires a `Contract` object:

```python
contract = Contract()
contract.symbol = "ES"          # Symbol
contract.secType = "FUT"        # Security type
contract.exchange = "CME"       # Exchange
contract.currency = "USD"       # Currency
contract.lastTradeDateOrExpiry = "20260320"  # For futures/options
```

**For stocks:** exchange = `"SMART"` (IB's smart routing)
**For futures:** must specify exchange + expiry
**For forex:** symbol = `"EUR"`, exchange = `"IDEALPRO"`, currency = `"USD"` → trades EUR/USD

---

## 15. Summary: CAN vs CANNOT

### ✅ PA + IB CAN

| Capability | How |
|------------|-----|
| Stream real-time quotes | `reqMktData` → `QuoteEvent` |
| Stream 5-second bars | `reqRealTimeBars` → `BarEvent` |
| Get historical bars at 21 native sizes | `reqHistoricalData` → `BarEvent` |
| Stream live-updating bars at native sizes | `reqHistoricalData(keepUpToDate=True)` |
| Get tick-by-tick data | `reqTickByTickData` |
| Place market/limit/stop/stop-limit orders | `placeOrder` → `OrderUpdateEvent` / `FillEvent` |
| Cancel individual orders | `cancelOrder` → `OrderUpdateEvent` |
| Cancel ALL orders instantly | `reqGlobalCancel` |
| Flatten all positions | PA logic: query positions → send closing orders |
| Get account balances & margin | `reqAccountSummary` / `reqAccountUpdates` |
| Get real-time positions | `reqPositions` → `PositionEvent` |
| Get real-time P&L | `reqPnL` / `reqPnLSingle` |
| Trade stocks, futures, forex, options | Supported via contract specification |
| Paper trade (simulated) | Same API, different port |
| Kill switch (soft + hard) | PA r2 kill states |
| Dead man's switch | PA r2 heartbeat failsafe |
| Recover from pacing violations | PA r2 pacing recovery |
| Reconcile local vs broker state | PA r2 reconciliation |

### ❌ PA + IB CANNOT

| Limitation | Why |
|------------|-----|
| Real-time bars at non-5s intervals | IB only does 5s real-time; Aggregator must build others |
| True tick-by-tick from `reqMktData` | Aggregated snapshots at 250ms |
| Historical tick-by-tick data | Only real-time tick-by-tick exists |
| Programmatic login | Manual GUI login required |
| Headless deployment | GUI always needed (VNC/X11 for remote) |
| Unlimited market data subscriptions | Capped by market data lines |
| Real-time margin updates | Account summary updates every ~3 min |
| Guaranteed fill prices | Market = market; slippage exists |
| Run strategy or make decisions | PA is a thin pipe only |
| Store historical data | PA relays, doesn't persist |
| Calculate indicators (VWAP, EMA, etc.) | That's the Kitchen's job |
| Risk management / drawdown limits | That's the Risk Governor's job |

---

*This document reflects IB TWS API v9.72+ as of January 2026. PA wraps these capabilities — it doesn't add or remove them. For what PA emits and accepts, see the Interface Contracts document.*
