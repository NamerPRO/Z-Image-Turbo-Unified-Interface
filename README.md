# Z-Image Turbo - One-Click Windows Installer + Userfriendly Advanced UI
## Supports even low VRAM: from 4GB

![logo of repository](./logo.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows)](https://www.microsoft.com/windows)
[![Built with Gradio](https://img.shields.io/badge/Built%20with-Gradio-FFD21F?logo=gradio)](https://gradio.app)
[![Low VRAM Support](https://img.shields.io/badge/VRAM-4GB+-green)](https://github.com/leejet/stable-diffusion.cpp)

A beginner-friendly Windows package to run **Z-Image Turbo (GGUF)** locally with an advanced **Gradio Web UI**.

**Target users:**

- Low-VRAM NVIDIA GPUs (including 4GB)
- Anyone who wants free local image generation without complex tools

## Requirements

- Windows 10/11 (64-bit)
- Python 3.10+
- Microsoft Visual C++ Redistributable 2015-2022 (x64)
- NVIDIA GPU users (optional)
  - Latest NVIDIA driver recommended

## Quickstart

1. Run `git clone https://github.com/NamerPRO/Z-Image-Turbo-Unified-Interface.git` in powershell.
2. Switch to Z-Image-Turbo-Unified-Interface folder: `cd .\Z-Image-Turbo-Unified-Interface\`.
3. Double click `installer.bat` and follow its instructions.
4. Press enter to close your powershell window.
5. Congradulations! Type `imggen` in new powershell instance open `http://localhost:9000` and you are ready to go.

**No tricks:** This installer will never perform any network operations. Instead it will tell you what to download and where to put it so it works. Provided links are going to be to trusted platfolrms `huggingface.co` and `github.com` only. Stay absolutely safe. See below what you are going to be asked to download.


## What the installer asks to download
### (to-do, not actual information yet, please, see setup manually)

Automatic (safe, non-executable downloads):

- Z-Image Turbo GGUF (diffusion model)
- Qwen GGUF (LLM/text encoder)

Manual:

- stable-diffusion.cpp backend files:
  - Current NVIDIA build: `sd-cli.exe`, `sd-server.exe`, `stable-diffusion.dll`
  - CUDA runtime DLLs from `cudart-sd-bin-win-cu12-x64.zip`
  - Legacy builds: `sd.exe`
- VAE: `models\vae\ae.safetensors`
  - This file may require a Hugging Face login, so the installer asks you to download it manually.

Manual download sources:

- Z-Image Turbo GGUF:
  - https://huggingface.co/leejet/Z-Image-Turbo-GGUF/tree/main
- VAE (`ae.safetensors`):
  - https://huggingface.co/black-forest-labs/FLUX.1-schnell/tree/main
- Qwen GGUF:
  - https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/tree/main

## Credits / Upstream

This project is a Windows-friendly wrapper around the excellent **stable-diffusion.cpp** backend:

- https://github.com/leejet/stable-diffusion.cpp

Z-Image weights and related resources are hosted on Hugging Face by their respective authors.

