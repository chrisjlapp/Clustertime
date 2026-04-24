
<img width="2048" height="2048" alt="Gemini_Generated_Image_4edecu4edecu4ede" src="https://github.com/user-attachments/assets/bba02c7e-4150-4ca5-ba7a-d6c0ed8e3cdc" />



# Clustertime
Lots of media applications hardcode certain aspects of PTP to not behave when you get into overlay based networking technologies, as well, some network platforms have limitations on how to forward PTP packets. 
Clustertime aims to add a simple way to solve this by creating a time Cluster, or "constellation" with master and relay nodes.

Simply put, using a PTP Unicast-to-Multicast Relay Appliance. Clustertime bridges a PTPv2 unicast master node to a multicast downstream network, enabling accurate time synchronization across cluster nodes.

Best results are with hardware timestamping on intel 225/226 nic series. Raspberry Pi5 provides relatively good, but somtimes mixed results, but uses hybrid timestamping.

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
# Optional multi-interface master mode:
# master_interfaces: [eth0, eth1]
# Optional per-interface master flags:
# master_interface_options:
#   eth0:
#     inhibit_multicast_service: false
#   eth1:
#     inhibit_multicast_service: true

# config/relay.yaml
interface: eth0
master:
  ip: 192.168.1.10   # change to your master node's IP
```

Any config value can also be overridden via environment variables (e.g. `CT_INTERFACE`, `CT_MODE`, `CT_MASTER_IP`).
For multi-interface master serving, use `master_interfaces` in YAML or
`CT_MASTER_INTERFACES=eth0,eth1`.
`inhibit_multicast_service` defaults to `false` for each master interface and
can be set independently under `master_interface_options`.

### Relay downstream identity override

By default, relay downstream announces use the relay's own clock identity.

If you need the relay downstream instance to advertise a fixed identity
(for example, matching the upstream master), set:

```yaml
ptp:
  downstream_clock_identity: aabbcc.ddee.ff0011
```

or environment override:

```bash
CT_PTP_DOWNSTREAM_CLOCK_IDENTITY=aabbcc.ddee.ff0011
```

Clustertime also accepts `aa:bb:cc:dd:ee:ff:00:11` and normalizes it for
linuxptp.

You can also set automatic derivation:

```yaml
ptp:
  downstream_clock_identity: auto
```

In `auto` mode, Clustertime reads the master's MAC from `ip neigh` and derives
the PTP clock identity using EUI-48 → EUI-64 expansion
(`xxxxxx.fffe.xxxxxx`). If neighbor/MAC lookup is unavailable at startup,
Clustertime falls back to relay self-identity and logs a warning.

> Caution: advertising the same clockIdentity from multiple active clocks in
> one PTP domain can make BMCA/debugging ambiguous.

### Timestamping mode

`ptp.time_stamping` supports:
- `auto` (default): use hardware timestamping when the interface reports support, otherwise fall back to software
- `hardware`: force hardware timestamping
- `software`: force software timestamping

Equivalent env override: `CT_PTP_TIME_STAMPING=auto|hardware|software`.

For Raspberry Pi deployments, optional hybrid behavior is available:

- `ptp.rpi_hybrid_ts: true` forces the **relay upstream** and **master** ptp4l
  instances to software timestamping on Raspberry Pi devices.
- Downstream instance keeps normal `ptp.time_stamping` behavior.

Equivalent env override: `CT_PTP_RPI_HYBRID_TS=true|false`.

### PTP minor version compatibility

`ptp.minor_version` controls the PTP minor version used by generated ptp4l configs:

- `0` (default): PTPv2.0 compatibility mode
- `1`: PTPv2.1 behavior

Equivalent env override: `CT_PTP_MINOR_VERSION=0|1`.

If a relay (notably some Raspberry Pi 5 setups) shows repeated
`received SYNC without timestamp` against a specific upstream master, validate
both `ptp.minor_version: 0` and `ptp.minor_version: 1` across peers to confirm
which interop combination is stable.

### Tiered relay (relay-to-relay unicast)

You can point a relay upstream at the **downstream IP of another relay** to
build a tiered topology when one master cannot fan out to all clients.

Set `master.ip` on the child relay to the parent relay downstream address:

```yaml
master:
  ip: 192.168.1.51   # parent relay downstream IP
```

Clustertime configures relay downstream ptp4l with `unicast_listen` enabled,
so child relays can negotiate unicast service from a parent relay over UDPv4.

If a child relay occasionally flips `SLAVE -> LISTENING` on
`ANNOUNCE_RECEIPT_TIMEOUT_EXPIRES` in tiered topologies, you can increase the
upstream announce receipt window:

```yaml
ptp:
  announce_interval: 0
  announce_receipt_timeout: 5
```

Equivalent env override:

```bash
CT_PTP_ANNOUNCE_RECEIPT_TIMEOUT=5
```

### Relay priority configuration

Relay nodes can set BMCA priorities for both upstream and downstream ptp4l
instances:

```yaml
ptp:
  relay_priority1: 255
  relay_priority2: 255
```

Equivalent env overrides:

```bash
CT_PTP_RELAY_PRIORITY1=255
CT_PTP_RELAY_PRIORITY2=255
```

Valid range is `0..255` (lower values have higher priority in BMCA).

### Master priority configuration

Master nodes can also set BMCA priorities for their ptp4l instance:

```yaml
ptp:
  master_priority1: 128
  master_priority2: 128
```

Equivalent env overrides:

```bash
CT_PTP_MASTER_PRIORITY1=128
CT_PTP_MASTER_PRIORITY2=128
```

Valid range is `0..255` (lower values have higher priority in BMCA).

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

## Start automatically on system boot (systemd)

Clustertime includes a helper installer that creates and enables a systemd unit
for either Docker-based or native startup:

```bash
sudo ./scripts/install_systemd_service.sh --runtime <docker|native> --node <master|relay>
```

Examples:

```bash
# Docker master
sudo ./scripts/install_systemd_service.sh --runtime docker --node master

# Docker relay
sudo ./scripts/install_systemd_service.sh --runtime docker --node relay

# Native master
sudo ./scripts/install_systemd_service.sh --runtime native --node master

# Native relay
sudo ./scripts/install_systemd_service.sh --runtime native --node relay
```

What this does:

- Writes a service file in `/etc/systemd/system/`
- Runs `systemctl daemon-reload`
- Enables and starts the service immediately (`systemctl enable --now ...`)

Useful service commands:

```bash
systemctl status clustertime-docker-master.service
systemctl status clustertime-docker-relay.service
systemctl status clustertime-native-master.service
systemctl status clustertime-native-relay.service

journalctl -u clustertime-docker-master.service -f
```

## Logs

```bash
docker compose --profile master logs -f
docker compose --profile relay logs -f
```

## Troubleshooting

### Relay log shows `received SYNC without timestamp`

If relay upstream logs repeatedly show messages like:

```text
ptp4l[upstream]: port 1 (eth0.up): received SYNC without timestamp
```

that means PTP Sync packets are arriving, but the NIC/driver path did not attach RX timestamps for those packets. In this state, the upstream ptp4l instance cannot lock to the master clock.

Typical causes and checks:

1. Verify timestamp capability on the **failing** upstream interface:

   ```bash
   ethtool -T <upstream-interface>
   ```

   Confirm hardware or software RX timestamping is reported.

2. Compare working vs failing relay effective timestamp mode, tx timeout, and TTL settings:

   - Config file: `ptp.time_stamping`, `ptp.tx_timestamp_timeout`, `ptp.multicast_ttl`, `ptp.unicast_ttl`
   - Env override: `CT_PTP_TIME_STAMPING`, `CT_PTP_TX_TS_TIMEOUT`, `CT_PTP_MULTICAST_TTL`, `CT_PTP_UNICAST_TTL`

   Note: linuxptp exposes `udp_ttl` for UDP transports; Clustertime maps
   `ptp.multicast_ttl`/`ptp.unicast_ttl` to the generated role configs so you can
   tune relay upstream/downstream behavior independently.

   If logs include `timed out while polling for tx timestamp`, increase timeout
   temporarily (for example to 30 seconds) to determine whether this is
   a latency/driver issue instead of total timestamp failure:

   ```yaml
   ptp:
     time_stamping: software
     tx_timestamp_timeout: 30
   ```

   Environment equivalent:

   ```bash
   export CT_PTP_TX_TS_TIMEOUT=30
   ```

   For isolation, force software mode first:

   ```yaml
   ptp:
     time_stamping: software
   ```

3. Ensure the chosen interface is the actual upstream NIC used to receive master traffic (especially in multi-interface setups with `upstream_interface` / `downstream_interfaces`).

4. Check for offload/driver differences between the two relay devices (driver version, firmware, NIC model), since one device working and another failing is often a hardware/driver timestamp path mismatch.

5. Validate no network middlebox is rewriting/filtering PTP event traffic on the failing path.

Expected recovery signal after fixing timestamping is that upstream logs switch from repeated SYNC timestamp errors to normal RMS/freq/delay lines and relay status reports `state=SLAVE` with finite `master_offset` / `path_delay`.

### Device-side command checklist (working vs failing relay)

Use this sequence on both relays and compare outputs side-by-side.

1. Confirm which interfaces Clustertime is configured to use:

   ```bash
   # If running with a file config
   awk '1' config/relay.yaml

   # If running in container with env overrides
   docker compose --profile relay exec relay env | grep '^CT_'
   ```

2. Validate link state and addressing on upstream/downstream interfaces:

   ```bash
   ip -br link
   ip -br addr
   ```

3. Check NIC timestamp capabilities (critical for this issue):

   ```bash
   ethtool -T <upstream-interface>
   ethtool -T <downstream-interface>
   ```

   Compare support flags between working and failing devices.

4. Capture driver + firmware identity:

   ```bash
   ethtool -i <upstream-interface>
   uname -a
   ```

5. Inspect offload settings that can affect PTP behavior:

   ```bash
   ethtool -k <upstream-interface>
   ```

6. Confirm ptp4l command/config actually in use:

   ```bash
   ps -ef | grep '[p]tp4l'
   docker compose --profile relay logs --tail=200 relay
   ```

7. Verify host PTP clocks and mapping:

   ```bash
   ls -l /dev/ptp*
   for d in /sys/class/net/*/device/ptp/ptp*; do echo "$d"; done
   ```

8. Observe live PTP traffic on the upstream interface:

   ```bash
   tcpdump -ni <upstream-interface> -vv '(udp port 319 or udp port 320)'
   ```

9. A/B test software timestamping as an isolation step on the failing relay:

   - Set `ptp.time_stamping: software` in `config/relay.yaml`, or set `CT_PTP_TIME_STAMPING=software`.
   - Restart relay:

   ```bash
   docker compose --profile relay up -d --force-recreate
   docker compose --profile relay logs -f relay
   ```

   If errors stop in software mode, the problem is likely hardware timestamp path (NIC/driver/firmware/offload).

10. Optional sanity check for clock discipline after recovery:

   ```bash
   docker compose --profile relay logs --tail=300 relay | grep -E 'Relay sync status|rms|received SYNC without timestamp'
   ```

### One-step vs two-step clarification

Clustertime-generated ptp4l configs set:

```ini
twoStepFlag 1
```

for master, relay upstream, and relay downstream roles. So the presence of
`onestep-sync` in `ethtool -T` capabilities does **not** mean Clustertime is
defaulting to one-step mode; that value only indicates what the NIC can do.

If one relay still shows `received SYNC without timestamp` while another works,
the more likely issue is timestamp delivery on that interface path
(driver/firmware/offload/macvlan behavior), not one-step vs two-step selection.

### Why ptp4l can report missing SYNC timestamp in two-step mode

In two-step PTP, the precise transmit time is sent later in `Follow_Up`. That is
true at the protocol level. However, ptp4l still needs a **local receive
timestamp** for each incoming `SYNC` frame from the kernel/NIC timestamping API.

So this log line:

```text
received SYNC without timestamp
```

means the packet arrived but the OS did not deliver RX timestamp metadata
(`SO_TIMESTAMPING`/ancillary data) with that packet. It does **not** mean the
PTP `SYNC` payload should have carried the master timestamp directly.

In short:

- `Follow_Up` carries the master's precise origin timestamp (two-step behavior).
- RX timestamping provides the slave's local ingress time for the received event.
- ptp4l needs both pieces to compute offset, so missing RX timestamp still breaks
  synchronization even in two-step mode.

### Driver-specific hint (e.g., `macb` vs server NICs)

If your working relay uses a server NIC driver and the failing relay uses
`macb` (common on some ARM/Raspberry Pi platforms), both may still advertise
timestamp capability in `ethtool -T` while behaving differently for sustained
PTP RX timestamp delivery.

For this case, prefer a deterministic setup on the failing host:

1. Force software timestamping (`ptp.time_stamping: software` or
   `CT_PTP_TIME_STAMPING=software`).
2. Restart relay and verify SYNC timestamp errors stop.
3. Confirm effective runtime config in generated files:

   ```bash
   docker compose --profile relay exec relay sh -lc "grep -n 'time_stamping\\|twoStepFlag' /var/run/clustertime/ptp4l_*.conf"
   ```

If software mode resolves the issue, keep that host pinned to software mode
until kernel/NIC-driver behavior is validated for hardware timestamping.

For Raspberry Pi 5 specifically: if you need hardware timestamping, run relay in
dual-interface mode using two physical NICs (for example onboard `eth0` + a USB
Ethernet adapter). Single-interface relay mode relies on macvlan virtual
interfaces and is not a reliable hardware timestamping path on `macb`.

### Troubleshooting a consistent ~20 second offset on a switch

If relay nodes are tightly in sync with each other, but a switch directly
connected to the **master multicast** segment is consistently off by roughly
20 seconds, focus on announce/timescale interpretation on that switch path
instead of relay lock quality.

Typical pattern:
- Relay unicast lock to master looks healthy (normal `rms/freq/delay` lines).
- Relay multicast clients look correct.
- One switch on the master-facing multicast segment shows a stable seconds-level
  offset (for example ~20 s).

That pattern usually points to one of:
- Profile mismatch (PTPv2 default profile vs 802.1AS/gPTP expectations)
- UTC/TAI handling mismatch on the switch
- Domain/profile settings applied differently on that interface or VLAN

Quick checks:
1. Verify the switch is in the same PTP profile/domain as the master.
2. Inspect master announce/status datasets from a Linux host on that segment:

   ```bash
   pmc -u -b 0 'GET TIME_PROPERTIES_DATA_SET'
   pmc -u -b 0 'GET TIME_STATUS_NP'
   pmc -u -b 0 'GET GRANDMASTER_SETTINGS_NP'
   ```

3. Compare the switch's UTC-offset/timescale interpretation (`currentUtcOffset`,
   `currentUtcOffsetValid`, PTP-vs-ARB time scale behavior) to what the master
   is announcing.
4. Confirm no second grandmaster is visible on that segment/domain and BMCA
   state on the switch is what you expect.

Background: linuxptp behavior differs by timestamping mode when acting as
domain server. In software timestamping mode, `ptp4l` announces Arbitrary
timescale (effectively UTC there), while in hardware timestamping mode it
announces PTP timescale and relies on `phc2sys` to maintain UTC/TAI offset
handling for system clock users.

In Clustertime hardware mode:
- **Master** serves time via `ptp4l` only (no Clustertime-managed `phc2sys`
  sidecar by default).
- **Relay** runs `phc2sys -s <up_iface> -c CLOCK_REALTIME -O 0`
  so relay `CLOCK_REALTIME` follows upstream PHC without UTC/TAI reinterpretation.

#### Why this can happen even when *all nodes use hardware timestamping*

You can still see "master off by ~20 seconds while relays agree with each
other" when relay downstream service is based on `CLOCK_REALTIME` but relay
upstream lock in hardware mode is only disciplining PHC.

In that case:
- Relay upstream `ptp4l` can be healthy against master (PHC aligned).
- Relay downstream can still advertise local system time if `CLOCK_REALTIME`
  is not being steered from PHC.
- Multiple relays may match each other (same OS/NTP behavior) yet all differ
  from what a direct master-attached switch reports.

Use `phc2sys` on each relay in hardware mode so PHC lock is transferred to
`CLOCK_REALTIME` before downstream multicast is served.

If relay `phc2sys` hovers around ~37-second offsets or jumps between near-zero
and ~37 seconds, that usually indicates UTC/TAI reinterpretation mismatch.
Relay sidecars therefore use explicit `-O 0` to keep PHC and `CLOCK_REALTIME`
in the same timescale on the relay host.

`phc2sys` offset logs are in **nanoseconds**. For example, an offset around
`36889711156` means ~36.9 seconds, which is typically a UTC/TAI context issue
rather than a normal steady-state servo error.

If you see `freq +100000000` or `-100000000` for long periods, the servo is
railed at its configured frequency limit and still trying to recover a large
offset. Clustertime enables `-S 1.0` on phc2sys sidecars so second-level
startup errors can be stepped quickly instead of taking minutes to slew down.

By contrast, offsets in the low microseconds-to-tens-of-microseconds range
(`~5,000` to `~30,000` ns) that trend downward after `SLAVE` lock are expected
during convergence and usually indicate healthy phc2sys behavior.
