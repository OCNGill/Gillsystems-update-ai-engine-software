# Changelog

All notable changes to the **Gillsystems AI Stack Updater** are documented here per semantic versioning.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.1] — 2026-05-06 — Windows 11 Hardening (Current)

### Added

- **`bootstrap.ps1` — Windows Unicode support**: Sets `$env:PYTHONUTF8 = '1'` and forces `[Console]::OutputEncoding = UTF8` before launching the agent. Prevents Rich box-drawing characters from being mangled by PowerShell 5.1's `Tee-Object` pipe transcoding to OEM cp437.
- **`bootstrap.ps1` — Stderr isolation**: Changed `2>&1 | Tee-Object` to `2>>$logFile | Tee-Object -Append`. This sends httpx INFO/DEBUG logs (which PowerShell 5.1 wraps in red `NativeCommandError` decorations) directly to the log file, keeping the console clean.
- **`src/cli.py` — `PYTHONUTF8` env var**: Sets `os.environ['PYTHONUTF8'] = '1'` at module import time, before any stdio interaction, ensuring Python 3.12+ uses UTF-8 for all I/O on Windows.
- **`src/main.py` — httpx log suppression**: Adds `logging.getLogger('httpx').setLevel(logging.WARNING)` and same for `httpcore` to stop INFO-level HTTP request logs from polluting stderr.
- **`src/windows/hip_updater.py` — HIP SDK 7.x support**: Updated version search list to include `7.2.2` through `7.0.0` (was only `6.x`), updated fallback URL to `7.2.2`, and updated environment scanner to search `ROCm/7.0` through `ROCm/7.3` paths first.
- **`tests/test_version_intel.py` — API failure mock**: Added `HEAD` side-effect mock to cover the HTML redirect fallback path in `_get_latest_llama()`.

### Fixed

- **`bootstrap.ps1` — Duplicate exit block**: Removed duplicated exit-code block at end of file.
- **`tests/test_version_intel.py` — Indentation**: Corrected whitespace corruption in `test_get_latest_llama_success` and `test_get_latest_llama_api_failure` that prevented test collection.

---

## [1.0.0] — 2026-05-06 — Full-Stack Rebrand & Post-MVP Hardening

### Changed

- **Project rename**: GASU → **Gillsystems AI Stack Updater** across all source, config, env vars, systemd services, scheduled tasks, and documentation (commit `b432fe6`).
- **Linux AMD docs compliance** (commit `fba910a`): Switched to AMD's official `ROCm/llama.cpp` fork, set `HIPCXX`/`HIP_PATH` from `hipconfig`, added `-DLLAMA_CURL=ON`, widened GPU target list. Default targets: `gfx1100;gfx1101;gfx1102;gfx1030;gfx1031;gfx1032;gfx1033;gfx906`.
- **Windows repo split** (commit `fba910a`): Windows uses `ggml-org/llama.cpp` (no AMD native Windows build docs), config now has `llama_cpp_repo` (Linux) / `llama_cpp_repo_windows`.

### Added

- **`bootstrap.ps1`**: Self-contained PowerShell first-run bootstrap script. Auto-finds Python 3.11–3.14 via `py` launcher, PATH, or common install paths; downloads and silently installs Python 3.12.9 if none found; upgrades pip; installs requirements; launches agent with `Tee-Object` logging. Always keeps console window open on error (commit `6f6457c`).
- **`--force` clean-build** (commit `fc85951`): Nukes CMake cache directory before configure — fixes stale HIP SDK link pollution. Also renames locked `.exe` files to `.exe.old` before `cmake --install`.
- **GPU targets**: `gfx906` (Vega 20 / Radeon VII) and `gfx1033` (Steam Deck Van Gogh APU) added to default target list.
- **`version_intel.py`**: GitHub rate-limit fallback via HTML redirect; `GITHUB_TOKEN` env var support; `needs_update=True` when component is not installed (commit `b3e18ee`).

### Fixed

- **Version table rendering** (commit `b3e18ee`): Replaced plain-text version cell with `Text.from_markup()` so Rich markup styling renders correctly.
- **Windows bootstrap UX** (commit `6f6457c`): `update-ai-stack.bat` rewritten as thin wrapper — no longer closes cmd window immediately.
- **Version check logic** (commit `b3e18ee`): Null-installed components now correctly report `installed=None` without false comparisons.
- **ROCm 7.x path detection** (commit `fc85951`): Added ROCm 7.0–7.3 to `_find_hip_path()` candidate list.

---

## [0.9.0] — 2026-04-29 — Tier 1/2 Architecture & Hardware Profiling

### Added

- **Tier-based hardware profiling** (commit `209fe27`): Tier 1 (full HIP/ROCm) vs Tier 2 (Vulkan + HIP UMA) detection. Flash Attention support (`GGML_HIP_ROCWMMA_FATTN=ON`). UMA memory controls for integrated GPUs.
- **Bleeding-edge mode** (commit `baf4f54`): `--bleeding-edge` flag compiles from `master` branch for zero-day GGML tensor format support (e.g. Gemma 4 CoT, sliding window attention).
- **Vulkan fallback** (commit `baf4f54`): Tier 2 machines (iGPUs, Steam Deck) get `GGML_VULKAN=ON` as compile backend when native HIP is unavailable.
- **Tier enforcement**: Launcher enforces minimum ROCm/llama.cpp versions per hardware tier.

---

## [0.8.0] — 2026-04-29 — Full-Stack Implementation (MVP)

### Added

- **Core orchestrator** (`main.py`): State machine with SQLite checkpoint ledger, reboot-resilient resume.
- **Version intelligence** (`version_intel.py`): Checks GitHub API for llama.cpp releases, AMD repo for ROCm versions.
- **GPU architecture detection** (`gpu_detect.py`): `rocminfo`/sysfs on Linux, WMI/`hipInfo` on Windows.
- **Privilege management** (`privilege.py`): UAC elevation (Windows) and `sudo` detection (Linux).
- **Rich terminal UI** (`cli.py`): Colored output, progress bars, dry-run warnings, summary tables.
- **Linux sub-agent** (`linux/rocm_updater.py`, `linux/llama_builder.py`, `linux/reboot_handler.py`): `amdgpu-install` automation, CMake+HIP llama.cpp build, systemd one-shot resume service.
- **Windows sub-agent** (`windows/hip_updater.py`, `windows/llama_builder.py`, `windows/reboot_handler.py`): HIP SDK silent installer, Visual Studio Build Tools + Ninja build, Scheduled Task resume.
- **Configuration** (`config.py`, `config/default_config.yaml`): Pydantic models, YAML loader, env var support.
- **Cross-platform launchers**: `update-ai-stack.bat` (Windows) and `update-ai-stack.sh` (Linux).
- **Test suite**: 59 unit tests across 4 test modules with isolation mocks.
- **Project scaffolding**: `pyproject.toml`, `requirements.txt`, `.gitignore`, `__init__.py`.

---

## [0.0.1] — 2026-04-16 — Initial Concept

### Added

- Agent architecture defined.
- Conductor files established: `conductor/index.md`, `product.md`, `tech-stack.md`, `tracks.md`, `workflow.md`, `setup_state.json`.
- Track T-001-agent-core created with spec and plan.
- `conductor/product-guidelines.md` — quality gates and standards.

---

## Legend

- `[1.0.1]` — Current release on `main`.
- Releases follow semantic versioning — breaking changes bump major, features bump minor, fixes bump patch.
