
iteration: 2026-03-03.7 
project: SniperZero – [PAr2 Architecture Hardening]
audience: JK / Pete / Juan  

___


### Running TODO 

1. PipelineContext v0 ✅ _(now)_
2. PAr2 Wire Contract v0 template
3. JournalDB listening/recording model v0
4. Quick consistency re-check (ticket/spec/checklist) + CR addendum after contracts
5. **Create CR for Pattern + C2 dedicated thread** (new)

---

# PipelineContext v0 — SniperZero Runtime Package Contract

iteration: 2026-03-03.2  
status: v0 (architecture-locked; broker-agnostic)  
audience: Q, Pete, Juan, future devs  
purpose: define the single “package” passed module-to-module in the locked pipeline loop

## 1) Law: Locked pipeline flow

PAr2 → Normalizer → Aggregator → MFE → Pattern → C2 → Policy → RiskGov → Dispatcher → PAr2

No bypass paths. No side-channel dependencies. The package carries forward state required for correct decisions.

`JournalDB` is a listener/recorder (append-only history). It is not in the decision flow and must not be a runtime dependency for live decisions.

## 2) Law: Command vs Truth

- Commands (Dispatcher → PAr2) are instructions, not proof.
- Truth comes only from IB via PAr2:
    - execution events (accepted/rejected/status/fill)
    - reconciliation snapshots (positions/orders/account)
- Truth is appended into PipelineContext.exec and carried through the loop.

## 3) Construction: where and when the package is created

- PipelineContext is created at the start of each cycle by **PAr2** when it emits the next-cycle input into the pipeline.
- It is then transformed/extended by each module in order.
- “Cycle” is triggered by one of:
    - new market bar / bar_update / bar_close (per configured base feed)
    - execution event arrival (fill/status/pacing/kill/reconcile) that must be processed promptly
    - operator control event (kill/mode change) that must be acted on promptly

## 4) Persistence: file format if persistent

Default: in-memory object passed through runtime loop.  
when persisted:
- JSON Lines (one context per line) for debug/replay, 
	- file will be created per run or per 8hr loop, whichever is smaller
	- file will contain all details needed for replay and debug, including aggregated bars
- with split persistence: persist only selected slices to JournalDB, not the entire context

## 5) JournalDB: what must be recorded

JournalDB is append-only durable history, not live state.

Minimum records per cycle:
- ctx.meta (cycle identifiers + timestamps + mode)
- ctx.exec.events + ctx.exec.reconciliation (execution truth events + reconciliation snapshot summary) 
- ctx.intent + ctx.risk.decision + ctx.dispatch.result (command lifecycle summary)
- any pacing/kill/failsafe state transitions
- Feature snapshots: optional if JSONL replay is enabled (we can recompute features from persisted bars); otherwise store minimal feature summaries needed for post-mortem analysis. 

## 6) Structure (v0)

PipelineContext has three top-level sections:
A) meta  (meta = timing + identifiers)
B) market  (market = bars/features/candidates)
C) exec  (exec = broker truth + safety state)
These three sections are always present in every PipelineContext instance.
Downstream sections are appended later in the same object: intent, risk, dispatch.

### PipelineContext Ownership Map (LAW)
- PAr2 owns: ctx.exec + ctx.meta creation
- Normalizer owns: canonicalization into ctx.market.bars (base) and canonical shaping of ctx.exec.events (schema-only, no semantic inference)
- Aggregator owns: ctx.market.bars.by_tf
- MFE owns: ctx.market.features.by_tf
- Pattern owns: ctx.market.candidates
- C2 owns: ctx.market.scored_candidates
- Policy owns: ctx.intent
- RiskGov owns: ctx.risk
- Dispatcher owns: ctx.dispatch
**LAW**: ctx.dispatch may record only outbound intent + lifecycle bookkeeping.
All confirmations live in ctx.exec.events / reconciliation.

### Immutability Rule (LAW):
Modules MUST NOT mutate subtrees owned by earlier modules.

### 6.1 meta (always present):

- `ctx_id`: unique id for this context instance
- `cycle_id`: monotonically increasing per runtime session
- `session_id`: stable id for the runtime process session
- `created_ts_utc_ms`: when PAr2 created this context
- `trigger`: one of [MARKET_UPDATE, MARKET_CLOSE, EXEC_EVENT, OPERATOR_EVENT, RECONNECT]
	- If `trigger == EXEC_EVENT`, then the cycle **must carry** the exec event(s) that caused it  
    - If `trigger == OPERATOR_EVENT`, then the cycle **must carry** the operator command payload (even if redacted) 
- `trading_mode`: LIVE | PAPER
- `symbol`: primary symbol for this instance
- `config_hash`: hash of runtime config (optional but recommended)
- `prev_ctx_id`
- `event_batch_id`
- `trace_id`
- `source_seq`
- timing:
    - `ts_ingest_start`, `ts_ingest_end`
    - `ts_features_done`
    - `ts_pattern_done`
    - `ts_c2_done`
    - `ts_policy_done`
    - `ts_risk_done`
    - `ts_dispatch_done`  
        (used to enforce NFR latency budgets)

### 6.2 market (populated by Normalizer/Aggregator/MFE/Pattern/C2)

market contains only market-side data and derived features.

- feed:
    - raw_events_summary (optional; count + last_ts)
- bars:
    - `base_tf`: e.g., "1s" or "15s"
    - `by_tf`: map of tf -> bar bundle  
        Each bar bundle:
        - `tf`
        - `bar_state`: UPDATE | CLOSE
        - `ts`
        - ohlcv
        - `source`: TRADES | MID | etc (if known)
- features:
    - by_tf: map of tf -> FeatureFrame  
        FeatureFrame:
        - ts
        - tf
        - indicators: key->number/bool (true/false, never 1/0)
        - derived: key->number/bool
- candidates (appended by Pattern):
    - CandidateSet:
        - ts
        - candidates: list of Candidate  
            Candidate:
	        - candidate_id
	        - action: OPEN | ADD | EXIT | HOLD | ADJUST_STOP_HINT
	        - direction: LONG | SHORT | NONE
	        - tf
	        - pattern_id
	        - pattern_features: dict
	        - notes (optional, short)
- scored_candidates (appended by C2):
    - ScoredCandidateSet:
        - ts
        - scored: list of ScoredCandidate  
            ScoredCandidate:
	        - candidate_id
	        - c_final (0..1, may exceed 1 with bonus)
	        - pass_min_conf (bool; e.g. >=0.65)
	        - sizing_guidance (risk_multiplier, capital_slice_pct, add_slice_pct)
	        - gates_failed (list)
	        - explain (optional, short)

### 6.3 exec (truth + safety state; sourced from PAr2)

exec contains execution truth and safety enforcement state. It is never inferred from outbound commands.

- connection:
    - ib_connected: bool
    - gateway_host, gateway_port (optional)
    - last_connect_ts
    - last_disconnect_ts + reason (optional)
- kill_state:
    - softkill_enabled: bool
    - failsafe_stage: NORMAL | FREEZE | AUTOEXIT
    - hardkill_last_ts (optional)
    - lockout_enabled: bool
    - lockout_reason (optional)
  **LAW**: If failsafe_stage == AUTOEXIT and failsafe.autoexit_implies_lockout == true (default), then lockout_enabled must be true until operator reset.
- pacing:
    - pacing_active: bool
    - cooldown_until_ts (optional)
    - last_pacing_event (optional)
- reconciliation (append-only snapshots; latest is truth):
    - last_reconcile_ts
    - positions_snapshot (symbol, qty, avg_price, unrealized_pnl if available)
    - open_orders_snapshot (list; minimal fields)
    - account_snapshot (optional; equity/margin/buying_power)
    - reconcile_report_id (optional)
  - **LAW:** `positions_snapshot` and `open_orders_snapshot` MUST be full snapshots of current IB truth at reconcile time (not deltas).
- events (execution events since last cycle):
    - pa_events: list of PAEvent (JSON-serializable; MUST conform to PAr2 Wire Contract v0)  
        PAEvent types include:
        - ORDER_ACCEPTED / ORDER_REJECTED / ORDER_STATUS / FILL
        - POSITION_SNAPSHOT / ACCOUNT_SNAPSHOT
        - PACING_EVENT
        - KILL_STATE_CHANGED / FAILSAFE_STAGE_CHANGED
        - RECONCILIATION_REPORT
        - CONNECTION_STATUS

## 7) Downstream decision sections appended (v0)

These sections are appended later in the pipeline. They must not mutate exec truth.

### 7.1 intent (appended by Policy)

- intent_package:
    - selected actions (may include compatible multi-actions like HOLD + STOP_ADJUST)
    - provenance (candidate_id, c_final)
    - priority: EXIT | NORMAL

### 7.2 risk (appended by RiskGov)

- risk_decision:
    - status: APPROVED | VETO | FORCED_EXIT | SOFTKILL | HARDKILL
    - reason
    - overrides (e.g., tighten_only)
- risk_state_summary (optional snapshot for logging):
    - daily_realized_pnl
    - drawdown
    - loss_count_48h
    - rule_of_5_state

### 7.3 dispatch (appended by Dispatcher)

- approved_commands_sent:
    - list of PACommands issued (ids, types, priority)
    - `dispatch` is what we **attempted**
    - `exec.events` is what **happened**
- command_lifecycle:
    - command_id -> broker_order_id mapping
    - dedupe decisions
    - last_fill_ts
- notes (optional)

## 8) Module rules: transform vs append

- PAr2: constructs ctx + appends exec truth
- Normalizer: transforms inbound market/execution events into canonical schema; appends to market/exec as appropriate
	- Normalizer **MUST** preserve source truth fields without inventing “meaning”
	- LAW: Normalizer may only canonicalize exec event SHAPE (field names/types); it must not infer, aggregate, or reinterpret execution truth.
- Aggregator: appends bars.by_tf
- MFE: appends features.by_tf
- Pattern: appends market.candidates (does not overwrite features)
- C2: appends market.scored_candidates (does not overwrite candidates)
- Policy: appends intent (does not overwrite scored_candidates)
- RiskGov: appends risk (does not overwrite intent)
- Dispatcher: appends dispatch + issues outbound PA commands (does not overwrite risk)

Default mutation policy: append-only. Transform allowed only by owner module on its owned subtrees (e.g., Normalizer canonicalization).

## 9) Versioning + compatibility rules

- ctx.meta.contract_version = "PipelineContext.v0"
- v0 additions are allowed only if:
    - backward compatible (new optional fields)
    - do not change meaning of existing fields
- breaking changes require new version tag (v1) and explicit approval (architecture change classification)

## 10) Epistemic/ontological rules

- Do not infer execution truth from commands.
- Do not infer risk state from market state alone; risk state is maintained by RiskGov.
- Treat IB reconciliation snapshot as truth after reconnect.
- Avoid “bus” language. This is a looped pipeline contract.
- in this artifact and in SniperZero as a whole, "bool" will mean "true/false" and never represented as "1/0" unless we are forced to do so due to programming language constraints 
- “Configured base feed” = the smallest timeframe we ingest from the platform adapter (e.g., 1s or 15s). 
	- The aggregator then builds additional TFs from this base feed per config.

---



