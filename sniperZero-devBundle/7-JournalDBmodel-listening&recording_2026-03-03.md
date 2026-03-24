


___
# JournalDB Listening/Recording Model v0 — SniperZero

iteration: 2026-03-03.7 
status: v0  
audience: JK / Pete / Juan / future devs  
purpose: define what we record, who emits it, who consumes it, and how we avoid DB-as-hub

___

**SniperZero v1 Locked Runtime Flow (LAW)**  
`PAr2` → `Normalizer` → `Aggregator` → `MFE` → `Pattern` → `C2` → `Policy` → `RiskGov` → `Dispatcher` → `PAr2`  
`JournalDB` is a listener/recorder (append-only history). It is not in the decision flow and must not be a runtime dependency for live decisions.

___

## 0) Instructions for Juan (paste at top when sharing)
Juan — this document defines what events must be recorded to JournalDB and how PAr2 and other modules should emit them.  
PAr2 does not write directly to Postgres; it must emit structured PAEvent objects that the Journal listener stores.  
Please ensure every order/action produces a clear lifecycle trail (submitted/accepted/rejected/status/fill), plus pacing, kill, failsafe, and reconciliation events.  
Deliverable is: consistent event emission that allows replay/debug and audit.
Replay, debug, and audit workflows are supported primarily by JournalDB records and JSONL replay files.

## 1) Law: JournalDB is history, not live truth
- JournalDB is append-only durable history (audit + replay + analytics).
- Live truth for execution comes from IB (via PAr2 reconciliation + PAEvents) carried in PipelineContext.exec.
- Live truth for risk comes from RiskGov’s in-memory risk state, fed by PipelineContext.exec truth.
- No module may require a synchronous DB read on the hot path for decisions.

## 2) Two recording channels (to manage sprawl)
A) Required “Truth Trail” (must record)
- execution truth events
- command lifecycle
- kill/failsafe transitions
- reconciliation reports
- pacing warnings + cooldown actions

B) Optional “Replay/Debug” (record if enabled)
- market bars (base + aggregated)
- feature summaries
- candidates + scores + intent
- per-cycle latency metrics

We prefer replay/debug via JSONL files per run; DB stores slices.

## 3) Who emits what (minimum required)
### 3.1 PAr2 (highest priority)
PAr2 must emit PAEvents and those events must be journaled:
- MARKET_BAR (if DB logging enabled; otherwise replay file only)
- ORDER_SUBMITTED / ORDER_ACCEPTED / ORDER_REJECTED / ORDER_STATUS / FILL
- POSITION_SNAPSHOT / ACCOUNT_SNAPSHOT (optional account)
- PACING_WARNING / PACING_COOLDOWN_STARTED / PACING_COOLDOWN_ENDED
- SOFTKILL_ENABLED/DISABLED
- FAILSAFE_STAGE_CHANGED
- HARDKILL_EXECUTED
- LOCKOUT_ENABLED/DISABLED  
>LOCKOUT_ENABLED must be recorded for every FAILSAFE_STAGE_CHANGED(AUTOEXIT) when autoexit_implies_lockout=true (default).
- RECONCILIATION_REPORT
- CONNECTION_STATUS (connect/disconnect/reconnect)

### 3.2 Dispatcher (required)
Dispatcher must journal:
- CommandIssued (Risk-approved command received)
- CommandSent (PACommand sent to PAr2)
- CommandAck (accepted)
- CommandRejected (rejected + reason)
- CommandFilled (fill received)
- CommandComplete (position state achieved)
- DedupeDecision (ignored duplicate command_id)
- PriorityExitTriggered (EXIT queue used)

Dispatcher must also emit a compact execution-state summary periodically:
- current position snapshot (symbol, qty, avg)
- open orders count
- kill state

### 3.3 RiskGov (required)
RiskGov must journal:
- RiskDecision (APPROVED/VETO/FORCED_EXIT/SOFTKILL/HARDKILL) + reason
- RiskStateSnapshot (compact):
  - daily_realized_pnl
  - drawdown
  - loss_count_48h
  - rule_of_5_state
- Shock/News triggers (if any)
- Daily halt triggers + operator-reset required flag

### 3.4 Policy (optional, recommended)
Policy may journal:
- IntentFormed (intent package summary)
- SelectedCandidate (candidate_id + c_final + action)
- PolicyMode (NORMAL/SCALP/COOLDOWN)

### 3.5 C2 (optional, recommended)
C2 may journal:
- C2Snapshot (candidate_id -> c_final + sizing guidance + gates_failed)
Keep it compact.

### 3.6 Pattern (optional)
Pattern may journal:
- CandidateSet summary (counts, ids, tf, pattern_id)
Avoid logging large feature blobs unless debugging.

### 3.7 MFE / Aggregator / Normalizer (optional)
- Prefer replay JSONL for bars/aggregation outputs.
- DB logging of market bars is optional and should be configurable/downsampled.

## 4) Replayability model (how we support reproducible debugging)
We support two replay modes:

Mode A (recommended): JSONL per run for replay + DB for truth trail
- JSONL contains PipelineContext slices sufficient to replay (including aggregated bars).
- DB contains truth trail: PAEvents + decisions + commands + risk snapshots.

Mode B: DB-only replay (heavier)
- DB stores base bars and aggregated bars + enough features/candidates to replay.
- Requires careful storage controls and is more expensive.

Default: Mode A.

## 5) Storage and performance rules (avoid killing latency)
- DB writes must be asynchronous/batched. No synchronous DB writes on the decision hot path.
- Market data logging is optional and should be downsampled or moved to JSONL replay files.
- Execution events must always be recorded (truth trail).

## 6) Consumption rules (who reads DB and when)
### Live mode
- Policy/C2/Pattern/MFE do not read DB.
- RiskGov does not rely on DB reads on the hot path.
- Dispatcher does not rely on DB reads on the hot path.
- DB is write-only during live operation (append-only).

### Restart/bootstrap
- On restart, PAr2 reconciles with IB and emits RECONCILIATION_REPORT truth.
- Dispatcher and RiskGov rebuild runtime state from:
  - PA reconciliation truth (primary)
  - recent Journal trail (optional, for diagnostics; not required for correctness)

### Offline / analysis
- MetaBot (future) reads DB.
- Backtest analytics reads DB.
- RiskGov may run offline audits using DB history.

## 7) Minimal schema guidance (logical tables, not final SQL)
We will likely implement these logical tables:

- journal_events:
  - ts, session_id, cycle_id, module, event_type, symbol, payload_json

- executions:
  - session_id, symbol, broker_order_id, command_id, status, fills_json

- positions_snapshots:
  - ts, session_id, symbol, qty, avg_price, unrealized_pnl_json

- risk_snapshots:
  - ts, session_id, daily_pnl, drawdown, loss_count_48h, rule_of_5_state, payload_json

- reconciliations:
  - ts, session_id, report_id, positions_json, orders_json, account_json, notes

- alerts:
  - ts, session_id, severity, type, message, payload_json

The final Postgres schema will follow this model.

## 8) Config toggles (minimum)
- journal.enabled (true/false)
- journal.mode ("TRUTH_ONLY" | "TRUTH_PLUS_DEBUG")
- journal.market_log_enabled (true/false)
- journal.market_log_downsample (int)
- replay_jsonl_enabled (true/false)
- replay_jsonl_roll_hours (default 8)

End of JournalDB model v0





