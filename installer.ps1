Write-Host 'Starting Z-Image Turbo installer...'
Write-Host ''

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install Python 3.10+ from https://python.org and re-run."
    exit 1
}

# 1. Create folders
$root = $PSScriptRoot
$sdBin = Join-Path $root "sd_bin"
$modelsDir = Join-Path $root "models"
$zimageDir = Join-Path $modelsDir "zimage"
$vaeDir = Join-Path $modelsDir "vae"
$llmDir = Join-Path $modelsDir "llm"
$loraDir = Join-Path $modelsDir "loras"
if (!(Test-Path $sdBin)) { New-Item -ItemType Directory -Path $sdBin | Out-Null }
if (!(Test-Path $modelsDir)) { New-Item -ItemType Directory -Path $modelsDir | Out-Null }
if (!(Test-Path $zimageDir)) { New-Item -ItemType Directory -Path $zimageDir | Out-Null }
if (!(Test-Path $vaeDir)) { New-Item -ItemType Directory -Path $vaeDir | Out-Null }
if (!(Test-Path $llmDir)) { New-Item -ItemType Directory -Path $llmDir | Out-Null }
if (!(Test-Path $loraDir)) { New-Item -ItemType Directory -Path $loraDir | Out-Null }

Write-Host 'Project structure was successfully prepared:'
Write-Host (" - sd_bin  : {0}" -f $sdBin)
Write-Host (" - models/zimage  : {0}" -f $zimageDir)
Write-Host (" - models/vae  : {0}" -f $vaeDir)
Write-Host (" - models/llm  : {0}" -f $llmDir)
Write-Host ''

# 2. Ask user about VRAM tier
Write-Host 'Your GPUs and their VRAMs are listed below:'
Get-WmiObject -Class Win32_VideoController | Select-Object Name, AdapterRAM, @{Name="VRAM(GB)";Expression={[math]::Round($_.AdapterRAM/1GB,2)}}
Write-Host ''
Write-Host 'Choose GPU VRAM tier you would like (pick the number):'
Write-Host ' 1) 4 GB  (Fastest, smallest model, with ok quality)'
Write-Host ' 2) 6-8 GB  (Better quality, gold standard)'
Write-Host ' 3) 10+ GB  (Highest quality - only for good video cards)'
Write-Host ''
$choice = Read-Host 'Enter 1, 2 or 3'

switch ($choice) {
    "1" {
        $moshort = "4GB"
        $model_name = "Qwen3-4b-Z-Image-Turbo-AbliteratedV1.Q4_0.gguf"
        $model_url = "https://huggingface.co/BennyDaBall/Qwen3-4b-Z-Image-Turbo-AbliteratedV1/blob/main/Z-Image-AbliteratedV1.Q4_K_S.gguf"
    }
    "2" {
        $moshort = "6-8GB"
        $model_name = "Qwen3-4b-Z-Image-Turbo-AbliteratedV1.Q6_0.gguf"
        $model_url = "https://huggingface.co/BennyDaBall/Qwen3-4b-Z-Image-Turbo-AbliteratedV1/blob/main/Z-Image-AbliteratedV1.Q6_K.gguf"
    }
    "3" {
        $moshort = "10+GB"
        $model_name = "Qwen3-4b-Z-Image-Turbo-AbliteratedV1.Q8_0.gguf"
        $model_url = "https://huggingface.co/BennyDaBall/Qwen3-4b-Z-Image-Turbo-AbliteratedV1/blob/main/Z-Image-AbliteratedV1.Q8_0.gguf"
    }
    default {
        Write-Host "Invalid choice. Please, restart the installer and try again. Exiting."
        exit 1
    }
}

Write-Host ''
Write-Host ("You picked: {0}" -f $moshort)
Write-Host ''

# 3. Create venv (if missing)
$venv = Join-Path $root "venv"
if (!(Test-Path $venv)) {
    Write-Host "Creating Python virtual environment..."
    python -m venv venv
} else {
    Write-Host "Virtual environment already exists (venv/)."
}

# 4. Use venv python directly (avoids PowerShell execution policy issues with Activate.ps1)
$venvPython = Join-Path $venv "Scripts\python.exe"
if (!(Test-Path $venvPython)) {
    Write-Host "ERROR: venv python not found at: $venvPython"
    exit 1
}

# 5. Upgrade pip safely
Write-Host "Upgrading pip..."
& $venvPython -m pip install --upgrade pip

# 6. Install Python deps for minimal UI
Write-Host 'Installing Python requirements (gradio, requests...)...'
& $venvPython -m pip install pil numpy gradio requests tqdm llama-cpp-python

# 7. Check for sd-cli.exe
$sdCliExe = Join-Path $sdBin "sd-cli.exe"

if ((Test-Path $sdCliExe)) {
    Write-Host "Found sd-cli.exe"
    $sdexe = $sdCliExe
} else {
	Write-Host ""
    Write-Host "A stable-diffusion.cpp Windows binary is REQUIRED to run the model."
    Write-Host "Please download from the official stable-diffusion.cpp releases:"
    Write-Host "    https://github.com/leejet/stable-diffusion.cpp/releases"
    Write-Host "You should search for something like: sd-master-*******-bin-win-..."
	Write-Host ""
    Write-Host "If you are using cuda also download cudart-sd from same page."
	Write-Host ""
	Write-Host "Extract everything to this path:"
    Write-Host "    $sdBin"
    Write-Host ""
    Write-Host "Press Enter after you have placed the executable, or Ctrl+C to exit."
    Read-Host
}

if (!(Test-Path $sdexe)) {
    Write-Host "Executable still not found in $sdBin. Please, restart the installer and try again. Exiting."
    exit 1
}

# 7b. Sanity-check executable (common crash is missing DLL / wrong build)
Write-Host "`nChecking executable..."
try {
    & $sdexe --help | Out-Null
} catch {
    # swallow - we will check exit code below
}
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Executable failed to start (exit code: $LASTEXITCODE)."
    Write-Host "This usually means a missing dependency or wrong build." 
    Write-Host "" 
    Write-Host "Please check:" 
    Write-Host " 1) You extracted the release ZIP and copied the executable AND any .dll files into:"
    Write-Host "    $sdBin"
    Write-Host " 2) Microsoft Visual C++ Redistributable 2015-2022 (x64) is installed"
    Write-Host " 3) If you downloaded a CUDA build, your NVIDIA driver supports that CUDA version"
	Write-Host " 4) If you downloaded a CUDA build, make sure you also downloaded cudart-sd and extracted its contents into:"
	Write-Host "    $sdBin"
    Write-Host " 5) Try the CPU-only ZIP (sd-...-bin-win-x64.zip) to confirm it works on your PC"
    Write-Host ""
    Write-Host "Press Enter to exit. Once you fixed the problem, run installer again to continue."
    Read-Host
    exit 1
}

# 8. Download the chosen quantized GGUF model if it does not exist
$dest = Join-Path $zimageDir $model_name
if (Test-Path $dest) {
    Write-Host "Model already exists: $dest"
} else {
    Write-Host "Please download the quantized model manually and place it into:"
	Write-Host "  $dest"
	Write-Host "Source URL:"
    Write-Host "  $model_url`n"
	Write-Host "Then press Enter to continue."
	Read-Host
	if (!(Test-Path $dest)) {
		Write-Host "Model not found. Please, download it and place to mentioned folder and restart the installer. Exiting."
		exit 1
	}
}

# 9. Download VAE + LLM (required by Z-Image pipeline)
$vaeName = "ae.safetensors"
$vaeUrl = "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors"
$vaePath = Join-Path $vaeDir $vaeName

$llmName = "Qwen3VL-8B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
$llmUrl = "https://huggingface.co/HauhauCS/Qwen3VL-8B-Uncensored-HauhauCS-Aggressive/blob/main/Qwen3VL-8B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
$llmPath = Join-Path $llmDir $llmName

if (Test-Path $vaePath) {
    Write-Host "VAE already exists: $vaePath"
} else {
    Write-Host "`nVAE is required but may be restricted for non-logged-in downloads on Hugging Face."
    Write-Host "Please download it manually (login may be required):"
    Write-Host "  $vaeUrl"
    Write-Host "Save it to:"
    Write-Host "  $vaePath"
    Write-Host "`nPress Enter after you have placed ae.safetensors, or Ctrl+C to exit."
    Read-Host
    if (!(Test-Path $vaePath)) {
        Write-Host "VAE not found. Please, download it and place to mentioned folder and restart the installer. Exiting."
        exit 1
    }
}

if (Test-Path $llmPath) {
    Write-Host "LLM already exists: $llmPath"
} else {
    Write-Host "Please download the LLM (Qwen) manually and place it into:"
	Write-Host "  $llmPath"
	Write-Host "Source URL:"
    Write-Host "  $llmUrl`n"
	Write-Host "Then press Enter to continue."
	Read-Host
	if (!(Test-Path $llmPath)) {
		Write-Host "LLM not found. Please, download it and place to mentioned folder and restart the installer. Exiting."
		exit 1
	}
}

$mmprojName = "Qwen3-VL-8B-Instruct-abliterated-v2.mmproj-f16.gguf"
$mmprojUrl = "https://huggingface.co/mradermacher/Qwen3-VL-8B-Instruct-abliterated-v2.0-GGUF/blob/main/Qwen3-VL-8B-Instruct-abliterated-v2.0.mmproj-f16.gguf"
$mmprojPath = Join-Path $llmDir $llmName

if (Test-Path $mmprojPath) {
    Write-Host "MMPROJ already exists: $mmprojPath"
} else {
    Write-Host "Please download MMPROJ manually and place it into:"
    Write-Host "  $mmprojPath"
    Write-Host "Source URL:"
    Write-Host "  $mmprojUrl"
    Write-Host "`nThen press Enter to continue."
    Read-Host
    if (!(Test-Path $mmprojPath)) {
        Write-Host "MMPROJ not found. Please, download it and place to mentioned folder and restart the installer. Exiting."
        exit 1
    }
}

# Create the function to use in powershell
$zimagePath = Join-Path (Get-Location) "Z-Image-Turbo-Unified-Interface"

$functionScript = @"

function imggen {
    `$zimagePath = "$($zimagePath -replace '\\', '\\')"
    
    Set-Location `$zimagePath
    
    `$venvPython = Join-Path `$zimagePath "venv\Scripts\python.exe"
    
    if (Test-Path `$venvPython) {
        Write-Host "Found Python at: `$venvPython"
        Write-Host "Starting Z-Image UI at http://0.0.0.0:9000..."
        
        & `$venvPython (Join-Path `$zimagePath "run_gradio_ui.py")
    } else {
        Write-Host "No python found! Cannot start..."
    }
}
"@

if (-not (Test-Path $PROFILE)) {
    Write-Host "Creating new profile at: $PROFILE"
    New-Item -Path $PROFILE -ItemType File -Force | Out-Null
}

$currentProfile = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue

$functionExists = $currentProfile -match "function imggen\s*\{"


if ($functionExists) {
    Write-Host "`nimggen function already exists in your profile!"
    
    $choice = Read-Host "Do you want to (R) replace it, (S) skip, or (V) view existing function? [R/S/V]"
    
    switch ($choice.ToUpper()) {
        'R' {
            Write-Host "Removing existing imggen function..."
            
            # Remove existing imggen function using regex
            $pattern = '(?s)function imggen\s*\{.*?\n\}'
            $newProfile = $currentProfile -replace $pattern, ''
            
            # Clean up extra blank lines
            $newProfile = $newProfile -replace '(\r?\n){3,}', "`n`n"
            
            # Write back without the function
            Set-Content -Path $PROFILE -Value $newProfile.Trim()
            
            # Append new function
            Add-Content -Path $PROFILE -Value $functionScript
            Write-Host "Replaced imggen function with new version!"
        }
        'S' {
            Write-Host "Skipping - keeping existing imggen function"
        }
        'V' {
            Write-Host "`n=== Existing imggen function ==="
            $currentProfile | Select-String -Pattern '(?s)(function imggen\s*\{.*?\n\})' -AllMatches | 
                ForEach-Object { $_.Matches.Value } | 
                ForEach-Object { Write-Host $_ -ForegroundColor Gray }
            Write-Host "=============================`n"
            
            $confirm = Read-Host "Replace it anyway? [Y/N]"
            if ($confirm.ToUpper() -eq 'Y') {
                # Same replacement logic as 'R' above
                $pattern = '(?s)function imggen\s*\{.*?\n\}'
                $newProfile = $currentProfile -replace $pattern, ''
                $newProfile = $newProfile -replace '(\r?\n){3,}', "`n`n"
                Set-Content -Path $PROFILE -Value $newProfile.Trim()
                Add-Content -Path $PROFILE -Value $functionScript
                Write-Host "Replaced imggen function with new version!"
            } else {
                Write-Host "Keeping existing function"
            }
        }
        default {
            Write-Host "Invalid choice. Please, restart the installer and make a correct choice. Exiting."
            exit 1
        }
    }
} else {
    # No existing function, just append
    Add-Content -Path $PROFILE -Value $functionScript
    Write-Host "Successfully appended imggen function to $PROFILE" -ForegroundColor Green
}

Write-Host "All done! Press any key to close this window"
Read-Host
exit


