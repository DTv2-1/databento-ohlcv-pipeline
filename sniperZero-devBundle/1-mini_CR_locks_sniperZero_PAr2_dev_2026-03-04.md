teration: 2026-03-05.1
project: SniperZero – [sniperZero Architecture Hardening]
author: JK

___

# SniperZero — PAr2 Development Locks

Version: v1  
Scope: Implementation invariants and architecture constraints for SniperZero runtime

---

# 1. Locked Runtime Architecture

The SniperZero runtime executes as a **single closed-loop pipeline**.

Locked processing order:
> PAr2 → Normalizer → Aggregator → MFE → Pattern → C2 → Policy → RiskGov → Dispatcher → PAr2

Rules:
- Modules must execute in this order.
- No module may bypass the pipeline.
- No direct module-to-module calls outside this flow.
- JournalDB is **not part of the decision pipeline**.

JournalDB role:
- append-only recorder
- audit + replay support
- must **never be a runtime dependency** for live trading decisions.

---

# 2. Command vs Execution Truth

SniperZero enforces a strict separation between **commands** and **truth**.

Commands:
- instructions issued by Dispatcher to PAr2.

Execution truth:
- broker state observed via IB execution events and reconciliation.

Rules:
- Commands are **intent only**, not confirmation.
- Execution truth must originate from IB events via PAr2.
- Execution truth must be emitted as **PAEvents**.
- Execution truth is carried forward through the pipeline via `PipelineContext.exec`.

Downstream modules must **never infer state from commands alone**.

---

# 3. Runtime Data Contract

Each runtime cycle passes a single object through the pipeline.

Name:
> PipelineContext

Rules:
- PipelineContext is the **only package passed module-to-module per cycle**.
- Modules may only modify their owned portion of the package.
- No module may access external shared state instead of using the package.

Append/transform responsibilities:

Normalizer
- canonicalizes inbound schema (timestamps, symbol mapping, etc.)

Aggregator
- appends timeframe bars and updates

MFE
- computes indicators and features
- **only module allowed to compute indicators**

Pattern
- appends candidate trades and derived pattern features

C2
- appends confidence scores and sizing guidance

Policy
- appends trade intents

RiskGov
- appends approvals, vetoes, or kill directives

Dispatcher
- emits commands and tracks command lifecycle metadata

PAr2
- emits execution truth events and reconciliation snapshots

Additional rule:
> PAr2 must **not canonicalize market/event schemas** beyond minimal transport shaping required by the broker API.

Canonicalization belongs exclusively to Normalizer.

---

# 4. State Ownership

Runtime state ownership is strictly partitioned.

Execution truth source
- IB broker state via PAr2 reconciliation and events

Execution lifecycle state
- owned by Dispatcher
- minimal cache for idempotency, dedupe, and ordering

Risk state
- owned by RiskGov
- includes drawdown tracking, rule-of-5, session loss limits, and kill logic

Historical record
- owned by JournalDB
- append-only event history

JournalDB must **not act as live state or shared memory**.

---

# 5. PAr2 Contract Dependencies

PAr2 implementation must follow three contracts:

PipelineContext v0
- runtime package contract

PAr2 Wire Contract v0
- PACommand and PAEvent shapes

JournalDB listening model v0
- defines required events for recording and replay

Implementation must **propose contract changes before deviating** from these artifacts.

---

# 6. Execution Safety Rules

Priority EXIT actions must always take precedence.

Priority EXIT types include:
> CLOSE  
> FLATTEN  
> HARDKILL

Rules:
- Priority EXIT must jump the command queue.
- EXIT must not be delayed by:
    - stop-modify throttling
    - pacing backoff
    - normal command traffic.

---

# 7. Failsafe Behavior

Failsafe escalation includes an AutoExit stage.

When AutoExit occurs:
- PAr2 must flatten all positions.
- PAr2 must cancel all open orders.
- System enters **LOCKOUT mode** until manual reset.

Default configuration:
`failsafe.autoexit_implies_lockout `= `true`

Events that must be emitted:
`FailsafeAutoExit`  
`LOCKOUT_ENABLED`

---

# 8. Reconciliation Rules

On restart or reconnect:
> PAr2 must reconcile broker state.

Unknown open orders
> 
> default action:  
> CANCEL

Unexpected open positions

default action:  
> FORCED CLOSE (flatten)  
> then enable LOCKOUT

Reconciliation must emit:
> RECONCILIATION_REPORT  
> ORDER_STATUS / ORDER_CANCELED events when applicable.

---

# 9. Performance Requirements

Soft constraints (subject to tuning):
- decision loop should support sub-second cycles at configured timeframes
- EXIT operations must remain serviceable under pacing constraints.

Latency measurement must be recorded through timestamps at module boundaries inside PipelineContext metadata.

---

# 10. Terminology Locks

PipelineContext
- runtime package passed through pipeline

Command
- outbound instruction to broker

Execution event
- inbound broker truth event

Stop-modify
- modification of stop order parameters

Tighten-only
- stop update allowed only when risk decreases

Priority EXIT
- CLOSE / FLATTEN / HARDKILL actions that bypass queue

---

# 11. Change Control

All proposed changes must be classified as one of:

Clarification
- documentation wording only

Data Contract Detail
- schema changes that do not alter pipeline structure

Architecture Change
- pipeline order change
- new module introduction
- shared state or hub architecture

Architecture changes require explicit approval.

---

# 12. Explicit Anti-Goals

The following patterns are prohibited:
- event-bus architecture
- shared global state store
- modules subscribing directly to PAr2 events
- treating commands as execution confirmation
- making JournalDB part of the runtime decision path

All runtime decisions must derive from PipelineContext and execution truth events.

---


