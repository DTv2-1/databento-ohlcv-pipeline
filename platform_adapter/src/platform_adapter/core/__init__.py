"""Core components: Connection Manager + PA r2 enforcement modules"""

from .connection_manager import ConnectionManager
from .kill_manager import KillManager, KillState, CommandIntent, KillStateChange
from .failsafe_monitor import FailsafeMonitor, FailsafeStage, FailsafeEvent
from .order_queue import OrderQueue, QueuedCommand, QueuedCommandType, COMMAND_PRIORITIES
from .stop_modify_throttler import StopModifyThrottler
from .pacing_engine import PacingEngine, PacingEvent
from .reconciliation import ReconciliationEngine, ReconciliationReport

__all__ = [
    "ConnectionManager",
    "KillManager", "KillState", "CommandIntent", "KillStateChange",
    "FailsafeMonitor", "FailsafeStage", "FailsafeEvent",
    "OrderQueue", "QueuedCommand", "QueuedCommandType", "COMMAND_PRIORITIES",
    "StopModifyThrottler",
    "PacingEngine", "PacingEvent",
    "ReconciliationEngine", "ReconciliationReport",
]
