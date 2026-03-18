"""
PAr2 Configuration Schema
==========================
Canonical config keys for the PAr2 adapter.

All keys match the spec exactly — never rename without JK approval.
Load from YAML (via PyYAML) or from a plain dict.

Canonical key groups:
  ib.*              — connection settings
  pacing.*          — rate limit settings
  stop_modify.*     — stop-modify throttling
  failsafe.*        — kill / failsafe thresholds
  reconciliation.*  — reconciliation behavior

Usage:
    cfg = PAr2Config.from_yaml("config/config.yaml")
    cfg = PAr2Config.from_dict({"ib": {"host": "127.0.0.1", ...}})
    cfg = PAr2Config()   # all defaults
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IBConfig:
    host:         str = "127.0.0.1"
    port:         int = 4002               # 4001=live, 4002=paper
    client_id:    int = 1
    trading_mode: str = "PAPER"            # "LIVE" | "PAPER"


@dataclass
class PacingConfig:
    sustained_msgs_per_sec: float = 20.0   # PAr2 soft limit per channel
    burst_msgs_per_sec:     float = 40.0   # peak burst per channel
    # IB hard limit is 50/sec at Gateway level — do not set above 45


@dataclass
class StopModifyConfig:
    min_modify_interval_ms:    float = 75.0  # reject modify if last < this ms ago
    min_delta_ticks_or_pips:   float = 1.0   # reject if price move < 1 tick/pip


@dataclass
class FailsafeConfig:
    heartbeat_interval_ms:      float = 5_000.0   # expected Dispatcher ping interval
    freeze_after_ms:            float = 15_000.0  # T_freeze — NORMAL/SK → FREEZE
    autoexit_after_ms:          float = 180_000.0 # T_flatten — FREEZE → AUTOEXIT
    autoexit_implies_lockout:   bool  = True
    lockout_requires_operator_reset: bool = True


@dataclass
class ReconciliationConfig:
    timeout_sec:           float = 10.0   # IB API collection timeout per request
    run_on_reconnect:      bool  = True   # always reconcile on reconnect
    lockout_on_mismatch:   bool  = True   # RECONCILIATION_UNSAFE_MISMATCH → LOCKOUT


@dataclass
class PAr2Config:
    ib:             IBConfig             = field(default_factory=IBConfig)
    pacing:         PacingConfig         = field(default_factory=PacingConfig)
    stop_modify:    StopModifyConfig     = field(default_factory=StopModifyConfig)
    failsafe:       FailsafeConfig       = field(default_factory=FailsafeConfig)
    reconciliation: ReconciliationConfig = field(default_factory=ReconciliationConfig)

    # Drain loop
    drain_interval_ms: float = 10.0      # how often to poll queue + flush throttler

    @classmethod
    def from_dict(cls, d: dict) -> "PAr2Config":
        cfg = cls()

        ib = d.get("ib", {})
        cfg.ib = IBConfig(
            host=ib.get("host", "127.0.0.1"),
            port=int(ib.get("port", 4002)),
            client_id=int(ib.get("client_id", 1)),
            trading_mode=ib.get("trading_mode", "PAPER").upper(),
        )

        p = d.get("pacing", {})
        cfg.pacing = PacingConfig(
            sustained_msgs_per_sec=float(p.get("sustained_msgs_per_sec", 20.0)),
            burst_msgs_per_sec=float(p.get("burst_msgs_per_sec", 40.0)),
        )

        sm = d.get("stop_modify", {})
        cfg.stop_modify = StopModifyConfig(
            min_modify_interval_ms=float(sm.get("min_modify_interval_ms", 75.0)),
            min_delta_ticks_or_pips=float(sm.get("min_delta_ticks_or_pips", 1.0)),
        )

        fs = d.get("failsafe", {})
        cfg.failsafe = FailsafeConfig(
            heartbeat_interval_ms=float(fs.get("heartbeat_interval_ms", 5_000.0)),
            freeze_after_ms=float(fs.get("freeze_after_ms", 15_000.0)),
            autoexit_after_ms=float(fs.get("autoexit_after_ms", 180_000.0)),
            autoexit_implies_lockout=bool(fs.get("autoexit_implies_lockout", True)),
            lockout_requires_operator_reset=bool(fs.get("lockout_requires_operator_reset", True)),
        )

        rec = d.get("reconciliation", {})
        cfg.reconciliation = ReconciliationConfig(
            timeout_sec=float(rec.get("timeout_sec", 10.0)),
            run_on_reconnect=bool(rec.get("run_on_reconnect", True)),
            lockout_on_mismatch=bool(rec.get("lockout_on_mismatch", True)),
        )

        cfg.drain_interval_ms = float(d.get("drain_interval_ms", 10.0))
        return cfg

    @classmethod
    def from_yaml(cls, path: str) -> "PAr2Config":
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML required for PAr2Config.from_yaml: pip install pyyaml") from exc

        resolved = os.path.expanduser(path)
        with open(resolved) as fh:
            raw = yaml.safe_load(fh) or {}

        return cls.from_dict(raw.get("pa_r2", raw))

    def to_dict(self) -> dict:
        return {
            "ib": {
                "host":         self.ib.host,
                "port":         self.ib.port,
                "client_id":    self.ib.client_id,
                "trading_mode": self.ib.trading_mode,
            },
            "pacing": {
                "sustained_msgs_per_sec": self.pacing.sustained_msgs_per_sec,
                "burst_msgs_per_sec":     self.pacing.burst_msgs_per_sec,
            },
            "stop_modify": {
                "min_modify_interval_ms":  self.stop_modify.min_modify_interval_ms,
                "min_delta_ticks_or_pips": self.stop_modify.min_delta_ticks_or_pips,
            },
            "failsafe": {
                "heartbeat_interval_ms":           self.failsafe.heartbeat_interval_ms,
                "freeze_after_ms":                 self.failsafe.freeze_after_ms,
                "autoexit_after_ms":               self.failsafe.autoexit_after_ms,
                "autoexit_implies_lockout":         self.failsafe.autoexit_implies_lockout,
                "lockout_requires_operator_reset":  self.failsafe.lockout_requires_operator_reset,
            },
            "reconciliation": {
                "timeout_sec":         self.reconciliation.timeout_sec,
                "run_on_reconnect":    self.reconciliation.run_on_reconnect,
                "lockout_on_mismatch": self.reconciliation.lockout_on_mismatch,
            },
            "drain_interval_ms": self.drain_interval_ms,
        }
