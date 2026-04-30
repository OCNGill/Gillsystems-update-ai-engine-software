# Repository Analysis: Bullet-Proofing AMD Builds for Modern Models

**Phase:** Define → Design  
**Track:** T-001-agent-core  
**Objective:** Top-down analysis of the Gillsystems AI Stack Updater to ensure state-of-the-art, failure-proof ROCm/HIP compilation of `llama.cpp` for the most modern models.

---

## Agent 1: Lead Architect (System Orchestration & State)
**Analysis:** 
The architecture must distinguish between "Production-Grade" GPU nodes (HTPC/Main with 7000 series) and "Mobile/Edge" nodes (Laptop/Steam Deck). Success is defined by maximizing the hardware potential, not just getting a successful exit code.
**Improvements & Iterations:**
- **Hardware-Specific Backend Selection:** The agent must identify the machine. For 7000 series GPUs (HTPC/Main), it MUST enforce a successful ROCm/HIP build. No fallback to CPU or Vulkan is permitted on these high-performance targets.
- **Manual Quality Gate:** Remove automated test model downloads. The system will provide a "Ready for Commander Testing" status upon successful compilation, deferring final validation to the human authority.

---

## Agent 2: Hardware / AMD Specialist (Architecture & Compatibility)
**Analysis:**
The 7000 series (RDNA 3) requires absolute precision in ROCm/HIP targeting to ensure modern models (Llama 3, DeepSeek) utilize hardware acceleration. Mobile and APU targets (Laptop/Steam Deck) have narrower bandwidth and are suited for Vulkan if HIP fails.
**Improvements & Iterations:**
- **Tiered Build Logic:** 
    - **Tier 1 (HTPC/Main):** Enforce `gfx1100` targets with mandatory ROCm 7.x libraries. Failure to link HIP is a hard failure for the agent.
    - **Tier 2 (Laptop/Steam Deck):** Attempt HIP first, but allowed to default to the Vulkan backend to ensure usability on diverse mobile RDNA 2/3 variants.
- **UMA Flag Injection:** For APUs, automatically set `LLAMA_HIP_UMA=1` (or equivalent Vulkan memory flags) to prevent VRAM allocation failures on shared system memory.

---

## Agent 3: Build & Compilers Expert (CMake & Performance)
**Analysis:**
The base `CMake` commands lack the aggressive optimization flags required for modern, long-context models. Flash Attention is critical for Llama 3 context windows but must be explicitly enabled at compile time.
**Improvements & Iterations:**
- **Mandatory CMake Flags:** Ensure the build pipeline injects:
  - `-DGGML_HIP=ON` (Core ROCm integration)
  - `-DGGML_HIP_ROCWMMA_FATTN=ON` (Enables `rocWMMA` library for Flash Attention acceleration, vital for 8k+ context).
  - `-DCMAKE_BUILD_TYPE=Release`
- **Concurrency Control:** Build scripts must calculate `$(nproc) - 1` to prevent system lockups during ninja/make execution on lower-end systems.

---

## Agent 4: OS Integration Engineer (Windows vs. Linux Parity)
**Analysis:**
Linux has direct `amdgpu-install` pipelines and native Docker ROCm environments. Windows relies on the HIP SDK, which frequently trails Linux in library updates and path configurations.
**Improvements & Iterations:**
- **Windows HIP SDK Path Injection:** Windows builds frequently fail because CMake cannot locate the HIP SDK. The agent must proactively locate `%HIP_PATH%` and pass it directly to the CMake configure step via `-DHIP_ROOT_DIR`.
- **Dependencies Verification:** On Windows, the agent must enforce the presence of Visual Studio Build Tools (MSVC) before attempting the `llama.cpp` compile, stopping cleanly if missing rather than throwing cryptic CMake errors.

---

## Agent 5: AI Models Analyst (Model Compatibility & GGUF)
**Analysis:**
To run the most recent models (Llama 3, DeepSeek MoE), the build must prioritize the latest GGML kernels and Flash Attention. The human operator (Commander) handles validation, so the agent's focus is purely on "Successful Deployment of Infrastructure."
**Improvements & Iterations:**
- **Rolling Release Focus:** Always check the `llama.cpp` master branch for the latest architectural support. Use the `--bleeding-edge` flag by default for the HTPC/Main machines to ensure zero-day model support.
- **No Automated Launch Generation:** The agent will not generate any test scripts, launch parameters, or text files. The Commander will handle all testing and execution directly.
