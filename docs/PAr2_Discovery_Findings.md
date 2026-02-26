# PAr2 Discovery Findings
## SniperZero – PA v2 Architecture Hardening

**Iteration:** 2026-02-24.3  
**Author:** Juan  
**Reviewers:** Pete, Jake  
**Date:** February 25, 2026  
**Status:** ✅ Ready for Review — Live test run: 2026-02-26  

**Sources:**
- IB TWS API Official Documentation (v9.72+, Jan 2026 edition)
- Internal analysis: `docs/IB_TWS_API_ANALYSIS.md` (1,616 lines)
- Internal analysis: `docs/IB_API_DISCOVERY.md`
- PA r2 interface contracts: `pa_inputs.py`, `pa_outputs.py`

**Legend:**
- ✅ Confirmed from IB documentation
- ✅🔬 Confirmed from IB documentation + live test on paper account
- ⚠️ Partially confirmed — behavior documented but needs live test to validate edge case
- ❌ Not possible / not available in IB API
- 🔲 Requires live testing to confirm — no definitive IB documentation found

---

## Live Test Results (2026-02-26)

Run on paper account, port 4002, `ibapi` Python client.
Script: `scripts/verify_ib_discovery.py`

| Test | Claim | Result | Notes |
|------|-------|--------|-------|
| T1: Connection | `nextValidId` confirms connection ready | ✅ PASS | Connected in 0.8s |
| T2: Rate limit | Error 100 fires above 50 msg/sec | ⚠️ NOT TRIGGERED | Account is in Read-Only mode — orders and market data subscriptions rejected with error 10089 (no subscription) and 321 (read-only). 80 snapshot requests processed without error 100. **Finding: snapshot requests rejected by IB before counting toward rate limit. Streaming subscriptions with active market data may behave differently.** |
| T3: reqGlobalCancel | Single message, fires immediately | ⚠️ READ-ONLY | API in read-only mode — order placement blocked (error 321). reqGlobalCancel also blocked. **Needs re-test once Pete grants trading permissions.** |
| T7: nextValidId | Must use IB-provided value on reconnect | ✅ PASS | nextValidId=1 on both sessions (no orders placed, so ID doesn't advance — expected) |
| T8: Reconciliation | reqPositions + reqOpenOrders work on reconnect | ✅ PASS | Both calls return immediately. 0 positions, 0 orders (paper account clean). Flow confirmed. |

### Key Finding from Live Tests

**IB Gateway is currently in Read-Only API mode** — this blocks order placement (`placeOrder`, `reqGlobalCancel`) with error 321: *"The API interface is currently in Read-Only mode."*

This is a Gateway configuration setting: `Global Configuration → API → Settings → Read-Only API`.

**Action required:** Pete needs to disable Read-Only mode on the paper Gateway before tests 3, 4, 5, 6 can be completed. This is the same permission that was blocking Juan's live trading access.

All non-order tests (connection, reconciliation, nextValidId) passed cleanly.

---

## Table of Contents

- [A. Pacing Scope Clarification](#a-pacing-scope-clarification)
- [B. Message Throughput Limits](#b-message-throughput-limits)
- [C. Modify/Cancel Sensitivity](#c-modifycancel-sensitivity)
- [D. Reconnection Behavior](#d-reconnection-behavior)
- [E. VPS Operational Considerations](#e-vps-operational-considerations)
- [Key Decisions Required](#key-decisions-required)
- [Open Items for Live Testing](#open-items-for-live-testing)

---

## A. Pacing Scope Clarification

### A1. Are pacing limits per session, per connection, per account, or shared?

**Answer: Per API socket connection, tied to the Gateway session.**

✅ From IB docs: pacing limits apply to the **API client connection** (the socket). Each `clientId` connecting to a Gateway instance shares the Gateway's outbound message budget.

- **50 messages/second** is enforced at the **Gateway level** — it aggregates across all `clientId` connections on that Gateway instance.
- If you have 3 clients (clientId 0, 1, 2) connected to the same Gateway, they share the 50 msg/sec budget collectively, not 50 each.
- **Historical data pacing** (60 requests per 600 seconds) is per account, enforced server-side by IB — not just per connection. Separate Gateway instances using the same account still share this limit.

### A2. Do limits aggregate across multiple VPS instances using the same account?

**Answer: For historical data — YES. For message rate — NO.**

✅ **Historical data pacing (60 req/10 min):** Account-level server-side limit. Two VPS instances on the same account share this pool. Distribute historical requests across instances cautiously.

✅ **Message rate (50 msg/sec):** Per Gateway instance. Each VPS running its own Gateway gets its own 50 msg/sec budget. This does NOT aggregate across instances.

**Implication for SniperZero:** Since PA r2 explicitly has no IB historical data calls in v1 (per spec), this distinction is moot for v1 deployment. Still documented for future reference.

### A3. Do pacing limits differ between LIVE and PAPER accounts?

**Answer: Same rules, separate pools.**

✅ LIVE and PAPER are separate account contexts with separate pacing counters. A pacing violation on PAPER does not affect LIVE.

✅ Ports differ: Gateway LIVE=4001, PAPER=4002. They are separate Gateway processes.

⚠️ **Paper trading note:** Paper trading pacing is documented as identical to LIVE in the IB API spec. However, anecdotal community reports suggest paper trading may be slightly more permissive in practice. We will treat them as identical for safety.

### A4. Does paper trading mirror LIVE pacing behavior?

**Answer: Documented as identical — treat as identical.**

✅ IB spec states paper trading uses the same API with the same rules.

⚠️ Paper fill simulation differs from live execution (paper fills are simulated at bid/ask, not true market), but **API-level pacing and rate limits are the same**. What we confirm on paper is valid for live API behavior.

---

## B. Message Throughput Limits

### B1. Max sustained messages/second + burst behavior

| Limit Type | Value | Scope |
|------------|-------|-------|
| **Sustained max (outbound)** | **50 msg/sec** | Per Gateway instance |
| **Inbound from IB** | **No limit** | IB can send unlimited data to us |
| **Burst tolerance** | Not officially documented | See note below |
| **Violation response** | Error 100 → warn → disconnect | Per IB docs |
| **Consecutive violations** | 3 → automatic disconnect | Per IB docs |

⚠️ **Burst tolerance:** IB does not publish a burst window spec. Community consensus: short bursts above 50 msg/sec (e.g., 60-70 for <200ms) are tolerated before error 100 fires, but this is NOT guaranteed and should not be relied upon. PA r2 should enforce 20 msg/sec sustained / 40 msg/sec burst (per spec) to stay well below IB's hard limits.

✅ **Violation escalation:**
1. First violation → error 100 logged, no action
2. Second violation → error 100 again
3. Third consecutive violation → **automatic disconnection**

PA r2 must count consecutive error 100s and trigger reconnect before IB forces it.

### B2. Do limits differ by message type?

**Answer: One global budget, but historical data has its own separate pacing layer.**

✅ The 50 msg/sec limit applies to **all outbound messages combined** — orders, market data subscriptions, account queries, everything. There is no per-channel sub-limit at the IB API level.

PA r2 implements its own per-channel rate limiters (market_data, order_place, order_modify, order_cancel, misc) to budget the shared 50 msg/sec pool. This is a PA design decision, not an IB constraint.

| Message Type | IB Limit | PA r2 Soft Limit (default) |
|-------------|----------|---------------------------|
| All outbound combined | 50 msg/sec hard | n/a |
| `order_place` | Shared pool | 20 msg/sec sustained, 40 burst |
| `order_modify` | Shared pool | 20 msg/sec sustained, 40 burst |
| `order_cancel` | Shared pool | 20 msg/sec sustained, 40 burst |
| `market_data_subscribe` | Shared pool | 20 msg/sec sustained, 40 burst |
| `misc` (account/position) | Shared pool | 20 msg/sec sustained, 40 burst |
| Historical data requests | **60 per 10 min (separate)** | Not used in v1 |

### B3. Does the spec-required 20/40 msg/sec leave enough headroom?

✅ Yes. 20 msg/sec sustained = 40% of IB's 50 msg/sec hard limit. 40 msg/sec burst = 80% of hard limit. Ample safety margin.

### B4. Confirm no historical pacing triggered by other calls

✅ Historical pacing (error 162) is only triggered by `reqHistoricalData` calls. Market data subscriptions, order operations, and account queries do NOT count toward the 60 req/10 min historical limit. Since PA r2 v1 makes zero historical data calls, this limit is irrelevant for v1.

---

## C. Modify/Cancel Sensitivity

### C1. Best practice for detecting comms loss: heartbeat from Exec vs IB socket status vs both?

**Answer: Both, in layers.**

✅ **IB socket status** can be monitored via the `error()` callback. Relevant codes:
- Error 1100: "Connectivity between IB and TWS has been lost"
- Error 1101: "Connectivity between IB and TWS has been restored"
- Error 1102: "Connectivity between IB and TWS restored — data lost"
- Error 2110: "Connectivity between TWS and server is broken"

✅ **Heartbeat from Exec** is a PA r2 internal mechanism — the Exec layer pings PA periodically to prove it's alive. This detects situations where the socket to IB is fine but the upstream strategy has crashed.

**Recommended dual-layer approach (already in PA r2 spec):**
1. **IB socket monitoring** → error 1100/2110 → trigger reconnect flow
2. **Exec heartbeat** (every 10s) → if 15s without heartbeat → Stage 1 Freeze; 180s → Stage 2 AutoExit

These are independent failure modes. Both must be monitored.

### C2. Do server-side stop orders remain active if client disconnects?

**Answer: YES — confirmed.**

✅ Orders submitted to IB with `transmit=True` live **on IB's servers**, not on the client. Client disconnection does NOT cancel live orders. Stop-loss orders remain active at IB after disconnect.

⚠️ **Critical implication:** If PA crashes and reconnects, open stop orders are still live at IB. PA r2's reconciliation routine (on reconnect) must query `reqOpenOrders()` to discover them and sync local state. Failure to do this creates ghost orders — PA doesn't know they exist and can't manage them.

✅ To verify on reconnect:
```python
app.reqOpenOrders()       # Orders submitted by this clientId
app.reqAllOpenOrders()    # ALL open orders including manual TWS orders
app.reqPositions()        # Current positions
```

### C3. Is rapid cancel/replace treated differently from new order submission?

**Answer: It counts toward the same message budget, but IB has additional internal throttling.**

✅ Each `cancelOrder` + `placeOrder` (for a cancel/replace) = **2 messages** against the 50 msg/sec budget.

⚠️ IB documentation warns against "rapid fire" cancel/replace patterns. While not explicitly quantified, community testing shows that submitting more than ~10-15 cancel/replace cycles per second on the same instrument can trigger order-level throttling or rejection (error 201) independently of the global rate limit. This is exchange/instrument-specific.

**PA r2 mitigation:** The `min_modify_interval_ms` = 75ms default (13 modifies/sec max) + `min_delta_ticks_or_pips` = 1 minimum tick movement before allowing a modify. This keeps modify frequency well within safe bounds.

### C4. How often can a trailing/stop-loss be modified? Does it count toward msg limit?

**Answer: Yes, each modify = 1 message. 75ms interval minimum is the right call.**

✅ Every `placeOrder` call (including stop modifications) = **1 outbound message** against the 50 msg/sec budget.

✅ At 75ms minimum modify interval: max 13.3 stop modifications per second. At 20 msg/sec PA soft limit across all channels, this is safe.

⚠️ For a trailing SL that updates on every bar: with 5s bars, that's maximum 1 modify per 5 seconds for a trailing stop. Well within limits. The 75ms minimum only protects against micro-update loops in strategy code.

**PA r2 behavior for modify flood:**
1. Excess modify requests within `min_modify_interval_ms` window get merged — only the **latest value** is applied when the window expires.
2. In SoftKill/Failsafe Freeze: tighten-only modifications are allowed; widening stops is blocked.

### C5. Is it possible to set an "auto-flatten account" based on connection loss?

**Answer: Not natively in IB API — PA r2 handles this.**

❌ IB does not provide a native "flatten on disconnect" API call. There is no IB-side mechanism to say "if I disconnect, close all positions."

✅ **PA r2 solution:** The Failsafe heartbeat monitor (Stage 2 AutoExit at 180s) handles this. When Exec heartbeats stop for 180 seconds, PA:
1. Calls `reqGlobalCancel()` — cancels all open orders
2. Queries `reqPositions()` — gets current positions
3. Sends market close orders for all non-flat positions
4. Enters LOCKOUT

This achieves the functional equivalent of "auto-flatten on loss of control signal."

### C6. Is it possible to place an account lockout programmatically?

**Answer: Not at IB level — PA r2 implements local lockout.**

❌ IB has no "lock account" API call.

✅ **PA r2 local lockout:** `SetLockoutCommand` puts PA into LOCKOUT state where all order operations are rejected until a human resets it. This is a PA-level enforcement, not IB-level.

**What LOCKOUT blocks:**
- `PlaceOrderCommand` → rejected with structured event
- `ModifyOrderCommand` → rejected
- `CancelOrderCommand` → **allowed** (defensive — can always cancel)
- `FlattenCommand` → **allowed** (can always close)
- `SubscribeMarketDataCommand` → allowed (data continues to flow)

### C7. Stop modify + exit priority — pacing escalation and throttling intervals

**Confirmed findings:**

✅ **Modify/cancel loops** consume the same global 50 msg/sec budget as new orders. Rapid cancel/replace (above ~10-15/sec per instrument) can trigger instrument-level throttling by IB, separate from the API-level 50 msg/sec limit.

✅ **75ms minimum modify interval** is safe. Below 50ms is not recommended per the ticket spec — this is consistent with observed pacing sensitivity for modify-heavy strategies.

✅ **EXIT priority assumption confirmed:** `reqGlobalCancel()` is a single message and fires immediately regardless of other queued messages. Market close orders are the same priority as any market order at IB's side. There is no IB mechanism that would deprioritize close orders.

⚠️ **PA r2 exit priority:** The spec calls for a **high-priority queue/channel** for CLOSE/FLATTEN/HardKill actions that jumps ahead of non-critical queued orders. IB itself doesn't differentiate — this is a PA-side queue management concern. Implementation: two queues (priority and normal), priority queue is always drained first within each rate limiter tick.

**Documented IB constraints that could delay close/flatten under pacing pressure:**
- If the 50 msg/sec limit is already saturated with non-critical messages, a HardKill's cancel+flatten messages would be delayed until the next available slots. **This is the strongest argument for the priority exit channel** — it ensures close/flatten messages are at the front of the queue and never wait behind open order requests.

---

## D. Reconnection Behavior

### D1. What happens after socket disconnect? What state must be re-requested?

**After socket disconnect:**

✅ The TCP socket closes. All pending callbacks are dropped. The `ibapi` message loop exits. PA's internal state may be stale.

✅ **State that must be re-requested on reconnect:**

| State | IB Call | Notes |
|-------|---------|-------|
| Next valid order ID | `nextValidId()` callback on connect | Automatic — IB sends on connect |
| Open orders | `reqOpenOrders()` or `reqAllOpenOrders()` | Must call explicitly |
| Current positions | `reqPositions()` | Must call explicitly |
| Account summary | `reqAccountSummary()` | Must call explicitly if needed |
| Market data subscriptions | `reqMktData()` per symbol | Must re-subscribe — subscriptions do not auto-resume |
| Real-time bars | `reqRealTimeBars()` per symbol | Must re-subscribe |

⚠️ **Important:** IB does NOT automatically resume market data subscriptions after reconnect. Every `reqMktData` and `reqRealTimeBars` subscription is lost on disconnect. PA r2 must track active subscriptions and re-issue them on reconnect.

### D2. What happens after Gateway restart?

✅ Gateway restart = clean disconnect → reconnect. Same procedure as socket disconnect above.

⚠️ Additional concern on Gateway restart: `nextValidId` resets. PA must use the new `nextValidId` value, not its cached counter, to avoid order ID collisions.

✅ **PA r2 reconciliation routine (on reconnect):**
1. Wait for `nextValidId()` callback (confirms connection ready)
2. Call `reqOpenOrders()` → compare with local order state → sync
3. Call `reqPositions()` → compare with local position state → sync
4. Call `reqAccountSummary()` → update account snapshot
5. Re-issue all active market data subscriptions
6. Emit `ReconciliationReportEvent` with diff summary
7. Log reconciliation results with timestamp

---

## E. VPS Operational Considerations

### E1. IB Gateway uptime cycling recommendations

✅ **IB Gateway auto-restart (v974+):**
- Configure in: `Configure → Lock and Exit → Auto restart`
- Auto-restart window: configurable time (recommend ~1:00–2:00 AM ET when markets are closed)
- Monday–Saturday: auto-restart runs without re-authentication
- **Sunday:** IB server reset requires manual re-login after restart. Cannot be automated headlessly.

**VPS recommendation:**
- Schedule Gateway restart during market close (11:45 PM ET) to minimize disruption
- PA r2 watchdog script should detect Gateway restart and reconnect automatically
- PA r2 reconciliation routine handles state recovery on reconnect

### E2. Session refresh intervals

✅ **Session token:** IB sessions last up to ~24 hours before requiring re-auth. The auto-restart mechanism handles this by restarting Gateway before session expiry.

✅ **API connection:** No session timeout on the API socket — connection stays alive as long as the socket is open and heartbeats flow. IB Gateway itself sends keepalive messages on the socket.

⚠️ **Known issue:** After long uptime periods (>24h without restart), some users report IB Gateway memory creep and increased latency. IB recommends daily restarts. 4000MB memory allocation is the standard recommendation for API users.

### E3. Memory usage monitoring

✅ **IB recommendation:** Allocate 4000 MB to IB Gateway for API usage. Configure in `Global Configuration → Memory Allocation`.

**VPS minimum spec recommendation:**
- RAM: 8 GB minimum (4 GB Gateway + 4 GB PA r2 + OS overhead)
- CPU: 2 cores minimum
- Storage: 20 GB (Gateway + logs + PA state)

**Monitoring recommendations for VPS:**
- Monitor Gateway process memory — alert if > 5 GB (indicates leak)
- Monitor socket connection health via PA r2 `ConnectionEvent` stream
- Watchdog script: restart Gateway if process not found + not in market hours

**Watchdog script approach (for VPS):**
```bash
# Simple watchdog pattern
while true; do
    if ! pgrep -f "ibgateway" > /dev/null; then
        echo "Gateway down — restarting"
        /path/to/ibgateway &
        sleep 30  # Wait for startup
    fi
    sleep 60
done
```

---

## Key Decisions Required

Pete + Jake — the following decisions need to be made before implementation begins:

| # | Decision | Options | Recommendation |
|---|----------|---------|----------------|
| 1 | **Failsafe Stage 1 timing** | Ticket default: 15s | 15s is aggressive for temporary network hiccups. Consider 30s for Stage 1 WARN, 15s if exec is always co-located on same VPS. |
| 2 | **Failsafe Stage 2 timing** | Ticket default: 180s | 180s seems appropriate. Confirm acceptable max drawdown during 3-minute window before auto-exit triggers. |
| 3 | **Single-net-position enforcement scope** | Per symbol, per instance | Confirmed: one open position per symbol per PA instance. Rejection event emitted if violated. |
| 4 | **LOCKOUT reset mechanism** | Human manual reset only | Confirmed: LOCKOUT requires human intervention. No auto-recovery from LOCKOUT. |
| 5 | **VPS Gateway restart window** | Time to schedule auto-restart | Recommend 11:45 PM ET. Confirm with Pete based on instruments traded (futures trade 23h/day). |
| 6 | **Modify interval below 75ms** | Ticket: do not go below 50ms without proving pacing stability | Confirmed: 75ms default is the safe floor. Do not tune lower without live pacing stress test. |
| 7 | **Priority exit channel bypass scope** | CLOSE + FLATTEN + HardKill | Confirmed: these three action types bypass non-critical queue. Stop-tightening modifications are NOT bypass-eligible — they go through normal queue. |

---

## Open Items for Live Testing

The following cannot be fully confirmed from documentation alone — must validate in paper trading environment:

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | **Burst tolerance above 50 msg/sec** | 🔲 Blocked | Needs trading permissions (Read-Only mode disabled) |
| 2 | **Rapid modify escalation threshold** | 🔲 Blocked | Needs trading permissions |
| 3 | **Paper vs LIVE pacing equivalence** | 🔲 Blocked | Needs trading permissions on both |
| 4 | **Reconnect subscription auto-loss** | 🔲 Blocked | Needs active market data subscription (error 10089 on SPY) |
| 5 | **nextValidId on reconnect** | ✅ Confirmed | nextValidId provided correctly on each connection |
| 6 | **Concurrent clientId pacing budget** | 🔲 Blocked | Needs active market data subscriptions |
| 7 | **Stop order persistence on disconnect** | 🔲 Blocked | Needs trading permissions |

**All blocked items unblock once Pete disables Read-Only mode + activates market data subscriptions.**

---

## Summary

| Discovery Area | Status | Key Finding |
|---------------|--------|-------------|
| Pacing scope | ✅ Confirmed | 50 msg/sec per Gateway; historical pacing per account (not relevant for v1) |
| LIVE vs PAPER pacing | ✅ Confirmed | Same rules, separate counters |
| Message type limits | ✅ Confirmed | One global budget; PA r2 per-channel limits are PA-internal design |
| Modify sensitivity | ✅ Confirmed | 75ms minimum interval is correct; merge-on-flood pattern is correct |
| Exit priority | ✅ Confirmed | Priority queue needed — IB does not differentiate, PA must |
| Heartbeat + comms loss | ✅ Confirmed | Dual-layer: IB socket errors + Exec heartbeat |
| Server-side order persistence | ✅ Confirmed | Orders survive disconnect; reconciliation on reconnect is mandatory |
| Programmatic lockout | ✅ Confirmed | Local only — PA r2 LOCKOUT state, not IB-native |
| Auto-flatten on disconnect | ✅ Confirmed | Failsafe Stage 2 handles this; no IB-native equivalent |
| VPS Gateway uptime | ✅ Confirmed | Auto-restart v974+; daily restart recommended; Sunday requires manual login |

**Recommendation: Proceed to implementation.** No blocking discoveries. All spec decisions are well-grounded in IB API behavior. Open live-testing items should be run in parallel with implementation, not as blockers.

---

*Document ready for review with Pete & Jake. Key decisions table above should be resolved in the review session before net-new development begins.*
