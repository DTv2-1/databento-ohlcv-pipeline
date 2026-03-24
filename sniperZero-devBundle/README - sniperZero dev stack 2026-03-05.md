iteration: 2026-03-05.2
project: SniperZero – [sniperZero Architecture Hardening]
author: JK

___

# README — SniperZero Contract Stack (Consistency-Checked)

## What this folder is

This folder contains the **current authoritative spec/contract stack** for the SniperZero runtime system, **patched for consistency** across architecture, contracts, and acceptance criteria.

If two documents disagree, do **not** “average them.” Treat that as a bug, report to the team, and JK will patch the docs.

## How to read this (recommended order)

1. **Laws / invariants**
2. **Architecture flow**
3. **Module boundaries**
4. **Runtime package contract**
5. **Wire contract (commands/events)**
6. **Journal (recording model)**
7. **Implementation plan (dev spec + ticket)**
8. **Acceptance checklist (verification)**    

---

## Files included

### 1) `mini_CR_locks_sniperZero_PAr2_dev_2026-03-04.md`

**Role:** Governing laws / invariants / process constraints.  
**Who uses it:** Juan + Pete.  
**How to use it:**
- Treat as the **highest-level constraints**.
- If a change touches pipeline order, shared state, or “subscriptions,” it’s an **architecture change** and requires explicit approval.    

### 2) `architecture diagram v2026-02-15.md`

**Role:** The canonical pipeline flow diagram and boundary visualization.  
**Who uses it:** Juan + Pete.  
**How to use it:**
- Confirms the locked processing order (the “one true loop”).
- Use it to reject any implementation that introduces bypass paths or side channels.    

### 3) `ZERO Module Definitions SniperZero v1 rewrite 2026-03-03.md`

**Role:** Module responsibilities and _explicit non-responsibilities_ (the “do not do this” list).  
**Who uses it:** Juan (implementation), Pete (review).  
**How to use it:**
- This is how we prevent module creep (“just one more responsibility”) that turns systems into spaghetti.
- When coding: if you can’t point to a module’s responsibility section, don’t put that logic there.    

### 4) `LFC-Lifecycle Flow Chart 2025-02-18.md`

**Role:** Runtime lifecycle sequencing and operational flow narrative.  
**Who uses it:** Juan.  
**How to use it:**
- Use as a behavioral map for: kill/failsafe, pacing behavior, reconciliation steps, restart expectations.
- If you’re unsure what happens “next,” this doc usually answers it.    

### 5) `PipelineContext v0 - sniperZero Runtime Package Contract.md`

**Role:** The runtime “package” schema passed through the pipeline each cycle (single object; append/transform rules).  
**Who uses it:** Juan (implementation) + anyone building integrations.  
**How to use it:**
- This is the _data contract_. Build your internal types/interfaces around this.
- Execution truth is surfaced via `PipelineContext.exec` (events + reconciliation snapshots).
- Modules should **not reach sideways** for data if it can be carried forward in the package.    

### 6) `PAr2 WireContract v0 Template 2026-03-02.md`

**Role:** Command/event envelope and taxonomy for PACommand + PAEvent (template).  
**Who uses it:** Juan (PAr2 implementation), Pete (review).  
**How to use it:**
- Treat this as the canonical shape for emitted events and accepted commands.
- Naming matters: don’t invent new event names because it “feels cleaner.”
- The goal is strict, machine-readable lifecycle events with stable fields (especially `command_id`).    

> Note: It’s a “Template” intentionally — Juan may adjust types/field names _only_ if he also patches the dependent docs and keeps compatibility rules explicit.

### 7) `JournalDBmodel-listening&recording_2026-03-03.md`

**Role:** Append-only listening/recording model for JournalDB.  
**Who uses it:** Juan.  
**How to use it:**
- JournalDB is **not** runtime truth and **not** a hub.
- It records events for audit/replay and later analysis; it must not become a synchronous dependency on the hot path.    

### 8) `runtime state machine spec v0 2026-03-03.md`

^^ROLE:** Runtime safety enforcement
**Who uses it:** Juan, any future dev
**How to use it:** 
- the bot includes a runtime safety state machine (SoftKill, Freeze, AutoExit, HardKill, Lockout) enforced by PAr2. In unsafe conditions the system automatically flattens positions and blocks new trading until reset.
- this is quidance on implementing compliant functions within any individual module

### 9) `PAr2 dev spec+acceptance criteria 2026-02-15.md`

**Role:** PAr2 scope, behavior requirements, and acceptance criteria.  
**Who uses it:** Juan (implementation).  
**How to use it:**
- Use this as the “what good looks like” spec.
- It defines responsibilities like: queueing, pacing compliance, stop-mod throttling, kill/failsafe, reconciliation, event emission.    

### 9) `PAr2 implementation ticket for Juan.md`

**Role:** Concrete implementation plan + deliverables for Juan.  
**Who uses it:** Juan.  
**How to use it:**
- This is the task list to build PAr2 without ambiguity.
- Includes canonical config key names (seed list) to prevent config drift.
- Includes “laws” such as **AutoExit ⇒ Lockout (default true)** and **EXIT idempotency**.    

### 10) `PAr2 checklist for Pete 2026-02-18.md`

**Role:** Verification checklist for Pete to validate implementation behavior.  
**Who uses it:** Pete (review/QA), Juan (self-check).  
**How to use it:**
- Pete should treat this as the acceptance gate for sign-off.
- Juan should run it as a pre-delivery sanity check.    

---

## Critical invariants (summary)

These are intentionally repeated because humans forget things:
- **One pipeline, no bypass:** modules run in a locked order; no event bus/hub/side-channel architecture.
- **Commands are not truth:** truth comes from IB execution events and reconciliation; carried into next cycle via `PipelineContext.exec`.
- **Ownership boundaries matter:**
    - MFE computes indicators only (no scoring / no pattern decisions).
    - Policy must not execute.
    - Dispatcher is the only caller of PAr2.
- **EXIT priority:** exit actions must preempt normal actions.
- **AutoExit ⇒ Lockout:** default true; AutoExit should trigger lockout until explicit reset.
- **JournalDB is not a runtime dependency:** append-only recorder.
- **Runtime safety enforcement**
	- The system includes a **runtime safety state machine** enforced at the PAr2 boundary. Safety states (NORMAL, SOFTKILL, FAILSAFE_FREEZE, FAILSAFE_AUTOEXIT, HARDKILL, LOCKOUT) determine which commands are allowed. Strategy modules may still generate intents, but PAr2 enforces safety rules and filters commands accordingly. Execution truth for safety state must surface through `PipelineContext.exec.kill_state` and corresponding PAEvents.

---

## What to implement first

Juan - sequencing work:
1. Implement **PACommand / PAEvent envelope** from WireContract
2. Implement PAr2 **queue + idempotency** and command lifecycle tracking
3. Implement **reconciliation** and `RECONCILIATION_REPORT` emission
4. Implement **kill/failsafe** with AutoExit⇒Lockout default true
5. Implement stop-mod throttling + pacing compliance
6. Run the Pete checklist end-to-end    

---

## What Pete should review first

Pete can skim the technical docs and focus on:
- Architecture diagram
- Mini CR locks
- Pete checklist
- (then spot-check) PipelineContext + WireContract for sanity    

---

## Change control (don’t “quietly improve” things)

Any proposal that changes:
- module order
- introduces subscriptions / hubs / shared global state
- changes truth origin or reconciliation behavior    

…must be labeled as an **Architecture Change** and explicitly approved before implementation.

---




