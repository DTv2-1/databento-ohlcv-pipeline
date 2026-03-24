SniperZero v1 — Lifecycle Flow Chart (LFC)
iteration: 2026-03-03.7
scope: Operator start → trading day → shutdown → restart recovery
note: one symbol per instance; LIVE or PAPER per instance (restart to switch)

___

**SniperZero v1 Locked Runtime Flow (LAW)**  
`PAr2` → `Normalizer` → `Aggregator` → `MFE` → `Pattern` → `C2` → `Policy` → `RiskGov` → `Dispatcher` → `PAr2`  
`JournalDB` is a listener/recorder (append-only history). It is not in the decision flow and must not be a runtime dependency for live decisions.

___


LEGEND
- [Module] = runtime module/process
- (Event)  = emitted event/telemetry
- {State}  = persisted/critical state
- -->      = control or data flow

================================================================================
0) PRE-FLIGHT (Operator / User Stack)
================================================================================
Operator:
  - selects symbol + contract set (e.g., ES micro/mini), timeframes, mode (LIVE/PAPER)
  - confirms risk caps + kill timers + PA rate/stop throttles
  - confirms "one net position per symbol per instance" rule is ON

Outputs:
  - runtime_config.json (immutable for this session)
  - (Event) OperatorSessionStart

================================================================================
1) BOOT SEQUENCE (Cold Start)
================================================================================
1.1 [Config+Mode Loader]
  - load runtime_config
  - validate schema + required keys
  - lock trading_mode = LIVE|PAPER (restart required to change)
  - publish config to all modules
  - (Event) ConfigLoaded(trading_mode, symbol, tf_set)

FAIL -> abort startup, alert operator

1.2 [PAr2] connect
  - start IB Gateway (VPS) OR confirm reachable (local dev allowed)
  - connect to IB Gateway socket API (with client_id)
  - subscribe required streams (per config):
      - bars/quotes for base feed (e.g., 1s or 15s)
      - account summary / positions (as needed)
  - enable enforcement subsystems:
      - single order queue
      - per-channel rate limiters
      - burst caps
      - pacing recovery
      - stop-modify throttle (interval+delta+merge)
      - kill state machine (SoftKill/Failsafe/HardKill)
  - (Event) PAConnected / PAConnectFailed
  - enforce trading_mode (LIVE or PAPER) at connection boundary (cannot mix within instance)

FAIL -> retry policy; if fails beyond N attempts -> abort + alert operator

1.3 [PAr2] RECONCILE (mandatory on boot)
  - query IB truth:
      - positions
      - open orders
      - account balances
  - emit reconciliation report upstream
  - adopt/cancel orphan orders per policy (config, default to cancel) 
	       **Specific Values:**
	   - **Unknown open orders → CANCEL**
	   - **Unexpected open position → CLOSE, forced flatten + lockout**
  - set local lockout if unsafe mismatch detected 
  - (Event) ReconciliationReport

1.4 [Runtime Pipeline] start dataflow
  - [Normalizer] begins canonicalizing inbound market/execution events
  - [Aggregator] begins producing configured TF bars (bar_update + bar_close)
  - [MFE] begins computing indicators/features per TF
  - (Event) RuntimeDataFlowStarted

================================================================================
2) MAIN LOOP (Per Update Tick)
================================================================================
Each cycle operates on a PipelineContext package.

Modules append or transform only their owned subtree and pass the package forward.
No module may reach sideways for data outside the PipelineContext.

Trigger sources (one or more):
  - new base bar (1s/15s) OR bar_update event OR bar_close event
  - execution event (fill/order status)
  - risk timer/heartbeat tick

2.1 Data Prep ("Fridge")
	Rule:
	PAr2 emits raw/structured market events only.
	Canonicalization (schema, timestamps, symbol mapping) is owned exclusively by Normalizer.
  [Normalizer] --> canonical_event
  [Aggregator] --> mtf_bar_events
	  Aggregator must remain deterministic and replayable from canonical base events.

2.2 Feature Compute ("Kitchen")
  [MFE] consumes mtf_bar_events
  --> FeatureFrame (indicators + derived features)
  (Event) FeatureFrameSnapshot (optional, for journaling)

2.3 Candidate Generation ("Kitchen")
  [Pattern Engine] consumes:
    - mtf bars
    - FeatureFrame (forwarded, not recomputed)
  --> CandidateSet:
    - OPEN / ADD / EXIT / HOLD / ADJUST_STOP_HINT
    - candidate features (evidence)
  (Event) CandidateSet (optional)

2.4 Candidate Scoring ("Kitchen")
  [C2 Engine] consumes:
    - CandidateSet + candidate features
    - FeatureFrame (forwarded)
  --> ScoredCandidateSet:
    - c_final scalar 0..1 (+bonus >1 possible)
    - sizing guidance
    - reject/gate reasons
  (Event) C2Snapshot (important for Journal)

2.5 Intent Formation ("Table/Plating")
  [Policy Engine] consumes:
    - ScoredCandidateSet
    - current execution truth snapshot (positions + open orders) carried in PipelineContext.exec (IB truth via PAr2)
  --> IntentPackage:
    - may include multiple compatible intents in one cycle:
        e.g., HOLD + STOP_ADJUST
    - OPEN / ADD / EXIT remain mutually exclusive unless explicitly allowed by a future rule update.
  (Event) IntentFormed

2.6 Safety Gate ("Table/Plating")
  [Risk Governor] consumes:
    - IntentPackage
    - execution truth snapshot (from PipelineContext.exec)
    - risk state (daily P/L, drawdown trackers, rule-of-5 counters)
    - configured risk limits (caps, timers, shock/news guards)
    - kill state context
  --> ApprovedCommands OR Veto OR KillCommand
  (Event) RiskDecision(approved/vetoed/forced_exit/kill)

RiskGov may emit FORCED_EXIT regardless of Policy intent.
Safety authority overrides strategy intent.


2.7 Execution Dispatch
  [Dispatcher/Command Router] consumes ApprovedCommands
  --> calls [PAr2] order methods (ONLY caller)
  Priority rule:
    - CLOSE/FLATTEN/HARDKILL use Priority EXIT channel (jump queue; bypass stop-throttle)
    - STOP modifications go through stop-throttle + merge
  (Event) CommandDispatched

2.8 Execution Event Return Path
	Execution events originate from IB and are surfaced by PAr2.
	These events enter the next cycle through the normal pipeline:
	
	PAr2 → Normalizer → Aggregator → ...
	
	This is not a side-channel; it is the start of the next PipelineContext cycle.
  [PAr2] emits:
    - order status / fills / rejects / pacing events / reconnect events
  --> [Dispatcher] updates trade state + journal
  --> (Event) FillReceived / OrderRejected / PacingEvent / PAReconnect

================================================================================
3) HEARTBEAT + FAILSAFE (Always On)
================================================================================
3.1 Heartbeat (Dispatcher → PAr2)
  - [Dispatcher] sends heartbeat to [PAr2] at interval H (config)
  - [PAr2] monitors last heartbeat timestamp

3.2 Failsafe Stages (heartbeat loss)
  Stage 1 Freeze @ T_freeze:
    - PA blocks NEW OPEN/ADD commands
    - allows CLOSE + protective stop tighten-only
    - (Event) FailsafeFreeze

 Stage 2 AutoExit @ T_flatten:
  - PA flattens all positions + cancels open orders
  - sets local lockout until human reset (MANDATORY; failsafe.autoexit_implies_lockout default=true)
  - (Event) FailsafeAutoExit
  - (Event) LOCKOUT_ENABLED

================================================================================
4) OPERATOR KILL COMMANDS (Any Time)
================================================================================
SoftKill (operator or RiskGov triggered):
  - PA blocks NEW OPEN/ADD
  - allows CLOSE + protective stop tighten-only
  - (Event) SoftKillEnabled/Disabled

HardKill (operator panic button or RiskGov triggered):
  - PA immediately flattens + cancels open orders
  - sets local lockout until human reset
  - (Event) HardKillExecuted

================================================================================
5) SHUTDOWN (Planned)
================================================================================
Operator chooses shutdown mode:
  A) Graceful (preferred):
     - Policy stops issuing OPEN/ADD intents
     - RiskGov requests controlled EXIT if position exists (optional)
     - Dispatcher drains queue (priority exits first)
     - PA unsubscribes market data
     - PA disconnects from IB Gateway
     - (Event) OperatorSessionEnd

  B) Immediate:
     - SoftKill then exit
     - OR HardKill then exit (if necessary)
     - (Event) OperatorAbort

================================================================================
6) RESTART RECOVERY (After crash / reconnect / redeploy)
================================================================================
On restart:
  - repeat BOOT sequence 1.1 → 1.4
  - mandatory reconciliation:
      - query IB truth (positions/orders/account)
      - emit ReconciliationReport
      - adopt/cancel orphan orders per config policy (config defaults to cancel)
  - if mismatch unsafe:
      - enable local lockout + alert operator
  - resume main loop

================================================================================
END LFC


