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
    _warn_if_master_timescale_needs_validation(cfg)

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
        # Keep the master PHC aligned to system CLOCK_REALTIME so generated
        # Sync timestamps reflect the intended free-running system clock source.
        mgr.add(
            ManagedProcess(
                name="phc2sys-master",
                cmd=[
                    "/usr/sbin/phc2sys",
                    "-s",
                    "CLOCK_REALTIME",
                    "-c",
                    cfg.interface,
                    "-m",
                ],
                log_prefix="phc2sys[master]",
            )
        )
        log.info(
            "Enabled phc2sys on master interface %s to discipline PHC from CLOCK_REALTIME.",
            cfg.interface,
        )

    mgr.start_all()
    log.info(
        "Master PTP node is running — accepting unicast sync requests on %s",
        cfg.interface,
    )

    _watch_loop(mgr)


def _warn_if_master_timescale_needs_validation(cfg: ClusterTimeConfig) -> None:
    """
    Flag a common UTC/TAI pitfall for direct multicast clients.

    linuxptp advertises different time-scale semantics depending on timestamping
    mode when the node is the domain server. Mixed client expectations on the
    master multicast segment can appear as a stable seconds-level offset.
    """
    mode = (cfg.ptp.time_stamping or "auto").strip().lower()
    if mode == "software":
        return
    log.warning(
        "Master ptp.time_stamping=%s. Direct multicast clients (for example "
        "switches) should be validated for UTC/TAI interpretation using "
        "`pmc GET TIME_PROPERTIES_DATA_SET` and `GET TIME_STATUS_NP` on this "
        "segment if you observe stable second-level offsets.",
        mode,
    )


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
