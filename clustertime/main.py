"""Clustertime entry point.

Usage:
    python3 -m clustertime.main [-c config.yaml] [--mode master|relay]

Environment variables override YAML config — see config.py for full list.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import ClusterTimeConfig
from .master_node import run_master
from .relay_node import run_relay


def _setup_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)-8s %(name)-20s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="clustertime",
        description="PTP Unicast-to-Multicast Relay Appliance",
    )
    parser.add_argument(
        "-c", "--config",
        default=os.environ.get("CT_CONFIG", "/etc/clustertime/config.yaml"),
        metavar="FILE",
        help="Path to YAML config file (default: /etc/clustertime/config.yaml)",
    )
    parser.add_argument(
        "--mode",
        choices=["master", "relay"],
        default=None,
        help="Override mode from config/env (CT_MODE)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        metavar="LEVEL",
        help="Override log level (CT_LOG_LEVEL)",
    )
    args = parser.parse_args(argv)

    # Load config (YAML then ENV)
    cfg = ClusterTimeConfig.load(yaml_path=args.config)

    # CLI flags take final precedence
    if args.mode:
        cfg.mode = args.mode
    if args.log_level:
        cfg.log_level = args.log_level

    _setup_logging(cfg.log_level)
    log = logging.getLogger("clustertime")

    try:
        cfg.validate()
    except ValueError as exc:
        log.error("Configuration error: %s", exc)
        sys.exit(1)

    log.info(
        "Clustertime %s starting | mode=%s | interface=%s",
        _version(),
        cfg.mode,
        cfg.interface,
    )

    if cfg.mode == "master":
        run_master(cfg)
    else:
        run_relay(cfg)


def _version() -> str:
    try:
        from . import __version__
        return __version__
    except ImportError:
        return "dev"


if __name__ == "__main__":
    main()
