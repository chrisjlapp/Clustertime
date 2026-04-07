# Product Requirements Document (PRD)
## PTP Unicast-to-Multicast Relay Appliance (Master-Elected Model)

---

## 1. Executive Summary

This document defines the requirements for a lightweight, deployable application (VM or container-based) that enables distributed nodes across a LAN to:

1. Elect a **single master node**
2. Use the **master node’s system time as the authoritative PTPv2 source (unicast)**
3. Synchronize all other nodes to that master via **PTPv2 unicast**
4. Redistribute synchronized time locally using **PTPv2 multicast** from each node

Each non-master node acts as a **boundary clock relay**, ingesting upstream time and serving downstream clients.

---

## 2. Problem Statement

Many environments require:
- A consistent, shared timebase across distributed compute nodes
- Deterministic synchronization without reliance on external grandmasters
- Compatibility with multicast PTP clients

Challenges:
- Multicast PTP does not scale across domains
- External grandmasters may not be available or desired
- Existing solutions rely on hardware clocks

This system solves that by:
- Dynamically selecting a **master node within the cluster**
- Using its **system clock as the PTP source**
- Distributing time via **unicast (upstream)** and **multicast (downstream)**

---

## 3. Goals & Objectives

### Primary Goals
- Establish a **cluster-wide authoritative clock**
- Ensure all nodes synchronize to a single master
- Provide multicast PTP output for downstream devices

### Secondary Goals
- Enable automatic or manual master selection
- Support container and VM deployments
- Provide observability and failover

---

## 4. Non-Goals

- Replace high-precision GPS-based grandmasters
- Provide telecom-grade holdover initially
- Implement full distributed consensus timing (beyond master election)

---

## 5. System Architecture

### Logical Flow

[ Master Node (System Clock) ]
              ↓ (PTP Unicast)
      [ Relay Nodes ]
              ↓ (PTP Multicast)
      [ Downstream Clients ]

---

### Node Roles

#### 1. Master Node (Authoritative Clock)
- Selected via:
  - Static config OR
  - Election mechanism (future)
- Uses **system clock as PTP reference**
- Acts as:
  - PTPv2 unicast server
  - Optional multicast source

#### 2. Relay Nodes
- Act as:
  - PTP unicast clients (to master)
  - PTP multicast servers (to local network)
- Maintain synchronized local clocks

---

## 6. Functional Requirements

### 6.1 Master Selection
- System must support:
  - Static master designation (MVP)
  - Future dynamic election
- Only one active master at a time

### 6.2 Time Synchronization
- Must support PTPv2 (IEEE 1588-2008)
- Master node:
  - Uses system clock as reference
  - Serves time via unicast
- Relay nodes:
  - Lock to master via unicast

### 6.3 Relay Behavior
- Relay nodes must:
  - Act as PTP slaves upstream
  - Act as PTP masters downstream
- Must maintain stable clock discipline

### 6.4 Configuration
- Must support configuration via:
  - YAML or ENV

Configurable parameters:
- master_node_ip
- interface
- domain number
- transport (UDPv4)
- sync interval

### 6.5 Networking
- Must support:
  - Single-interface mode
  - Dual-interface mode
- Must run in host networking

### 6.6 Observability
- Metrics:
  - Offset from master
  - Servo state
  - GM identity
  - Sync status
- Logs:
  - Master changes
  - Sync loss

---

## 7. Non-Functional Requirements

### 7.1 Performance
- Hardware timestamping: sub-microsecond target
- Software timestamping: <1ms

### 7.2 Reliability
- Must detect master failure
- Must support failover to backup master (Phase 2)

### 7.3 Security
- Minimal attack surface
- Interface binding

### 7.4 Footprint
- Memory: <100MB
- CPU: <5%

---

## 8. Technical Design

### 8.1 Core Components

#### LinuxPTP
- ptp4l
- phc2sys

#### Wrapper Service
- Master/relay role enforcement
- Config generation
- Health monitoring

---

### 8.2 Process Model

Master Node:
- ptp4l (server mode, unicast enabled)

Relay Node:
- ptp4l (client to master)
- ptp4l (multicast server behavior)
- phc2sys

---

### 8.3 Configuration Example

```yaml
mode: relay
interface: eth0

master:
  ip: 192.168.1.10

ptp:
  domain: 0
  transport: UDPv4
  sync_interval: -3
```

---

## 9. Deployment Architecture

### VM Deployment
- Minimal Linux
- systemd services

### Container Deployment
- hostNetwork: true
- privileged: true
- /dev/ptp* mounted

---

## 10. Failure Scenarios

| Scenario | Behavior |
|----------|---------|
| Master failure | Failover (Phase 2) |
| Network loss | Holdover |
| Node restart | Re-sync |

---

## 11. Success Criteria

- All nodes locked to master
- Offset <1µs (HW timestamping)
- Fast convergence (<10s)

---

## 12. Roadmap

### Phase 1
- Static master
- Basic relay

### Phase 2
- Master failover
- Metrics

### Phase 3
- Dynamic election
- UI

---

## 13. Risks

| Risk | Mitigation |
|------|-----------|
| System clock instability | Use PHC sync |
| Master overload | Scale via relays |
| Mis-election | Add validation |

---

## 14. Open Questions

- Election mechanism design?
- ST 2110 profile requirements?

---

## 15. Summary

This system creates a **self-contained PTP timing fabric** where:

- One node becomes the **authoritative master (system clock)**
- All nodes synchronize via **unicast PTP**
- Each node redistributes via **multicast PTPv2**

This enables a fully software-defined, scalable timing architecture.

---

