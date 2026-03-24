iteration: 2026-02-24.3
project: SniperZero – PAr2 Architecture Hardening


___



## SniperZero – PAr2 Discovery Requirements

Before implementing Release 2, confirm the following with IB documentation and testing:

**TARGET: IB Gateway** 

### A) Pacing Scope Clarification

1. Are pacing limits:
    - Per login session?
    - Per API socket connection?
    - Per account?
    - Shared across simultaneous Gateway instances?
2. Do limits aggregate across multiple VPS instances using same account?
3. Confirm whether pacing limits differ between LIVE and PAPER accounts.
4. Confirm whether paper trading environment mirrors pacing behavior of LIVE.

### B) Message Throughput Limits

1. Confirm:
    - Max sustained messages/sec
    - Burst tolerance window
    - Whether limits differ for:
        - Order placement
        - Order modification
        - Order cancellation
        - Market data subscription
        - (Note: IB historical data will NOT be used in v1. Confirm that no historical pacing rules are triggered by other API calls.)
2. Confirm if pacing violations escalate (warning → reject → disconnect).
### C) Modify/Cancel Sensitivity

1. What is the best practice for detecting comms loss: heartbeat from Exec vs IB socket status vs both?
2. Confirm whether server-side stop orders remain active if client disconnects (expected yes), and how to query/verify on reconnect 
3. Is rapid cancel/replace treated differently from new order submission?
4. Is there internal throttling for stop modifications?
	- how often can a trailing SL be set or changed? 
	- does modifying SL programmatically count toward API msg limit?
5. is it possible to set an "auto-flatten account" threshold based on lack of response or connection loss?
6. Is it possible to place an account lockout programmatically, or if IB won't provide a true “lock account” API action then place local lockout? 
7. Stop Modify + Exit Priority Discovery
	→ Confirm best practice for IB order modification pacing:
	- how IB treats frequent stop modifications vs new orders
	- whether rapid modify/cancel loops cause pacing escalation faster than other message types
	- confirm recommended throttling intervals for modify-heavy strategies
	→ Confirm EXIT priority assumptions:
	- verify that CLOSE/FLATTEN/HARDKILL orders can be issued immediately even when throttling other message classes, and document any cases where pacing could delay protective exits.
	- document any IB constraints that would delay close/flatten actions under pacing pressure
### D) Reconnection Behavior

1. What happens after:
    - Socket disconnect?
    - Gateway restart?
2. What state must be re-requested?
    - Open orders?
    - Positions?
    - Account summary?
### E) VPS Operational Considerations

1. Any IB recommendations for:
    - Gateway uptime cycling?
    - Session refresh intervals?
    - Memory usage monitoring?

---

Discovery deliverable:  
 - [ ] Written confirmation of above as artifact md file "PAr2 Discovery Findings" with documented IB references 
 - [ ] Review of Discovery Findings with Pete & JK, demo if needed
 - [ ] Key Decisions from Review recorded and shared with Pete & JK 

Implementation note: Only after this reconciliation does implementation begin. Group must review before any net-new development. 



