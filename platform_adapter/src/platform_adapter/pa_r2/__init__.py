"""
PAr2 — SniperZero Execution + Enforcement Layer
================================================
IB execution boundary for the SniperZero runtime pipeline.

Pipeline position:
    PAr2 → Normalizer → Aggregator → MFE → Pattern → C2 → Policy → RiskGov → Dispatcher → PAr2

PAr2 responsibilities:
- Accept PACommand objects from Dispatcher only
- Execute orders via IB Gateway (ibapi)
- Enforce safety state machine (NORMAL/SOFTKILL/FREEZE/AUTOEXIT/HARDKILL/LOCKOUT)
- Rate limit all outbound IB messages (token bucket per channel)
- Throttle stop modifications (min interval + min delta)
- Reconcile state on reconnect
- Emit PAEvent objects (execution truth) into PipelineContext.exec

Wire contract version: PAWire.v0
"""

from .models import PACommand, PAEvent, KillState, PAEventType, TradingMode, Channel, Priority, Action, IntentType
from .config import PAr2Config
from .adapter import PAr2Adapter
from .kill_state import KillStateMachine
from .reconciliation import ReconciliationRoutine, ReconciliationResult

__all__ = [
    "PACommand",
    "PAEvent",
    "KillState",
    "PAEventType",
    "TradingMode",
    "Channel",
    "Priority",
    "Action",
    "IntentType",
    "PAr2Config",
    "PAr2Adapter",
    "KillStateMachine",
    "ReconciliationRoutine",
    "ReconciliationResult",
]
