# Product Definition — Gillsystems AI Stack Updater Agent

## Mission
Provide a single-invocation, fully autonomous agent that detects, downloads, builds, and installs the latest stable releases of **ROCm/HIP** (and all dependencies) and **llama.cpp** (compiled against the installed ROCm) — across both **Windows** and **Linux** — on AMD consumer GPU hardware.

## Core Value
Eliminates the painful, error-prone manual process of keeping the AMD AI software stack current on consumer hardware where official tooling is sparse and the dependency graph is deep.

## Target User
Stephen (Commander) — running AMD consumer GPUs (RDNA 2/3) across multiple machines.

## Key Capabilities
1. **Version Detection** — Checks currently installed versions vs. latest upstream releases.
2. **Automated Update** — Downloads, compiles (if needed), and installs new versions.
3. **Reboot Resilience** — Survives reboots mid-update, resumes exactly where it left off.
4. **Dual-OS** — Separate sub-agents for Windows and Linux with shared core logic.
5. **Dual-Target** — ROCm/HIP stack + llama.cpp, each as independent update routines.
6. **Invocation-Only** — Does nothing unless explicitly launched via `.bat` / `.sh`.
7. **Admin/Sudo** — Runs with elevated privileges for driver/kernel-level installs.
