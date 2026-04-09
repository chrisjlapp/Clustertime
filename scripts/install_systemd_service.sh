#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  sudo ./scripts/install_systemd_service.sh --runtime <docker|native> --node <master|relay> [--repo-dir /path/to/repo]

Examples:
  sudo ./scripts/install_systemd_service.sh --runtime docker --node master
  sudo ./scripts/install_systemd_service.sh --runtime native --node relay
USAGE
}

RUNTIME=""
NODE=""
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runtime)
      RUNTIME="${2:-}"
      shift 2
      ;;
    --node)
      NODE="${2:-}"
      shift 2
      ;;
    --repo-dir)
      REPO_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$RUNTIME" != "docker" && "$RUNTIME" != "native" ]]; then
  echo "--runtime must be docker or native" >&2
  usage
  exit 1
fi

if [[ "$NODE" != "master" && "$NODE" != "relay" ]]; then
  echo "--node must be master or relay" >&2
  usage
  exit 1
fi

if [[ ! -f "$REPO_DIR/docker-compose.yml" ]]; then
  echo "Could not find docker-compose.yml in repo dir: $REPO_DIR" >&2
  exit 1
fi

SERVICE_NAME="clustertime-${RUNTIME}-${NODE}.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

if [[ "$RUNTIME" == "docker" ]]; then
  EXEC_START="/usr/bin/docker compose --profile ${NODE} up"
  EXEC_STOP="/usr/bin/docker compose --profile ${NODE} down"
  AFTER="network-online.target docker.service"
  WANTS="network-online.target docker.service"
else
  CONFIG_PATH="${REPO_DIR}/config/${NODE}.yaml"
  if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "Missing config file: $CONFIG_PATH" >&2
    exit 1
  fi

  EXEC_START="/usr/bin/python3 -m clustertime.main -c ${CONFIG_PATH} --mode ${NODE}"
  EXEC_STOP="/bin/kill -s SIGINT \$MAINPID"
  AFTER="network-online.target"
  WANTS="network-online.target"
fi

cat > "$SERVICE_PATH" <<UNIT
[Unit]
Description=Clustertime ${NODE} (${RUNTIME})
After=${AFTER}
Wants=${WANTS}

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
ExecStart=${EXEC_START}
ExecStop=${EXEC_STOP}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"

cat <<DONE
Installed and started $SERVICE_NAME
Check status with:
  systemctl status $SERVICE_NAME
Follow logs with:
  journalctl -u $SERVICE_NAME -f
DONE
