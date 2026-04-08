# Clustertime

PTP Unicast-to-Multicast Relay Appliance. Clustertime bridges a PTPv2 unicast master to a multicast downstream network, enabling accurate time synchronization across cluster nodes.

## Requirements

- Docker and Docker Compose
- Host networking support (Linux)
- Privileged container access (for PTP and macvlan)

## Installation

Clone the repository and build the image:

```bash
git clone https://github.com/chrisjlapp/clustertime.git
cd clustertime
docker compose build
```

## Configuration

Edit the config files before running:

- `config/master.yaml` — master node settings (interface, PTP domain, sync interval)
- `config/relay.yaml` — relay node settings (interface, master IP, failover options)

At minimum, set the correct network interface and (for relay) the master IP:

```yaml
# config/master.yaml
interface: eth0   # change to your interface

# config/relay.yaml
interface: eth0
master:
  ip: 192.168.1.10   # change to your master node's IP
```

Any config value can also be overridden via environment variables (e.g. `CT_INTERFACE`, `CT_MODE`, `CT_MASTER_IP`).

### Timestamping mode

`ptp.time_stamping` supports:
- `auto` (default): use hardware timestamping when the interface reports support, otherwise fall back to software
- `hardware`: force hardware timestamping
- `software`: force software timestamping

Equivalent env override: `CT_PTP_TIME_STAMPING=auto|hardware|software`.

## Running

### Master node

```bash
docker compose --profile master up
```

### Relay node

```bash
docker compose --profile relay up
```

Run in detached mode with `-d`:

```bash
docker compose --profile master up -d
docker compose --profile relay up -d
```

### Without Docker

Install dependencies:

```bash
apt-get install -y linuxptp iproute2
pip install -r requirements.txt
```

Run directly (requires root for PTP):

```bash
# Master
sudo python3 -m clustertime.main -c config/master.yaml --mode master

# Relay
sudo python3 -m clustertime.main -c config/relay.yaml --mode relay
```

## Logs

```bash
docker compose --profile master logs -f
docker compose --profile relay logs -f
```
