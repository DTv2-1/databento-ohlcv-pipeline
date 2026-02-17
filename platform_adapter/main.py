"""
Platform Adapter r2 — Execution Enforcement Layer

PA r2 does 3 things:
  1. Pull & stream broker FACTS → PAOutputStream
  2. Receive commands from OE → enforce safety → translate → send to broker
  3. Self-protect via kill states, failsafe, pacing recovery, reconciliation

New in r2:
  - Kill State Machine (NORMAL/SOFTKILL/HARDKILL/FAILSAFE_FREEZE/LOCKOUT)
  - Failsafe Heartbeat Monitor (3-stage escalation)
  - Central Order Queue (all IB calls go through queue)
  - Per-Channel Rate Limiting + Global Burst Cap
  - Stop-Modify Throttler (merge/debounce)
  - Pacing Recovery Engine (cooldown/backoff on error 100/162)
  - Reconciliation Engine (IB truth vs local state)
  - Live/Paper Mode Switching (port toggle)

Author: Platform Adapter Team
Refactored: 2026-02-16 (PA r2)
"""

import sys
import signal
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import yaml

from loguru import logger

from src.platform_adapter.core.connection_manager import ConnectionManager
from src.platform_adapter.core.kill_manager import (
    KillManager, KillState, CommandIntent, KillStateChange,
)
from src.platform_adapter.core.failsafe_monitor import (
    FailsafeMonitor, FailsafeStage, FailsafeEvent,
)
from src.platform_adapter.core.order_queue import (
    OrderQueue, QueuedCommand, QueuedCommandType, COMMAND_PRIORITIES,
)
from src.platform_adapter.core.stop_modify_throttler import StopModifyThrottler
from src.platform_adapter.core.pacing_engine import PacingEngine, PacingEvent
from src.platform_adapter.core.reconciliation import (
    ReconciliationEngine, ReconciliationReport,
)
from src.platform_adapter.core.state_manager import StateManager

from src.platform_adapter.adapters.market_data_adapter import MarketDataAdapter
from src.platform_adapter.adapters.order_execution_adapter import (
    OrderExecutionAdapter, OrderAction, OrderType,
)
from src.platform_adapter.adapters.account_manager import AccountManager
from src.platform_adapter.models.contract import Contract
from src.platform_adapter.utils.logger import setup_logger
from src.platform_adapter.utils.rate_limiter import PerChannelRateLimiter

# Contracts
from src.platform_adapter.interfaces.pa_outputs import (
    PAOutputStream,
    QuoteEvent,
    BarEvent,
    OrderUpdateEvent,
    FillEvent,
    PositionEvent,
    AccountValueEvent,
    ConnectionEvent,
    ConnectionStatus,
    KillStateEvent,
    FailsafeStageEvent,
    PacingStateEvent,
    ReconciliationReportEvent,
)
from src.platform_adapter.interfaces.pa_inputs import (
    PlaceOrderCommand,
    CancelOrderCommand,
    ModifyOrderCommand,
    FlattenCommand,
    SubscribeMarketDataCommand,
    UnsubscribeMarketDataCommand,
    HistoricalDataCommand,
    SoftKillCommand,
    HardKillCommand,
    ResumeNormalCommand,
    SetLockoutCommand,
    HeartbeatCommand,
    ReconcileCommand,
    SwitchModeCommand,
)


class PlatformAdapter:
    """
    PA r2 — Execution Enforcement Layer.

    Outputs: broker facts via PAOutputStream
    Inputs:  commands via handle_*() methods
    Safety:  kill states, failsafe, pacing, rate limiting, reconciliation

    Every broker-bound command flows through:
      Kill Gate → Order Queue → Rate Limiter → (Stop Throttle) → IB API
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        # Load configuration
        self.config = self._load_config(config_path)

        # Setup logging
        log_config = self.config.get("logging", {})
        setup_logger(
            log_dir=log_config.get("log_dir", "logs"),
            level=log_config.get("level", "INFO"),
            rotation=log_config.get("rotation", "00:00"),
            retention_days=log_config.get("retention_days", 7),
            console=True,
        )

        logger.info("PA r2 initializing — execution enforcement layer")

        # Output stream — downstream consumers register here
        self.stream = PAOutputStream()

        # ====================================================================
        # r2 CORE: Kill Manager
        # ====================================================================
        kill_config = self.config.get("kill", {})
        self._kill_manager = KillManager(
            on_state_changed=self._on_kill_state_changed,
            on_hardkill_triggered=self._execute_hardkill_sequence,
            lockout_requires_human=kill_config.get("lockout_requires_human", True),
        )

        # ====================================================================
        # r2 CORE: Per-Channel Rate Limiter
        # ====================================================================
        rl_config = self.config.get("rate_limiting", {})
        channel_configs = rl_config.get("channels", None)
        self._rate_limiter = PerChannelRateLimiter(
            channel_configs=channel_configs,
            global_sustained_per_sec=rl_config.get("global_sustained_per_sec", 45),
            global_burst_cap=rl_config.get("global_burst_cap", 50),
        )

        # ====================================================================
        # r2 CORE: Pacing Engine
        # ====================================================================
        pacing_config = self.config.get("pacing", {})
        self._pacing_engine = PacingEngine(
            cooldown_sec=pacing_config.get("cooldown_sec", 5.0),
            backoff_multiplier=pacing_config.get("backoff_multiplier", 2.0),
            max_cooldown_sec=pacing_config.get("max_cooldown_sec", 60.0),
            critical_only_during_recovery=pacing_config.get(
                "critical_only_during_recovery", True
            ),
            on_pacing_event=self._on_pacing_event,
        )

        # ====================================================================
        # r2 CORE: Order Queue
        # ====================================================================
        queue_config = self.config.get("order_queue", {})
        self._order_queue = OrderQueue(
            max_size=queue_config.get("max_size", 1000),
            drain_interval_ms=queue_config.get("drain_interval_ms", 50),
            kill_gate=self._kill_gate_check,
            rate_gate=self._rate_gate_check,
        )

        # ====================================================================
        # r2 CORE: Stop-Modify Throttler
        # ====================================================================
        smt_config = self.config.get("stop_modify_throttle", {})
        self._stop_throttler = StopModifyThrottler(
            min_interval_ms=smt_config.get("min_interval_ms", 250),
            min_delta_ticks=smt_config.get("min_delta_ticks", 1),
            tick_size=0.25,  # Default for ES; configurable per symbol later
            merge_window_ms=smt_config.get("merge_window_ms", 100),
        )

        # ====================================================================
        # r2 CORE: Failsafe Monitor
        # ====================================================================
        fs_config = self.config.get("failsafe", {})
        self._failsafe = FailsafeMonitor(
            t_warn_sec=fs_config.get("t_warn_sec", 10.0),
            t_freeze_sec=fs_config.get("t_freeze_sec", 15.0),
            t_flatten_sec=fs_config.get("t_flatten_sec", 180.0),
            on_stage_changed=self._on_failsafe_stage_changed,
            on_freeze=lambda: self._kill_manager.set_failsafe_freeze(
                reason="Failsafe Stage 2: no heartbeat", source="failsafe"
            ),
            on_flatten=lambda: self._kill_manager.hardkill(
                reason="Failsafe Stage 3: auto-flatten", source="failsafe"
            ),
        )

        # ====================================================================
        # r2 CORE: Reconciliation Engine
        # ====================================================================
        recon_config = self.config.get("reconciliation", {})
        self._reconciliation = ReconciliationEngine(
            orphan_policy=recon_config.get("orphan_policy", "log_and_alert"),
            position_mismatch_policy=recon_config.get(
                "position_mismatch_policy", "accept_broker"
            ),
            on_report=self._on_reconciliation_report,
        )

        # ====================================================================
        # r2 CORE: State Manager (un-quarantined)
        # ====================================================================
        self._state = StateManager()

        # ====================================================================
        # Broker connection + adapters
        # ====================================================================
        self._connection: Optional[ConnectionManager] = None
        self._market_data: Optional[MarketDataAdapter] = None
        self._orders: Optional[OrderExecutionAdapter] = None
        self._account: Optional[AccountManager] = None

        # Subscription tracking (symbol → req_id)
        self._md_subscriptions: Dict[str, int] = {}

        # Connection state
        self._connected = False
        self._shutdown_requested = False
        self._active_mode = self.config.get("ib_connection", {}).get(
            "active_mode", "paper"
        )

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("PA r2 initialized — all enforcement modules ready")

    # ========================================================================
    # CONNECTION
    # ========================================================================

    def connect(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client_id: Optional[int] = None,
    ) -> bool:
        """Connect to IB Gateway, wire broker callbacks, start enforcement."""
        if self._connected:
            logger.warning("Already connected")
            return True

        try:
            conn_config = self.config["ib_connection"]
            host = host or conn_config["host"]
            port = port or conn_config["port"]
            client_id = client_id or conn_config["client_id"]
            timeout = conn_config.get("timeout", 30)

            logger.info(
                f"Connecting to IB Gateway at {host}:{port} "
                f"(client_id={client_id}, mode={self._active_mode})"
            )

            # Initialize broker components
            self._connection = ConnectionManager()
            self._market_data = MarketDataAdapter(self._connection)
            self._orders = OrderExecutionAdapter(self._connection)
            self._account = AccountManager(self._connection)

            # Hook pacing engine into connection error handler
            self._wire_pacing_to_connection()

            # Hook reconnection → auto-reconciliation + connection events
            self._wire_reconnection_hooks()

            # Connect
            success = self._connection.connect_to_ib(host, port, client_id, timeout)

            if success:
                self._connected = True
                self._wire_broker_to_stream()

                # Start r2 enforcement services
                self._order_queue.start()
                self._stop_throttler.start()
                self._failsafe.start()

                self.stream.emit_connection(
                    ConnectionEvent(
                        ConnectionStatus.CONNECTED,
                        f"Connected to {host}:{port} ({self._active_mode})",
                    )
                )

                # Run reconciliation on connect
                recon_config = self.config.get("reconciliation", {})
                if recon_config.get("on_connect", True):
                    self._run_reconciliation()

                logger.info("✅ PA r2 connected — enforcement active")
                return True
            else:
                logger.error("❌ Failed to connect to IB Gateway")
                self.stream.emit_connection(
                    ConnectionEvent(ConnectionStatus.ERROR, "Connection failed")
                )
                return False

        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            self.stream.emit_connection(
                ConnectionEvent(ConnectionStatus.ERROR, str(e))
            )
            return False

    def disconnect(self):
        """Disconnect from IB Gateway and stop enforcement."""
        if not self._connected:
            return

        logger.info("Disconnecting PA r2...")

        try:
            # Stop enforcement services
            self._failsafe.stop()
            self._stop_throttler.stop()
            self._order_queue.stop()

            if self._account:
                self._account.subscribe_account_updates(subscribe=False)
            if self._connection:
                self._connection.disconnect_from_ib()
            self._connected = False
            self.stream.emit_connection(
                ConnectionEvent(ConnectionStatus.DISCONNECTED, "Disconnected")
            )
            logger.info("✅ PA r2 disconnected")
        except Exception as e:
            logger.error(f"❌ Error during disconnect: {e}")

    # ========================================================================
    # r2 COMMAND HANDLERS — Kill States
    # ========================================================================

    def set_softkill(self, cmd: SoftKillCommand) -> bool:
        """Activate SoftKill — blocks OPEN/ADD."""
        return self._kill_manager.set_softkill(
            reason=cmd.reason or "SoftKill from Exec", source="exec"
        )

    def hardkill(self, cmd: HardKillCommand) -> bool:
        """Activate HardKill — cancel all + flatten all → LOCKOUT."""
        return self._kill_manager.hardkill(
            reason=cmd.reason or "HardKill from Exec", source="exec"
        )

    def resume_normal(self, cmd: ResumeNormalCommand) -> bool:
        """Resume NORMAL from SoftKill/FailsafeFreeze."""
        return self._kill_manager.resume_normal(
            reason=cmd.reason or "Resume from Exec", source="exec"
        )

    def set_lockout(self, cmd: SetLockoutCommand) -> bool:
        """Force LOCKOUT."""
        return self._kill_manager.set_lockout(
            reason=cmd.reason or "Lockout from Exec", source="exec"
        )

    # ========================================================================
    # r2 COMMAND HANDLERS — Failsafe
    # ========================================================================

    def heartbeat_from_exec(self, cmd: HeartbeatCommand = None) -> None:
        """Exec heartbeat — resets failsafe timer."""
        self._failsafe.heartbeat_from_exec()

    # ========================================================================
    # r2 COMMAND HANDLERS — Reconciliation
    # ========================================================================

    def reconcile_state(self, cmd: ReconcileCommand = None) -> None:
        """Trigger manual reconciliation."""
        self._ensure_connected()
        self._run_reconciliation()

    # ========================================================================
    # r2 COMMAND HANDLERS — Mode Switching
    # ========================================================================

    def switch_mode(self, cmd: SwitchModeCommand) -> bool:
        """Switch between Live and Paper trading mode."""
        target_mode = cmd.mode
        if target_mode == self._active_mode:
            logger.info(f"Already in {target_mode} mode")
            return True

        conn_config = self.config["ib_connection"]
        port = (
            conn_config.get("port_live", 4001)
            if target_mode == "live"
            else conn_config.get("port_paper", 4002)
        )

        logger.warning(f"Switching mode: {self._active_mode} → {target_mode} (port {port})")

        self.disconnect()
        self._active_mode = target_mode
        self.config["ib_connection"]["port"] = port

        success = self.connect(port=port)
        if success:
            logger.info(f"✅ Mode switched to {target_mode}")
        else:
            logger.error(f"❌ Failed to switch to {target_mode}")
        return success

    # ========================================================================
    # COMMAND HANDLERS (Order execution — now via queue)
    # ========================================================================

    def handle_place_order(self, cmd: PlaceOrderCommand) -> int:
        """Place order via queue. Returns order_id."""
        self._ensure_connected()

        def _execute():
            contract = Contract(
                symbol=cmd.symbol,
                sec_type=cmd.sec_type,
                exchange=cmd.exchange,
                currency=cmd.currency,
            )
            return self._orders.place_order(
                contract=contract,
                action=OrderAction(cmd.action),
                quantity=cmd.quantity,
                order_type=OrderType(cmd.order_type),
                limit_price=cmd.limit_price,
                stop_price=cmd.stop_price,
            )

        queued = QueuedCommand(
            command_type=QueuedCommandType.PLACE_ORDER,
            executor=_execute,
            symbol=cmd.symbol,
            priority=COMMAND_PRIORITIES[QueuedCommandType.PLACE_ORDER],
        )
        self._order_queue.enqueue(queued)
        result = queued.wait_for_result(timeout=15.0)
        logger.info(
            f"Command executed: PLACE {cmd.action} {cmd.quantity} "
            f"{cmd.symbol} → order_id={result}"
        )
        return result

    def handle_cancel_order(self, cmd: CancelOrderCommand) -> bool:
        """Cancel order via queue."""
        self._ensure_connected()

        def _execute():
            return self._orders.cancel_order(cmd.order_id)

        queued = QueuedCommand(
            command_type=QueuedCommandType.CANCEL_ORDER,
            executor=_execute,
            symbol="",
            priority=COMMAND_PRIORITIES[QueuedCommandType.CANCEL_ORDER],
        )
        self._order_queue.enqueue(queued)
        result = queued.wait_for_result(timeout=10.0)
        logger.info(f"Command executed: CANCEL order_id={cmd.order_id} → {result}")
        return result

    def handle_modify_order(self, cmd: ModifyOrderCommand) -> bool:
        """Modify order via queue. Stop modifications go through throttler."""
        self._ensure_connected()

        # Check if this is a stop-only modification (use throttler)
        if cmd.stop_price is not None and cmd.quantity is None and cmd.limit_price is None:
            def _execute_modify():
                self._orders.modify_order(
                    order_id=cmd.order_id,
                    stop_price=cmd.stop_price,
                )

            action = self._stop_throttler.submit_stop_modify(
                order_id=cmd.order_id,
                new_stop_price=cmd.stop_price,
                executor=_execute_modify,
            )
            logger.info(
                f"Stop modify: order_id={cmd.order_id}, "
                f"price={cmd.stop_price} → {action}"
            )
            return action in ("sent", "deferred", "merged")

        # Non-stop modification: go through queue
        def _execute():
            return self._orders.modify_order(
                order_id=cmd.order_id,
                quantity=cmd.quantity,
                limit_price=cmd.limit_price,
                stop_price=cmd.stop_price,
            )

        queued = QueuedCommand(
            command_type=QueuedCommandType.MODIFY_ORDER,
            executor=_execute,
            symbol="",
            priority=COMMAND_PRIORITIES[QueuedCommandType.MODIFY_ORDER],
        )
        self._order_queue.enqueue(queued)
        result = queued.wait_for_result(timeout=10.0)
        logger.info(f"Command executed: MODIFY order_id={cmd.order_id} → {result}")
        return result

    def handle_flatten(self, cmd: FlattenCommand) -> Optional[int]:
        """Flatten position via queue."""
        self._ensure_connected()

        def _execute():
            # Ask broker for current positions
            positions = self._account.get_positions(block=True, timeout=5.0)
            pos = next((p for p in positions if p.symbol == cmd.symbol), None)

            if pos is None or pos.quantity == 0:
                logger.info(f"FLATTEN {cmd.symbol} → already flat")
                return None

            # Close with opposite action
            action = "SELL" if pos.quantity > 0 else "BUY"
            contract = Contract(
                symbol=cmd.symbol,
                sec_type=cmd.sec_type,
                exchange=cmd.exchange,
                currency=cmd.currency,
            )
            order_id = self._orders.place_order(
                contract=contract,
                action=OrderAction(action),
                quantity=abs(pos.quantity),
                order_type=OrderType.MARKET,
            )
            logger.info(
                f"FLATTEN {cmd.symbol} → {action} {abs(pos.quantity)}, "
                f"order_id={order_id}"
            )
            return order_id

        queued = QueuedCommand(
            command_type=QueuedCommandType.FLATTEN,
            executor=_execute,
            symbol=cmd.symbol,
            priority=COMMAND_PRIORITIES[QueuedCommandType.FLATTEN],
        )
        self._order_queue.enqueue(queued)
        return queued.wait_for_result(timeout=15.0)

    def handle_subscribe_market_data(self, cmd: SubscribeMarketDataCommand) -> int:
        """Subscribe to market data via queue."""
        self._ensure_connected()

        def _execute():
            contract = Contract(
                symbol=cmd.symbol,
                sec_type=cmd.sec_type,
                exchange=cmd.exchange,
                currency=cmd.currency,
            )

            def _on_quote(quote):
                event = QuoteEvent(
                    symbol=quote.symbol,
                    timestamp=quote.timestamp,
                    bid=quote.bid,
                    ask=quote.ask,
                    bid_size=quote.bid_size,
                    ask_size=quote.ask_size,
                    last=quote.last,
                    last_size=quote.last_size,
                    volume=quote.volume,
                )
                self.stream.emit_quote(event)

            req_id = self._market_data.subscribe_market_data(
                contract, callback=_on_quote, snapshot=cmd.snapshot
            )
            self._md_subscriptions[cmd.symbol] = req_id
            return req_id

        queued = QueuedCommand(
            command_type=QueuedCommandType.SUBSCRIBE_MD,
            executor=_execute,
            symbol=cmd.symbol,
            priority=COMMAND_PRIORITIES[QueuedCommandType.SUBSCRIBE_MD],
        )
        self._order_queue.enqueue(queued)
        return queued.wait_for_result(timeout=10.0)

    def handle_unsubscribe_market_data(self, cmd: UnsubscribeMarketDataCommand) -> None:
        """Unsubscribe from market data via queue."""
        self._ensure_connected()

        def _execute():
            req_id = self._md_subscriptions.pop(cmd.symbol, None)
            if req_id is not None:
                self._market_data.unsubscribe_market_data(req_id)
            return True

        queued = QueuedCommand(
            command_type=QueuedCommandType.UNSUBSCRIBE_MD,
            executor=_execute,
            symbol=cmd.symbol,
            priority=COMMAND_PRIORITIES[QueuedCommandType.UNSUBSCRIBE_MD],
        )
        self._order_queue.enqueue(queued)
        queued.wait_for_result(timeout=10.0)

    def handle_historical_data(self, cmd: HistoricalDataCommand) -> int:
        """Request historical data. NOTE: r2 spec says block in v1."""
        logger.warning(
            "Historical data requests are disabled in PA r2 v1 per spec. "
            "Use external data sources instead."
        )
        raise RuntimeError("Historical data requests disabled in PA r2 v1")

    # ========================================================================
    # CONVENIENCE — request broker snapshots
    # ========================================================================

    def request_positions(self) -> List:
        """Request positions from broker. Also emits PositionEvents."""
        self._ensure_connected()
        positions = self._account.get_positions(block=True, timeout=5.0)
        for pos in positions:
            self.stream.emit_position(
                PositionEvent(
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    avg_cost=pos.avg_cost,
                    account=pos.account,
                    sec_type=pos.sec_type,
                    exchange=pos.exchange,
                    currency=pos.currency,
                )
            )
        return positions

    def request_account_summary(self) -> Dict[str, Any]:
        """Request account summary from broker."""
        self._ensure_connected()
        account_values = self._account.get_account_summary(block=True, timeout=5.0)
        for av in account_values.values():
            self.stream.emit_account_value(
                AccountValueEvent(
                    key=av.key,
                    value=av.value,
                    currency=av.currency,
                    account=av.account,
                )
            )
        return account_values

    def subscribe_account_updates(self):
        """Subscribe to real-time account updates."""
        self._ensure_connected()
        self._account.subscribe_account_updates(subscribe=True)
        logger.info("Subscribed to real-time account updates")

    # ========================================================================
    # r2 STATUS
    # ========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive PA r2 status."""
        return {
            "connected": self._connected,
            "mode": self._active_mode,
            "kill_state": self._kill_manager.get_status(),
            "failsafe": self._failsafe.get_status(),
            "order_queue": self._order_queue.get_status(),
            "stop_throttler": self._stop_throttler.get_status(),
            "pacing": self._pacing_engine.get_status(),
            "rate_limiting": self._rate_limiter.get_all_usage(),
            "state": self._state.get_state_summary(),
        }

    # ========================================================================
    # INTERNAL — Kill gate and rate gate for OrderQueue
    # ========================================================================

    def _kill_gate_check(self, cmd_type: QueuedCommandType) -> bool:
        """Check if command is allowed by kill state. Used by OrderQueue."""
        intent_map = {
            QueuedCommandType.PLACE_ORDER: CommandIntent.OPEN,
            QueuedCommandType.CANCEL_ORDER: CommandIntent.CANCEL,
            QueuedCommandType.MODIFY_ORDER: CommandIntent.MODIFY_STOP,
            QueuedCommandType.FLATTEN: CommandIntent.CLOSE,
            QueuedCommandType.SUBSCRIBE_MD: CommandIntent.MARKET_DATA,
            QueuedCommandType.UNSUBSCRIBE_MD: CommandIntent.MARKET_DATA,
        }
        intent = intent_map.get(cmd_type, CommandIntent.ADMIN)

        # Also check pacing
        is_critical = cmd_type in (
            QueuedCommandType.CANCEL_ORDER, QueuedCommandType.FLATTEN
        )
        if not self._pacing_engine.is_operation_allowed(is_critical=is_critical):
            logger.warning(f"Command blocked by pacing recovery: {cmd_type.value}")
            return False

        return self._kill_manager.is_command_allowed(intent)

    def _rate_gate_check(self, cmd_type: QueuedCommandType) -> None:
        """Apply rate limiting for command type. Used by OrderQueue."""
        channel_map = {
            QueuedCommandType.PLACE_ORDER: "order_place",
            QueuedCommandType.CANCEL_ORDER: "order_cancel",
            QueuedCommandType.MODIFY_ORDER: "order_modify",
            QueuedCommandType.FLATTEN: "order_place",
            QueuedCommandType.SUBSCRIBE_MD: "market_data_subscribe",
            QueuedCommandType.UNSUBSCRIBE_MD: "market_data_subscribe",
        }
        channel = channel_map.get(cmd_type, "misc")
        self._rate_limiter.wait_if_needed(channel, operation=cmd_type.value)

    # ========================================================================
    # INTERNAL — Event callbacks for r2 modules → stream
    # ========================================================================

    def _on_kill_state_changed(self, change: KillStateChange) -> None:
        """Kill state changed → emit event."""
        self.stream.emit_kill_state(
            KillStateEvent(
                from_state=change.from_state.value,
                to_state=change.to_state.value,
                reason=change.reason,
                source=change.source,
                timestamp=change.timestamp,
            )
        )

    def _on_failsafe_stage_changed(self, event: FailsafeEvent) -> None:
        """Failsafe stage changed → emit event."""
        self.stream.emit_failsafe(
            FailsafeStageEvent(
                stage=event.stage.value,
                seconds_since_heartbeat=event.seconds_since_heartbeat,
                message=event.message,
                timestamp=event.timestamp,
            )
        )

    def _on_pacing_event(self, event: PacingEvent) -> None:
        """Pacing state changed → emit event."""
        self.stream.emit_pacing(
            PacingStateEvent(
                in_recovery=event.in_recovery,
                error_code=event.error_code,
                cooldown_sec=event.cooldown_sec,
                violation_count=event.violation_count,
                message=event.message,
                timestamp=event.timestamp,
            )
        )

    def _on_reconciliation_report(self, report: ReconciliationReport) -> None:
        """Reconciliation completed → emit event."""
        self.stream.emit_reconciliation(
            ReconciliationReportEvent(
                success=report.success,
                duration_sec=report.duration_sec,
                positions_broker=report.positions_broker,
                positions_local=report.positions_local,
                orders_broker=report.orders_broker,
                orders_local=report.orders_local,
                orders_orphaned=len(report.orders_orphaned),
                positions_mismatches=len(report.positions_mismatches),
                actions_taken=report.actions_taken,
                message=report.summary(),
                timestamp=report.timestamp,
            )
        )

    # ========================================================================
    # INTERNAL — HardKill sequence
    # ========================================================================

    def _execute_hardkill_sequence(self) -> None:
        """
        Execute HardKill: cancel all open orders, flatten all positions.
        Called by KillManager when HardKill is triggered.
        """
        logger.critical("🔴 HARDKILL SEQUENCE INITIATED")

        try:
            # 1. Cancel all open orders
            if self._orders:
                active_orders = self._orders.get_active_orders()
                for order in active_orders:
                    try:
                        self._orders.cancel_order(order.order_id)
                        logger.warning(f"HardKill: cancelled order {order.order_id}")
                    except Exception as e:
                        logger.error(f"HardKill: failed to cancel {order.order_id}: {e}")

                # Also request global cancel from IB
                if self._connection and self._connection.is_ready():
                    self._connection.reqGlobalCancel()
                    logger.warning("HardKill: reqGlobalCancel sent")

            # 2. Flatten all positions
            if self._account:
                positions = self._account.get_positions(block=True, timeout=5.0)
                for pos in positions:
                    if pos.quantity != 0:
                        action = "SELL" if pos.quantity > 0 else "BUY"
                        contract = Contract(
                            symbol=pos.symbol,
                            sec_type=pos.sec_type,
                            exchange=pos.exchange,
                            currency=pos.currency,
                        )
                        try:
                            self._orders.place_order(
                                contract=contract,
                                action=OrderAction(action),
                                quantity=abs(pos.quantity),
                                order_type=OrderType.MARKET,
                            )
                            logger.warning(
                                f"HardKill: flatten {pos.symbol} "
                                f"{action} {abs(pos.quantity)}"
                            )
                        except Exception as e:
                            logger.error(
                                f"HardKill: failed to flatten {pos.symbol}: {e}"
                            )

            logger.critical("🔴 HARDKILL SEQUENCE COMPLETE")

        except Exception as e:
            logger.critical(f"🔴 HARDKILL SEQUENCE ERROR: {e}")

    # ========================================================================
    # INTERNAL — Reconciliation
    # ========================================================================

    def _run_reconciliation(self) -> None:
        """Run reconciliation: query IB, diff vs local, resolve."""
        logger.info("Running reconciliation...")

        try:
            # Query broker truth
            broker_positions = self._account.get_positions(block=True, timeout=10.0)
            self._orders.request_open_orders()
            import time
            time.sleep(2)  # Wait for open orders to arrive

            broker_orders = self._orders.get_all_orders()

            # Get local state
            local_positions = {
                pos.symbol: pos for pos in self._state.get_all_positions()
            }
            local_orders = {
                order.order_id: order for order in self._state.get_all_orders()
            }

            # Run reconciliation
            report = self._reconciliation.reconcile(
                broker_positions=broker_positions,
                broker_orders=broker_orders,
                local_positions=local_positions,
                local_orders=local_orders,
                cancel_order_fn=lambda oid: self._orders.cancel_order(oid),
                update_local_positions_fn=self._state.update_positions,
                update_local_orders_fn=self._state.update_orders,
            )

            logger.info(f"Reconciliation complete: success={report.success}")

        except Exception as e:
            logger.error(f"Reconciliation failed: {e}")

    # ========================================================================
    # INTERNAL — Wire pacing engine to connection errors
    # ========================================================================

    def _wire_pacing_to_connection(self) -> None:
        """Hook pacing engine into ConnectionManager error handler."""
        original_error = self._connection.on_error

        def _error_with_pacing(reqId, errorCode, errorString):
            # Check for pacing violations
            self._pacing_engine.on_ib_error(errorCode, errorString)
            # Call original handler if any
            if original_error:
                original_error(reqId, errorCode, errorString)

        self._connection.on_error = _error_with_pacing

    # ========================================================================
    # INTERNAL — Wire reconnection hooks
    # ========================================================================

    def _wire_reconnection_hooks(self) -> None:
        """Hook ConnectionManager reconnection events to reconciliation + stream."""

        def _on_reconnected():
            logger.info("Reconnection detected — running auto-reconciliation")
            self.stream.emit_connection(
                ConnectionEvent(ConnectionStatus.CONNECTED, "Reconnected to IB")
            )
            recon_config = self.config.get("reconciliation", {})
            if recon_config.get("on_reconnect", True):
                try:
                    self._run_reconciliation()
                except Exception as e:
                    logger.error(f"Post-reconnect reconciliation failed: {e}")

        def _on_disconnected():
            self.stream.emit_connection(
                ConnectionEvent(ConnectionStatus.DISCONNECTED, "Connection lost")
            )

        def _on_reconnecting(attempt, max_attempts):
            self.stream.emit_connection(
                ConnectionEvent(
                    ConnectionStatus.RECONNECTING,
                    f"Reconnecting {attempt}/{max_attempts}",
                )
            )

        def _on_reconnect_failed():
            self.stream.emit_connection(
                ConnectionEvent(ConnectionStatus.ERROR, "All reconnection attempts failed")
            )

        self._connection.on_connected = _on_reconnected
        self._connection.on_disconnected = _on_disconnected
        self._connection.on_reconnecting = _on_reconnecting
        self._connection.on_reconnect_failed = _on_reconnect_failed

    # ========================================================================
    # INTERNAL — Wire broker callbacks to output stream
    # ========================================================================

    def _wire_broker_to_stream(self):
        """Wire broker adapter callbacks to PAOutputStream events."""

        def _on_position(pos):
            self._state.update_position(pos)
            self.stream.emit_position(
                PositionEvent(
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    avg_cost=pos.avg_cost,
                    account=pos.account,
                    sec_type=pos.sec_type,
                    exchange=pos.exchange,
                    currency=pos.currency,
                )
            )

        self._account.add_position_callback(_on_position)

        def _on_account_value(av):
            self.stream.emit_account_value(
                AccountValueEvent(
                    key=av.key,
                    value=av.value,
                    currency=av.currency,
                    account=av.account,
                )
            )

        self._account.add_account_callback(_on_account_value)

        logger.debug("Broker callbacks wired to output stream + state manager")

    # ========================================================================
    # UTILITY
    # ========================================================================

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        with open(config_file, "r") as f:
            return yaml.safe_load(f)

    def _signal_handler(self, signum, frame):
        logger.warning(f"Received signal {signum}, shutting down...")
        self._shutdown_requested = True
        self.disconnect()
        sys.exit(0)

    def _ensure_connected(self):
        if not self._connected:
            raise RuntimeError("PA not connected. Call connect() first.")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def kill_state(self) -> KillState:
        return self._kill_manager.state

    @property
    def connection(self) -> ConnectionManager:
        return self._connection

    @property
    def market_data(self) -> MarketDataAdapter:
        return self._market_data

    @property
    def orders(self) -> OrderExecutionAdapter:
        return self._orders

    @property
    def account(self) -> AccountManager:
        return self._account

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        kill = self._kill_manager.state.value
        return f"PlatformAdapter(PA r2, {status}, kill={kill}, mode={self._active_mode})"


# ============================================================================
# Example usage
# ============================================================================

def main():
    """Example: PA r2 as execution enforcement layer."""
    pa = PlatformAdapter()

    # Register downstream listeners
    pa.stream.on_quote(lambda q: logger.info(f"QUOTE: {q}"))
    pa.stream.on_fill(lambda f: logger.info(f"FILL: {f}"))
    pa.stream.on_order_update(lambda u: logger.info(f"ORDER: {u}"))
    pa.stream.on_position(lambda p: logger.info(f"POSITION: {p}"))
    pa.stream.on_account_value(lambda a: logger.info(f"ACCOUNT: {a}"))
    pa.stream.on_connection(lambda c: logger.info(f"CONNECTION: {c}"))

    # r2 event listeners
    pa.stream.on_kill_state(lambda e: logger.warning(f"KILL STATE: {e}"))
    pa.stream.on_failsafe(lambda e: logger.warning(f"FAILSAFE: {e}"))
    pa.stream.on_pacing(lambda e: logger.warning(f"PACING: {e}"))
    pa.stream.on_reconciliation(lambda e: logger.info(f"RECONCILIATION: {e}"))

    if not pa.connect():
        logger.error("Failed to connect")
        return

    try:
        # Send heartbeat (Exec does this periodically)
        pa.heartbeat_from_exec()

        # Subscribe to data
        pa.handle_subscribe_market_data(
            SubscribeMarketDataCommand(symbol="AAPL")
        )

        # Subscribe to account updates
        pa.subscribe_account_updates()

        # Request snapshots
        pa.request_positions()
        pa.request_account_summary()

        # Place an order (from OE)
        order_id = pa.handle_place_order(
            PlaceOrderCommand(symbol="AAPL", action="BUY", quantity=100)
        )
        logger.info(f"Placed order: {order_id}")

        # Show status
        logger.info(f"PA Status: {pa.get_status()}")

        # Keep running
        import time
        logger.info("PA r2 running — Ctrl+C to stop")
        while True:
            pa.heartbeat_from_exec()  # Keep failsafe happy
            time.sleep(5)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        pa.disconnect()


if __name__ == "__main__":
    main()
