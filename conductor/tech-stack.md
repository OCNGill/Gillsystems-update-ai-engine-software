# Tech Stack

## Runtime
- **Python 3.11+** — Agent core
- **SQLite** — State persistence / progress ledger
- **JSON** — Config and checkpoint files

## Dependencies (Python)
- `httpx` — Async HTTP for GitHub API / AMD repo checks
- `rich` — Terminal UI / progress bars
- `pydantic` — Config and state validation
- `packaging` — Version comparison

## Build Tools (Targets)
- **ROCm 7.x** — `amdgpu-install` (Linux), HIP SDK installer (Windows)
- **llama.cpp** — CMake + HIP/ROCm backend

## OS Targets
- **Linux:** Ubuntu 22.04 / 24.04 (primary), Fedora (secondary)
- **Windows:** Windows 10/11 with HIP SDK support
