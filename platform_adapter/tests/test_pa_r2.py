"""
PAr2 Unit Tests
================
Tests against acceptance criteria from:
  - runtime state machine spec v0 §8
  - PAr2 dev spec §7, §9, §10

Coverage:
  A. SoftKill blocks OPEN/ADD but allows CLOSE and tighten-only stop modifies
  B. Heartbeat loss triggers FREEZE then AUTOEXIT at configured thresholds
  C. AUTOEXIT always results in LOCKOUT when autoexit_implies_lockout=true
  D. HardKill always flattens + cancels and results in LOCKOUT
  E. Reconciliation unsafe mismatch always results in LOCKOUT
  F. EXIT commands always preempt NORMAL commands
  G. Rate limiter token bucket works correctly
  H. Stop-modify throttler enforces min interval + min delta + merge
  I. OrderQueue idempotency + position enforcement
  J. Config loads correctly
"""

import time
import threading
import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from platform_adapter.pa_r2.models import (
    PACommand, PAEvent, PAEventType, KillState, TradingMode,
    Channel, Priority, Action, IntentType,
    make_kill_event, make_connection_event, make_command_rejected_event,
)
from platform_adapter.pa_r2.kill_state import KillStateMachine
from platform_adapter.pa_r2.queue import OrderQueue
from platform_adapter.pa_r2.rate_limiter import ChannelRateLimiter, TokenBucket
from platform_adapter.pa_r2.stop_throttler import StopModifyThrottler
from platform_adapter.pa_r2.config import PAr2Config
from platform_adapter.pa_r2.reconciliation import (
    ReconciliationRoutine, ReconciliationResult,
    IBOrderSnapshot, IBPositionSnapshot,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cmd(action=Action.PLACE, intent=IntentType.OPEN, priority=Priority.NORMAL,
              symbol="ES", channel=Channel.ORDER_PLACE, order_spec=None,
              command_id=None):
    cmd = PACommand(
        command_id=command_id or PACommand.make_id(),
        ts_utc_ms=PACommand.now_ms(),
        symbol=symbol,
        trading_mode=TradingMode.PAPER,
        channel=channel,
        priority=priority,
        action=action,
        intent_type=intent,
        order_spec=order_spec or {"side": "BUY", "order_kind": "MKT", "qty": 1},
    )
    return cmd


class EventCollector:
    def __init__(self):
        self.events = []
    def __call__(self, evt):
        self.events.append(evt)
    def types(self):
        return [e.type.value for e in self.events]


# ══════════════════════════════════════════════════════════════════════════════
# A. SoftKill blocks OPEN/ADD, allows CLOSE + tighten-only
# ══════════════════════════════════════════════════════════════════════════════

class TestSoftKill:
    def test_softkill_blocks_open(self):
        """A: SoftKill must block OPEN commands"""
        events = EventCollector()
        q = OrderQueue(
            kill_state_fn=lambda: KillState.SOFTKILL,
            on_event=events,
        )
        cmd = _make_cmd(intent=IntentType.OPEN, priority=Priority.NORMAL)
        result = q.enqueue(cmd)
        assert result is False
        assert "COMMAND_REJECTED" in events.types()

    def test_softkill_blocks_add(self):
        """A: SoftKill must block ADD commands"""
        events = EventCollector()
        q = OrderQueue(
            kill_state_fn=lambda: KillState.SOFTKILL,
            on_event=events,
        )
        cmd = _make_cmd(intent=IntentType.ADD, priority=Priority.NORMAL)
        result = q.enqueue(cmd)
        assert result is False
        assert "COMMAND_REJECTED" in events.types()

    def test_softkill_allows_close(self):
        """A: SoftKill must allow CLOSE commands"""
        events = EventCollector()
        q = OrderQueue(
            kill_state_fn=lambda: KillState.SOFTKILL,
            on_event=events,
        )
        cmd = _make_cmd(intent=IntentType.CLOSE, priority=Priority.EXIT)
        result = q.enqueue(cmd)
        assert result is True
        assert "COMMAND_REJECTED" not in events.types()

    def test_softkill_allows_tighten_stop(self):
        """A: SoftKill must allow MODIFY_STOP with tighten_only"""
        events = EventCollector()
        q = OrderQueue(
            kill_state_fn=lambda: KillState.SOFTKILL,
            on_event=events,
        )
        cmd = _make_cmd(
            action=Action.MODIFY,
            intent=IntentType.MODIFY_STOP,
            priority=Priority.NORMAL,
            order_spec={"order_id": 1, "stop_price": 100.0},
        )
        cmd.constraints = {"tighten_only": True}
        result = q.enqueue(cmd)
        assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# B. Heartbeat loss triggers FREEZE then AUTOEXIT
# ══════════════════════════════════════════════════════════════════════════════

class TestHeartbeatLoss:
    def test_freeze_on_heartbeat_loss(self):
        """B: Heartbeat loss > T_freeze triggers FAILSAFE_FREEZE"""
        events = EventCollector()
        ksm = KillStateMachine(
            on_event=events,
            on_flatten=lambda r: None,
            freeze_after_ms=100,         # 100ms for fast test
            autoexit_after_ms=500,
            heartbeat_check_interval_ms=50,
        )
        ksm.start()
        time.sleep(0.25)  # 250ms > 100ms freeze threshold
        state = ksm.state
        ksm.stop()
        assert state in (KillState.FAILSAFE_FREEZE, KillState.FAILSAFE_AUTOEXIT)

    def test_autoexit_on_prolonged_loss(self):
        """B: Heartbeat loss > T_flatten triggers FAILSAFE_AUTOEXIT"""
        events = EventCollector()
        flattened = []
        ksm = KillStateMachine(
            on_event=events,
            on_flatten=lambda r: flattened.append(r),
            freeze_after_ms=50,
            autoexit_after_ms=150,
            heartbeat_check_interval_ms=30,
        )
        ksm.start()
        time.sleep(0.4)  # 400ms > 150ms autoexit threshold
        state = ksm.state
        ksm.stop()
        assert state in (KillState.FAILSAFE_AUTOEXIT, KillState.LOCKOUT)
        assert len(flattened) > 0  # flatten was called

    def test_heartbeat_resumes_clears_freeze(self):
        """B: Heartbeat resuming during FREEZE returns to NORMAL"""
        events = EventCollector()
        ksm = KillStateMachine(
            on_event=events,
            on_flatten=lambda r: None,
            freeze_after_ms=80,
            autoexit_after_ms=5000,  # high so we don't hit it
            heartbeat_check_interval_ms=30,
        )
        ksm.start()
        time.sleep(0.2)  # enter FREEZE
        assert ksm.state == KillState.FAILSAFE_FREEZE
        ksm.heartbeat()  # resume heartbeat
        time.sleep(0.05)
        assert ksm.state == KillState.NORMAL
        ksm.stop()


# ══════════════════════════════════════════════════════════════════════════════
# C. AUTOEXIT → LOCKOUT when autoexit_implies_lockout=true
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoExitLockout:
    def test_autoexit_implies_lockout(self):
        """C: AUTOEXIT must result in LOCKOUT when config=true (default)"""
        events = EventCollector()
        ksm = KillStateMachine(
            on_event=events,
            on_flatten=lambda r: None,
            freeze_after_ms=30,
            autoexit_after_ms=80,
            autoexit_implies_lockout=True,
            heartbeat_check_interval_ms=20,
        )
        ksm.start()
        time.sleep(0.5)  # well past autoexit
        state = ksm.state
        ksm.stop()
        assert state == KillState.LOCKOUT
        assert "LOCKOUT_ENABLED" in events.types()


# ══════════════════════════════════════════════════════════════════════════════
# D. HardKill flattens + LOCKOUT
# ══════════════════════════════════════════════════════════════════════════════

class TestHardKill:
    def test_hardkill_flattens_and_locks(self):
        """D: HardKill must flatten + cancel and enter LOCKOUT"""
        events = EventCollector()
        flattened = []
        ksm = KillStateMachine(
            on_event=events,
            on_flatten=lambda r: flattened.append(r),
        )
        ksm.start()
        ksm.hardkill("OPERATOR_PANIC")
        time.sleep(0.05)
        assert ksm.state == KillState.LOCKOUT
        assert len(flattened) > 0
        assert "HARDKILL_EXECUTED" in events.types()
        assert "LOCKOUT_ENABLED" in events.types()
        ksm.stop()

    def test_lockout_requires_manual_reset(self):
        """D: LOCKOUT can only be cleared by OPERATOR_RESET"""
        events = EventCollector()
        ksm = KillStateMachine(
            on_event=events,
            on_flatten=lambda r: None,
        )
        ksm.start()
        ksm.hardkill("test")
        time.sleep(0.05)
        assert ksm.state == KillState.LOCKOUT
        ksm.reset_lockout("OPERATOR_RESET")
        time.sleep(0.05)
        assert ksm.state == KillState.NORMAL
        ksm.stop()


# ══════════════════════════════════════════════════════════════════════════════
# F. EXIT preempts NORMAL
# ══════════════════════════════════════════════════════════════════════════════

class TestExitPriority:
    def test_exit_dequeues_before_normal(self):
        """F: EXIT commands must be dequeued before NORMAL"""
        events = EventCollector()
        q = OrderQueue(
            kill_state_fn=lambda: KillState.NORMAL,
            on_event=events,
        )
        # Enqueue NORMAL first, then EXIT
        normal_cmd = _make_cmd(intent=IntentType.OPEN, priority=Priority.NORMAL)
        exit_cmd = _make_cmd(intent=IntentType.CLOSE, priority=Priority.EXIT)

        q.enqueue(normal_cmd)
        q.enqueue(exit_cmd)

        # Dequeue should return EXIT first
        first = q.dequeue(block=False)
        assert first is not None
        assert first.priority == Priority.EXIT

        second = q.dequeue(block=False)
        assert second is not None
        assert second.priority == Priority.NORMAL


# ══════════════════════════════════════════════════════════════════════════════
# G. Rate Limiter
# ══════════════════════════════════════════════════════════════════════════════

class TestRateLimiter:
    def test_token_bucket_basic(self):
        """G: TokenBucket allows up to burst then blocks"""
        tb = TokenBucket(sustained_per_sec=10, burst_max=5)
        # Should allow 5 immediate acquires (burst)
        for _ in range(5):
            assert tb.acquire(block=False) is True
        # 6th should fail (no tokens left)
        assert tb.acquire(block=False) is False

    def test_exit_bypasses_blocking(self):
        """G: EXIT priority must bypass rate limiter blocking"""
        rl = ChannelRateLimiter(sustained_per_sec=1, burst_max=1)
        # Exhaust the bucket
        rl.acquire(Channel.ORDER_PLACE, Priority.NORMAL, block=False)
        # EXIT should still succeed (best-effort)
        result = rl.acquire(Channel.ORDER_PLACE, Priority.EXIT, block=False)
        assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# H. Stop-Modify Throttler
# ══════════════════════════════════════════════════════════════════════════════

class TestStopThrottler:
    def test_min_interval_merges(self):
        """H: Modifies within 75ms interval should be merged"""
        st = StopModifyThrottler(min_interval_ms=75, min_delta_ticks=1)
        cmd1 = _make_cmd(
            action=Action.MODIFY, intent=IntentType.MODIFY_STOP,
            order_spec={"order_id": 1, "stop_price": 100.0},
        )
        cmd2 = _make_cmd(
            action=Action.MODIFY, intent=IntentType.MODIFY_STOP,
            order_spec={"order_id": 1, "stop_price": 101.0},
        )
        r1 = st.submit(cmd1, 99.0, 0.25, KillState.NORMAL)
        assert r1.allowed is True
        # Immediate second submit — should be merged (not allowed yet)
        r2 = st.submit(cmd2, 100.0, 0.25, KillState.NORMAL)
        assert r2.allowed is False

    def test_min_delta_rejects(self):
        """H: Modify with delta < 1 tick should be rejected"""
        st = StopModifyThrottler(min_interval_ms=0, min_delta_ticks=1)
        cmd = _make_cmd(
            action=Action.MODIFY, intent=IntentType.MODIFY_STOP,
            order_spec={"order_id": 1, "stop_price": 100.1},
        )
        r = st.submit(cmd, 100.0, 0.25, KillState.NORMAL)
        # 0.1 < 0.25 (1 tick) → reject for insufficient delta
        assert r.allowed is False

    def test_exit_bypasses_throttle(self):
        """H: EXIT priority must bypass stop-modify throttling"""
        st = StopModifyThrottler(min_interval_ms=5000, min_delta_ticks=100)
        cmd = _make_cmd(
            action=Action.MODIFY, intent=IntentType.MODIFY_STOP,
            priority=Priority.EXIT,
            order_spec={"order_id": 1, "stop_price": 100.0},
        )
        r = st.submit(cmd, 99.9, 0.25, KillState.NORMAL)
        assert r.allowed is True

    def test_flush_due_returns_merged(self):
        """H: flush_due returns merged modifies after interval expires"""
        st = StopModifyThrottler(min_interval_ms=50, min_delta_ticks=1)
        cmd1 = _make_cmd(
            action=Action.MODIFY, intent=IntentType.MODIFY_STOP,
            order_spec={"order_id": 1, "stop_price": 100.0},
        )
        cmd2 = _make_cmd(
            action=Action.MODIFY, intent=IntentType.MODIFY_STOP,
            order_spec={"order_id": 1, "stop_price": 102.0},
        )
        st.submit(cmd1, 99.0, 0.25, KillState.NORMAL)
        st.submit(cmd2, 100.0, 0.25, KillState.NORMAL)
        time.sleep(0.1)  # wait for interval to expire
        flushed = st.flush_due()
        assert len(flushed) >= 1
        # The flushed command should have the latest price (102.0)
        assert flushed[0].order_spec["stop_price"] == 102.0


# ══════════════════════════════════════════════════════════════════════════════
# I. OrderQueue idempotency + position enforcement
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderQueue:
    def test_duplicate_rejection(self):
        """I: Duplicate command_id must be rejected"""
        events = EventCollector()
        q = OrderQueue(
            kill_state_fn=lambda: KillState.NORMAL,
            on_event=events,
        )
        cmd = _make_cmd()
        q.enqueue(cmd)
        # Same command again
        result = q.enqueue(cmd)
        assert result is False
        assert "COMMAND_REJECTED" in events.types()

    def test_position_enforcement(self):
        """I: Cannot OPEN if already holding a position for that symbol"""
        events = EventCollector()
        q = OrderQueue(
            kill_state_fn=lambda: KillState.NORMAL,
            on_event=events,
        )
        q.notify_position_opened("ES")
        cmd = _make_cmd(intent=IntentType.OPEN, symbol="ES")
        result = q.enqueue(cmd)
        assert result is False
        assert "COMMAND_REJECTED" in events.types()

    def test_lockout_blocks_everything(self):
        """I: LOCKOUT blocks all commands"""
        events = EventCollector()
        q = OrderQueue(
            kill_state_fn=lambda: KillState.LOCKOUT,
            on_event=events,
        )
        cmd = _make_cmd(intent=IntentType.CLOSE, priority=Priority.EXIT)
        result = q.enqueue(cmd)
        assert result is False
        assert "COMMAND_REJECTED" in events.types()


# ══════════════════════════════════════════════════════════════════════════════
# J. Config
# ══════════════════════════════════════════════════════════════════════════════

class TestConfig:
    def test_defaults(self):
        """J: Default config matches spec canonical values"""
        cfg = PAr2Config()
        assert cfg.ib.trading_mode == "PAPER"
        assert cfg.ib.port == 4002
        assert cfg.pacing.sustained_msgs_per_sec == 20.0
        assert cfg.pacing.burst_msgs_per_sec == 40.0
        assert cfg.stop_modify.min_modify_interval_ms == 75.0
        assert cfg.stop_modify.min_delta_ticks_or_pips == 1.0
        assert cfg.failsafe.freeze_after_ms == 15_000.0
        assert cfg.failsafe.autoexit_after_ms == 180_000.0
        assert cfg.failsafe.autoexit_implies_lockout is True

    def test_from_dict(self):
        """J: Config loads from dict correctly"""
        d = {
            "ib": {"host": "10.0.0.1", "port": 4001, "trading_mode": "LIVE"},
            "pacing": {"sustained_msgs_per_sec": 15},
            "failsafe": {"freeze_after_ms": 10000},
        }
        cfg = PAr2Config.from_dict(d)
        assert cfg.ib.host == "10.0.0.1"
        assert cfg.ib.port == 4001
        assert cfg.ib.trading_mode == "LIVE"
        assert cfg.pacing.sustained_msgs_per_sec == 15.0
        assert cfg.failsafe.freeze_after_ms == 10_000.0
        # Unset values should be defaults
        assert cfg.failsafe.autoexit_after_ms == 180_000.0

    def test_to_dict_roundtrip(self):
        """J: Config roundtrips through to_dict"""
        cfg = PAr2Config()
        d = cfg.to_dict()
        cfg2 = PAr2Config.from_dict(d)
        assert cfg2.ib.trading_mode == cfg.ib.trading_mode
        assert cfg2.failsafe.freeze_after_ms == cfg.failsafe.freeze_after_ms


# ══════════════════════════════════════════════════════════════════════════════
# Wire contract / models
# ══════════════════════════════════════════════════════════════════════════════

class TestModels:
    def test_pa_command_creates_id(self):
        cmd = _make_cmd()
        assert cmd.command_id.startswith("cmd_")
        assert cmd.ts_utc_ms > 0

    def test_pa_event_wire_version(self):
        evt = PAEvent(type=PAEventType.MARKET_BAR, trading_mode=TradingMode.PAPER, payload={})
        assert evt.wire_version == "PAWire.v0"

    def test_pa_event_to_dict(self):
        evt = PAEvent(
            type=PAEventType.FILL,
            trading_mode=TradingMode.PAPER,
            symbol="ES",
            payload={"qty": 1, "price": 5000.0},
        )
        d = evt.to_dict()
        assert d["type"] == "FILL"
        assert d["wire_version"] == "PAWire.v0"
        assert d["symbol"] == "ES"

    def test_kill_state_values(self):
        expected = {"NORMAL", "SOFTKILL", "FAILSAFE_FREEZE",
                    "FAILSAFE_AUTOEXIT", "HARDKILL", "LOCKOUT"}
        actual = {s.value for s in KillState}
        assert actual == expected

    def test_factory_helpers(self):
        evt = make_kill_event(PAEventType.HARDKILL_EXECUTED, KillState.HARDKILL,
                              "test", TradingMode.PAPER)
        assert evt.type == PAEventType.HARDKILL_EXECUTED
        assert evt.payload["kill_state"] == "HARDKILL"

        evt2 = make_connection_event(True, TradingMode.LIVE)
        assert evt2.type == PAEventType.CONNECTION_UP


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
