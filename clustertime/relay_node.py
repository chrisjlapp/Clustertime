"""Relay node orchestration.

A relay node runs two ptp4l instances:

  ptp4l-upstream   — unicast slave to the master node.
                     Syncs CLOCK_REALTIME via software timestamping.

  ptp4l-downstream — multicast master to local PTP clients.
                     free_running=1: distributes the (already-synced)
                     system clock without attempting further adjustment.

For single-interface deployments, the network module creates two macvlan
sub-interfaces before ptp4l is started so the two instances don't conflict
on UDP ports 319/320.

Phase 2 adds a MasterHealthMonitor that pings the master and logs failures.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from typing import Optional

from .config import ClusterTimeConfig
from .config_gen import generate_configs
from .health_monitor import MasterHealthMonitor, SyncStateMonitor
from .network import setup_relay_interfaces, teardown_relay_interfaces
from .process_manager import ManagedProcess, ProcessManager

log = logging.getLogger(__name__)

_RESTART_COOLDOWN = 5
_STATUS_INTERVAL = 30  # seconds between periodic status log lines


def run_relay(cfg: ClusterTimeConfig) -> None:
    _maybe_resolve_auto_downstream_identity(cfg)

    log.info(
        "Starting relay node | master=%s | interface=%s | dual_iface=%s | "
        "failover=%s | domain=%d",
        cfg.master.ip,
        cfg.interface,
        cfg.dual_interface,
        cfg.failover.enabled,
        cfg.ptp.domain,
    )

    # --- Network setup -------------------------------------------------------
    up_iface, down_iface = setup_relay_interfaces(cfg)
    log.info("Upstream interface: %s | Downstream interface: %s", up_iface, down_iface)

    # --- Config files --------------------------------------------------------
    paths = generate_configs(cfg)

    # --- Sync state monitor (Phase 2 observability) --------------------------
    sync_monitor = SyncStateMonitor("upstream")

    # --- Process manager -----------------------------------------------------
    mgr = ProcessManager()

    mgr.add(
        ManagedProcess(
            name="ptp4l-upstream",
            cmd=["/usr/sbin/ptp4l", "-f", paths["upstream"], "-m"],
            log_prefix="ptp4l[upstream]",
            line_callback=sync_monitor.process_line,
        )
    )
    mgr.add(
        ManagedProcess(
            name="ptp4l-downstream",
            cmd=["/usr/sbin/ptp4l", "-f", paths["downstream"], "-m"],
            log_prefix="ptp4l[downstream]",
        )
    )

    mgr.start_all()
    log.info(
        "Relay node running | upstream (unicast slave) → %s | "
        "downstream (multicast master) → %s",
        up_iface,
        down_iface,
    )

    # --- Phase 2: master health monitoring -----------------------------------
    health_monitor: Optional[MasterHealthMonitor] = None
    if cfg.failover.enabled:
        health_monitor = MasterHealthMonitor(
            cfg,
            on_failure=lambda: _on_master_failure(cfg),
            on_recovered=lambda: log.warning(
                "Master %s recovered — sync will resume automatically", cfg.master.ip
            ),
        )
        health_monitor.start()
    else:
        log.info("Master health monitoring disabled (failover.enabled=false)")

    # --- Watch loop ----------------------------------------------------------
    try:
        _watch_loop(mgr, sync_monitor)
    finally:
        if health_monitor:
            health_monitor.stop()
        teardown_relay_interfaces(cfg)


def _watch_loop(mgr: ProcessManager, sync_monitor: SyncStateMonitor) -> None:
    last_status = time.monotonic()
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

        now = time.monotonic()
        if now - last_status >= _STATUS_INTERVAL:
            _log_status(sync_monitor)
            last_status = now

        time.sleep(2)


def _log_status(sync_monitor: SyncStateMonitor) -> None:
    s = sync_monitor.status()
    offset = s["master_offset_ns"]
    offset_str = f"{offset:+d} ns" if offset is not None else "n/a"
    log.info(
        "Relay sync status | state=%s | master_offset=%s | path_delay=%s",
        s["state"],
        offset_str,
        f"{s['path_delay_ns']} ns" if s["path_delay_ns"] is not None else "n/a",
    )


def _on_master_failure(cfg: ClusterTimeConfig) -> None:
    log.error(
        "MASTER FAILURE DETECTED: %s is unreachable. "
        "Relay will continue serving downstream clients from local clock "
        "(accuracy will degrade until master recovers).",
        cfg.master.ip,
    )

    if cfg.failover.backup_masters:
        log.warning(
            "Backup masters configured: %s — "
            "dynamic failover is not yet implemented (Phase 3). "
            "Manual reconfiguration required.",
            cfg.failover.backup_masters,
        )

    if cfg.failover.promote_to_master:
        log.warning(
            "promote_to_master=true is set but automatic promotion is not "
            "yet implemented. The relay will hold its current clock state."
        )


def _maybe_resolve_auto_downstream_identity(cfg: ClusterTimeConfig) -> None:
    identity = (cfg.ptp.downstream_clock_identity or "").strip().lower()
    if identity != "auto":
        return

    resolved = _derive_clock_identity_from_master_mac(cfg.master.ip or "")
    if resolved:
        cfg.ptp.downstream_clock_identity = resolved
        log.info(
            "Resolved downstream clock identity automatically from master %s: %s",
            cfg.master.ip,
            resolved,
        )
    else:
        cfg.ptp.downstream_clock_identity = None
        log.warning(
            "Could not auto-resolve downstream clock identity for master %s; "
            "downstream will use relay's own identity. "
            "Set ptp.downstream_clock_identity explicitly to override.",
            cfg.master.ip,
        )


def _derive_clock_identity_from_master_mac(master_ip: str) -> Optional[str]:
    if not master_ip:
        return None
    try:
        result = subprocess.run(
            ["ip", "neigh", "show", master_ip],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    match = re.search(r"lladdr\s+([0-9a-fA-F:]{17})", result.stdout)
    if not match:
        return None

    mac_octets = match.group(1).lower().split(":")
    if len(mac_octets) != 6:
        return None

    # IEEE 1588 default clockIdentity derivation from EUI-48 MAC:
    # xx:xx:xx:xx:xx:xx -> xx:xx:xx:ff:fe:xx:xx:xx
    clock_id_octets = mac_octets[:3] + ["ff", "fe"] + mac_octets[3:]
    compact = "".join(clock_id_octets)
    return f"{compact[:6]}.{compact[6:10]}.{compact[10:]}"
