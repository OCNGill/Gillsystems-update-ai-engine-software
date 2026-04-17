# Track Plan: T-001-agent-core

## Phase 1: Foundation (Design)
- [x] Analyze requirements and research ROCm/llama.cpp update paths
- [x] Define agent architecture and team roles
- [x] Create implementation plan
- [ ] Finalize GPU target list and install paths (awaiting feedback)

## Phase 2: Core Development (Develop)
- [ ] Implement `state_manager.py` with SQLite persistence
- [ ] Implement `version_intel.py` for GitHub/AMD version checks
- [ ] Implement `gpu_detect.py` for architecture auto-detection
- [ ] Implement `privilege.py` for UAC/sudo elevation
- [ ] Create `main.py` entry point and orchestrator logic

## Phase 3: Sub-Agent Implementation
- [ ] Implement Linux `rocm_updater.py` and `llama_builder.py`
- [ ] Implement Windows `hip_updater.py` and `llama_builder.py`
- [ ] Implement reboot-resume handlers for both OSs

## Phase 4: Integration & UX
- [ ] Implement `cli.py` with Rich output
- [ ] Create `.bat` and `.sh` launchers
- [ ] Perform integrated dry-run testing

## Phase 5: Verification & Delivery (Document/Deliver)
- [ ] Run full update cycles on test machines
- [ ] Document final usage in README.md
- [ ] Prepare final delivery artifacts
