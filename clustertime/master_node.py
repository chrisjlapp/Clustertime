"""Master node orchestration.

The master node runs a single ptp4l instance in server mode using the
system clock as the free-running PTP reference (clockClass 135).
Relay nodes connect to it via PTPv2 unicast.
"""

from __future__ import annotations

import logging
import time

from .config import ClusterTimeConfig
from .config_gen import generate_configs
from .process_manager import ManagedProcess, ProcessManager

log = logging.getLogger(__name__)

_RESTART_COOLDOWN = 5  # seconds to wait before restarting a crashed process


def run_master(cfg: ClusterTimeConfig) -> None:
    log.info(
        "Starting master node | interface=%s | domain=%d | sync_interval=%d",
        cfg.interface,
        cfg.ptp.domain,
        cfg.ptp.sync_interval,
    )

    paths = generate_configs(cfg)
    master_conf = paths["master"]
    log.debug("Generated ptp4l config: %s", master_conf)

    mgr = ProcessManager()
    mgr.add(
        ManagedProcess(
            name="ptp4l-master",
            cmd=["/usr/sbin/ptp4l", "-f", master_conf, "-m"],
            log_prefix="ptp4l[master]",
        )
    )

    mgr.start_all()
    log.info(
        "Master PTP node is running — accepting unicast sync requests on %s",
        cfg.interface,
    )

    _watch_loop(mgr)


def _watch_loop(mgr: ProcessManager) -> None:
    """Monitor processes and restart any that exit unexpectedly."""
    while True:
        failed = mgr.any_exited()
        if failed:
            proc = mgr.get(failed)
            log.error(
                "Process '%s' exited (returncode=%s). Restarting in %ds...",
                failed,
                proc.returncode if proc else "?",
                _RESTART_COOLDOWN,
            )
            time.sleep(_RESTART_COOLDOWN)
            if proc:
                proc.start()
        time.sleep(2)
