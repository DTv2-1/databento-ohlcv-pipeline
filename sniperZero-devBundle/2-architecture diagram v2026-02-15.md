iteration: 2026-03-03.7
project: SniperZero – PAr2 Architecture Hardening
authors & wu-titles:
Q, 🎭 The Hidden Thesis
Pete, 🌀 The Hypnotist


___

```text

SniperZero v1 — High-Level Architecture (IB-first)
(one symbol per instance; Live OR Paper per instance; no IB historical)

┌─────────────────────────────── USER STACK (Control Plane) ─────────────────────────────────┐
│  Operator                                                                                  │
│  - CLI/UI controls: start/stop, mode select (LIVE/PAPER), kill, status                     │
│  - Operator Alerts *target* (Telegram/SMS)                                                 │
└───────────────┬────────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌────────────────────────────────┐
│ Config + Mode Loader           │
│ - symbols/contracts            │
│ - timeframes                   │
│ - C2 profile + thresholds      │
│ - risk limits + kill timers    │
│ - PA limits (rate/stop/pacing) │
└───────────────┬────────────────┘
                │ runtime_config
                ▼


┌────────────────────────────── RUNTIME PIPELINE (Data → Decisions → Orders) ───────────────┐

   MARKET DATA IN / EXEC EVENTS IN                                      ORDER COMMANDS OUT
┌────────────────────────┐                                         ┌─────────────────────────┐
│ IBKR Backend           │                                         │ IBKR Backend            │
└──────────┬─────────────┘                                         └──────────┬──────────────┘
           │ (socket)                                                         ▲ (socket)
           ▼                                                                  │
┌────────────────────────┐                                                    │
│ IB Gateway (VPS)       │                                                    │
│ - headless             │                                                    │
└──────────┬─────────────┘                                                    │
           │                                                                  │
           ▼                                                                  │
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│ PAr2 — Platform Adapter (Execution + Enforcement)                                         │
│ - market data ingest/subscriptions                                                        │
│ - executes orders ONLY from Dispatcher                                                    │
│ - single order queue + per-channel rate limiting + burst caps                             │
│ - stop-modify throttling (min interval + min delta + merge)                               │
│ - pacing recovery (cooldown/backoff)                                                      │
│ - kill execution: SoftKill / HardKill / Failsafe (heartbeat loss 3-stage)                 │
│ - restart reconciliation (positions/orders/account truth)                                 │
│ - local lockout (human reset)                                                             │
│ - NO strategy/risk/indicator computation                                                  │
└──────────┬────────────────────────────────────────────────────────────────────────────────┘
           │ structured market events + execution truth events (PAr2 does transport shaping only; canonicalization happens in Normalizer)
           ▼
┌────────────────────────┐
│ Normalizer (UNI)       │   "Fridge"
│ - canonical schema     │
│ - timestamp alignment  │
│ - symbol mapping       │
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│ Aggregator (MTF)       │   "Fridge"
│ - builds TF bars       │
│ - emits bar_update/close
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│ MFE — Market Feature   │   "Kitchen"
│ Engine                 │
│ - computes indicators  │   (ONLY owner of indicator math)
│ - derived features     │
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│ Pattern Engine         │   "Kitchen"
│ - emits candidates +   │   (OPEN/ADD/EXIT/HOLD/ADJUST_STOP_HINT)
│   candidate features   │   (no scalar confidence)
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│ C2 — Confidence 2.0    │   "Kitchen"
│ - scores candidates    │   (scalar 0..1 + bonus >1)
│ - sizing guidance      │   (does NOT recompute indicators)
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│ Policy Engine          │   "Table/Plating"
│ - selects action(s)    │   (can emit HOLD + STOP_ADJUST together)
│ - builds IntentPackage │
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│ Risk Governor          │   "Table/Plating"
│ - veto/override/kill   │   RiskGov manages Risk State, computed from execution events + Journaldb history
│ - shock/news + limits  │
│ - approves commands    │
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│ Dispatcher (Command    │   manages execution state and owns execution-state cache (runtime); JournalDB stores durable history (not live state)
│ Router)                │
│ - ONLY caller of PA    │   
│ - priority EXIT path   │   (CLOSE/FLATTEN/HARDKILL first)
└──────────┬─────────────┘
           │ commands
           ▼
          [PAr2 executes → IB Gateway → IBKR]


└───────────────────────────────────────────────────────────────────────────────────────────┘


┌──────────────────────────── OBSERVABILITY (Parallel / Outside Runtime) ────────────────────┐
│ Journal_DB (Postgres) + structured logs                                                    │
│ - fills, orders, pacing events, kill states, failsafe stages, reconciliation reports       │
│ Operator Alerts (Telegram/SMS)                                                             │
│ - entries/exits, kill/failsafe, reconnects, pacing violations, heartbeat loss              │
└────────────────────────────────────────────────────────────────────────────────────────────┘

```

___
___

SniperZero v1 — Module Definitions + Dataflow Responsibilities
(IB-first, one symbol per instance, paper/live toggle supported)

Golden Rule:
- Only MFE computes indicators/features.
- Pattern and C2 never recompute indicators; they only consume/forward. 
- Modules pass a PipelineContext package forward through the locked flow; modules append/transform only within their owned sections.
- JournalDB records events/slices (append-only history) and must not become a live-decision dependency.
- every module writes their own debug log, writing debug log is always last in priority
- If asked “where does state live?” the correct answer is:
	- Broker truth → IB, surfaced by PAr2 (events + reconciliation)
	- Execution state cache (runtime correctness) → Dispatcher
	- Risk state (P/L, drawdown, rule-of-5, kills) → RiskGov
	- Durable history/observability → JournalDB (append-only; not live truth)

**Where does state management live?**
Now formally:
- *Execution State → Dispatcher*
- *Risk State → RiskGov*
- *Historical Observability → JournalDB*
- *Broker Truth → PAr2 (reconciled on reconnect)*
PAr2 implementation must conform to:
- PipelineContext v0 (runtime package contract)
- PAr2 Wire Contract v0 (PACommand/PAEvent shapes)
- JournalDB model v0 (truth trail + replay rules)




