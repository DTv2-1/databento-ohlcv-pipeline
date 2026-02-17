"""
PA r2 — Central Order Queue

All commands that produce IB API calls go through this queue.
The queue processor drains items one at a time, applying:
  1. Kill state gate (from KillManager)
  2. Per-channel rate limit check
  3. Stop-modify throttle (if applicable)
  4. Send to IB via the appropriate adapter method

This ensures:
  - No concurrent IB calls from multiple threads
  - Centralized rate limiting
  - Kill state enforcement at the choke point
  - Clean audit trail of all commands

Author: PA r2
Date: 2026-02-16
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional

from loguru import logger


class QueuedCommandType(str, Enum):
    """Types of commands that flow through the order queue."""
    PLACE_ORDER = "PLACE_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    MODIFY_ORDER = "MODIFY_ORDER"
    FLATTEN = "FLATTEN"
    SUBSCRIBE_MD = "SUBSCRIBE_MD"
    UNSUBSCRIBE_MD = "UNSUBSCRIBE_MD"


@dataclass
class QueuedCommand:
    """
    A command waiting in the order queue.
    
    The executor is a callable that does the actual work
    (calls the adapter method). The queue processor invokes it.
    """
    command_type: QueuedCommandType
    executor: Callable[[], Any]
    symbol: str = ""
    priority: int = 5       # Lower = higher priority. Cancel=1, Flatten=2, etc.
    enqueued_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Result tracking
    result: Any = None
    error: Optional[Exception] = None
    done_event: threading.Event = field(default_factory=threading.Event)
    
    def wait_for_result(self, timeout: float = 10.0) -> Any:
        """Block until the command has been processed."""
        if self.done_event.wait(timeout=timeout):
            if self.error:
                raise self.error
            return self.result
        raise TimeoutError(f"Command {self.command_type.value} timed out after {timeout}s")


# Priority values for command types
COMMAND_PRIORITIES = {
    QueuedCommandType.CANCEL_ORDER: 1,    # Highest — safety
    QueuedCommandType.FLATTEN: 2,          # Safety
    QueuedCommandType.MODIFY_ORDER: 3,     # Stop modification
    QueuedCommandType.PLACE_ORDER: 5,      # Normal
    QueuedCommandType.SUBSCRIBE_MD: 7,     # Low
    QueuedCommandType.UNSUBSCRIBE_MD: 8,   # Lowest
}


class OrderQueue:
    """
    Central command queue for PA r2.
    
    All broker-bound commands flow through this queue.
    A background thread processes commands sequentially.
    
    Features:
      - Priority queue (cancel > flatten > modify > place > subscribe)
      - Kill-state gate (checked at dequeue time)
      - Rate limit check (checked at dequeue time)
      - Synchronous result waiting via done_event
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        drain_interval_ms: int = 50,
        kill_gate: Optional[Callable[[QueuedCommandType], bool]] = None,
        rate_gate: Optional[Callable[[QueuedCommandType], None]] = None,
        on_command_processed: Optional[Callable[[QueuedCommand], None]] = None,
    ):
        """
        Args:
            max_size: Maximum queue depth
            drain_interval_ms: Sleep between drain cycles (ms)
            kill_gate: Callable that returns True if command is allowed
            rate_gate: Callable that waits if rate limit exceeded
            on_command_processed: Callback after each command completes
        """
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_size)
        self._drain_interval = drain_interval_ms / 1000.0
        self._kill_gate = kill_gate
        self._rate_gate = rate_gate
        self._on_command_processed = on_command_processed
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._processed_count = 0
        self._rejected_count = 0
        self._error_count = 0
        self._lock = threading.Lock()
        self._seq = 0  # Sequence number for stable priority queue ordering
        
        logger.info(f"OrderQueue initialized: max_size={max_size}")
    
    @property
    def pending_count(self) -> int:
        """Number of commands waiting in queue."""
        return self._queue.qsize()
    
    def enqueue(self, cmd: QueuedCommand) -> QueuedCommand:
        """
        Add a command to the queue.
        
        Args:
            cmd: The command to enqueue
            
        Returns:
            The same QueuedCommand (caller can wait on cmd.done_event)
            
        Raises:
            queue.Full: If queue is at max capacity
        """
        with self._lock:
            self._seq += 1
            seq = self._seq
        
        # PriorityQueue uses tuple ordering: (priority, sequence, command)
        try:
            self._queue.put_nowait((cmd.priority, seq, cmd))
            logger.debug(
                f"Enqueued: {cmd.command_type.value} {cmd.symbol} "
                f"(priority={cmd.priority}, pending={self.pending_count})"
            )
            return cmd
        except queue.Full:
            logger.error(f"Order queue FULL — rejecting {cmd.command_type.value}")
            cmd.error = RuntimeError("Order queue full")
            cmd.done_event.set()
            raise
    
    def start(self) -> None:
        """Start the queue processor thread."""
        if self._running:
            logger.warning("OrderQueue already running")
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._drain_loop,
            daemon=True,
            name="PA-OrderQueue",
        )
        self._thread.start()
        logger.info("OrderQueue processor started")
    
    def stop(self) -> None:
        """Stop the queue processor. Pending commands will NOT be processed."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info(
            f"OrderQueue stopped. "
            f"Processed={self._processed_count}, "
            f"Rejected={self._rejected_count}, "
            f"Errors={self._error_count}"
        )
    
    def _drain_loop(self) -> None:
        """Background loop: dequeue and process commands."""
        while self._running:
            try:
                # Non-blocking get with short timeout
                try:
                    priority, seq, cmd = self._queue.get(timeout=self._drain_interval)
                except queue.Empty:
                    continue
                
                self._process_command(cmd)
                
            except Exception as e:
                logger.error(f"Error in queue drain loop: {e}")
                time.sleep(0.1)
    
    def _process_command(self, cmd: QueuedCommand) -> None:
        """Process a single command from the queue."""
        try:
            # 1. Kill state gate
            if self._kill_gate and not self._kill_gate(cmd.command_type):
                logger.warning(
                    f"Command REJECTED by kill gate: {cmd.command_type.value} {cmd.symbol}"
                )
                cmd.error = RuntimeError(
                    f"Command {cmd.command_type.value} blocked by kill state"
                )
                with self._lock:
                    self._rejected_count += 1
                cmd.done_event.set()
                return
            
            # 2. Rate limit gate (blocks until allowed)
            if self._rate_gate:
                self._rate_gate(cmd.command_type)
            
            # 3. Execute
            cmd.result = cmd.executor()
            
            with self._lock:
                self._processed_count += 1
            
            logger.debug(
                f"Processed: {cmd.command_type.value} {cmd.symbol} → {cmd.result}"
            )
            
        except Exception as e:
            cmd.error = e
            with self._lock:
                self._error_count += 1
            logger.error(
                f"Command failed: {cmd.command_type.value} {cmd.symbol} → {e}"
            )
        finally:
            cmd.done_event.set()
            
            if self._on_command_processed:
                try:
                    self._on_command_processed(cmd)
                except Exception as e:
                    logger.error(f"Error in command processed callback: {e}")
    
    def get_status(self) -> dict:
        """Get queue status."""
        with self._lock:
            return {
                "pending": self.pending_count,
                "processed": self._processed_count,
                "rejected": self._rejected_count,
                "errors": self._error_count,
                "running": self._running,
            }
    
    def __repr__(self) -> str:
        return (
            f"OrderQueue(pending={self.pending_count}, "
            f"processed={self._processed_count})"
        )
