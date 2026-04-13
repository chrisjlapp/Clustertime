"""Configuration loading: YAML file with ENV variable overrides.

ENV vars (all prefixed CT_):
    CT_CONFIG              Path to YAML config file
    CT_MODE                master | relay
    CT_INTERFACE           Primary network interface (default: eth0)
    CT_UPSTREAM_INTERFACE  Relay dual-iface: upstream NIC
    CT_DOWNSTREAM_INTERFACE Relay dual-iface: downstream NIC
    CT_MASTER_IP           Master node IP (required for relay)
    CT_UPSTREAM_IP         IP/prefix for upstream macvlan, e.g. 192.168.1.50/24
                           (required in single-interface relay mode)
    CT_DOWNSTREAM_IP       IP/prefix for downstream macvlan, e.g. 192.168.1.51/24
                           (required for UDPv4 downstream in single-interface mode)
    CT_LOG_LEVEL           Log level (default: INFO)
    CT_PTP_DOMAIN          PTP domain number (default: 0)
    CT_PTP_TRANSPORT       Transport (default: UDPv4)
    CT_PTP_SYNC_INTERVAL   Sync interval as log2 (default: -3)
    CT_PTP_MINOR_VERSION   PTP minor version: 0 (PTPv2.0) or 1 (PTPv2.1) (default: 0)
    CT_PTP_TIME_STAMPING   software | hardware | auto (default: auto)
    CT_PTP_TX_TS_TIMEOUT   ptp4l tx_timestamp_timeout seconds (default: 10)
    CT_PTP_MULTICAST_TTL   ptp4l UDP TTL/hop-limit for multicast packets (default: 1)
    CT_PTP_UNICAST_TTL     Clustertime unicast UDP TTL/hop-limit hint (default: 1)
    CT_PTP_MASTER_PRIORITY1 Master ptp4l priority1 (default: 128)
    CT_PTP_MASTER_PRIORITY2 Master ptp4l priority2 (default: 128)
    CT_PTP_RPI_HYBRID_TS   Enable Raspberry Pi hybrid mode:
                           relay upstream + master use software timestamping
    CT_PTP_RELAY_PRIORITY1 Relay ptp4l priority1 (default: 255)
    CT_PTP_RELAY_PRIORITY2 Relay ptp4l priority2 (default: 255)
    CT_PTP_DOWNSTREAM_CLOCK_IDENTITY
                           Override relay downstream ptp4l clockIdentity
                           (e.g. to match the upstream master identity)
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
    minor_version: int = 0
    announce_interval: int = 1
    announce_receipt_timeout: int = 3
    min_delay_req_interval: int = 0
    unicast_req_duration: int = 300
    time_stamping: str = "auto"
    tx_timestamp_timeout: int = 10
    multicast_ttl: int = 1
    unicast_ttl: int = 1
    master_priority1: int = 128
    master_priority2: int = 128
    rpi_hybrid_ts: bool = False
    relay_priority1: int = 255
    relay_priority2: int = 255
    downstream_clock_identity: Optional[str] = None


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
    # IP address (with prefix) assigned to the upstream macvlan in
    # single-interface mode, e.g. "192.168.1.50/24".  Required so that
    # ptp4l can send unicast SIGNALING packets to the master.
    upstream_ip: Optional[str] = None
    # Optional IP address (with prefix) assigned to the downstream macvlan in
    # single-interface mode when using UDPv4 downstream PTP traffic.
    downstream_ip: Optional[str] = None
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
            upstream_ip=data.get("upstream_ip") or None,
            downstream_ip=data.get("downstream_ip") or None,
            master=MasterConfig(ip=master_d.get("ip")),
            ptp=PTPConfig(
                domain=int(ptp_d.get("domain", 0)),
                transport=ptp_d.get("transport", "UDPv4"),
                sync_interval=int(ptp_d.get("sync_interval", -3)),
                minor_version=int(ptp_d.get("minor_version", 0)),
                announce_interval=int(ptp_d.get("announce_interval", 1)),
                announce_receipt_timeout=int(ptp_d.get("announce_receipt_timeout", 3)),
                min_delay_req_interval=int(ptp_d.get("min_delay_req_interval", 0)),
                unicast_req_duration=int(ptp_d.get("unicast_req_duration", 300)),
                time_stamping=str(ptp_d.get("time_stamping", "auto")),
                tx_timestamp_timeout=int(ptp_d.get("tx_timestamp_timeout", 10)),
                multicast_ttl=int(ptp_d.get("multicast_ttl", 1)),
                unicast_ttl=int(ptp_d.get("unicast_ttl", 1)),
                master_priority1=int(ptp_d.get("master_priority1", 128)),
                master_priority2=int(ptp_d.get("master_priority2", 128)),
                rpi_hybrid_ts=bool(ptp_d.get("rpi_hybrid_ts", False)),
                relay_priority1=int(ptp_d.get("relay_priority1", 255)),
                relay_priority2=int(ptp_d.get("relay_priority2", 255)),
                downstream_clock_identity=ptp_d.get("downstream_clock_identity") or None,
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
        if v := env.get("CT_UPSTREAM_IP"):
            cfg.upstream_ip = v
        if v := env.get("CT_DOWNSTREAM_IP"):
            cfg.downstream_ip = v
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
        if v := env.get("CT_PTP_ANNOUNCE_RECEIPT_TIMEOUT"):
            cfg.ptp.announce_receipt_timeout = int(v)
        if v := env.get("CT_PTP_MINOR_VERSION"):
            cfg.ptp.minor_version = int(v)
        if v := env.get("CT_PTP_TIME_STAMPING"):
            cfg.ptp.time_stamping = v
        if v := env.get("CT_PTP_TX_TS_TIMEOUT"):
            cfg.ptp.tx_timestamp_timeout = int(v)
        if v := env.get("CT_PTP_MULTICAST_TTL"):
            cfg.ptp.multicast_ttl = int(v)
        if v := env.get("CT_PTP_UNICAST_TTL"):
            cfg.ptp.unicast_ttl = int(v)
        if v := env.get("CT_PTP_MASTER_PRIORITY1"):
            cfg.ptp.master_priority1 = int(v)
        if v := env.get("CT_PTP_MASTER_PRIORITY2"):
            cfg.ptp.master_priority2 = int(v)
        if v := env.get("CT_PTP_RPI_HYBRID_TS"):
            cfg.ptp.rpi_hybrid_ts = v.lower() in ("1", "true", "yes")
        if v := env.get("CT_PTP_RELAY_PRIORITY1"):
            cfg.ptp.relay_priority1 = int(v)
        if v := env.get("CT_PTP_RELAY_PRIORITY2"):
            cfg.ptp.relay_priority2 = int(v)
        if v := env.get("CT_PTP_DOWNSTREAM_CLOCK_IDENTITY"):
            cfg.ptp.downstream_clock_identity = v
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
        if self.mode == "relay" and not self.dual_interface and not self.upstream_ip:
            raise ValueError(
                "Single-interface relay mode requires upstream_ip to be set "
                "(e.g. upstream_ip: 192.168.1.50/24 in config, or CT_UPSTREAM_IP env var). "
                "This IP is assigned to the upstream macvlan so ptp4l can send "
                "unicast packets to the master."
            )
        if (
            self.mode == "relay"
            and not self.dual_interface
            and self.ptp.transport.upper() == "UDPV4"
            and not self.downstream_ip
        ):
            raise ValueError(
                "Single-interface relay mode with ptp.transport=UDPv4 requires "
                "downstream_ip to be set (e.g. downstream_ip: 192.168.1.51/24 "
                "or CT_DOWNSTREAM_IP). This IP is assigned to the downstream "
                "macvlan so ptp4l can send Delay_Resp and other UDPv4 messages."
            )
        if (
            self.mode == "relay"
            and not self.dual_interface
            and self.upstream_ip
            and self.downstream_ip
            and self.upstream_ip == self.downstream_ip
        ):
            raise ValueError(
                "upstream_ip and downstream_ip must be different in single-interface "
                "relay mode. Each macvlan needs its own unique address."
            )
        ts_mode = self.ptp.time_stamping.lower()
        if ts_mode not in ("software", "hardware", "auto"):
            raise ValueError(
                "ptp.time_stamping must be one of: software, hardware, auto "
                "(or set CT_PTP_TIME_STAMPING accordingly)."
            )
        if self.mode == "relay" and not self.dual_interface and ts_mode == "hardware":
            raise ValueError(
                "Single-interface relay mode uses macvlan sub-interfaces "
                "(<iface>.up / <iface>.down). Hardware timestamping is not "
                "reliable on virtual interfaces with many NIC drivers "
                "(including Raspberry Pi macb). Use dual-interface relay mode "
                "with physical NICs for hardware timestamping, or switch to "
                "ptp.time_stamping=software."
            )
        if self.ptp.tx_timestamp_timeout <= 0:
            raise ValueError(
                "ptp.tx_timestamp_timeout must be > 0 "
                "(or set CT_PTP_TX_TS_TIMEOUT accordingly)."
            )
        if not 1 <= self.ptp.multicast_ttl <= 255:
            raise ValueError(
                "ptp.multicast_ttl must be in the range 1..255 "
                "(or set CT_PTP_MULTICAST_TTL accordingly)."
            )
        if not 1 <= self.ptp.unicast_ttl <= 255:
            raise ValueError(
                "ptp.unicast_ttl must be in the range 1..255 "
                "(or set CT_PTP_UNICAST_TTL accordingly)."
            )
        if self.ptp.minor_version not in (0, 1):
            raise ValueError(
                "ptp.minor_version must be 0 (PTPv2.0) or 1 (PTPv2.1) "
                "(or set CT_PTP_MINOR_VERSION accordingly)."
            )
        if not 0 <= self.ptp.master_priority1 <= 255:
            raise ValueError(
                "ptp.master_priority1 must be in the range 0..255 "
                "(or set CT_PTP_MASTER_PRIORITY1 accordingly)."
            )
        if not 0 <= self.ptp.master_priority2 <= 255:
            raise ValueError(
                "ptp.master_priority2 must be in the range 0..255 "
                "(or set CT_PTP_MASTER_PRIORITY2 accordingly)."
            )
        if not 0 <= self.ptp.relay_priority1 <= 255:
            raise ValueError(
                "ptp.relay_priority1 must be in the range 0..255 "
                "(or set CT_PTP_RELAY_PRIORITY1 accordingly)."
            )
        if not 0 <= self.ptp.relay_priority2 <= 255:
            raise ValueError(
                "ptp.relay_priority2 must be in the range 0..255 "
                "(or set CT_PTP_RELAY_PRIORITY2 accordingly)."
            )
        if self.ptp.downstream_clock_identity:
            if self.ptp.downstream_clock_identity.lower() != "auto":
                compact = (
                    self.ptp.downstream_clock_identity.replace(":", "")
                    .replace(".", "")
                    .strip()
                )
                if len(compact) != 16:
                    raise ValueError(
                        "ptp.downstream_clock_identity must be 'auto' or 8 octets in hex "
                        "format (e.g. aa:bb:cc:dd:ee:ff:00:11 or "
                        "aabbcc.ddee.ff0011)."
                    )
                try:
                    int(compact, 16)
                except ValueError as exc:
                    raise ValueError(
                        "ptp.downstream_clock_identity contains non-hex octets."
                    ) from exc
