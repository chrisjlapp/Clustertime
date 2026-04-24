"""Master node orchestration.

The master node runs a single ptp4l instance in server mode using the
system clock as the free-running PTP reference (clockClass 135).
Relay nodes connect to it via PTPv2 unicast.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

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
    master_ts = _read_time_stamping_mode(master_conf)
    if master_ts == "hardware":
        mgr.add(
            ManagedProcess(
                name="phc2sys-master",
                cmd=[
                    "/usr/sbin/phc2sys",
                    "-s",
                    cfg.interface,
                    "-c",
                    "CLOCK_REALTIME",
                    "-O",
                    "0",
                    "-S",
                    "1.0",
                    "-m",
                ],
                log_prefix="phc2sys[master]",
            )
        )
        log.info(
            "Enabled phc2sys on master interface %s to discipline CLOCK_REALTIME from PHC.",
            cfg.interface,
        )

    mgr.start_all()
    log.info(
        "Master PTP node is running — accepting unicast sync requests on %s",
        cfg.interface,
    )

    _watch_loop(mgr)


def _read_time_stamping_mode(conf_path: str) -> Optional[str]:
    if not conf_path or not os.path.exists(conf_path):
        return None
    try:
        with open(conf_path) as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if not line.lower().startswith("time_stamping"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    return None
                return parts[1].strip().lower()
    except OSError:
        return None
    return None


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
