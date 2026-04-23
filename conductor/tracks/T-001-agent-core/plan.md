# Track Plan: T-001-agent-core

## Phase 1: Foundation (Design)
- [x] Analyze requirements and research ROCm/llama.cpp update paths
- [x] Define agent architecture and team roles
- [x] Create implementation plan
- [x] Finalize GPU target list and install paths (defaults set in config/default_config.yaml)

## Phase 2: Core Development (Develop)
- [x] Implement `state_manager.py` with SQLite persistence
- [x] Implement `version_intel.py` for GitHub/AMD version checks
- [x] Implement `gpu_detect.py` for architecture auto-detection
- [x] Implement `privilege.py` for UAC/sudo elevation
- [x] Implement `config.py` with Pydantic models and YAML loader
- [x] Implement `cli.py` with Rich terminal UI
- [x] Create `main.py` entry point and orchestrator logic

## Phase 3: Sub-Agent Implementation
- [x] Implement Linux `rocm_updater.py` and `llama_builder.py`
- [x] Implement Linux `reboot_handler.py` (systemd one-shot)
- [x] Implement Windows `hip_updater.py` and `llama_builder.py`
- [x] Implement Windows `reboot_handler.py` (Scheduled Task)

## Phase 4: Integration & UX
- [x] Implement `cli.py` with Rich output
- [x] Create `.bat` and `.sh` launchers
- [x] Create config/default_config.yaml
- [x] Create requirements.txt and pyproject.toml

## Phase 5: Testing (QA)
- [x] test_version_intel.py — Version detection unit tests
- [x] test_state_manager.py — SQLite checkpoint tests
- [x] test_linux_rocm.py — Linux sub-agent unit tests
- [x] test_windows_hip.py — Windows sub-agent unit tests
- [x] tests/mocks/mock_installers.py — Mock binary helpers

## Phase 6: Verification & Delivery (Document/Deliver)
- [x] Document usage in README.md
- [ ] Full live run on test Linux machine
- [ ] Full live run on test Windows machine
- [ ] Tag v1.0.0 release
