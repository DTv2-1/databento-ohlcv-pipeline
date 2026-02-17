"""
Tests for PA r2 enforcement modules.

Tests cover:
  - KillManager state machine
  - FailsafeMonitor escalation
  - OrderQueue priority + kill gate
  - StopModifyThrottler merge/debounce
  - PacingEngine cooldown/backoff
  - ReconciliationEngine diff/policy
  - PerChannelRateLimiter

Author: PA r2
"""

import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# KillManager
# ---------------------------------------------------------------------------
from src.platform_adapter.core.kill_manager import (
    KillManager,
    KillState,
    CommandIntent,
    KillStateChange,
)


class TestKillManager:
    def test_initial_state_is_normal(self):
        km = KillManager()
        assert km.state == KillState.NORMAL

    def test_softkill_blocks_open(self):
        km = KillManager()
        km.set_softkill(reason="test")
        assert km.state == KillState.SOFTKILL
        assert not km.is_command_allowed(CommandIntent.OPEN)
        assert not km.is_command_allowed(CommandIntent.ADD)
        # But CLOSE/CANCEL should still be allowed
        assert km.is_command_allowed(CommandIntent.CLOSE)
        assert km.is_command_allowed(CommandIntent.CANCEL)

    def test_hardkill_triggers_callback(self):
        cb = MagicMock()
        km = KillManager(on_hardkill_triggered=cb)
        km.set_softkill(reason="pre")
        km.hardkill(reason="test")
        cb.assert_called_once()
        # After hardkill, should be in LOCKOUT
        assert km.state == KillState.LOCKOUT

    def test_lockout_blocks_everything_except_admin_and_account(self):
        km = KillManager(on_hardkill_triggered=lambda: None)
        km.set_softkill(reason="step1")
        km.hardkill(reason="step2")
        assert km.state == KillState.LOCKOUT
        assert not km.is_command_allowed(CommandIntent.OPEN)
        assert not km.is_command_allowed(CommandIntent.CLOSE)
        assert not km.is_command_allowed(CommandIntent.CANCEL)
        # Only ADMIN and ACCOUNT are allowed in LOCKOUT
        assert km.is_command_allowed(CommandIntent.ADMIN)
        assert km.is_command_allowed(CommandIntent.ACCOUNT)

    def test_resume_normal_from_softkill(self):
        km = KillManager()
        km.set_softkill(reason="test")
        km.resume_normal(reason="resume")
        assert km.state == KillState.NORMAL

    def test_resume_from_lockout_requires_human(self):
        km = KillManager(lockout_requires_human=True, on_hardkill_triggered=lambda: None)
        km.set_softkill(reason="step1")
        km.hardkill(reason="step2")
        assert km.state == KillState.LOCKOUT
        # Non-human resume should fail
        result = km.resume_normal(reason="auto", source="system")
        assert result is False
        assert km.state == KillState.LOCKOUT
        # Human resume should succeed
        result2 = km.resume_normal(reason="manual reset", source="human")
        assert result2 is True
        assert km.state == KillState.NORMAL

    def test_state_change_callback(self):
        changes = []
        km = KillManager(on_state_changed=lambda c: changes.append(c))
        km.set_softkill(reason="test")
        assert len(changes) == 1
        assert changes[0].from_state == KillState.NORMAL
        assert changes[0].to_state == KillState.SOFTKILL

    def test_failsafe_freeze_from_normal(self):
        km = KillManager()
        km.set_failsafe_freeze(reason="no heartbeat")
        assert km.state == KillState.FAILSAFE_FREEZE


# ---------------------------------------------------------------------------
# OrderQueue
# ---------------------------------------------------------------------------
from src.platform_adapter.core.order_queue import (
    OrderQueue,
    QueuedCommand,
    QueuedCommandType,
    COMMAND_PRIORITIES,
)


class TestOrderQueue:
    def test_enqueue_and_process(self):
        oq = OrderQueue(drain_interval_ms=10)
        oq.start()
        try:
            result_value = 42
            cmd = QueuedCommand(
                command_type=QueuedCommandType.PLACE_ORDER,
                executor=lambda: result_value,
                symbol="ES",
                priority=COMMAND_PRIORITIES[QueuedCommandType.PLACE_ORDER],
            )
            oq.enqueue(cmd)
            result = cmd.wait_for_result(timeout=5.0)
            assert result == 42
        finally:
            oq.stop()

    def test_kill_gate_rejects_command(self):
        def gate(cmd_type):
            return False  # Reject everything

        oq = OrderQueue(drain_interval_ms=10, kill_gate=gate)
        oq.start()
        try:
            cmd = QueuedCommand(
                command_type=QueuedCommandType.PLACE_ORDER,
                executor=lambda: 1,
                symbol="ES",
                priority=5,
            )
            oq.enqueue(cmd)
            with pytest.raises(RuntimeError, match="blocked by kill state"):
                cmd.wait_for_result(timeout=5.0)
        finally:
            oq.stop()

    def test_priority_ordering(self):
        """Cancel commands should be processed before place commands."""
        execution_order = []
        oq = OrderQueue(drain_interval_ms=5)
        # Don't start yet — let commands queue up

        cmd_place = QueuedCommand(
            command_type=QueuedCommandType.PLACE_ORDER,
            executor=lambda: execution_order.append("place"),
            symbol="ES",
            priority=COMMAND_PRIORITIES[QueuedCommandType.PLACE_ORDER],
        )
        cmd_cancel = QueuedCommand(
            command_type=QueuedCommandType.CANCEL_ORDER,
            executor=lambda: execution_order.append("cancel"),
            symbol="ES",
            priority=COMMAND_PRIORITIES[QueuedCommandType.CANCEL_ORDER],
        )

        # Enqueue place first, then cancel
        oq.enqueue(cmd_place)
        oq.enqueue(cmd_cancel)

        # Now start processing
        oq.start()
        try:
            cmd_place.wait_for_result(timeout=5.0)
            cmd_cancel.wait_for_result(timeout=5.0)
            # Cancel (priority 1) should be processed before place (priority 5)
            assert execution_order[0] == "cancel"
            assert execution_order[1] == "place"
        finally:
            oq.stop()

    def test_get_status(self):
        oq = OrderQueue()
        status = oq.get_status()
        assert "pending" in status
        assert "processed" in status
        assert "rejected" in status


# ---------------------------------------------------------------------------
# PacingEngine
# ---------------------------------------------------------------------------
from src.platform_adapter.core.pacing_engine import PacingEngine, PacingEvent


class TestPacingEngine:
    def test_initial_state_not_in_recovery(self):
        pe = PacingEngine()
        assert pe.is_operation_allowed(is_critical=False)

    def test_pacing_error_triggers_recovery(self):
        events = []
        pe = PacingEngine(
            cooldown_sec=0.5,
            on_pacing_event=lambda e: events.append(e),
        )
        pe.on_ib_error(100, "Max rate exceeded")
        assert not pe.is_operation_allowed(is_critical=False)
        # Critical ops should still be allowed
        assert pe.is_operation_allowed(is_critical=True)
        assert len(events) == 1
        assert events[0].in_recovery is True

    def test_recovery_ends_after_cooldown(self):
        pe = PacingEngine(cooldown_sec=0.2)
        pe.on_ib_error(100, "Max rate exceeded")
        assert not pe.is_operation_allowed(is_critical=False)
        time.sleep(0.3)
        assert pe.is_operation_allowed(is_critical=False)

    def test_backoff_multiplier(self):
        pe = PacingEngine(cooldown_sec=0.1, backoff_multiplier=2.0, max_cooldown_sec=10.0)
        pe.on_ib_error(100, "violation 1")
        status1 = pe.get_status()
        assert status1["current_cooldown_sec"] == 0.1
        # Second violation while still in recovery → cooldown doubles
        pe.on_ib_error(100, "violation 2")
        status2 = pe.get_status()
        assert status2["current_cooldown_sec"] == pytest.approx(0.2, abs=0.01)

    def test_non_pacing_error_ignored(self):
        pe = PacingEngine()
        pe.on_ib_error(200, "Some other error")
        assert pe.is_operation_allowed(is_critical=False)


# ---------------------------------------------------------------------------
# StopModifyThrottler
# ---------------------------------------------------------------------------
from src.platform_adapter.core.stop_modify_throttler import StopModifyThrottler


class TestStopModifyThrottler:
    def test_first_modify_sent_immediately(self):
        executor = MagicMock()
        smt = StopModifyThrottler(min_interval_ms=250, min_delta_ticks=1, tick_size=0.25)
        result = smt.submit_stop_modify(
            order_id=1, new_stop_price=5000.0, executor=executor
        )
        assert result == "sent"
        executor.assert_called_once()

    def test_rapid_modify_deferred(self):
        executor = MagicMock()
        smt = StopModifyThrottler(min_interval_ms=500, min_delta_ticks=1, tick_size=0.25)
        # First: sent
        r1 = smt.submit_stop_modify(order_id=1, new_stop_price=5000.0, executor=executor)
        assert r1 == "sent"
        # Second immediately after: should be deferred or merged
        r2 = smt.submit_stop_modify(order_id=1, new_stop_price=5001.0, executor=executor)
        assert r2 in ("deferred", "merged")

    def test_small_delta_dropped(self):
        executor = MagicMock()
        smt = StopModifyThrottler(min_interval_ms=10, min_delta_ticks=2, tick_size=0.25)
        smt.submit_stop_modify(order_id=1, new_stop_price=5000.0, executor=executor)
        time.sleep(0.02)  # Wait for min_interval
        # Change only 0.25 (1 tick) — below min_delta of 2 ticks
        r = smt.submit_stop_modify(order_id=1, new_stop_price=5000.25, executor=executor)
        assert r == "dropped"

    def test_get_status(self):
        smt = StopModifyThrottler()
        status = smt.get_status()
        assert "sent" in status
        assert "dropped" in status
        assert "merged" in status


# ---------------------------------------------------------------------------
# ReconciliationEngine
# ---------------------------------------------------------------------------
from src.platform_adapter.core.reconciliation import (
    ReconciliationEngine,
    ReconciliationReport,
)


class TestReconciliationEngine:
    def _make_position(self, symbol, quantity):
        """Create a mock position object."""
        pos = MagicMock()
        pos.symbol = symbol
        pos.quantity = quantity
        pos.sec_type = "FUT"
        pos.exchange = "CME"
        pos.currency = "USD"
        return pos

    def _make_order(self, order_id):
        """Create a mock order object."""
        order = MagicMock()
        order.order_id = order_id
        return order

    def test_no_diff_produces_clean_report(self):
        re = ReconciliationEngine()
        pos = self._make_position("ES", 1)
        order = self._make_order(100)

        report = re.reconcile(
            broker_positions=[pos],
            broker_orders=[order],
            local_positions={"ES": pos},
            local_orders={100: order},
        )
        assert report.success
        assert len(report.positions_mismatches) == 0
        assert len(report.orders_orphaned) == 0

    def test_orphan_detection(self):
        re = ReconciliationEngine(orphan_policy="log_and_alert")
        broker_order = self._make_order(200)

        report = re.reconcile(
            broker_positions=[],
            broker_orders=[broker_order],
            local_positions={},
            local_orders={},
        )
        assert 200 in report.orders_orphaned

    def test_position_mismatch_detected(self):
        re = ReconciliationEngine(position_mismatch_policy="alert_only")
        broker_pos = self._make_position("ES", 3)
        local_pos = self._make_position("ES", 1)

        report = re.reconcile(
            broker_positions=[broker_pos],
            broker_orders=[],
            local_positions={"ES": local_pos},
            local_orders={},
        )
        assert len(report.positions_mismatches) == 1
        assert report.positions_mismatches[0]["broker_qty"] == 3
        assert report.positions_mismatches[0]["local_qty"] == 1

    def test_orphan_cancel_policy(self):
        cancel_fn = MagicMock()
        re = ReconciliationEngine(orphan_policy="cancel")
        broker_order = self._make_order(300)

        report = re.reconcile(
            broker_positions=[],
            broker_orders=[broker_order],
            local_positions={},
            local_orders={},
            cancel_order_fn=cancel_fn,
        )
        cancel_fn.assert_called_once_with(300)

    def test_report_callback(self):
        reports = []
        re = ReconciliationEngine(on_report=lambda r: reports.append(r))

        re.reconcile(
            broker_positions=[],
            broker_orders=[],
            local_positions={},
            local_orders={},
        )
        assert len(reports) == 1
        assert reports[0].success


# ---------------------------------------------------------------------------
# FailsafeMonitor
# ---------------------------------------------------------------------------
from src.platform_adapter.core.failsafe_monitor import (
    FailsafeMonitor,
    FailsafeStage,
    FailsafeEvent,
)


class TestFailsafeMonitor:
    def test_initial_stage_is_normal(self):
        fm = FailsafeMonitor(t_warn_sec=10, t_freeze_sec=15, t_flatten_sec=180)
        status = fm.get_status()
        assert status["stage"] == "NORMAL"

    def test_heartbeat_resets_timer(self):
        fm = FailsafeMonitor(t_warn_sec=0.2, t_freeze_sec=0.4, t_flatten_sec=1.0)
        fm.start()
        try:
            time.sleep(0.1)
            fm.heartbeat_from_exec()
            status = fm.get_status()
            assert status["stage"] == "NORMAL"
        finally:
            fm.stop()

    def test_warn_stage_escalation(self):
        events = []
        fm = FailsafeMonitor(
            t_warn_sec=0.1,
            t_freeze_sec=10.0,
            t_flatten_sec=20.0,
            on_stage_changed=lambda e: events.append(e),
            check_interval_sec=0.05,
        )
        fm.start()
        try:
            time.sleep(0.25)
            # Should have escalated to at least WARN
            assert any(e.stage == FailsafeStage.WARN for e in events)
        finally:
            fm.stop()

    def test_freeze_callback_fires(self):
        freeze_called = threading.Event()
        fm = FailsafeMonitor(
            t_warn_sec=0.05,
            t_freeze_sec=0.15,
            t_flatten_sec=10.0,
            on_freeze=lambda: freeze_called.set(),
            check_interval_sec=0.05,
        )
        fm.start()
        try:
            assert freeze_called.wait(timeout=2.0)
        finally:
            fm.stop()

    def test_validation_rejects_bad_thresholds(self):
        with pytest.raises(ValueError):
            FailsafeMonitor(
                t_warn_sec=10, t_freeze_sec=5, t_flatten_sec=20
            )


# ---------------------------------------------------------------------------
# PerChannelRateLimiter
# ---------------------------------------------------------------------------
from src.platform_adapter.utils.rate_limiter import PerChannelRateLimiter


class TestPerChannelRateLimiter:
    def test_creation(self):
        rl = PerChannelRateLimiter(
            global_sustained_per_sec=45,
            global_burst_cap=50,
        )
        assert rl is not None

    def test_can_proceed(self):
        rl = PerChannelRateLimiter(
            global_sustained_per_sec=100,
            global_burst_cap=200,
        )
        assert rl.can_proceed("order_place")

    def test_get_all_usage(self):
        rl = PerChannelRateLimiter()
        usage = rl.get_all_usage()
        assert isinstance(usage, dict)


# ---------------------------------------------------------------------------
# r2 Events in PAOutputStream
# ---------------------------------------------------------------------------
from src.platform_adapter.interfaces.pa_outputs import (
    PAOutputStream,
    KillStateEvent,
    FailsafeStageEvent,
    PacingStateEvent,
    ReconciliationReportEvent,
)


class TestR2Events:
    def test_kill_state_event_emission(self):
        received = []
        stream = PAOutputStream()
        stream.on_kill_state(lambda e: received.append(e))
        stream.emit_kill_state(
            KillStateEvent(
                from_state="NORMAL",
                to_state="SOFTKILL",
                reason="test",
                source="exec",
                timestamp=datetime.now(),
            )
        )
        assert len(received) == 1
        assert received[0].to_state == "SOFTKILL"

    def test_failsafe_event_emission(self):
        received = []
        stream = PAOutputStream()
        stream.on_failsafe(lambda e: received.append(e))
        stream.emit_failsafe(
            FailsafeStageEvent(
                stage=1,
                seconds_since_heartbeat=12.5,
                message="WARN stage",
                timestamp=datetime.now(),
            )
        )
        assert len(received) == 1
        assert received[0].stage == 1

    def test_pacing_event_emission(self):
        received = []
        stream = PAOutputStream()
        stream.on_pacing(lambda e: received.append(e))
        stream.emit_pacing(
            PacingStateEvent(
                in_recovery=True,
                error_code=100,
                cooldown_sec=5.0,
                violation_count=1,
                message="pacing violation",
                timestamp=datetime.now(),
            )
        )
        assert len(received) == 1
        assert received[0].in_recovery is True

    def test_reconciliation_event_emission(self):
        received = []
        stream = PAOutputStream()
        stream.on_reconciliation(lambda e: received.append(e))
        stream.emit_reconciliation(
            ReconciliationReportEvent(
                success=True,
                duration_sec=0.5,
                positions_broker=2,
                positions_local=2,
                orders_broker=1,
                orders_local=1,
                orders_orphaned=0,
                positions_mismatches=0,
                actions_taken=[],
                message="clean",
                timestamp=datetime.now(),
            )
        )
        assert len(received) == 1
        assert received[0].success is True


# ---------------------------------------------------------------------------
# r2 Commands (PAInputStream)
# ---------------------------------------------------------------------------
from src.platform_adapter.interfaces.pa_inputs import (
    SoftKillCommand,
    HardKillCommand,
    ResumeNormalCommand,
    SetLockoutCommand,
    HeartbeatCommand,
    ReconcileCommand,
    SwitchModeCommand,
)


class TestR2Commands:
    def test_softkill_command(self):
        cmd = SoftKillCommand(reason="test")
        assert cmd.reason == "test"

    def test_hardkill_command(self):
        cmd = HardKillCommand(reason="emergency")
        assert cmd.reason == "emergency"

    def test_resume_command(self):
        cmd = ResumeNormalCommand(reason="all clear")
        assert cmd.reason == "all clear"

    def test_heartbeat_command(self):
        cmd = HeartbeatCommand()
        assert cmd is not None

    def test_reconcile_command(self):
        cmd = ReconcileCommand()
        assert cmd is not None

    def test_switch_mode_valid(self):
        cmd = SwitchModeCommand(mode="live")
        assert cmd.mode == "live"
        cmd2 = SwitchModeCommand(mode="paper")
        assert cmd2.mode == "paper"

    def test_switch_mode_invalid(self):
        with pytest.raises(ValueError):
            SwitchModeCommand(mode="invalid")
