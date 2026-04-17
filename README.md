<p align="center">
  <img src="Gillsystems_logo_stuff/Gill%20Systems%20Logo.png" alt="Gill Systems Logo" width="800">
</p>

# Gillsystems Update AI Engine Software

Welcome to the **Gillsystems AI Stack Updater (GASU)**. This project is a portable, invocation-only Python agent designed to keep your AMD consumer GPU AI stack (ROCm/HIP and llama.cpp) up-to-date across both Windows and Linux, without any of the manual headaches.

## 🚀 Overview

Keeping ROCm/HIP and llama.cpp up to date on AMD consumer GPUs usually involves dealing with a deep dependency chain (kernel drivers → `amdgpu` → ROCm runtime → HIP → rocBLAS → hipBLAS → llama.cpp with `GGML_HIP`) and sparse official tooling. 

**GASU** solves this by providing a single command that:
1. Detects your current software versions against the upstream stable releases.
2. Downloads, compiles (if needed), and installs new versions automatically.
3. Fully handles any necessary OS reboots, gracefully saving its state to resume immediately after start-up.

## 📖 User Guide

For detailed information on the agent architecture, team composition, configuration, and internal workings, check out our [User Guide](UserGuide.md).

## 🛠️ Key Features
- **Smart Detection:** Automatically checks GitHub Releases API and AMD repositories.
- **Dual-OS Sub-Agents:** Handles `amdgpu-install` for Linux and silent HIP SDK installs on Windows.
- **Robust llama.cpp Building:** Automatically clones the latest branches, auto-detects GPU architecture (e.g. `gfx1030`, `gfx1100`), and builds against HIP.
- **Reboot Resilience:** Safely checkpoints progress to disk, establishes startup tasks, and automatically resumes after intermediate driver installation reboots.
- **Strictly Invocation-Only:** Does absolutely nothing unless explicitly run via our `.bat` (Windows) or `.sh` (Linux) launchers.
- **Safe Elevated Runs:** Intelligently checks and requests `sudo` on Linux and Administrator (UAC) on Windows to fulfill driver-level operations.

---

## 💖 Support / Donate

If you find this project helpful, you can support ongoing work — thank you!

<p align="center">
	<img src="Gillsystems_logo_stuff/Readme%20Donation%20files/qr-paypal.png" alt="PayPal QR code" width="180" style="margin:8px;">
	<img src="Gillsystems_logo_stuff/Readme%20Donation%20files/qr-venmo.png" alt="Venmo QR code" width="180" style="margin:8px;">
</p>


**Donate:**

- [![PayPal](https://img.shields.io/badge/PayPal-Donate-009cde?logo=paypal&logoColor=white)](https://paypal.me/gillsystems) https://paypal.me/gillsystems
- [![Venmo](https://img.shields.io/badge/Venmo-Donate-3d95ce?logo=venmo&logoColor=white)](https://venmo.com/Stephen-Gill-007) https://venmo.com/Stephen-Gill-007

---


<p align="center">
	<img src="Gillsystems_logo_stuff/Readme%20Donation%20files/Gillsystems_logo_with_donation_qrcodes.png" alt="Gillsystems logo with QR codes and icons" width="800">
</p>

<p align="center">
	<a href="https://paypal.me/gillsystems"><img src="Gillsystems_logo_stuff/Readme%20Donation%20files/paypal_icon.png" alt="PayPal" width="32" style="vertical-align:middle;"></a>
	<a href="https://venmo.com/Stephen-Gill-007"><img src="Gillsystems_logo_stuff/Readme%20Donation%20files/venmo_icon.png" alt="Venmo" width="32" style="vertical-align:middle;"></a>
</p>
