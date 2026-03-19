#!/usr/bin/env python3
"""
PAr2 Live Smoke Test — IB Gateway
===================================
Connects PAr2Adapter to IB Gateway, subscribes to market data,
runs the kill state machine, collects events, and writes output JSON.

Usage:
    python3 scripts/test_par2_live.py

Output:
    platform_adapter/output/par2_live_test_<timestamp>.json
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone

# Add source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from platform_adapter.pa_r2 import (
    PAr2Adapter,
    PAr2Config,
    PACommand,
    PAEvent,
    PAEventType,
    KillState,
    TradingMode,
    Channel,
    Priority,
    Action,
    IntentType,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)-7s %(message)s",
)
logger = logging.getLogger("par2_live_test")


# ── Event collector ──────────────────────────────────────────────────────────

class LiveEventCollector:
    def __init__(self):
        self.events = []
        self.start_ts = time.time()

    def __call__(self, evt: PAEvent):
        elapsed = round(time.time() - self.start_ts, 3)
        entry = {
            "elapsed_sec": elapsed,
            "type":         evt.type.value,
            "event_id":     evt.event_id,
            "ts_utc_ms":    evt.ts_utc_ms,
            "trading_mode": evt.trading_mode.value,
            "symbol":       evt.symbol or "",
            "wire_version": evt.wire_version,
            "payload":      evt.payload,
        }
        self.events.append(entry)
        logger.info("EVENT [+%.3fs] %s %s %s",
                     elapsed, evt.type.value, evt.symbol or "", evt.payload)


def run_live_test():
    """Run PAr2 live smoke test against IB Gateway."""

    # ── Config ────────────────────────────────────────────────────────────────
    cfg = PAr2Config.from_dict({
        "ib": {
            "host": "127.0.0.1",
            "port": 4001,
            "client_id": 50,          # unique client id for test
            "trading_mode": "PAPER",  # treat as paper even on live gateway
        },
        "failsafe": {
            "freeze_after_ms": 60000,     # 60s for test (longer to avoid false freeze)
            "autoexit_after_ms": 300000,  # 5min
        },
        "reconciliation": {
            "run_on_reconnect": False,    # disable auto-recon on connect for test
        },
    })

    collector = LiveEventCollector()
    adapter = PAr2Adapter(config=cfg)
    adapter.register_event_handler(collector)

    test_results = {
        "test_name":   "PAr2 Live Smoke Test",
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "config":      cfg.to_dict(),
        "phases":      [],
        "events":      [],
        "summary":     {},
    }

    # ── Phase 1: Connect ──────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("PHASE 1: Connect to IB Gateway %s:%d", cfg.ib.host, cfg.ib.port)
    logger.info("=" * 60)

    try:
        adapter.connect()
    except Exception as exc:
        logger.error("CONNECT FAILED: %s", exc)
        test_results["phases"].append({
            "phase": "1_connect",
            "status": "FAILED",
            "error": str(exc),
        })
        _write_output(test_results, collector)
        return

    # Wait for nextValidId
    deadline = time.time() + 10
    while not adapter._connected and time.time() < deadline:
        time.sleep(0.2)

    if adapter._connected:
        logger.info("CONNECTED — nextValidId received")
        # Allow IB info messages (farm connections etc.) to settle
        time.sleep(2)
        test_results["phases"].append({
            "phase": "1_connect",
            "status": "OK",
            "next_valid_id": adapter._next_order_id,
        })
    else:
        logger.error("CONNECT TIMEOUT — no nextValidId within 10s")
        test_results["phases"].append({
            "phase": "1_connect",
            "status": "TIMEOUT",
        })
        adapter.disconnect()
        _write_output(test_results, collector)
        return

    # ── Phase 2: Status check ─────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 2: Adapter status")
    logger.info("=" * 60)

    status = adapter.status()
    logger.info("Status: %s", json.dumps(status, indent=2))
    test_results["phases"].append({
        "phase": "2_status",
        "status": "OK",
        "adapter_status": status,
    })

    # ── Phase 3: Subscribe to real-time 5s bars ──────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 3: Subscribe to real-time bars (ES futures)")
    logger.info("=" * 60)

    bar_symbols = []
    try:
        req_id_es = adapter.subscribe_bars_futures("ES", bar_size="5 secs", source="TRADES",
                                                    exchange="GLOBEX", contract_month="202506")
        bar_symbols.append("ES")
        logger.info("Subscribed ES bars, req_id=%d", req_id_es)
        test_results["phases"].append({
            "phase": "3_subscribe_bars",
            "status": "OK",
            "symbols": bar_symbols,
            "req_ids": {"ES": req_id_es},
        })
    except Exception as exc:
        logger.error("SUBSCRIBE BARS FAILED: %s", exc)
        test_results["phases"].append({
            "phase": "3_subscribe_bars",
            "status": "FAILED",
            "error": str(exc),
        })

    # ── Phase 4: Kill state verification ──────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 4: Kill state machine verification")
    logger.info("=" * 60)

    ks_results = []

    # 4a. Check initial state
    state_before = adapter._kill_state.state
    logger.info("Initial kill state: %s", state_before.value)
    ks_results.append({"check": "initial_state", "value": state_before.value, "expected": "NORMAL"})

    # 4b. SoftKill ON
    adapter.set_softkill(True, "test_softkill_on")
    time.sleep(0.1)
    state_sk = adapter._kill_state.state
    logger.info("After set_softkill(True): %s", state_sk.value)
    ks_results.append({"check": "softkill_on", "value": state_sk.value, "expected": "SOFTKILL_ENABLED"})

    # 4c. SoftKill OFF
    adapter.set_softkill(False, "test_softkill_off")
    time.sleep(0.1)
    state_sk_off = adapter._kill_state.state
    logger.info("After set_softkill(False): %s", state_sk_off.value)
    ks_results.append({"check": "softkill_off", "value": state_sk_off.value, "expected": "NORMAL"})

    # 4d. Heartbeat
    adapter.heartbeat_from_dispatcher()
    logger.info("Heartbeat sent")
    ks_results.append({"check": "heartbeat", "value": "sent", "expected": "accepted"})

    test_results["phases"].append({
        "phase": "4_kill_state",
        "status": "OK",
        "checks": ks_results,
    })

    # ── Phase 5: Queue + command rejection test ───────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 5: Queue command rejection (SoftKill blocks OPEN)")
    logger.info("=" * 60)

    adapter.set_softkill(True, "test_open_block")
    time.sleep(0.1)

    open_cmd = PACommand(
        command_id=PACommand.make_id(),
        ts_utc_ms=PACommand.now_ms(),
        symbol="SPY",
        trading_mode=TradingMode.PAPER,
        channel=Channel.ORDER_PLACE,
        priority=Priority.NORMAL,
        action=Action.PLACE,
        intent_type=IntentType.OPEN,
        order_spec={"side": "BUY", "order_kind": "MKT", "qty": 1},
    )

    queued = adapter._queue.enqueue(open_cmd)
    logger.info("OPEN command queued in SOFTKILL: %s (expected: False)", queued)

    adapter.set_softkill(False, "test_done")
    time.sleep(0.1)

    test_results["phases"].append({
        "phase": "5_softkill_blocks_open",
        "status": "PASS" if not queued else "FAIL",
        "queued": queued,
        "expected": False,
    })

    # ── Phase 6: Collect bars for ~30s ────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 6: Collecting real-time bars for 30 seconds...")
    logger.info("=" * 60)

    # Send heartbeats every 5s while collecting
    collect_duration = 30
    collect_start = time.time()
    while time.time() - collect_start < collect_duration:
        adapter.heartbeat_from_dispatcher()
        time.sleep(5)

    bar_events = [e for e in collector.events if e["type"] == "MARKET_BAR"]
    logger.info("Collected %d bar events in %ds", len(bar_events), collect_duration)

    test_results["phases"].append({
        "phase": "6_bar_collection",
        "status": "OK" if len(bar_events) > 0 else "NO_BARS",
        "bar_count": len(bar_events),
        "duration_sec": collect_duration,
        "sample_bars": bar_events[:5],
    })

    # ── Phase 7: Rate limiter stats ───────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 7: Rate limiter stats")
    logger.info("=" * 60)

    rl_stats = adapter._rate_limiter.stats()
    logger.info("Rate limiter: %s", json.dumps(rl_stats, indent=2))

    test_results["phases"].append({
        "phase": "7_rate_limiter",
        "status": "OK",
        "stats": rl_stats,
    })

    # ── Phase 8: Reconciliation ───────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 8: Reconciliation (no local orders expected)")
    logger.info("=" * 60)

    try:
        recon_result = adapter.reconcile_state(
            local_order_ids=[],
            local_symbols=[],
        )
        logger.info("Reconciliation clean: %s", recon_result.is_clean)
        test_results["phases"].append({
            "phase": "8_reconciliation",
            "status": "OK" if recon_result.is_clean else "MISMATCH",
            "is_clean": recon_result.is_clean,
        })
    except Exception as exc:
        logger.error("RECONCILIATION FAILED: %s", exc)
        test_results["phases"].append({
            "phase": "8_reconciliation",
            "status": "ERROR",
            "error": str(exc),
        })

    # ── Phase 9: Clean disconnect ─────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("PHASE 9: Disconnect")
    logger.info("=" * 60)

    for sym in bar_symbols:
        adapter.unsubscribe_bars(sym)
        logger.info("Unsubscribed %s", sym)

    adapter.disconnect()
    logger.info("Disconnected cleanly")

    test_results["phases"].append({
        "phase": "9_disconnect",
        "status": "OK",
    })

    # ── Summary ───────────────────────────────────────────────────────────────
    total_events = len(collector.events)
    event_types = {}
    for e in collector.events:
        t = e["type"]
        event_types[t] = event_types.get(t, 0) + 1

    passed = sum(1 for p in test_results["phases"] if p.get("status") in ("OK", "PASS"))
    total  = len(test_results["phases"])

    test_results["summary"] = {
        "phases_passed":  passed,
        "phases_total":   total,
        "total_events":   total_events,
        "event_types":    event_types,
        "bar_count":      len(bar_events),
        "kill_state_final": adapter._kill_state.state.value,
    }
    test_results["events"] = collector.events

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY: %d/%d phases passed, %d events, %d bars",
                passed, total, total_events, len(bar_events))
    logger.info("=" * 60)

    _write_output(test_results, collector)


def _write_output(results, collector):
    """Write test output to JSON file."""
    out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"par2_live_test_{ts}.json"
    filepath = os.path.join(out_dir, filename)

    with open(filepath, "w") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info("Output written: %s", os.path.abspath(filepath))
    logger.info("Events collected: %d", len(collector.events))


if __name__ == "__main__":
    run_live_test()
