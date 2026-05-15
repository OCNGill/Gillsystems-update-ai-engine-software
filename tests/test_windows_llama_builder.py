from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import GillsystemsAIStackUpdaterConfig, load_config
from src.windows import llama_builder as windows_llama_builder
from src.windows.llama_builder import LlamaBuilderWindows


def _make_cfg(tmp_path: Path) -> GillsystemsAIStackUpdaterConfig:
    cfg = load_config()
    cfg.behavior.dry_run = False
    cfg.behavior.force = False
    cfg.paths.llama_cpp_source = str(tmp_path / "llama.cpp")
    cfg.paths.llama_cpp_install_windows = str(tmp_path / "install")
    return cfg


def _fake_which(hip_root: Path):
    def _inner(tool: str) -> str | None:
        if tool == "hipcc":
            return str(hip_root / "bin" / "hipcc.exe")
        return None

    return _inner


def test_configure_cmake_disables_rocwmma_when_header_missing(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder._use_ninja = True

    hip_root = tmp_path / "rocm"
    (hip_root / "bin").mkdir(parents=True)

    captured: list[list[str]] = []

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._run", side_effect=lambda cmd, timeout=3600, env=None: captured.append(cmd)):
        builder._configure_cmake()

    assert captured
    assert "-DGGML_HIP_ROCWMMA_FATTN=OFF" in captured[0]
    assert "-DGGML_HIP_ROCWMMA_FATTN=ON" not in captured[0]


def test_configure_cmake_enables_rocwmma_when_header_exists(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])
    builder._use_ninja = True

    hip_root = tmp_path / "rocm"
    header = hip_root / "include" / "rocwmma" / "rocwmma-version.hpp"
    header.parent.mkdir(parents=True)
    header.write_text("// stub header\n", encoding="ascii")
    (hip_root / "bin").mkdir(parents=True, exist_ok=True)

    captured: list[list[str]] = []

    with patch("src.windows.llama_builder.shutil.which", side_effect=_fake_which(hip_root)), \
         patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder._run", side_effect=lambda cmd, timeout=3600, env=None: captured.append(cmd)):
        builder._configure_cmake()

    assert captured
    assert "-DGGML_HIP_ROCWMMA_FATTN=ON" in captured[0]


def test_bundle_hip_runtime_libraries_copies_matching_dlls(tmp_path: Path) -> None:
    hip_root = tmp_path / "rocm"
    hip_bin = hip_root / "bin"
    hip_bin.mkdir(parents=True)

    for dll_name in ("libhipblas.dll", "rocblas.dll", "amdhip64_7.dll"):
        (hip_bin / dll_name).write_text("stub\n", encoding="ascii")
    (hip_bin / "clang.dll").write_text("stub\n", encoding="ascii")

    install_bin = tmp_path / "install" / "bin"

    copied = windows_llama_builder._bundle_hip_runtime_libraries(str(hip_root), install_bin)

    assert copied == 3
    assert (install_bin / "libhipblas.dll").exists()
    assert (install_bin / "rocblas.dll").exists()
    assert (install_bin / "amdhip64_7.dll").exists()
    assert not (install_bin / "clang.dll").exists()


def test_validate_uses_runtime_dirs_and_skips_failed_exit_codes(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    builder = LlamaBuilderWindows(cfg, ["gfx1100"])

    install_bin = Path(cfg.paths.llama_cpp_install_windows) / "bin"
    install_bin.mkdir(parents=True)
    (install_bin / "llama-cli.exe").write_text("stub\n", encoding="ascii")
    (install_bin / "llama-server.exe").write_text("stub\n", encoding="ascii")

    hip_root = tmp_path / "rocm"
    (hip_root / "bin").mkdir(parents=True)

    calls: list[tuple[list[str], dict]] = []
    results = [
        MagicMock(returncode=126, stdout="", stderr="libhipblas.dll missing"),
        MagicMock(returncode=0, stdout="llama-server build 1\n", stderr=""),
    ]

    def _fake_run(cmd: list[str], **kwargs):
        calls.append((cmd, kwargs))
        return results[len(calls) - 1]

    with patch("src.windows.llama_builder._find_hip_path", return_value=str(hip_root)), \
         patch("src.windows.llama_builder.subprocess.run", side_effect=_fake_run):
        builder._validate()

    assert len(calls) == 2
    assert calls[0][0][0].endswith("llama-cli.exe")
    assert calls[1][0][0].endswith("llama-server.exe")

    runtime_path = calls[0][1]["env"]["PATH"].split(";")
    assert runtime_path[0] == str(install_bin)
    assert str(hip_root / "bin") in runtime_path