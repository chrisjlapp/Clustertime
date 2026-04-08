"""Configuration loading: YAML file with ENV variable overrides.

ENV vars (all prefixed CT_):
    CT_CONFIG              Path to YAML config file
    CT_MODE                master | relay
    CT_INTERFACE           Primary network interface (default: eth0)
    CT_UPSTREAM_INTERFACE  Relay dual-iface: upstream NIC
    CT_DOWNSTREAM_INTERFACE Relay dual-iface: downstream NIC
    CT_MASTER_IP           Master node IP (required for relay)
    CT_LOG_LEVEL           Log level (default: INFO)
    CT_PTP_DOMAIN          PTP domain number (default: 0)
    CT_PTP_TRANSPORT       Transport (default: UDPv4)
    CT_PTP_SYNC_INTERVAL   Sync interval as log2 (default: -3)
    CT_FAILOVER_ENABLED    Enable master health monitoring (default: false)
    CT_FAILOVER_TIMEOUT    Seconds before master declared failed (default: 10)
    CT_FAILOVER_PROMOTE    Promote self to master on failure (default: false)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import yaml


@dataclass
class PTPConfig:
    domain: int = 0
    transport: str = "UDPv4"
    sync_interval: int = -3
    announce_interval: int = 1
    min_delay_req_interval: int = 0
    unicast_req_duration: int = 300


@dataclass
class MasterConfig:
    ip: Optional[str] = None


@dataclass
class FailoverConfig:
    enabled: bool = False
    backup_masters: List[str] = field(default_factory=list)
    detection_timeout: int = 10
    promote_to_master: bool = False


@dataclass
class ClusterTimeConfig:
    mode: str = "relay"
    interface: str = "eth0"
    upstream_interface: Optional[str] = None
    downstream_interface: Optional[str] = None
    master: MasterConfig = field(default_factory=MasterConfig)
    ptp: PTPConfig = field(default_factory=PTPConfig)
    failover: FailoverConfig = field(default_factory=FailoverConfig)
    log_level: str = "INFO"

    @property
    def dual_interface(self) -> bool:
        return bool(self.upstream_interface and self.downstream_interface)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def _from_dict(cls, data: dict) -> "ClusterTimeConfig":
        ptp_d = data.get("ptp", {})
        master_d = data.get("master", {})
        failover_d = data.get("failover", {})

        return cls(
            mode=data.get("mode", "relay"),
            interface=data.get("interface", "eth0"),
            upstream_interface=data.get("upstream_interface"),
            downstream_interface=data.get("downstream_interface"),
            master=MasterConfig(ip=master_d.get("ip")),
            ptp=PTPConfig(
                domain=int(ptp_d.get("domain", 0)),
                transport=ptp_d.get("transport", "UDPv4"),
                sync_interval=int(ptp_d.get("sync_interval", -3)),
                announce_interval=int(ptp_d.get("announce_interval", 1)),
                min_delay_req_interval=int(ptp_d.get("min_delay_req_interval", 0)),
                unicast_req_duration=int(ptp_d.get("unicast_req_duration", 300)),
            ),
            failover=FailoverConfig(
                enabled=bool(failover_d.get("enabled", False)),
                backup_masters=list(failover_d.get("backup_masters", [])),
                detection_timeout=int(failover_d.get("detection_timeout", 10)),
                promote_to_master=bool(failover_d.get("promote_to_master", False)),
            ),
            log_level=data.get("log_level", "INFO"),
        )

    @classmethod
    def from_yaml(cls, path: str) -> "ClusterTimeConfig":
        with open(path) as fh:
            data = yaml.safe_load(fh) or {}
        return cls._from_dict(data)

    @classmethod
    def load(cls, yaml_path: Optional[str] = None) -> "ClusterTimeConfig":
        """Load YAML config, then apply ENV overrides."""
        if yaml_path and os.path.exists(yaml_path):
            cfg = cls.from_yaml(yaml_path)
        else:
            cfg = cls._from_dict({})

        env = os.environ
        if v := env.get("CT_MODE"):
            cfg.mode = v
        if v := env.get("CT_INTERFACE"):
            cfg.interface = v
        if v := env.get("CT_UPSTREAM_INTERFACE"):
            cfg.upstream_interface = v
        if v := env.get("CT_DOWNSTREAM_INTERFACE"):
            cfg.downstream_interface = v
        if v := env.get("CT_MASTER_IP"):
            cfg.master.ip = v
        if v := env.get("CT_LOG_LEVEL"):
            cfg.log_level = v
        if v := env.get("CT_PTP_DOMAIN"):
            cfg.ptp.domain = int(v)
        if v := env.get("CT_PTP_TRANSPORT"):
            cfg.ptp.transport = v
        if v := env.get("CT_PTP_SYNC_INTERVAL"):
            cfg.ptp.sync_interval = int(v)
        if v := env.get("CT_FAILOVER_ENABLED"):
            cfg.failover.enabled = v.lower() in ("1", "true", "yes")
        if v := env.get("CT_FAILOVER_TIMEOUT"):
            cfg.failover.detection_timeout = int(v)
        if v := env.get("CT_FAILOVER_PROMOTE"):
            cfg.failover.promote_to_master = v.lower() in ("1", "true", "yes")

        return cfg

    # ------------------------------------------------------------------

    def validate(self) -> None:
        if self.mode not in ("master", "relay"):
            raise ValueError(f"Invalid mode {self.mode!r}. Must be 'master' or 'relay'.")
        if self.mode == "relay" and not self.master.ip:
            raise ValueError("mode=relay requires master.ip to be set (CT_MASTER_IP or config).")
        if self.dual_interface and self.upstream_interface == self.downstream_interface:
            raise ValueError("upstream_interface and downstream_interface must differ.")
