# PA r2 — Comprehensive Analysis
**Date:** 2026-02-16  
**Project:** SniperZero – Platform Adapter Release 2  
**Author:** 1di (Juan)  
**Status:** Pre-Discovery Analysis  

---

## 1. EXECUTIVE SUMMARY

JK and Pete are requesting a **modification** (not rewrite) of the Release 1 PA to transform it from a **connector** (market data + orders + basic orchestration) into an **execution enforcement layer** for the SniperZero ("Zero") project. 

The spec is well-structured and clear. After reviewing:
- The full PA r1 codebase (8 modules, ~2,500 LOC)
- The PA r2 Spec v0
- The Discovery Requirements checklist  
- IB TWS API official documentation (both our existing analysis docs and live IB docs)

**My assessment: This is very achievable.** The r1 architecture is already 60-70% compatible with the r2 requirements. The core modifications are additive — we're bolting on safety/enforcement layers around an already functional broker pipe.

---

## 2. WHAT WE ALREADY HAVE (r1 Inventory)

### ✅ Solid Foundation — Reusable As-Is or With Minor Changes

| Component | File | r2 Status |
|-----------|------|-----------|
| `ConnectionManager` | `core/connection_manager.py` | ✅ Reusable. Already has auto-reconnect with exponential backoff. Needs: failsafe hooks, reconnect event emission, reconciliation trigger on reconnect. |
| `OrderExecutionAdapter` | `adapters/order_execution_adapter.py` | ✅ Reusable. Place/cancel/modify already work. Needs: queue wrapper, kill-state gate, stop-modify throttle. |
| `MarketDataAdapter` | `adapters/market_data_adapter.py` | ✅ Reusable. Subscribe/unsubscribe work. Needs: bar subscription method (currently only quotes + historical). |
| `AccountManager` | `adapters/account_manager.py` | ✅ Reusable. Positions/account summary/subscriptions work. Needs: reconciliation method. |
| `RateLimiter` | `utils/rate_limiter.py` | ⚠️ Partial. Token bucket exists but is **global**, not per-channel. Needs: per-channel instances, burst cap, pacing recovery logic. |
| `PAOutputStream` | `interfaces/pa_outputs.py` | ✅ Reusable. Event bus pattern already in place. Needs: new event types (Kill, Failsafe, Pacing, Reconciliation). |
| `PAInputStream` | `interfaces/pa_inputs.py` | ✅ Reusable. Command dataclasses are clean. Needs: new commands (stop-specific, kill methods). |
| `Config` | `config/settings.py` | ⚠️ Partial. YAML loader works. Needs: r2 config keys expansion. |
| `PlatformAdapter` (main) | `main.py` | ✅ Core orchestrator. Needs: kill state machine, failsafe monitor, queue integration, reconciliation on connect. |
| `StateManager` | `_quarantine/state_manager.py` | 🔄 **Quarantined** in r1 (PA 2.0 was "zero state cache"). Needs to be **un-quarantined** for r2 — the spec requires local runtime state for kill tracking, reconciliation, and order queue management. |

### 📊 Effort Estimate by Module

| New/Modified Component | Complexity | Est. LOC | Notes |
|------------------------|-----------|----------|-------|
| Per-channel rate limiter + burst control | Medium | ~200 | Extend existing `RateLimiter` class |
| Central order queue | Medium | ~250 | `asyncio.Queue` or `queue.Queue` with priority |
| Stop-modify throttler | Medium | ~150 | Merge/debounce logic, min-interval/min-delta |
| Kill state machine (Soft/Hard/Failsafe) | High | ~400 | State enum + transition logic + command gating |
| Failsafe heartbeat monitor | Medium | ~200 | Background thread, 3-stage timer |
| Pacing recovery engine | Medium | ~200 | Cooldown/backoff, critical-only mode |
| Reconciliation module | Medium-High | ~300 | IB state query + diff + policy resolution |
| Event types expansion | Low | ~100 | New dataclasses for Kill/Failsafe/Pacing/Reconcile events |
| Config expansion | Low | ~50 | Add r2 config keys to YAML + Settings |
| Journal/telemetry emission | Low | ~100 | Structured log events (PA doesn't own DB) |
| Live/Paper mode switching | Low | ~80 | Port toggle (7497↔7496 / 4002↔4001) |
| **Total new/modified** | | **~2,030** | Plus tests |

---

## 3. DISCOVERY REQUIREMENTS — PRELIMINARY ANSWERS

Based on IB documentation review (our existing docs + official IB TWS API docs), here are preliminary answers. **These need confirmation via testing on paper account.**

### A) Pacing Scope Clarification

| Question | Preliminary Answer | Source | Confidence |
|----------|-------------------|--------|------------|
| Per login session? | **Yes** — pacing is per API socket connection | IB TWS API docs: "Pacing Limitations with regards to the TWS API are based on the number of requests submitted by a client connection" | 🟢 High |
| Per API socket connection? | **Yes** — each `clientId` connection has its own pacing counter | IB docs: "each TWS session can receive up to 32 different client applications simultaneously" | 🟢 High |
| Per account? | **No** — per connection, not per account. But if same account is used across connections, limits still apply per connection. | Inferred from docs | 🟡 Medium |
| Shared across simultaneous Gateway instances? | **No** — each Gateway instance is a separate session. But only one session per username is allowed. | IB docs: "Solo una sesión activa por username" | 🟡 Medium — needs VPS test |
| Aggregate across multiple VPS w/ same account? | **No** — if using different usernames on each VPS, they are independent sessions. Same username = only one session active. | IB docs: multiple usernames can be created in Account Management | 🟡 Medium |

### B) Message Throughput Limits

| Parameter | Value | Source |
|-----------|-------|--------|
| Max sustained messages/sec (client → IB) | **50 msg/s** (default; = market data lines / 2) | IB official docs |
| Burst tolerance | **No explicit burst window** — TWS setting controls behavior: reject msgs above max rate vs auto-pacing | IB docs: "Reject messages above maximum allowed message rate vs applying pacing" |
| Order placement | Counted in the 50 msg/s aggregate | Same pool |
| Order modification | Counted in the 50 msg/s aggregate (same as placement — uses `placeOrder` with same orderId) | IB docs: modification uses `placeOrder` with existing orderId |
| Order cancellation | Counted in the 50 msg/s aggregate | Same pool |
| Market data subscription | Counted in the 50 msg/s aggregate | Same pool |
| Historical data requests | **60 requests per 10 minutes**, PLUS special pacing for bars ≤30s | IB docs |
| Pacing violation escalation | **Error 100 → 3 violations = disconnection** (if "reject" mode enabled). If "auto-pace" mode, TWS queues internally. | IB official docs |

**Key finding:** IB does NOT have per-channel limits natively. The 50 msg/s is **aggregate**. Our r2 per-channel caps are a **PA-internal safety mechanism** layered on top. This is the right approach.

### C) Modify/Cancel Sensitivity

| Question | Answer | Source |
|----------|--------|--------|
| Comms loss detection | **Both recommended.** IB provides error codes 1100/1101/1102 for IB connectivity. Exec heartbeat is our own mechanism. | IB docs: error 1100 = "Connectivity between IB and TWS has been lost" |
| Server-side stops survive disconnect? | **Yes.** Once an order status = `Submitted`, it lives on IB servers regardless of API connection. | IB docs: `reqOpenOrders()` / `reqAllOpenOrders()` retrieve orders after reconnect. Also confirmed by "Intelligent Order Resubmission" feature (TWS 10.28+). |
| Verify stops on reconnect | Use `reqOpenOrders()` + `reqAllOpenOrders()` + `reqPositions()` after reconnect. | IB docs |
| Rapid cancel/replace vs new order | **Same mechanism** — modification uses `placeOrder()` with the existing orderId. Counts toward same 50 msg/s limit. | IB docs: "Modification of an API order... EClient.placeOrder can then be called with the same fields as the open order, except for the parameter to modify" |
| Internal throttling for stop modifications | **No IB-internal throttle** — every modify counts as a message. Our r2 stop-modify throttle is essential. | Confirmed by IB docs — no special treatment for stop modifications |
| How often can trailing SL be changed? | **As often as you want** within the 50 msg/s limit. But each change = 1 message. Our min_interval (250ms) + min_delta (1 tick) throttle is correct approach. | IB docs |
| Auto-flatten on connection loss? | **No.** IB does not provide this feature via API. Server-side orders remain active (which is GOOD — your stops stay). Our r2 Failsafe Stage 2 AutoExit handles this client-side. | IB docs — no such feature exists |
| Programmatic account lockout? | **No.** IB does not provide a "lock account" API action. Our r2 local lockout (`set_lockout()`) is the correct approach — PA refuses commands locally. | IB docs — no such feature exists |

### D) Reconnection Behavior

| Scenario | What Happens | What Must Be Re-Requested |
|----------|-------------|--------------------------|
| Socket disconnect | API client loses connection. `connectionClosed()` callback fires. IB server-side orders remain active. | Everything: `nextValidId` (automatic on reconnect), open orders (`reqOpenOrders`), positions (`reqPositions`), account summary, market data subscriptions. |
| Gateway restart | Same as socket disconnect but Gateway itself restarts. Auto-restart (v974+) handles Gateway restart. API client must reconnect. | Same as above. Additionally: IB docs state "Both TWS and IBGW were designed to be restarted daily." |
| IB server reset (nightly) | Error 1100 → brief disconnect → Error 1101 or 1102 on reconnect. | If 1101: market data lost, must re-subscribe. If 1102: market data maintained. In both cases: re-request open orders and positions. |

**Key finding for r2:** On reconnect, our `reconcile_state()` method MUST:
1. Wait for `nextValidId` callback (connection confirmed)
2. `reqAllOpenOrders()` — get ALL open orders (including any manual TWS orders)
3. `reqPositions()` — get current positions
4. `reqAccountSummary()` — get account state
5. Diff local state vs IB truth
6. Resolve orphans per config policy
7. Re-subscribe to market data
8. Emit reconciliation report

### E) VPS Operational Considerations

| Topic | IB Guidance |
|-------|-------------|
| Gateway uptime cycling | "Both TWS and IBGW were designed to be restarted daily." Auto-restart (v974+) handles Mon-Sat automatically. Sunday requires manual re-login. |
| Session refresh | Auto-restart handles daily refresh. Session is valid Mon-Sat continuous. Sunday = server reset + mandatory re-login. |
| Memory usage | IB recommends **4000 MB** for API users. Gateway uses ~40% less resources than TWS. |
| Java requirement | IB Gateway requires Java 8 update 192 minimum, Java 11+ recommended. |
| Ports | Gateway Live: **4001**, Gateway Paper: **4002**. TWS Live: 7496, Paper: 7497. |
| Max API clients | **32 simultaneous connections** per Gateway instance. |

---

## 4. ARCHITECTURE IMPACT ANALYSIS

### 4.1 What Changes in the Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PA r2 — Execution Enforcement Layer              │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     Kill State Machine                       │  │
│  │   [NORMAL] ─→ [SOFTKILL] ─→ [FAILSAFE_FREEZE]              │  │
│  │       │            │               │                         │  │
│  │       └──→ [HARDKILL] ←────────────┘                        │  │
│  │                 │                                            │  │
│  │            [LOCKOUT] (requires human reset)                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                           │                                        │
│  ┌─────────────┐    ┌────▼────────┐    ┌──────────────────────┐   │
│  │  Failsafe   │    │   Central   │    │  Per-Channel Rate    │   │
│  │  Heartbeat  │    │   Order     │    │  Limiters + Pacing   │   │
│  │  Monitor    │    │   Queue     │    │  Recovery Engine     │   │
│  │ (3-stage)   │    │ (gate all   │    │                      │   │
│  │             │    │  IB calls)  │    │  ┌─ mkt_data_sub    │   │
│  └──────┬──────┘    └──────┬──────┘    │  ├─ order_place     │   │
│         │                  │           │  ├─ order_modify     │   │
│         │                  │           │  ├─ order_cancel     │   │
│         │                  │           │  └─ misc             │   │
│         ▼                  ▼           └──────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │              Stop-Modify Throttler                           │ │
│  │   merge successive updates, enforce min_interval/min_delta  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                           │                                       │
│  ┌────────────────────────▼─────────────────────────────────────┐ │
│  │                 Connection Manager (existing)                │ │
│  │     + Reconnection hooks → Reconciliation Engine             │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                           │                                       │
│  ┌────────────────────────▼─────────────────────────────────────┐ │
│  │   Adapters (existing): MarketData | OrderExec | Account      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                           │                                       │
│  ┌────────────────────────▼─────────────────────────────────────┐ │
│  │              PAOutputStream (existing + new events)          │ │
│  │   + OnKillStateChanged, OnFailsafeStageChanged,              │ │
│  │     OnPacingEvent, OnReconciliationReport                    │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                    TCP Socket (Port 4001/4002)
                               │
                               ▼
                    ┌──────────────────┐
                    │   IB Gateway     │
                    │   (VPS)          │
                    └──────────────────┘
```

### 4.2 Command Flow (Before vs After)

**r1 (current):**
```
Exec → PA.handle_place_order() → OrderExecutionAdapter.place_order() → IB
```

**r2 (proposed):**
```
Exec → PA.handle_place_order()
         → Kill State Gate (check: is this command allowed in current state?)
            → Central Order Queue (enqueue; never call IB directly)
               → Queue Processor (dequeue one at a time)
                  → Per-Channel Rate Limiter (throttle if needed)
                     → Stop-Modify Throttler (if applicable: merge/debounce)
                        → OrderExecutionAdapter.place_order() → IB
```

### 4.3 File Structure Diff (r1 → r2)

```diff
  src/platform_adapter/
  ├── __init__.py
- ├── _quarantine/
-      ├── state_manager.py         # UN-QUARANTINE → move to core/
  ├── adapters/
  │   ├── account_manager.py        # Minor changes (reconciliation helper)
  │   ├── market_data_adapter.py    # Minor changes (bar subscription)
  │   └── order_execution_adapter.py # Minor changes (stop-specific methods)
  ├── config/
  │   └── settings.py               # Expand for r2 config keys
  ├── core/
  │   ├── connection_manager.py     # Add reconnect hooks for reconciliation
+ │   ├── state_manager.py          # UN-QUARANTINED: runtime state for kills/reconcile
+ │   ├── order_queue.py            # NEW: central order queue + processor
+ │   ├── kill_manager.py           # NEW: kill state machine (Soft/Hard/Failsafe)
+ │   ├── failsafe_monitor.py       # NEW: heartbeat monitor, 3-stage timer
+ │   ├── pacing_engine.py          # NEW: pacing recovery (cooldown/backoff)
+ │   └── reconciliation.py         # NEW: IB truth vs local state diff + resolve
  ├── interfaces/
  │   ├── pa_inputs.py              # Add kill commands, stop-specific commands
  │   └── pa_outputs.py             # Add kill/failsafe/pacing/reconcile events
  ├── models/
  │   ├── contract.py               # No change
  │   ├── order.py                  # No change
  │   └── position.py               # No change
  └── utils/
      ├── logger.py                 # No change
      └── rate_limiter.py           # Major refactor: per-channel + burst + pacing hooks
```

---

## 5. RISK ASSESSMENT & CONCERNS

### 🟡 Medium Risk Items

1. **Pacing "auto-pace" vs "reject" mode.** TWS/Gateway has a global setting that controls behavior when pacing is exceeded. If set to "auto-pace", IB queues internally (good). If set to "reject", error 100 is returned and 3 violations = disconnect (bad). **Recommendation:** Set Gateway to "auto-pace" mode AND still implement our own per-channel limiters as defense-in-depth.

2. **Stop-modify via `placeOrder()`.** IB doesn't have a dedicated "modify stop" endpoint — you re-submit the full order with the same orderId. This means every stop modification looks exactly like a new order to the 50 msg/s counter. Our throttler is essential.

3. **Sunday re-login.** IB requires manual GUI login every Sunday after server reset. This is a human operational process that cannot be automated (IB security policy: "no headless login"). **Recommendation:** Document VPS runbook with Sunday re-login procedure. Consider 2nd username as IB recommends.

4. **Paper vs Live port switching.** Pete's requirement to switch between Live and Paper is straightforward (port 4001 vs 4002) but requires disconnect → reconnect → full reconciliation. Need clean mode-switch method.

### 🟢 Low Risk Items

1. **Server-side stop persistence.** Confirmed: IB server-side orders survive API disconnects. This is critical for safety and it works as expected.

2. **Reconnection + reconciliation.** Our r1 already has auto-reconnect with exponential backoff. We just need to add the reconciliation step after reconnect.

3. **Event emission for journal.** PAOutputStream pattern already supports this. Adding new event types is mechanical.

### 🔴 Items Requiring Discovery Testing

1. **Exact pacing behavior on VPS.** Need to confirm with actual paper-trading tests:
   - Error 100 threshold under real conditions
   - Whether Gateway "auto-pace" mode is reliable enough
   - Actual throughput achievable under load

2. **Modify order during partially filled state.** Need to test: can we modify a stop that is partially filled?

3. **Gateway restart timing.** Need to measure: how long does Gateway auto-restart take? Is our reconnect backoff sufficient?

---

## 6. LIVE vs PAPER TRADING MODE

Per Pete's requirements:
- **Port 4001** = Live (real money)  
- **Port 4002** = Paper (simulated)  
- Cannot execute in both simultaneously
- Need ability to switch at runtime

**Implementation plan:**
```python
def switch_mode(self, mode: Literal["live", "paper"]) -> bool:
    """Switch between live and paper trading.
    
    Disconnects from current session, reconnects on new port.
    Full reconciliation runs after reconnect.
    """
    port = 4001 if mode == "live" else 4002
    self.disconnect()
    return self.connect(port=port)  # triggers reconcile_state()
```

Config will store both ports and track current mode:
```yaml
ib:
  host: "127.0.0.1"
  port_live: 4001
  port_paper: 4002
  active_mode: "paper"  # or "live"
  client_id: 1
```

---

## 7. SPEC v0 ALIGNMENT CHECK

| Spec Section | Covered? | Notes |
|-------------|----------|-------|
| §1 Scope | ✅ | All 7 items achievable |
| §2 Non-Goals | ✅ | r1 already follows these rules. Historical data command exists but will be disabled in r2 config (not removed from interface). |
| §3 System Boundary | ✅ | PAInputStream already enforces "only Exec calls PA" |
| §4 Minimal Public Interface | ✅ | Most methods already exist. Need: `set_softkill`, `hardkill`, `set_lockout`, `heartbeat_from_exec`, `set_failsafe_policy`, `reconcile_state`, `subscribe_bars` |
| §5 Events | ⚠️ | Need to add: `OnPacingEvent`, `OnKillStateChanged`, `OnFailsafeStageChanged`. Others already exist or are minor extensions. |
| §6 Rate Limiting & Queueing | ⚠️ | Rate limiter exists but needs per-channel + burst + queue refactor |
| §7 Stop Modify Throttling | 🆕 | New component entirely |
| §8 Pacing Recovery | 🆕 | New component entirely |
| §9 Kill States | 🆕 | New component entirely |
| §10 Failsafe | 🆕 | New component entirely |
| §11 Restart Reconciliation | 🆕 | New component (StateManager was quarantined, needs revival) |
| §12 Persistence | ⚠️ | Event emission exists; structured format for Postgres journal is new |
| §13 Configuration | ⚠️ | Config system exists; needs key expansion |
| §14 Acceptance Criteria | ✅ | All testable. Will need test harness. |

---

## 8. RECOMMENDED DISCOVERY TESTING PLAN

Before implementation, these tests should be run on paper account:

### Test 1: Pacing Baseline
- Connect to Gateway paper (port 4002)
- Send messages at increasing rates: 10/s, 20/s, 30/s, 40/s, 50/s, 60/s
- Log at what rate error 100 appears
- Confirm 3-strike disconnect behavior
- Test with "auto-pace" vs "reject" mode

### Test 2: Stop Order Persistence
- Place a stop order via API
- Disconnect API client (kill the Python process)
- Wait 30 seconds
- Reconnect
- Call `reqAllOpenOrders()` — verify stop is still there
- Verify stop still executes if price hits

### Test 3: Reconnection + State Recovery
- Connect, place 3 orders, subscribe to market data
- Kill the socket (simulate network loss)
- Let auto-reconnect fire
- After reconnect: `reqOpenOrders()` + `reqPositions()` + re-subscribe market data
- Verify all state is recovered

### Test 4: Modify Rate
- Place a stop order
- Modify it rapidly (every 100ms for 10 seconds = 100 modifications)
- Log how many succeed, how many trigger pacing
- Determine safe min_interval for production

### Test 5: Paper ↔ Live Switch
- Connect to paper (4002)
- Disconnect
- Connect to live (4001) — or use separate paper account on different port
- Verify full reconciliation works

---

## 9. IMPLEMENTATION SEQUENCE (Post-Discovery)

Recommended order:

1. **Config expansion** — add all r2 keys to YAML + settings loader
2. **Per-channel rate limiter refactor** — foundation for everything else
3. **Central order queue** — all commands go through queue
4. **Kill state machine** — command gating logic
5. **Stop-modify throttler** — debounce/merge layer
6. **Failsafe heartbeat monitor** — 3-stage timer
7. **Pacing recovery engine** — cooldown/backoff
8. **Reconciliation module** — IB truth sync
9. **Event types expansion** — new events for journal
10. **Live/Paper mode switch** — port toggle
11. **Integration testing** — against paper account
12. **Acceptance testing** — per §14 criteria

Estimated calendar time: **2-3 weeks** for implementation + testing, assuming discovery is completed first.

---

## 10. QUESTIONS FOR PETE & JK

1. **Failsafe timers:** The spec says T_freeze=15s, T_flatten=180s. Are these the final numbers or starting points for tuning?

2. **Lockout reset:** "human resets" — is this a CLI command? A config file edit? An API call from a separate admin tool?

3. **Journal format:** What Postgres schema is the Journal module expecting? Do we have a protobuf/JSON schema for events, or do we define it?

4. **Risk Governor:** The spec says "Kill decision lives in a separate Risk Governor." Is Risk Governor being built by someone else? Or is it part of PA r2 scope to expose the kill methods and let Exec call them?

5. **Historical data command:** The spec says "PA makes zero historical-data requests in v1." Should we remove the `HistoricalDataCommand` from the interface entirely, or just disable it in config and log a warning if called?

6. **`subscribe_bars`:** The spec mentions `subscribe_bars(symbol, bar_size, source="TRADES")`. IB's `reqRealTimeBars` only supports 5-second bars. For other bar sizes (1min, 5min, etc.), we'd need to aggregate from 5s bars or use `reqHistoricalData` with `keepUpToDate=True`. Which approach does the team prefer?

7. **Multi-symbol:** The spec mentions "Keep symbol state clean per instance." Does this mean one PA instance per symbol, or one PA instance managing multiple symbols with clean per-symbol state?

---

## 11. DISCOVERY DELIVERABLE CHECKLIST

- [ ] Written confirmation of Section 3 findings as artifact "PAr2 Discovery Findings"
- [ ] Paper account test results for Tests 1-5 (Section 8)
- [ ] Review of Discovery Findings with Pete & JK
- [ ] Key Decisions from Review recorded and shared
- [ ] **Only then:** implementation begins

---

*Analysis complete. Ready to proceed with Discovery testing upon team approval.*
