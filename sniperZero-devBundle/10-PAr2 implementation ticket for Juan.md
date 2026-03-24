iteration: 2026-03-03.7
project: SniperZero – PAr2 Architecture Hardening
audience: JK / Pete / Juan  

___

**SniperZero v1 Locked Runtime Flow (LAW)**  
`PAr2` → `Normalizer` → `Aggregator` → `MFE` → `Pattern` → `C2` → `Policy` → `RiskGov` → `Dispatcher` → `PAr2`  
`JournalDB` is a listener/recorder (append-only history). It is not in the decision flow and must not be a runtime dependency for live decisions.

**PAr2 Implementation Dependencies (LAW)**  
PAr2 must implement against our contracts: **PipelineContext v0** (runtime package), **PA Wire Contract v0** (PACommand/PAEvent shapes), and the **JournalDB listening model v0** (what events must be emitted for durable recording). These are required for correct downstream behavior and replay/debug; implementers must propose changes to the contracts before deviating.

___

## Ticket: PAr2 (Release 2) — IB Execution Enforcement Layer (SniperZero)

**Goal:** Upgrade existing Raptor PA (Release 1 connector) into **PAr2** for SniperZero: an **execution + enforcement** layer. Not a rewrite; structural hardening.

### Must run on

- **IB Gateway on VPS**
- Python socket API (ibapi / ib_insync acceptable if stable)
- Primary deployment target: AWS VPS (Linux), headless IB Gateway + watchdog restart script.
	Local development must also be supported (connect to local IB Gateway/TWS).

### Hard architecture rules

- **Only Dispatcher (Command Router) may call PAr2 order methods.**
- PA **executes commands**, does not decide strategy or risk.
- All emitted events must conform to PAEvent taxonomy and envelope in PAr2 WireContract v0. 
- **No IB historical data calls** in v1 (we use Databento/MASSIVE CSV for history).
	- Live market subscriptions (base feed only) may be used if required for runtime operation.

##### Idempotency rule:
EXIT intents (CLOSE/FLATTEN/HARDKILL) must be safe to repeat.
If already flat, PAr2 should emit a no-op status event rather than erroring.

##### Canonical config keys (v0):
- ib.trading_mode (LIVE|PAPER)
- pacing.sustained_msgs_per_sec
- pacing.burst_msgs_per_sec
- stop_modify.min_modify_interval_ms
- stop_modify.min_delta_ticks_or_pips
- failsafe.freeze_after_ms
- failsafe.autoexit_after_ms
- failsafe.autoexit_implies_lockout (default true)

### Acceptance Parameters: 
- Priority EXIT preempts NORMAL
- AutoExit triggers lockout (default true)
- Reconciliation emits RECONCILIATION_REPORT
- All lifecycle events include command_id
- No synchronous DB reads/writes on hot path

### Core features to implement

1. **Order Queue (single ingress)**
	- All place/modify/cancel go through one queue.
	- Queue is drained by rate limiters.
	- PAr2 must enforce single-net-position per symbol per instance (reject + log invalid OPEN/ADD).
	If an OPEN/ADD command would violate this rule, PAr2 must reject the command and emit a structured rejection event.

2. **Per-channel Rate Limiting + Burst Control**  
    Implement token/leaky bucket limiters for:
	- `market_data_subscribe`
	- `order_place`
	- `order_modify`
	- `order_cancel`
	- `misc` (positions/account queries)

	Defaults (configurable):
	- sustained max: **20 msg/sec**
	- burst max: **40 msg/sec**

3. **Stop Modify Throttling (no micro-adjust loops)**
	- `min_modify_interval_ms`: default **75ms** (configurable higher; do not set below 50ms without proving pacing stability)
	- `min_delta_ticks_or_pips`: default **1**
		- NOTE: application V1 _strategy logic_ relies on _bars_, we do not subscribe to tick-by-tick feeds in v1 due to pacing/throughput risk.
	- Merge updates inside interval, apply latest when allowed.
	- In SoftKill/Failsafe Freeze: **tighten-only** recommended.

4. **Pacing Recovery**  
    On pacing warnings/rejections:
	- log event
	- cooldown/backoff (base 5s, exponential on repeats)
	- allow critical actions (CLOSE/kill/protective stop) while delaying non-critical

5. **Kill states (PAr2 executes; runtime pipeline decides)**
	- **SoftKill:** block NEW OPEN/ADD; allow CLOSE + protective stop updates
	- **HardKill:** flatten all positions + cancel all orders immediately + set local lockout until human reset
	- **Failsafe (heartbeat loss 3-stage):**
	    - Stage 1 Freeze at default **15s** (configurable): block OPEN/ADD; allow CLOSE + tighten stops
	    - Stage 2 AutoExit at default **180s** (configurable; conservative default): flatten + cancel + local lockout
			LAW: AutoExit implies LOCKOUT (failsafe.autoexit_implies_lockout default=true).
			PAr2 must emit LOCKOUT_ENABLED after FAILSAFE_STAGE_CHANGED(AUTOEXIT).

6. **Restart Reconciliation**  
    On reconnect/restart:
	- query IB positions
	- query IB open orders
	- query account summary as needed
	- reconcile local state to IB truth
	- emit reconciliation report event + log

7. Structured Execution Events (Next-cycle execution truth)
	Execution events enter the next PipelineContext cycle via PAr2 → Normalizer as PAEvents carried in PipelineContext.exec. This is not a side-channel or bus.
	PAr2 must emit structured events for downstream consumers (Dispatcher, Journal, RiskGov).
	All emitted events must conform to the PAEvent envelope and taxonomy defined in PAr2 WireContract v0.
	
	Required event categories:
	(*Law: commands are not execution truth. PAr2 must emit IB-derived execution truth (status/fills/positions/reconcile) as events; downstream must not infer truth from commands.*)
	- Connection status changes
	- Order lifecycle (submitted, accepted, rejected, filled, canceled, partially filled)
	- Position updates
	- Account summary updates (if subscribed)
	- Pacing warnings + cooldown activation
	- Kill state transitions (SoftKill/HardKill/Failsafe stages)
	- Reconciliation reports

	All events must:
	- Include timestamp (UTC)
	- Include symbol (if applicable)
	- Include unique identifiers (order_id, client_id)
	- Be machine-readable (JSON-serializable structure)

8. Live / Paper Mode Support
	- Config key: `ib.trading_mode` = LIVE | PAPER
	- One mode per instance (restart required to switch)
	- All trading logic identical in both modes
	- Account balances are separate (IB real vs IB simulated)
	- Mode must be logged at startup and included in all reconciliation reports


9. Priority EXIT Channel
	- Implement a high-priority queue/channel for CLOSE/FLATTEN/HARDKILL actions.
	- Priority exits must bypass stop-modify throttling and jump ahead of non-critical actions.
	- Maintain global rate safety, but always service exits first.

___

### Discovery first (before tuning numbers)

Confirm IB pacing scope:
- per session vs per account vs per connection
- sensitivity to modify/cancel loops
- official pacing codes and escalation behavior

### Deliverables

- `pa_r2/` module with:
    - adapter core + queue + rate limiter + pacing recovery
    - kill state machine + failsafe heartbeat monitor
        Heartbeat source: pipeline loop heartbeat from Dispatcher (or configured upstream service).
		PAr2 must detect loss of heartbeat for T_freeze / T_flatten thresholds.
    - reconciliation routine
    - event emitter
    - config schema
- Short README: how to run on VPS with IB Gateway
- Test harness script:
    - pacing stress test
    - stop modify spam test (should throttle/merge)
    - simulated heartbeat loss test (15s → freeze, 180s → autoexit)




