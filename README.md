<p align="center">
  <img src="Gillsystems_logo_stuff/Gill%20Systems%20Logo.png" alt="Gill Systems Logo" width="800">
</p>

# Gillsystems AI Stack Updater 

> *"One command. Both OSes. Always current."*

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)](.)
[![AMD GPU](https://img.shields.io/badge/GPU-AMD%20ROCm%2FHIP-red?logo=amd)](https://rocm.docs.amd.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Gillsystems AI Stack Updater** is a portable, invocation-only Python agent that keeps your AMD consumer GPU AI stack — ROCm/HIP and llama.cpp — current on both Windows and Linux with a single command. No manual headaches. Reboot-resilient. Fully automated.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Requirements](#requirements)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [GPU Architecture Reference](#gpu-architecture-reference)
- [Running Tests](#running-tests)
- [How Reboot Resume Works](#how-reboot-resume-works)
- [Supported Operating Systems](#supported-operating-systems)
- [Project Layout](#project-layout)
- [User Guide](#user-guide)
- [Support / Donate](#support--donate)

---

## Overview

Keeping ROCm/HIP and llama.cpp up to date on AMD consumer GPUs involves a deep dependency chain:

```
kernel drivers → amdgpu → ROCm runtime → HIP → rocBLAS → hipBLAS → llama.cpp (GGML_HIP)
```

**Gillsystems AI Stack Updater** automates the entire chain:

1. Detects your currently installed versions against the upstream stable releases (GitHub Releases API + AMD repo probing).
2. Downloads, compiles (if needed), and installs new versions automatically using `amdgpu-install` on Linux and the silent HIP SDK installer on Windows.
3. Handles any required OS reboots — saves its checkpoint state to SQLite, registers a startup resume task, and picks up exactly where it left off.

---

## Key Features

| Feature | Detail |
|---|---|
| **Smart Version Detection** | Checks `rocm-smi`, `hipcc`, GitHub Releases API, and AMD repo HEAD |
| **Dual-OS Sub-Agents** | Linux: `amdgpu-install` automation. Windows: silent HIP SDK install |
| **GPU Architecture Auto-Detect** | `rocminfo`, `/sys/class/drm`, `lspci`, `wmi`, `hipInfo` — no manual config needed |
| **Reboot Resilience** | SQLite checkpoint + systemd (Linux) / Scheduled Task (Windows) resume |
| **llama.cpp HIP Build** | Clone, `cmake -DGGML_HIP=ON`, Ninja build, binaries to `PATH` |
| **Invocation-Only** | Does nothing unless explicitly run — no daemons, no watchers |
| **Dry-Run Mode** | Full simulation with `--dry-run`, no system changes made |
| **Rich Terminal UI** | Panels, progress bars, version tables, reboot countdown via `rich` |
| **Safe Elevation** | `sudo` on Linux, UAC `runas` on Windows — auto-requested if not already root/admin |

---

## Quick Start

### Windows

```bat
update-ai-stack.bat
```

Runs as Administrator (UAC prompt appears if not already elevated). On first run, installs Python dependencies automatically.

### Linux

```bash
chmod +x update-ai-stack.sh
./update-ai-stack.sh
```

Re-runs with `sudo` automatically if not already root. Installs Python dependencies via pip if missing.

### Dry Run (safe preview — no changes made)

```bash
# Linux
./update-ai-stack.sh --dry-run

# Windows
update-ai-stack.bat --dry-run
```

### Check for Updates Only

```bash
python -m src.main --check-only
```

---

## Requirements

| Requirement | Minimum Version |
|---|---|
| Python | 3.11+ |
| pip | 23+ |
| AMD GPU | Radeon RX 5000 / 6000 / 7000 series (GCN4+ / RDNA2+ / RDNA3) |
| OS | Ubuntu 22.04+, Fedora 39+, Windows 10 22H2+, Windows 11 |
| Disk Space | ~8 GB free (ROCm ~4 GB + llama.cpp build ~2 GB) |
| Internet | Required for version checks and downloads |

**Linux extras:** `cmake`, `ninja-build`, `git`, `gcc`, `g++` (all installable via your distro package manager)

**Windows extras:** [Visual Studio Build Tools 2022](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022) with C++ workload, [CMake](https://cmake.org/download/)

---

## CLI Reference

```
usage: gillsystems-ai-stack-updater [-h] [--dry-run] [--check-only] [--yes] [--force]
            [--no-rocm] [--no-llama] [--config CONFIG]
            [--gpu-targets TARGETS [TARGETS ...]] [--verbose] [--version]
```

| Flag | Description |
|---|---|
| `--dry-run` | Simulate the entire run — no installs, no builds, no reboots |
| `--check-only` | Check and display version status, then exit (implies `--dry-run`) |
| `--yes` / `-y` | Auto-confirm all prompts (non-interactive/CI mode) |
| `--force` | Re-run all steps even if already up to date |
| `--no-rocm` | Skip ROCm/HIP update step |
| `--no-llama` | Skip llama.cpp build step |
| `--config PATH` | Path to a custom config YAML (default: `config/default_config.yaml`) |
| `--gpu-targets T [T ...]` | Override GPU architecture targets (e.g. `gfx1100 gfx1030`) |
| `--verbose` | Enable verbose/debug logging |
| `--version` | Print Gillsystems AI Stack Updater version and exit |

---

## Configuration

Gillsystems AI Stack Updater reads `config/default_config.yaml` on startup. Every setting can also be overridden via environment variable.

### Key Config Sections (`config/default_config.yaml`)

```yaml
gpu:
  targets: [gfx1100, gfx1101, gfx1030]   # override with --gpu-targets
  auto_detect: true                        # auto-detect from rocminfo/lspci/WMI

paths:
  llama_src: ~/llama.cpp                   # where to clone llama.cpp
  llama_install: /usr/local                # cmake --install prefix (Linux)
  state_db: ~/.gillsystems-ai-stack-updater/state.db               # SQLite checkpoint database
  log_dir: ~/.gillsystems-ai-stack-updater/logs                    # log file directory

behavior:
  auto_reboot: false                       # require user confirmation before rebooting
  reboot_delay_seconds: 30                 # countdown before auto-reboot
  rocm_usecase: rocm,hiplibsdk             # amdgpu-install --usecase value
  llama_build_jobs: 0                      # 0 = use all CPU cores

repos:
  llama_cpp: https://github.com/ggml-org/llama.cpp
```

### Environment Variable Overrides

| Variable | Effect |
|---|---|
| `GILLSYSTEMS_AI_STACK_UPDATER_DRY_RUN=1` | Enables dry-run mode |
| `GILLSYSTEMS_AI_STACK_UPDATER_VERBOSE=1` | Enables verbose logging |
| `GILLSYSTEMS_AI_STACK_UPDATER_LOG_LEVEL=DEBUG` | Sets log level (DEBUG/INFO/WARNING/ERROR) |

---

## Architecture

### State Machine

```
START
  │
  ▼
CHECK_VERSIONS ──(no updates needed)──► DONE
  │
  ▼
DETECT_GPU_TARGETS
  │
  ▼
UPDATE_ROCM/HIP ──(reboot required)──► REBOOT ──► [resume after boot]
  │                                                      │
  ▼                                                      │
BUILD_LLAMA_CPP ◄─────────────────────────────────────-─┘
  │
  ▼
VALIDATE
  │
  ▼
DONE
```

### Module Overview

```
src/
├── __init__.py          # Package, version
├── main.py              # Orchestrator / entry point / state machine
├── config.py            # Pydantic config models + YAML loader
├── state_manager.py     # SQLite checkpoint ledger (StateManager)
├── version_intel.py     # Version detection (VersionIntel, UpdateManifest)
├── gpu_detect.py        # GPU arch auto-detection (GPUDetector)
├── privilege.py         # UAC / sudo elevation
├── cli.py               # Rich terminal UI
├── linux/
│   ├── rocm_updater.py  # amdgpu-install automation
│   ├── llama_builder.py # CMake + HIP build (Linux)
│   └── reboot_handler.py# systemd one-shot resume service
└── windows/
    ├── hip_updater.py   # HIP SDK silent installer
    ├── llama_builder.py # CMake + VS Build Tools + Ninja (Windows)
    └── reboot_handler.py# Scheduled Task resume
```

### Checkpoint Database Schema

```sql
CREATE TABLE runs (
    run_id    TEXT PRIMARY KEY,
    started   TEXT,
    finished  TEXT,
    status    TEXT   -- running | done | failed
);

CREATE TABLE steps (
    run_id     TEXT,
    step_name  TEXT,
    status     TEXT,  -- pending | running | done | failed | skipped
    started    TEXT,
    finished   TEXT,
    detail     TEXT,
    PRIMARY KEY (run_id, step_name)
);
```

---

## GPU Architecture Reference

| GPU Series | Architecture | `AMDGPU_TARGETS` |
|---|---|---|
| RX 5500 / 5600 / 5700 | RDNA1 | `gfx1010`, `gfx1011`, `gfx1012` |
| RX 6600 / 6700 / 6800 / 6900 | RDNA2 | `gfx1030`, `gfx1031`, `gfx1032` |
| RX 7600 / 7700 / 7800 / 7900 | RDNA3 | `gfx1100`, `gfx1101`, `gfx1102` |
| RX 9070 / 9070 XT | RDNA4 | `gfx1200`, `gfx1201` |
| Radeon VII / Vega 64 | Vega20 | `gfx906` |
| RX 580 / 590 | Polaris | `gfx803` |

Gillsystems AI Stack Updater auto-detects the correct targets using `rocminfo`, `/sys/class/drm`, `lspci -nn`, `wmi`, and `hipInfo`. Manual override is available via `--gpu-targets` or the config file.

---

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run full test suite
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run a specific test module
pytest tests/test_state_manager.py -v
pytest tests/test_version_intel.py -v
pytest tests/test_linux_rocm.py -v
pytest tests/test_windows_hip.py -v
```

Tests use `pytest-mock` and `responses` for isolation — no real network calls or system modifications are made during testing.

---

## How Reboot Resume Works

When a ROCm driver update requires a reboot:

1. Gillsystems AI Stack Updater writes a **reboot handoff JSON** file (`~/.gillsystems-ai-stack-updater/reboot_handoff.json`) recording the current `run_id` and the next step to execute.
2. Gillsystems AI Stack Updater registers a **resume task**:
   - **Linux:** writes `/etc/systemd/system/gillsystems-ai-stack-updater-resume.service` (one-shot, self-disabling), runs `systemctl enable`.
   - **Windows:** creates `GillsystemsAIStackUpdaterResumeTask` via `schtasks /create /sc ONLOGON /rl HIGHEST`.
3. Gillsystems AI Stack Updater initiates the OS reboot (`shutdown /r` or `systemctl reboot`).
4. After the system boots, the resume task runs Gillsystems AI Stack Updater automatically.
5. Gillsystems AI Stack Updater reads the handoff file, restores the `run_id`, and continues from the saved step.
6. The resume task is unregistered immediately after successful pickup.
7. The handoff file is deleted after the run completes.

---

## Supported Operating Systems

| OS | Version | ROCm Support | Notes |
|---|---|---|---|
| Ubuntu | 22.04 LTS | ✅ Full | Recommended for Linux |
| Ubuntu | 24.04 LTS | ✅ Full | |
| Fedora | 39+ | ✅ Full | Uses `dnf` backend |
| Debian | 12+ | ⚠️ Partial | May need manual repo setup |
| Windows 10 | 22H2+ | ✅ Full | HIP SDK 6.x |
| Windows 11 | Any | ✅ Full | HIP SDK 6.x |
| macOS | Any | ❌ No | AMD ROCm not supported on macOS |

---

## Project Layout

```
Gillsystems-update-ai-engine-software/
├── src/                     # Python source modules
│   ├── linux/               # Linux-specific sub-agents
│   └── windows/             # Windows-specific sub-agents
├── config/
│   └── default_config.yaml  # Default configuration
├── tests/                   # Pytest test suite
│   └── mocks/               # Mock helpers for integration tests
├── conductor/               # 7D Conductor project tracking
│   └── tracks/T-001-agent-core/
├── update-ai-stack.bat      # Windows launcher (UAC elevation)
├── update-ai-stack.sh       # Linux launcher (sudo elevation)
├── requirements.txt         # Runtime dependencies
├── pyproject.toml           # Project metadata + packaging
└── README.md                # This file
```

---

## User Guide

For detailed information on the agent architecture, team composition, configuration, and internal workings, see [UserGuide.md](UserGuide.md).

---

## 💖 Support / Donate

If you find this project helpful, you can support ongoing work — thank you!

<p align="center">
	<img src="Gillsystems_logo_stuff/Readme%20Donation%20files/qr-paypal.png" alt="PayPal QR code" width="180" style="margin:8px;">
	<img src="Gillsystems_logo_stuff/Readme%20Donation%20files/qr-venmo.png" alt="Venmo QR code" width="180" style="margin:8px;">
</p>


**Donate:**

- [![PayPal](https://img.shields.io/badge/PayPal-Donate-009cde?logo=paypal&logoColor=white)](https://paypal.me/gillsystems) https://paypal.me/gillsystems
- [![Venmo](https://img.shields.io/badge/Venmo-Donate-3d95ce?logo=venmo&logoColor=white)](https://venmo.com/Stephen-Gill-007) https://venmo.com/Stephen-Gill-007

---


<p align="center">
	<img src="Gillsystems_logo_stuff/Readme%20Donation%20files/Gillsystems_logo_with_donation_qrcodes.png" alt="Gillsystems logo with QR codes and icons" width="800">
</p>

<p align="center">
	<a href="https://paypal.me/gillsystems"><img src="Gillsystems_logo_stuff/Readme%20Donation%20files/paypal_icon.png" alt="PayPal" width="32" style="vertical-align:middle;"></a>
	<a href="https://venmo.com/Stephen-Gill-007"><img src="Gillsystems_logo_stuff/Readme%20Donation%20files/venmo_icon.png" alt="Venmo" width="32" style="vertical-align:middle;"></a>
</p>
