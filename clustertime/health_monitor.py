"""Phase 2: Master health monitoring and sync state tracking.

MasterHealthMonitor
    Periodically probes the master node via ICMP ping.
    Fires callbacks on failure and recovery.

SyncStateMonitor
    Parses ptp4l log lines to track servo state and offset.
    Integrated via the ManagedProcess line_callback.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Callable, Optional

from .config import ClusterTimeConfig

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Master reachability monitoring
# ---------------------------------------------------------------------------

class MasterHealthMonitor:
    """
    Probes master reachability; calls on_failure / on_recovered as state
    transitions occur.  Uses ICMP ping so it works without PTP knowledge.
    """

    _FAILURE_THRESHOLD = 3  # consecutive failed probes before declaring dead

    def __init__(
        self,
        cfg: ClusterTimeConfig,
        on_failure: Optional[Callable[[], None]] = None,
        on_recovered: Optional[Callable[[], None]] = None,
    ) -> None:
        self._cfg = cfg
        self._on_failure = on_failure
        self._on_recovered = on_recovered
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._consecutive_failures = 0
        self._master_up = True

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="master-health"
        )
        self._thread.start()
        log.info(
            "Master health monitor started (target=%s, poll_interval=%ds)",
            self._cfg.master.ip,
            self._cfg.failover.detection_timeout,
        )

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        interval = self._cfg.failover.detection_timeout
        while self._running:
            alive = self._ping(self._cfg.master.ip)

            if alive:
                if not self._master_up:
                    log.warning(
                        "Master %s is reachable again — recovered",
                        self._cfg.master.ip,
                    )
                    self._master_up = True
                    self._consecutive_failures = 0
                    if self._on_recovered:
                        self._on_recovered()
            else:
                self._consecutive_failures += 1
                log.warning(
                    "Master %s unreachable (%d/%d)",
                    self._cfg.master.ip,
                    self._consecutive_failures,
                    self._FAILURE_THRESHOLD,
                )
                if (
                    self._master_up
                    and self._consecutive_failures >= self._FAILURE_THRESHOLD
                ):
                    self._master_up = False
                    log.error(
                        "Master %s declared FAILED after %d consecutive probe failures",
                        self._cfg.master.ip,
                        self._consecutive_failures,
                    )
                    if self._on_failure:
                        self._on_failure()

            time.sleep(interval)

    @staticmethod
    def _ping(ip: str, count: int = 1, wait: int = 2) -> bool:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", str(wait), ip],
            capture_output=True,
        )
        return result.returncode == 0


# ---------------------------------------------------------------------------
# ptp4l output parsing
# ---------------------------------------------------------------------------

class SyncStateMonitor:
    """
    Parses ptp4l log lines to maintain current sync state.

    Sample ptp4l output:
        ptp4l[1234.5]: [eth0] UNCALIBRATED to SLAVE on MASTER_CLOCK_SELECTED
        ptp4l[1234.6]: [eth0] master offset 123 s2 freq -456 path delay 789
        ptp4l[1234.7]: [eth0] port 1: SLAVE to UNCALIBRATED on SYNCHRONIZATION_FAULT
    """

    def __init__(self, name: str = "ptp4l") -> None:
        self.name = name
        self.state = "INITIALIZING"
        self.master_offset_ns: Optional[int] = None
        self.path_delay_ns: Optional[int] = None
        self.gm_identity: Optional[str] = None
        self._lock = threading.Lock()

    def process_line(self, line: str) -> None:
        if "master offset" in line:
            self._parse_offset(line)
        elif " to SLAVE" in line:
            self._set_state("SLAVE", line)
        elif " to MASTER" in line:
            self._set_state("MASTER", line)
        elif " to UNCALIBRATED" in line:
            self._set_state("UNCALIBRATED", line)
        elif " to FAULTY" in line or "SYNCHRONIZATION_FAULT" in line:
            self._set_state("FAULTY", line)
            log.warning("[%s] Synchronization fault: %s", self.name, line.strip())
        elif "grandmaster changed" in line.lower():
            log.warning("[%s] Grandmaster changed: %s", self.name, line.strip())

    def _parse_offset(self, line: str) -> None:
        # "master offset NNN s2 freq +NNN path delay NNN"
        try:
            after = line.split("master offset", 1)[1].split()
            offset = int(after[0])
            # path delay is 4 tokens after offset: s2 freq <N> path delay <N>
            if len(after) >= 6 and after[3] == "delay":
                delay = int(after[4])
            else:
                delay = None
            with self._lock:
                self.master_offset_ns = offset
                if delay is not None:
                    self.path_delay_ns = delay
        except (IndexError, ValueError):
            pass

    def _set_state(self, state: str, line: str = "") -> None:
        with self._lock:
            prev = self.state
            if prev != state:
                log.info("[%s] Servo state: %s → %s", self.name, prev, state)
                self.state = state

    def status(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self.state,
                "master_offset_ns": self.master_offset_ns,
                "path_delay_ns": self.path_delay_ns,
                "gm_identity": self.gm_identity,
            }
