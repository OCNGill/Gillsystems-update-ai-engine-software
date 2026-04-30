"""
gpu_detect.py — Auto-detects AMD GPU architecture for AMDGPU_TARGETS.

Linux:  parses rocminfo, /sys/class/drm, or lspci
Windows: queries WMI or hipInfo
"""
from __future__ import annotations

import re
import subprocess
import sys
from typing import List, Optional


# Map of common AMD GPU product names → gfx architecture IDs
_PRODUCT_TO_GFX: dict[str, str] = {
    # RDNA 3 (GFX11)
    "RX 7900 XTX": "gfx1100",
    "RX 7900 XT":  "gfx1100",
    "RX 7900 GRE": "gfx1100",
    "RX 7800 XT":  "gfx1101",
    "RX 7700 XT":  "gfx1101",
    "RX 7600":     "gfx1102",
    # RDNA 2 (GFX10)
    "RX 6950 XT":  "gfx1030",
    "RX 6900 XT":  "gfx1030",
    "RX 6800 XT":  "gfx1030",
    "RX 6800":     "gfx1030",
    "RX 6750 XT":  "gfx1031",
    "RX 6700 XT":  "gfx1031",
    "RX 6700":     "gfx1031",
    "RX 6650 XT":  "gfx1032",
    "RX 6600 XT":  "gfx1032",
    "RX 6600":     "gfx1032",
    "RX 6500 XT":  "gfx1034",
    "RX 6400":     "gfx1034",
    # Steam Deck / Van Gogh APU (RDNA 2)
    "AMD Custom GPU 0405": "gfx1033",
    # Mobile APUs / Vega
    "Radeon Vega": "gfx90c",
    "AMD Radeon Graphics": "gfx1036",  # General fallback for modern mobile APUs
    # RDNA 1 (GFX10)
    "RX 5700 XT":  "gfx1010",
    "RX 5700":     "gfx1010",
    "RX 5600 XT":  "gfx1012",
    "RX 5500 XT":  "gfx1012",
    # Fallback
    "Radeon PRO W7900": "gfx1100",
}

# Fallback default when detection fails
DEFAULT_TARGETS: List[str] = ["gfx1100", "gfx1030"]


def get_compute_tier(targets: List[str]) -> int:
    """
    Returns 1 for Production-Grade GPUs (MUST use ROCm/HIP).
    Returns 2 for Mobile/Edge APUs (allowed Vulkan fallback, needs UMA).
    """
    tier_1 = {"gfx1100", "gfx1101", "gfx1102", "gfx1030", "gfx1031", "gfx1032"}
    for t in targets:
        if t in tier_1:
            return 1
    return 2


class GPUDetector:
    """Detects AMD GPU architecture and returns AMDGPU_TARGETS list."""

    def detect(self) -> List[str]:
        """
        Attempt GPU detection.  Returns a deduplicated list of gfx IDs.
        Falls back to DEFAULT_TARGETS if detection fails.
        """
        targets: List[str] = []

        if sys.platform == "linux":
            targets = self._detect_linux()
        elif sys.platform == "win32":
            targets = self._detect_windows()

        if not targets:
            return DEFAULT_TARGETS

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: List[str] = []
        for t in targets:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        return unique

    def detect_primary(self) -> str:
        """Return just the first (primary) GPU target."""
        return self.detect()[0]

    # ------------------------------------------------------------------
    # Linux detection
    # ------------------------------------------------------------------

    def _detect_linux(self) -> List[str]:
        strategies = [
            self._linux_via_rocminfo,
            self._linux_via_sys_drm,
            self._linux_via_lspci,
        ]
        for fn in strategies:
            result = fn()
            if result:
                return result
        return []

    def _linux_via_rocminfo(self) -> List[str]:
        try:
            out = subprocess.run(
                ["rocminfo"],
                capture_output=True, text=True, timeout=15
            ).stdout
            # Look for lines like: "Name: gfx1100"
            gfx_ids = re.findall(r"gfx\d{3,4}", out)
            return sorted(set(gfx_ids))
        except Exception:
            return []

    def _linux_via_sys_drm(self) -> List[str]:
        """Parse /sys/class/drm/card*/device/uevent for AMDGPU entries."""
        import glob
        targets: List[str] = []
        for uevent_path in glob.glob("/sys/class/drm/card*/device/uevent"):
            try:
                content = open(uevent_path).read()
                # DRIVER=amdgpu  and  PCI_ID=1002:xxxx
                if "amdgpu" not in content.lower():
                    continue
                match = re.search(r"PCI_ID=\w+:(\w{4})", content)
                if match:
                    pci_device_id = match.group(1).upper()
                    gfx = _pci_id_to_gfx(pci_device_id)
                    if gfx:
                        targets.append(gfx)
            except OSError:
                continue
        return targets

    def _linux_via_lspci(self) -> List[str]:
        try:
            out = subprocess.run(
                ["lspci", "-nn"],
                capture_output=True, text=True, timeout=10
            ).stdout
            targets: List[str] = []
            for line in out.splitlines():
                if "AMD" not in line and "Radeon" not in line:
                    continue
                for product, gfx in _PRODUCT_TO_GFX.items():
                    if product.upper() in line.upper():
                        targets.append(gfx)
            return targets
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Windows detection
    # ------------------------------------------------------------------

    def _detect_windows(self) -> List[str]:
        strategies = [
            self._windows_via_wmi,
            self._windows_via_hipinfo,
        ]
        for fn in strategies:
            result = fn()
            if result:
                return result
        return []

    def _windows_via_wmi(self) -> List[str]:
        try:
            import wmi  # type: ignore[import]
            c = wmi.WMI()
            targets: List[str] = []
            for gpu in c.Win32_VideoController():
                name: str = gpu.Name or ""
                if "AMD" not in name.upper() and "RADEON" not in name.upper():
                    continue
                for product, gfx in _PRODUCT_TO_GFX.items():
                    if product.upper() in name.upper():
                        targets.append(gfx)
                        break
                else:
                    # Try to extract gfx from driver description
                    match = re.search(r"gfx\d{3,4}", name, re.IGNORECASE)
                    if match:
                        targets.append(match.group(0).lower())
            return targets
        except Exception:
            return []

    def _windows_via_hipinfo(self) -> List[str]:
        try:
            out = subprocess.run(
                ["hipInfo"],
                capture_output=True, text=True, timeout=15
            ).stdout + subprocess.run(
                ["hipInfo"],
                capture_output=True, text=True, timeout=15
            ).stderr
            gfx_ids = re.findall(r"gfx\d{3,4}", out)
            return list(set(gfx_ids))
        except Exception:
            return []


# ---------------------------------------------------------------------------
# PCI device ID → gfx lookup table (partial, covers common consumer GPUs)
# ---------------------------------------------------------------------------

_PCI_TO_GFX: dict[str, str] = {
    # RDNA 3 (gfx1100)
    "744C": "gfx1100",  # RX 7900 XTX
    "7480": "gfx1100",  # RX 7900 XT
    "7448": "gfx1100",  # RX 7900 GRE
    # RDNA 3 (gfx1101)
    "747E": "gfx1101",  # RX 7800 XT
    "7470": "gfx1101",  # RX 7700 XT
    # RDNA 3 (gfx1102)
    "7422": "gfx1102",  # RX 7600
    # RDNA 2 (gfx1030)
    "73BF": "gfx1030",  # RX 6950 XT / 6900 XT
    "73A5": "gfx1030",  # RX 6800 XT
    "73AB": "gfx1030",  # RX 6800
    # RDNA 2 (gfx1031)
    "73DF": "gfx1031",  # RX 6750 XT / 6700 XT
    "73E1": "gfx1031",  # RX 6700
    # RDNA 2 (gfx1032)
    "73FF": "gfx1032",  # RX 6650 XT / 6600 XT / 6600
}


def _pci_id_to_gfx(pci_device_id: str) -> Optional[str]:
    return _PCI_TO_GFX.get(pci_device_id.upper())
