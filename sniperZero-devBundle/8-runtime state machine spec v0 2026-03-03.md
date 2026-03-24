
# Runtime Safety State Machine Spec v0 — SniperZero

iteration: 2026-03-04.3  
status: status: v0 (contract-aligned draft; safe for implementation)
audience: Pete / Juan / JK / future devs  
purpose: define the runtime safety states, transitions, required actions, and required event emissions (so nobody “interprets” safety behavior differently)

---

## 0) Purpose of this artifact & explanation (non-technical)

This document defines “what the bot is allowed to do” under normal conditions and under emergencies.

Think of it like a flight safety system:
- Most of the time, the system runs normally.
- If something bad happens (lost connection, operator panic button, risk limit breach), the system changes to a stricter safety mode.
- Each safety mode has clear rules: what trading actions are allowed, what must happen automatically, and what needs a human reset.

The goal is to prevent ambiguous behavior during failures. This makes implementation and testing much easier and prevents dangerous surprises.

**SPECIAL NOTE:** this artifact is the canonical source of config keys for the SniperZero project (as of iteration: 2026-03-04.2) until a dedicated config artifact has been finalized 

---

## 1) Law: This is runtime safety behavior, not strategy logic

- This state machine governs safety enforcement only.
- It does not decide trades. Strategy modules still decide intents.
- Safety state is enforced at the boundary (PAr2), and surfaced as truth via events + PipelineContext.exec.

---

## 2) Entities and ownership

### 2.1 Safety state owner
- **PAr2 is the enforcement owner** of runtime safety state and command filtering.
- **RiskGov may request transitions** (e.g., SoftKill/HardKill/ForcedExit) but PAr2 enforces the final behavior.
- **Dispatcher is the only module that issues commands** to PAr2.
- All other modules must treat safety state as read-only truth in `PipelineContext.exec`.

### 2.2 Where safety state appears
Safety truth must appear in:
- **PAEvents** emitted by PAr2
- **PipelineContext.exec.kill_state** for each cycle

---

## 3) State definitions

### 3.1 State list
- `NORMAL`
- `SOFTKILL`
- `FAILSAFE_FREEZE`
- `FAILSAFE_AUTOEXIT`
- `HARDKILL`
- `LOCKOUT`

### 3.2 Command permissions by state (enforcement rules)

Legend:
- Allowed = PAr2 will accept/execute
- Blocked = PAr2 rejects or ignores (must emit a rejection/blocked event)
- “Tighten-only stops” = stop modifications only allowed if they reduce risk

| State | OPEN / ADD | STOP place/modify | CLOSE / FLATTEN | Cancel orders | Notes |
|---|---|---|---|---|---|
| NORMAL | Allowed | Allowed | Allowed | Allowed | Standard operation |
| SOFTKILL | Blocked | Allowed (tighten-only for modify) | Allowed (priority EXIT) | Allowed | Prevents new exposure |
| FAILSAFE_FREEZE | Blocked | Allowed (tighten-only for modify) | Allowed (priority EXIT) | Allowed | Heartbeat loss stage 1 |
| FAILSAFE_AUTOEXIT | Blocked | N/A | Must execute flatten | Must cancel | Heartbeat loss stage 2 |
| HARDKILL | Blocked | N/A | Must execute flatten immediately | Must cancel | Emergency panic state |
| LOCKOUT | Blocked | Blocked (except optional “protective only” if you choose) | Blocked (unless operator explicitly commands HARDKILL again) | Blocked | Human reset required |

---

## 4) Events and triggers (inputs that cause transitions)

### 4.1 Operator triggers (via control plane)
- `OPERATOR_SOFTKILL_ENABLE`
- `OPERATOR_SOFTKILL_DISABLE`
- `OPERATOR_HARDKILL`
- `OPERATOR_RESET_LOCKOUT`

### 4.2 RiskGov triggers (requests)
- `RISK_SOFTKILL`
- `RISK_HARDKILL`
- `RISK_FORCED_EXIT`

### 4.3 System triggers (PAr2 observed)
- `HEARTBEAT_LOSS_STAGE_1` (T_freeze)
- `HEARTBEAT_LOSS_STAGE_2` (T_flatten)
- `RECONCILIATION_UNSAFE_MISMATCH`
- `PACING_DEGRADED` (does not change state by itself; may gate commands)
- `CONNECTION_LOSS` (may lead into failsafe stages via heartbeat logic)

---

## 5) Transition rules (the actual state machine)

### 5.1 Config toggles (canonical keys)
Even if a separate config artifact doesn’t exist yet, these keys are canonical and will later appear in runtime_config.

- `failsafe.heartbeat_interval_ms`
- `failsafe.freeze_after_ms`  (T_freeze)
- `failsafe.autoexit_after_ms` (T_flatten)
- `failsafe.autoexit_implies_lockout` = **true** (default)
- `lockout.requires_operator_reset` = true (default)
- `lockout.allow_protective_only` = false (default; optional future)

### 5.2 Transition table

| From | Trigger | To | Required Actions (PAr2) | Required Emitted PAEvents |
|---|---|---|---|---|
| NORMAL | OPERATOR_SOFTKILL_ENABLE or RISK_SOFTKILL | SOFTKILL | Block OPEN/ADD; keep EXIT allowed; tighten-only stop modifies | SOFTKILL_ENABLED |
| SOFTKILL | OPERATOR_SOFTKILL_DISABLE (only if safe) | NORMAL | Restore permissions | SOFTKILL_DISABLED |
| NORMAL or SOFTKILL | HEARTBEAT_LOSS_STAGE_1 (T_freeze) | FAILSAFE_FREEZE | Block OPEN/ADD; allow EXIT; tighten-only stop modifies | FAILSAFE_STAGE_CHANGED(FREEZE) |
| FAILSAFE_FREEZE | HEARTBEAT_LOSS_STAGE_2 (T_flatten) | FAILSAFE_AUTOEXIT | Flatten all positions + cancel open orders | FAILSAFE_STAGE_CHANGED(AUTOEXIT) + (ORDER_* / FILL as applicable) |
| FAILSAFE_AUTOEXIT | (completion) and autoexit_implies_lockout=true | LOCKOUT | Set lockout; require operator reset | LOCKOUT_ENABLED |
| ANY | OPERATOR_HARDKILL or RISK_HARDKILL | HARDKILL | Immediately flatten + cancel; stop all trading | HARDKILL_EXECUTED + FAILSAFE_STAGE_CHANGED(AUTOEXIT optional) |
| HARDKILL | (completion) | LOCKOUT | Require operator reset | LOCKOUT_ENABLED |
| ANY | RECONCILIATION_UNSAFE_MISMATCH | LOCKOUT | Block all trading until reset | LOCKOUT_ENABLED + RECONCILIATION_REPORT |
| LOCKOUT | OPERATOR_RESET_LOCKOUT | NORMAL | Clear lockout; require reconciliation before resuming | LOCKOUT_DISABLED + RECONCILIATION_REPORT |

### 5.3 Priority EXIT guarantee (hard law)
- EXIT commands (`CLOSE`, `FLATTEN`, `HARDKILL`) must be serviced before NORMAL commands.
- EXIT commands must bypass stop-modify throttling.
- Under pacing recovery, EXIT remains serviceable first; non-critical commands may be delayed.

---

## 6) Required PipelineContext.exec fields (truth surface)

PAr2 must ensure each cycle’s PipelineContext.exec includes:

- `exec.kill_state.softkill_enabled: bool`
- `exec.kill_state.failsafe_stage: NORMAL | FREEZE | AUTOEXIT`
- `exec.kill_state.lockout_enabled: bool`
- `exec.kill_state.lockout_reason: string (optional)`
- `exec.connection.ib_connected: bool`
- `exec.pacing.pacing_active: bool`
- `exec.pacing.cooldown_until_ts: int (optional)`
- `exec.reconciliation.last_reconcile_ts: int`
- `exec.events.pa_events: list[PAEvent]` (WireContract v0 compliant)

Law:
If `failsafe_stage == AUTOEXIT` and `failsafe.autoexit_implies_lockout == true` (default),
then `lockout_enabled` must be true until operator reset.

---

## 7) JournalDB recording requirements (truth trail)

JournalDB must record (append-only):
- FAILSAFE_STAGE_CHANGED
- SOFTKILL_ENABLED / SOFTKILL_DISABLED
- HARDKILL_EXECUTED
- LOCKOUT_ENABLED / LOCKOUT_DISABLED
- RECONCILIATION_REPORT
- ORDER_* lifecycle + FILL events
- PACING_* events

No synchronous DB reads on hot path.

---

## 8) Testing / acceptance criteria (minimal)

A. SoftKill blocks OPEN/ADD but allows CLOSE and tighten-only stop modifies.  
B. Heartbeat loss triggers FREEZE then AUTOEXIT at configured thresholds.  
C. AUTOEXIT always results in LOCKOUT_ENABLED when autoexit_implies_lockout=true (default).  
D. HardKill always flattens + cancels and results in LOCKOUT.  
E. Reconciliation unsafe mismatch always results in LOCKOUT.  
F. EXIT commands always preempt NORMAL commands.

End of Runtime Safety State Machine Spec v0.




