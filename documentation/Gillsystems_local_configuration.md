# Gillsystems Local Network Configuration

**Last Updated:** April 29, 2026
**Scope:** All Gillsystems projects — authoritative reference for local infrastructure, node identities, IPs, OS, roles, and storage layout.

---

## Network Subnet

| Detail | Value |
|--------|-------|
| **Subnet** | `10.0.0.0/24` |
| **DHCP / Assignment** | Static allocations per node (see below) |

---

## Node Inventory

| Node Name | IP Address | OS | Role | Storage | GPU | RAM | Disk |
|-----------|------------|----|------|---------|-----|-----|------|
| **Gillsystems-Main** | `10.0.0.164` | Windows 11 Pro | Orchestrator / Primary Compute | 2 TB NVMe | Radeon 7900 XTX (24 GB) | 48 GB | Ryzen 9 5900X |
| **Gillsystems-HTPC** | `10.0.0.42` | Kubuntu | Storage Authority / Worker | 2 TB ZFS | Radeon 7600 (8 GB) | 16 GB | Ryzen 5 5600G |
| **Gillsystems-Laptop** | `10.0.0.93` | Windows 10 | Worker | 1 TB SSD | Vega 6 (integrated) | 20 GB | Ryzen 5 4500U |
| **Gillsystems-Steam-Deck** | `10.0.0.139` | SteamOS (Arch Linux) | Worker | 512 GB NVMe | AMD RDNA 2 APU (shared) | 16 GB unified | 512 GB |

---

## Node Details

### Gillsystems-Main
- **IP:** `10.0.0.164`
- **OS:** Windows 11 Pro x64
- **Role:** Primary orchestrator / heavy compute node
- **Compute Tier:** Tier 1 (Production-Grade)
- **AI Build Target:** `gfx1100` (Navi 31 / RDNA 3)
- **Required Backend:** ROCm / HIP SDK (MUST use GPU; no fallback permitted)
- **CPU:** AMD Ryzen 9 5900X (Zen 3, 12 cores / 24 threads, 3.7 GHz base / 4.8 GHz boost, 64 MB L3, 105W TDP, no iGPU)
- **RAM:** 48 GB
- **GPU:** AMD Radeon 7900 XTX — 24 GB VRAM
- **Storage:** 2 TB NVMe
- **Model Path:** `C:\Models\Working_Models\`
- **LLM Inference Speed:** ~130 tokens/sec
- **Home Directory:** `C:\Users\Gillsystems Laptop\`

---

### Gillsystems-HTPC
- **IP:** `10.0.0.42`
- **OS:** Kubuntu (Linux)
- **Role:** Storage authority and secondary worker
- **Compute Tier:** Tier 1 (Production-Grade)
- **AI Build Target:** `gfx1102` (Navi 33 / RDNA 3)
- **Required Backend:** ROCm (MUST use GPU; no fallback permitted)
- **CPU:** AMD Ryzen 5 5600G (Zen 3, 6 cores / 12 threads, 3.9 GHz base / 4.4 GHz boost, 16 MB L3, 65W TDP, integrated Radeon Vega 7)
- **RAM:** 16 GB
- **GPU:** AMD Radeon 7600 — 8 GB VRAM
- **Storage:** 2 TB — ZFS pool (canonical source of truth for the cluster)
  - ZFS Pool Root: `/gillsystems_zfs_pool/AI_storage/`
- **Model Path:** `/home/gillsystems-htpc/Desktop/Models/`
- **LLM Inference Speed:** ~60 tokens/sec
- **Home Directory:** `/home/gillsystems-htpc/`

---

### Gillsystems-Laptop
- **IP:** `10.0.0.93`
- **OS:** Windows 10 x64
- **Role:** Worker node
- **Compute Tier:** Tier 2 (Mobile/Edge)
- **AI Build Target:** `gfx90c` (Renoir / Vega)
- **Required Backend:** Vulkan (Default) or HIP with mandatory `LLAMA_HIP_UMA=1` environment variable
- **CPU:** AMD Ryzen 5 4500U (Zen 2, 6 cores / 6 threads, 2.375 GHz base / 4.0 GHz boost, 8 MB L3, 15W TDP mobile)
- **RAM:** 20 GB
- **GPU:** AMD Radeon Vega 6 (integrated)
- **Storage:** 1 TB SSD
- **Model Path:** `C:\Users\Gillsystems Laptop\Desktop\Models\`
- **MAC Address:** `6D:B4:D3:4C:32:C8`
- **LLM Inference Speed:** ~9 tokens/sec
- **Home Directory:** `C:\Users\Gillsystems Laptop\`

---

### Gillsystems-Steam-Deck
- **IP:** `10.0.0.139`
- **OS:** SteamOS (Arch Linux base)
- **Role:** Worker node
- **Compute Tier:** Tier 2 (Mobile/Edge)
- **AI Build Target:** `gfx1033` (Van Gogh / RDNA 2)
- **Required Backend:** Vulkan (Default) or HIP with mandatory `LLAMA_HIP_UMA=1` environment variable
- **CPU:** AMD Zen 2 (4 cores / 8 threads, up to 3.5 GHz)
- **RAM / VRAM:** 16 GB LPDDR5 unified (shared between CPU and GPU)
- **GPU:** AMD RDNA 2 (8 CUs, integrated APU — draws from unified 16 GB)
- **Storage:** 512 GB NVMe
- **Model Path:** `/home/deck/Desktop/Models/`
- **LLM Inference Speed:** ~30 tokens/sec
- **Home Directory:** `/home/deck/`
- **Hostname:** `deck`

---

## Storage Architecture Summary

```
Cluster Storage Layout
─────────────────────────────────────────────────────────────────
Tier 1 — LOCAL (all nodes)
  Each node maintains fast local storage on its own NVMe/SSD.
  Windows nodes: C:\ drive (NVMe or SSD)
  Linux / SteamOS nodes: /home/<user>/

Tier 2 — CANONICAL (HTPC/ZFS)
  /gillsystems_zfs_pool/AI_storage/
  └── (project-defined subdirectories)
─────────────────────────────────────────────────────────────────
```

**Key principles:**
- **Local-first**: each node reads/writes locally for performance
- **ZFS authority**: HTPC is the single canonical source of truth for the cluster
- **Network resilience**: local storage remains functional if HTPC is unreachable

---

## Node Identity

MAC addresses are the authoritative node identity mechanism (overrides hostname and IP):

| Node | MAC Address |
|------|-------------|
| Gillsystems-Main | *(auto-detected — record here once confirmed)* |
| Gillsystems-HTPC | *(auto-detected — record here once confirmed)* |
| Gillsystems-Laptop | `6D:B4:D3:4C:32:C8` |
| Gillsystems-Steam-Deck | *(auto-detected — record here once confirmed)* |

Identity resolution order: **MAC → Hostname → IP fallback**

---

## Software (Common Baseline)

| Component | Version | Notes |
|-----------|---------|-------|
| **Python** | 3.10.x (3.10.11 recommended) | |
| **Node.js** | v20+ LTS | Required for GUI/frontend work |
| **Git** | Latest | All nodes |

---

## Quick Reference: Node IPs

```
Gillsystems-Main        10.0.0.164   (Windows — Orchestrator)
Gillsystems-HTPC        10.0.0.42    (Linux   — Storage/Relay)
Gillsystems-Laptop      10.0.0.93    (Windows — Worker)
Gillsystems-Steam-Deck  10.0.0.139   (SteamOS — Worker)
```

---

*This document is the authoritative local infrastructure reference for all Gillsystems projects. Keep in sync when node IPs or hardware changes.*
