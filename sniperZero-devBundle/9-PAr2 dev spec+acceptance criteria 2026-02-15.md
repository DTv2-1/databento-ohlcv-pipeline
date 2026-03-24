
iteration: 2026-03-03.7
project: SniperZero – Platform Adapter Release 2 (PAr2)
audience: JK / Pete / Juan  

___

**SniperZero v1 Locked Runtime Flow (LAW)**  
`PAr2` → `Normalizer` → `Aggregator` → `MFE` → `Pattern` → `C2` → `Policy` → `RiskGov` → `Dispatcher` → `PAr2`  
`JournalDB` is a listener/recorder (append-only history). It is not in the decision flow and must not be a runtime dependency for live decisions.

**PAr2 Implementation Dependencies (LAW)**  
PAr2 must implement against our contracts: **PipelineContext v0** (runtime package), **PA Wire Contract v0** (PACommand/PAEvent shapes), and the **JournalDB listening model v0** (what events must be emitted for durable recording). These are required for correct downstream behavior and replay/debug; implementers must propose changes to the contracts before deviating.

___

# PAr2 Module Spec v0 (IB-first)

## 0) Purpose
PAr2 is the execution + enforcement boundary between SniperZero runtime and Interactive Brokers (IB).
It must execute commands deterministically, enforce API pacing safety, and survive disconnects/restarts.

PAr2 is NOT a strategy engine.
PAr2 executes; it does not decide.

Law: Commands are not execution truth.
- Outbound commands (Dispatcher → PAr2) are instructions.
- Execution truth comes from IB via PAr2 (order status, fills, positions, reconciliation).
- PAr2 must emit execution truth as PAEvents to be carried forward in PipelineContext.exec and recorded by JournalDB.

## 1) Scope (What PAr2 MUST do)
1. Connect to IB via IB Gateway (VPS), Python socket API.
	1A. Support execution mode selection: LIVE or IB PAPER (simulated).
	   - One mode per instance/session (cannot execute both simultaneously).
	   - Switching mode requires restart (recommended).
	   - All enforcement behavior (rate limits, throttles, kills, reconciliation, logging) must be identical in both modes.
2. Deployment target: AWS VPS (Linux), headless IB Gateway + watchdog restart script
3. Ingest live market data (bars/quotes) from IB/Gateway and emit structured market events into the runtime pipeline (Normalizer consumes and canonicalizes).
4. Execute trade commands received ONLY from Dispatcher (Command Router):
   - OPEN / ADD / CLOSE (close position for a symbol) / FLATTEN (close ALL positions)
   - STOP placement and STOP modification
4. Enforce safety constraints:
   - per-channel rate limiting (market data / place / modify / cancel / misc)
   - order queue (single ingress)
	   - enforce single-net-position per symbol per instance:
		  - if an OPEN/ADD command would violate this constraint, PAr2 must reject it and log the rejection 
   - burst control + pacing recovery (cooldown/backoff)
   - stop-modify throttling (min interval + min delta)
5. Kill execution behaviors:
   - SoftKill (no new risk)
   - Failsafe (heartbeat loss staged behavior)
   - HardKill (panic flatten)
6. Restart reconciliation:
   - reconcile PAr2-maintained execution state cache vs IB truth (IB is authoritative)
1. Persistence hooks:
   - emit journal/telemetry events for Postgres/logging (PA does not own DB, that is in the module journalDB)

## 2) Non-Goals (Explicitly forbidden)
PAr2 MUST NOT:
- compute indicators, signals, patterns, confidence scores
- decide entries/exits or “trade management”
- call IB historical data endpoints in v1 (historical comes from Databento/MASSIVE CSV ingestion)

## 3) System Boundary / Contract
Only Dispatcher (Command Router) may call PAr2 command methods.
All other modules must communicate through the locked pipeline and produce commands via Policy → RiskGov → Dispatcher.

PAr2 provides:
- Market data stream (structured events) → Normalizer (canonicalization happens in Normalizer)
- Execution API (methods) ← Dispatcher (Command Router)
- Execution truth events (fills/status/errors/reconcile/kill/pacing) → emitted by PAr2 as PAEvents and recorded in PipelineContext.exec for the next cycle. This is not a side-channel; it is the start of the next PipelineContext cycle.

## 4) Minimal Public Interface (methods)
(Names are suggestions; exact naming flexible, behavior is not.)

Connection:
- connect()
- disconnect()
- status() -> {connected, last_heartbeat_ts, last_ib_msg_ts, lockout_state}

Market data:
- subscribe_bars(symbol, bar_size, source="TRADES")
- unsubscribe_bars(symbol, bar_size)
- subscribe_quote(symbol)
- unsubscribe_quote(symbol)

Orders:
- place_order(order_spec) -> client_order_id
- place_stop(stop_spec) -> client_order_id
- modify_order(order_id, changes)
- cancel_order(order_id)

Kills:
- set_softkill(enabled: bool (true/false), reason: str)
- hardkill(reason: str)
- set_lockout(enabled: bool (true/false), reason: str)   # local lockout, not “broker lock”

Failsafe / heartbeat:
- heartbeat_from_dispatcher(ts) # Dispatcher pings PA
- set_failsafe_policy(cfg) # timers, behavior

Reconciliation:
- reconcile_state() -> reconciliation_report

## 5) Events emitted by PAr2 (into runtime pipeline / execution truth)
**NOTE:** *All emitted events must conform to PAEvent taxonomy in PAr2 WireContract v0.* 
PA emits structured PAEvents (JSON-serializable) into the runtime (for PipelineContext.exec and Journal recording):
- OnConnectionStatus(connected/disconnected, reason)
- OnPacingEvent(type, channel, rate, action_taken)
- OnOrderAccepted(order_id)
- OnOrderRejected(order_id, reason_code, message)
- OnOrderStatus(order_id, status, filled_qty, avg_price, etc.)
- OnFill(order_id, symbol, side, qty, price, ts)
- OnPositionUpdate(symbol, qty, avg_price, unrealized_pnl)
- OnAccountUpdate(equity, margin, buying_power)
- OnKillStateChanged(state, reason)
- OnFailsafeStageChanged(stage, reason)

## 6) Rate Limiting & Queueing (hard rules)
PAr2 must implement:
- Single order queue (all order actions go through queue)
- Per-channel token bucket (or leaky bucket) rate limiters:
  Channels:
  - market_data_subscribe
  - order_place
  - order_modify
  - order_cancel
  - misc (account/positions queries)

Default thresholds (configurable):
- sustained_msg_rate_max = 20 msg/sec (aggregate across channels)
- burst_msg_rate_max    = 40 msg/sec (short burst cap)
- channel_caps          = configurable per channel (safe defaults lower than global)
- pacing_cooldown_sec   = 5 sec (first violation), escalates on repeats

Behavior:
- If queue would exceed caps: PAr2 must delay (throttle), not spam IB.
- If pacing violation detected: enter pacing recovery (Section 8).

Priority EXIT channel:
- PAr2 must implement a priority path for CLOSE/FLATTEN/HARDKILL actions.
- Priority EXIT actions must jump ahead of non-critical queue items.
- Priority EXIT actions must bypass stop-modify throttling.
- Priority EXIT actions still respect absolute global safety caps, but are always serviced first.
## 7) Stop Modify Throttling (no micro-adjust loops)
Stop modifications are the #1 pacing killer.

PAr2 must enforce:
- stop_modify_min_interval_ms = 75ms (configurable; floor can be set to 50ms but ONLY after proven stability/pacing validation)
- stop_modify_min_delta_ticks = 1 tick (or equivalent pip/price increment), configurable
- “tighten-only” option (config): in SoftKill/Failsafe Freeze, allow only tightening protection

Behavior:
- PA merges successive stop updates:
  - if a new stop arrives before interval elapsed, keep the latest valid update and apply when interval allows
  - discard “no meaningful change” updates (< min delta)
- CLOSE/FLATTEN/HARDKILL actions bypass stop-modify throttling entirely (Priority EXIT channel).

## 8) Pacing Recovery (cooldown/backoff)
If IB returns pacing warnings/rejections:
PAr2 must:
1) log pacing event with channel + rates + IB code/message
2) temporarily restrict non-critical sends
3) apply cooldown timer (base 5s, exponential backoff on repeats)
4) resume gradually (queue drain with limiter)
5) escalate to SoftKill if repeated pacing violations exceed threshold (config)

Critical messages allowed during pacing recovery (Priority EXIT semantics):
- CLOSE (symbol position)
- FLATTEN (all positions)
- HARDKILL (flatten + cancel + lockout)
- protective stop placement (if missing)
Everything else delayed.

## 9) Kill States (exact semantics)
Kill logic is EXECUTED by PAr2, DECIDED in the runtime pipeline (Policy → RiskGov → Dispatcher → PAr2).

SoftKill (no new risk):
- block NEW OPEN and NEW ADD commands
- allow CLOSE commands
- allow protective stop placement/modification (tighten-only recommended)
- continue receiving/streaming market data (unless market-data pacing requires reduction)

HardKill (panic):
- immediately send CLOSE/flatten for all open positions
- cancel all open orders
- set local lockout = ON until human reset (MANDATORY; failsafe.autoexit_implies_lockout default=true, kill.lockout_on_hardkill default=true)
- continue to log all actions/events

## 10) Failsafe (heartbeat loss) — 3-stage sequence (conservative)
Failsafe is a last line of defense.

Trigger source:
- Loss of heartbeat_from_dispatcher for a configured period
(IB connection loss can ALSO trigger failsafe stage changes.)

Stages (default conservative; configurable):
- Stage 0 Normal: heartbeat OK
- Stage 1 Freeze (T_freeze = 15s):
  - block NEW OPEN/ADD
  - allow CLOSE
  - allow protective stop updates (tighten-only recommended)
  - do not flatten yet
- Stage 2 AutoExit (T_flatten = 180s):
  - flatten all positions
  - cancel all open orders
  - set local lockout ON until human reset (MANDATORY; failsafe.autoexit_implies_lockout default=true)
  - emit LOCKOUT_ENABLED event

Rationale:
- prevents false-positive liquidation on brief hiccups
- still exits if the runtime is truly dead

## 11) Restart Reconciliation (must be explicit)
On connect/reconnect/restart, PAr2 must:
1) request positions from IB
2) request open orders from IB
3) request account summary (as needed)
4) update local runtime state to match IB truth (IB is source of truth)
5) identify orphan local orders vs IB orders and resolve per policy:
   - cancel unknown orders? (config)
   - keep IB orders and adopt into local state? (default is to CLOSE unexpected OPEN positions, CANCEL unknown OPEN orders)
1) emit reconciliation_report event and log to journal

## 12) Persistence & Journal Integration
PAr2 must emit structured log events for ingestion into Journal (Postgres):
- order lifecycle
- fills
- kill state changes
- failsafe stage changes
- pacing events + recovery actions
- reconciliation reports
- connectivity incidents + reconnect attempts

PA does NOT own the DB; it only emits events.

## 13) Configuration (PAr2 config keys)
Required config keys (names flexible):
- ib.host, ib.port, ib.client_id
- ib.trading_mode (LIVE | PAPER)   # one mode per instance; restart to switch
- rate.global_sustained_max
- rate.global_burst_max
- exit.priority_enabled (true|false)  # default true; CLOSE/FLATTEN/HARDKILL jump queue
- rate.channel_caps.{market_data_subscribe,order_place,order_modify,order_cancel,misc}
- pacing.cooldown_base_sec
- pacing.backoff_multiplier
- stop.min_modify_interval_ms
- stop.min_modify_delta_ticks_or_pips
- stop.tighten_only_in_softkill
- failsafe.t_freeze_sec
- failsafe.t_flatten_sec
- failsafe.autoexit_implies_lockout (default true)
- kill.lockout_on_hardkill (default `true`) 
- reconcile.policy (adopt_ib_orders/cancel_unknown/etc)
	- config; defaults to cancel_unknown/close/etc
	     **Specific Values:**
	   - **Unknown open orders → CANCEL**
	   - **Unexpected open position → CLOSE, forced flatten + lockout**

## 14) Hard Acceptance Criteria (tests Pete can hold us to)
PAr2 is accepted only if ALL are true:

Rate limiting:
- Under stress test, PA never exceeds sustained 20 msg/sec or burst 40 msg/sec (configurable).
- Per-channel caps enforced (visible in logs).
- Queue delays requests rather than spamming IB.

Stop throttling:
- Stop modifications respect min interval and min delta.
- No stop “micro-adjust loops” (verified by logs).

Pacing recovery:
- Pacing violations are detected, logged, and trigger cooldown.
- During cooldown, non-critical traffic is delayed; critical CLOSE/kill actions still execute.

Failsafe:
- If Dispatcher heartbeat stops:
  - Stage 1 Freeze occurs at ~15s (default)
  - Stage 2 AutoExit occurs at ~180s (default)
  - Events/logs are emitted for stage transitions
- AutoExit results in positions flattened + orders canceled + LOCKOUT_ENABLED emitted (failsafe.autoexit_implies_lockout default=true)

Reconciliation:
- After restart, PA reconciles positions/orders with IB and emits report.
- Local state matches IB truth after reconciliation.

Isolation:
- Only Dispatcher (Command Router) can call PAr2 commands (enforced via architecture / interface).
- PA does not compute strategy logic (verified by code review).

IB historical:
- PA makes zero historical-data requests in v1 (verified by logs).

Paper vs Live mode:
- When trading_mode=PAPER, orders do not affect the LIVE account (verified by IB account state).
- When trading_mode=LIVE, orders do not affect the PAPER account.
- Mode is logged at startup and included in reconciliation reports.
- Switching mode requires process restart (policy enforced by operator runbook and/or code guard).

Observability:
- All critical events are journaled: fills, rejects, pacing, kills, failsafe, reconnects.

___
END SPEC (v0)






