"""Network interface management for single-interface relay mode.

When a relay node has only one physical interface, we create two macvlan
sub-interfaces so that upstream (unicast slave) and downstream (multicast
master) ptp4l instances can each bind to their own interface without
conflicting on UDP ports 319/320.

  <physical iface>
       ├── <iface>.up   → unicast slave  (to master)
       └── <iface>.down → multicast master (to local clients)

In dual-interface mode this module is a no-op.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Tuple

from .config import ClusterTimeConfig

log = logging.getLogger(__name__)


def setup_relay_interfaces(cfg: ClusterTimeConfig) -> Tuple[str, str]:
    """
    Ensure upstream/downstream interfaces exist.
    Returns (upstream_iface, downstream_iface).
    """
    if cfg.dual_interface:
        log.info(
            "Dual-interface mode: upstream=%s downstream=%s",
            cfg.upstream_interface,
            cfg.downstream_interface,
        )
        return cfg.upstream_interface, cfg.downstream_interface  # type: ignore[return-value]

    base = cfg.interface
    up = f"{base}.up"
    down = f"{base}.down"

    log.info(
        "Single-interface mode: creating macvlan sub-interfaces %s and %s on %s",
        up,
        down,
        base,
    )

    for name in (up, down):
        _delete_iface(name)

    _run(["ip", "link", "add", "link", base, "name", up, "type", "macvlan", "mode", "bridge"])
    _run(["ip", "link", "set", up, "up"])

    _run(["ip", "link", "add", "link", base, "name", down, "type", "macvlan", "mode", "bridge"])
    _run(["ip", "link", "set", down, "up"])

    log.info("macvlan interfaces ready: %s, %s", up, down)
    return up, down


def teardown_relay_interfaces(cfg: ClusterTimeConfig) -> None:
    """Remove macvlan sub-interfaces (single-interface mode only)."""
    if cfg.dual_interface:
        return
    base = cfg.interface
    for name in (f"{base}.up", f"{base}.down"):
        _delete_iface(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _delete_iface(name: str) -> None:
    result = subprocess.run(
        ["ip", "link", "show", name], capture_output=True
    )
    if result.returncode == 0:
        log.debug("Removing existing interface %s", name)
        _run(["ip", "link", "delete", name])


def _run(cmd: list) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nstderr: {result.stderr.strip()}"
        )
