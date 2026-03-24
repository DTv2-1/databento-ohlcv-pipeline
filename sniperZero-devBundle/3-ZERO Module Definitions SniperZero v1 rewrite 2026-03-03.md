iteration: 2026-03-03.5
title: ZERO Module Definitions — SniperZero v1 (Source of Truth Draft)
audience: JK / Pete / Juan  
___

# ZERO Module Definitions — SniperZero v1

# 0) Purpose
This document defines what each SniperZero v1 module does, what it must not do, what it consumes/produces, and which contracts it must follow. It is a functional guide: a reader should be able to implement modules without improvising architecture.

This doc is constrained by:
- Locked runtime flow (LAW)
- Command vs Truth (LAW)
- PipelineContext v0 (runtime package contract)
- PAr2 Wire Contract v0 (PACommand/PAEvent shapes)
- JournalDB listening/recording model v0 (truth trail + replay rules)

# 1) Locked Runtime Flow (LAW)
PAr2 → Normalizer → Aggregator → MFE → Pattern → C2 → Policy → RiskGov → Dispatcher → PAr2

JournalDB is a listener/recorder (append-only history). It is not in the decision flow and must not be a runtime dependency for live decisions.

# 2) Non-Negotiable Rules (LAW)

### 2.1 Command vs Truth
- Commands (Dispatcher → PAr2) are instructions, not proof.
- Execution truth comes from IB via PAr2 (execution events + reconciliation snapshots).
- Execution truth must be carried forward through the loop via PipelineContext.exec.

### 2.2 No hubs / no side-channels
- Modules do not “subscribe” to each other.
- Modules do not reach sideways for data.
- Modules modify/append only within the PipelineContext they receive and then forward it to the next module.

### 2.3 State ownership (without adding new modules)
- Broker truth: IB (surfaced via PAr2 events + reconciliation).
- Execution state cache (runtime correctness): Dispatcher.
- Risk state (P/L, drawdown, rule-of-5, kills): RiskGov.
- Durable history/observability: JournalDB (append-only).

# 3) Common Data Contract
All modules pass a PipelineContext forward. Each module either:
- transforms its owned subtree (Normalizer canonicalization), or
- appends its results (default).

Key sections:
- meta: identity/timing
- market: bars/features/candidates/scored_candidates
- exec: broker truth + safety state
- intent/risk/dispatch: appended later in the pipeline

PipelineContext Ownership Rules

Modules may only modify their owned subtree:
	Normalizer → ctx.market base events
	Aggregator → ctx.market.bars
	MFE → ctx.market.features
	Pattern → ctx.market.candidates
	C2 → ctx.market.scored_candidates
	Policy → ctx.intent
	RiskGov → ctx.risk
	Dispatcher → ctx.dispatch
	PAr2 → ctx.exec

Modules must not modify earlier sections owned by previous modules.

(See PipelineContext v0 for structure.)

---

# 4) Module Definitions

## 4.1 PAr2 — Platform Adapter v2 (Execution + Enforcement Boundary)
Role: connect to IB Gateway, ingest market/execution truth, execute commands from Dispatcher, enforce safety boundaries.

Consumes:
- PACommands from Dispatcher (place/modify/cancel/kill)
- IB/Gateway inbound events (market feed + execution events)

Produces:
- PAEvents (raw/structured market events + execution truth events) and reconciliation reports
	  Note:  
		Bar construction to higher TFs is owned by Aggregator.  
		PAr2 must not construct or emit strategy bars.
- Updates to PipelineContext.exec (truth carried forward through the loop)
- Does not produce features, candidates, confidence, intent, or risk decisions

Must enforce (from specs/contracts):
- per-channel rate limits + global burst caps
- pacing recovery (cooldown/backoff + logging)
- stop-modify throttling (min interval + min delta + merge)
- Priority EXIT channel: CLOSE/FLATTEN/HARDKILL jump queue, bypass stop throttle
- LIVE vs PAPER mode selection (one mode per instance; restart to switch)
- kill execution: SoftKill/Failsafe/HardKill behaviors
- reconciliation on start/reconnect

Must NOT:
- normalize or canonicalize data (Normalizer does that)
- decide trades or risk actions (runtime pipeline does that)

Primary contracts:
- PAr2 dev spec + acceptance criteria
- PAr2 Wire Contract v0
- JournalDB model v0 (truth trail emission requirements)
- PipelineContext v0 (exec truth carriage)

## 4.2 Normalizer (Canonicalization / Mapping)
Role: convert PAr2-emitted market/execution events into a canonical internal schema.

Consumes:
- PipelineContext with raw/structured PAEvents for this cycle

Produces/appends:
- canonical market events into ctx.market (base bars and metadata)
- canonical execution events into ctx.exec.events / ctx.exec.reconciliation (if present)

Must:
- handle timestamps, symbol mapping, and schema stability
- preserve source truth fields without inventing “meaning”

Must NOT:
- compute indicators/features
- detect patterns
- score confidence
- apply risk logic

## 4.3 Aggregator (MTF Bar Builder)
Role: build configured higher timeframes from the base feed.

Consumes:
- ctx.market.bars base timeframe (already canonical from Normalizer)

Produces/appends:
- ctx.market.bars.by_tf for configured TFs (e.g., 15s base → 1m/3m/etc)

Must:
- be deterministic and replayable
- clearly mark bar_state UPDATE vs CLOSE

Must NOT:
- compute features/indicators
- detect patterns
- score confidence

## 4.4 MFE — Market Feature Engine (Indicators/Features)
Role: compute indicators/features from aggregated bars.

Consumes:
- ctx.market.bars.by_tf

Produces/appends:
- ctx.market.features.by_tf (FeatureFrames)

Must:
- compute only indicators/features, no pattern logic
- remain deterministic (replayable from bars)

Must NOT:
- create candidate actions
- assign confidence
- perform risk gating

## 4.5 Pattern Engine (Candidate Generator)
Role: propose candidate actions (“arrows”) based on bars + features.

Consumes:
- ctx.market.features.by_tf
- ctx.exec (only as context; Pattern does not compute execution truth)

Produces/appends:
- ctx.market.candidates (CandidateSet)

Candidate actions allowed:
- OPEN / ADD / EXIT / HOLD / ADJUST_STOP_HINT

Must:
- propose candidates only (no scalar confidence)
- remain consistent with the strategy’s pattern definitions
- forward relevant candidate features for C2 scoring (as part of candidate payload)

Must NOT:
- compute indicators/features (MFE does that)
- compute confidence scores (C2 does that)
- make final intent decisions (Policy does that)

## 4.6 C2 — Confidence 2.0 (Candidate Scoring + Sizing Guidance)
Role: score pattern candidates using features and produce sizing guidance.

Consumes:
- ctx.market.candidates
- ctx.market.features.by_tf (for scoring)
- ctx.exec (for gating context; truth only)

Produces/appends:
- ctx.market.scored_candidates (ScoredCandidateSet)

Must:
- compute confidence score (0..1, may exceed 1.0 with bonus conditions)
- enforce min confidence threshold for “trade-eligible” (current rule: no opens under 0.65)
- output sizing guidance (capital slice %, add slice %, multipliers)
- be deterministic and auditable

Must NOT:
- invent candidates
- decide final trade intent (Policy does that)

## 4.7 Policy (Intent Formation)
Role: choose what we want to do this cycle given scored candidates + current truth context.

Consumes:
- ctx.market.scored_candidates
- ctx.exec (execution truth context: positions/orders/kill state)

Produces/appends:
- ctx.intent (IntentPackage summary)

Must:
- form intent: which actions to attempt (including multi-actions if compatible)
- respect “commands ≠ truth” (it uses exec truth, not command echoes)
- avoid duplicative decisions if already in the desired execution state (e.g., don’t open if already long)

Must NOT:
- veto safety rules (RiskGov does that)
- call PAr2 (Dispatcher only)
- compute risk state (RiskGov does that)
- compute features/candidates/scores

Open clarification:
- Whether Policy produces a single intent per cycle or multiple intents (e.g., HOLD + STOP_ADJUST) is allowed, but ordering rules must be explicit (see RiskGov/Dispatcher).

## 4.8 RiskGov — Risk Governor (Safety Authority)
Role: final safety gate and kill authority.

Consumes:
- ctx.intent
- ctx.exec truth snapshot (positions/orders/pacing/kill state)
- its own in-memory risk state (daily P/L, drawdown, rule-of-5, loss counters)

Produces/appends:
- ctx.risk decision (APPROVED/VETO/FORCED_EXIT/SOFTKILL/HARDKILL) + reason
- constraints for Dispatcher/PAr2 (e.g., tighten_only)

Must:
- enforce daily limits + rule-of-5 + shock/news guards
- decide SoftKill/Failsafe/HardKill triggers
- force exits when needed

Must NOT:
- compute features/candidates/scores
- call PAr2 (Dispatcher only)

**Invariants:** 
- If a position exists, a protective stop must exist (unless explicitly exempted), and must be kept current.
- **RiskGov may emit FORCED_EXIT regardless of Policy intent.**

## 4.9 Dispatcher (Command Router / Only Caller of PAr2)
Role: turn RiskGov-approved decisions into PACommands and execute them via PAr2, while maintaining minimal execution-state cache.

Consumes:
- ctx.risk decision + approved intent
- ctx.exec truth events (via PipelineContext.exec in the loop)

Produces/appends:
- ctx.dispatch (commands sent + lifecycle metadata)
- outbound PACommands → PAr2

Must:
- be the only module that calls PAr2 command methods
- enforce Priority EXIT ordering (CLOSE/FLATTEN/HARDKILL before normal)
- ensure idempotency/dedupe (avoid duplicate orders for same command_id)
- maintain execution-state cache for runtime correctness (not strategy state)

Must NOT:
- decide intent or risk policy
- infer truth from commands
- compute features/candidates/scores

---

# 5) JournalDB (Listener/Recorder; Not in Flow)
Role: append-only durable record of truth trail and selected debug slices.

Consumes:
- emitted events/slices (primarily PAEvents + command lifecycle + risk decisions)

Produces:
- durable history for replay/debug/audit and future MetaBot analysis

Must:
- never block live decisions (no synchronous DB reads on hot path)
- drop debug first under load, never drop truth trail

---

# 6) Outstanding Questions / Open Slots (to resolve later)

1) Base feed granularity (v1): confirm smallest ingest TF from IB per strategy (1s vs 15s) and how bar_update is represented.
2) Policy multi-action semantics: what combinations are allowed in one cycle (HOLD + STOP_ADJUST, EXIT + CANCEL, etc.).
3) RiskGov live consumption: confirm whether any DB reads are allowed during restart bootstrap (optional) and define strict rules.
4) Replay mode default: confirm JSONL replay is mandatory in v1 and whether aggregated bars are always persisted.
5) Symbol/contract abstraction: confirm where “unit” / contract sizing lives (config vs C2 vs RiskGov).
6) Operator controls: formalize where CLI/dashboard events enter the cycle (Operator → config/mode loader → runtime triggers).

End of ZERO Module Definitions (Source of Truth Draft).



