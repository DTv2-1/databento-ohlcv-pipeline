iteration: 2026-03-03.7

___

**SniperZero v1 Locked Runtime Flow (LAW)**  
`PAr2` → `Normalizer` → `Aggregator` → `MFE` → `Pattern` → `C2` → `Policy` → `RiskGov` → `Dispatcher` → `PAr2`  
`JournalDB` is a listener/recorder (append-only history). It is not in the decision flow and must not be a runtime dependency for live decisions.

**PAr2 Implementation Dependencies (LAW)**  
PAr2 must implement against our contracts: **PipelineContext v0** (runtime package), **PA Wire Contract v0** (PACommand/PAEvent shapes), and the **JournalDB listening model v0** (what events must be emitted for durable recording). These are required for correct downstream behavior and replay/debug; implementers must propose changes to the contracts before deviating.

___

## PAr2 Review Checklist

Deployment target: AWS VPS (Linux), headless IB Gateway + watchdog restart script
### A) Boundary enforcement

- [ ] Only Dispatcher (Command Router) can call PAr2 command methods (no direct strategy-to-IB calls)
- [ ] No indicator/confidence/pattern logic inside PA
- [ ] Execution events re-enter the pipeline only via PAr2 → Normalizer → PipelineContext.exec (no event bus or side-channel)
- [ ] Execution truth events appear in PipelineContext.exec.events for the next cycle
### B) Rate limiting + queue

- [ ] Single order queue exists (place/modify/cancel all routed through it)
	- [ ] PAr2 enforces single-net-position per symbol per instance (reject + log invalid OPEN/ADD)
- [ ] Per-channel limiters exist (md/place/modify/cancel/misc)
- [ ] Global sustained/burst caps configurable
- [ ] Under stress test, logs prove caps are respected
#### B2) Priority EXIT Channel

- [ ] CLOSE/FLATTEN/HARDKILL actions are serviced ahead of stop updates and other non-critical actions
- [ ] Exit actions bypass stop-modify throttling (but still obey global safety caps)
- [ ] Repeated CLOSE/FLATTEN commands when already flat produce a safe no-op event (no error, no new order)
### C) Stop modify throttling

- [ ] Min interval enforced (default 75ms; do not set below 50ms without proven pacing stability)
- [ ] Min delta enforced (tick/pip threshold)
- [ ] Updates merged; no cancel/replace storms
- [ ] Tighten-only mode exists for SoftKill/Failsafe Freeze
### D) Pacing recovery

- [ ] Pacing errors detected and logged with IB codes
- [ ] Cooldown/backoff triggers correctly
- [ ] During cooldown, critical actions still allowed (Priority EXIT: CLOSE/FLATTEN/HARDKILL + protective stop placement if missing)
- [ ] Repeated pacing violations escalate (configurable)
### E) Kill behaviors

- [ ] SoftKill blocks OPEN/ADD, still allows CLOSE + stop tighten
- [ ] HardKill flattens + cancels, then local lockout until human reset
- [ ] Failsafe: heartbeat loss triggers Stage 1 Freeze at 15s
- [ ] Failsafe: Stage 2 AutoExit at 180s flattens + cancels + lockout
- [ ] AutoExit emits FAILSAFE_STAGE_CHANGED(AUTOEXIT) followed by LOCKOUT_ENABLED
- [ ] All state changes emit events + are logged
### F) Restart reconciliation

- [ ] On reconnect/restart: positions + open orders + account queried
- [ ] Local state updated to match IB truth (IB is source)
- [ ] Reconciliation report emitted/logged
- [ ] Handles orphan orders per policy (adopt/cancel config; default is cancel/close)
         **Specific Values:**
	   - **Unknown open orders → CANCEL**
	   - **Unexpected open position → CLOSE, forced flatten + lockout**
### G) “No IB historical data” constraint

- [ ] PA makes zero historical requests in v1 (verified by logs)
### G2) Live vs Paper Mode

- [ ] Config supports ib.trading_mode = LIVE | PAPER (one mode per instance; restart to switch)
- [ ] Mode is logged at startup and included in reconciliation reports
- [ ] Enforcement behavior identical in both modes (limits, throttles, kills, reconciliation)

### H) Observability

- [ ] Events include: fills, rejects, status, pacing, kills, failsafe, reconnects
- [ ] Journal output is structured for Postgres ingestion
- [ ] All events conform to PAEvent schema defined in PAr2 WireContract v0

## Final Proof 
Once Juan implements PAr2, run a **single scripted scenario test** that proves the whole stack works:

```
OPEN → fill → stop placed → tighten → forced exit → reconciliation
```

And log:
- PAEvents
- PipelineContext snapshots
- JournalDB entries

If those three match the contracts, the system is behaving exactly as designed.



