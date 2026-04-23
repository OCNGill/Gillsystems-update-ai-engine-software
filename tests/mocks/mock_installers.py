"""
mocks/mock_installers.py — Fake installer scripts for dry-run testing.

These simulate the behaviour of amdgpu-install and HIP SDK installer
without touching the real system.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


MOCK_AMDGPU_INSTALL_SCRIPT = """\
#!/usr/bin/env bash
# Mock amdgpu-install — simulates a successful ROCm installation
echo "amdgpu-install mock: Installing ROCm..."
echo "AMD ROCm 6.3.1 installed successfully."
exit 0
"""

MOCK_AMDGPU_INSTALL_REBOOT_SCRIPT = """\
#!/usr/bin/env bash
# Mock amdgpu-install — simulates a kernel driver update requiring reboot
echo "amdgpu-install mock: Installing kernel module..."
echo "Updated kernel module. Please reboot to complete installation."
exit 0
"""

MOCK_ROCM_SMI_SCRIPT = """\
#!/usr/bin/env bash
# Mock rocm-smi — returns a fake version string
echo "ROCm System Management Interface (RSMI) version: 6.3.1"
exit 0
"""

MOCK_HIPCC_SCRIPT = """\
#!/usr/bin/env bash
# Mock hipcc -- version
echo "HIP version: 6.3.42134-d03a1fdef"
exit 0
"""

MOCK_LLAMA_CLI_SCRIPT = """\
#!/usr/bin/env bash
# Mock llama-cli -- version
echo "version: 3682 (abc1234f)"
exit 0
"""


def create_mock_binaries(target_dir: Path) -> None:
    """
    Create mock executable scripts in target_dir for testing.

    Call this in test setup to create fake system commands.
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    scripts = {
        "amdgpu-install": MOCK_AMDGPU_INSTALL_SCRIPT,
        "rocm-smi": MOCK_ROCM_SMI_SCRIPT,
        "hipcc": MOCK_HIPCC_SCRIPT,
        "llama-cli": MOCK_LLAMA_CLI_SCRIPT,
        "rocminfo": "#!/usr/bin/env bash\necho 'gfx1100'\nexit 0\n",
    }

    for name, content in scripts.items():
        script_path = target_dir / name
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(0o755)
