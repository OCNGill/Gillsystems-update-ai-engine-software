# Track Spec: T-001-agent-core

## Objective
Establish the foundational architecture, state management, and cross-platform sub-agent orchestration for the Gillsystems AI Stack Updater.

## Scope
- Core Orchestrator (`main.py`)
- State Management (`state_manager.py`)
- Version Intelligence (`version_intel.py`)
- Privilege Management (`privilege.py`)
- GPU Detection (`gpu_detect.py`)
- Linux & Windows Sub-agent interfaces

## Dependencies
- Python 3.11+
- SQLite
- httpx, rich, pydantic
- amdgpu-install (Linux)
- HIP SDK (Windows)

## Constraints
- Must be reboot-resilient.
- Must be idempotent.
- Must handle consumer AMD GPUs.
