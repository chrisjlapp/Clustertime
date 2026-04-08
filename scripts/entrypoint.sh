#!/usr/bin/env bash
set -euo pipefail

# Verify required binaries are present
for bin in ptp4l ping ip; do
    if ! command -v "$bin" &>/dev/null; then
        echo "ERROR: required binary '$bin' not found" >&2
        exit 1
    fi
done

# Create runtime directory
mkdir -p /var/run/clustertime

exec python3 -m clustertime.main "$@"
