if (Test-Path "no_gpu.flag") { 
    Remove-Item "no_gpu.flag"
    $skipGPU = $true
} else {
    $skipGPU = $false
}

Write-Host 'Starting Z-Image Turbo installer...'
Write-Host ''

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install Python 3.10+ from https://python.org and re-run." -ForegroundColor Red
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

Write-Host 'Project structure was successfully prepared:' -ForegroundColor Green
Write-Host (" - sd_bin  : {0}" -f $sdBin) -ForegroundColor Green
Write-Host (" - models/zimage  : {0}" -f $zimageDir) -ForegroundColor Green
Write-Host (" - models/vae  : {0}" -f $vaeDir) -ForegroundColor Green
Write-Host (" - models/llm  : {0}" -f $llmDir) -ForegroundColor Green
Write-Host ''

# 2. Ask user about VRAM tier
if (-not $skipGPU) {
	Write-Host 'Loading your GPUs information. This may take a while...'
	Write-Host "(To ommit this check run installer with --no-gpu-fetch flag)`n"

	$tempFile = "$env:TEMP\dxdiag_$((Get-Date).Ticks).txt"

	try {
		# Run dxdiag
		$p = Start-Process "dxdiag" -ArgumentList "/t `"$tempFile`"" -NoNewWindow -PassThru -Wait
		Start-Sleep -Seconds 3
		
		if (Test-Path $tempFile) {
			$content = Get-Content $tempFile -Raw
			$lines = $content -split "`r?`n"
			
			$currentCard = $null
			
			for ($i = 0; $i -lt $lines.Count; $i++) {
				$line = $lines[$i].Trim()
				
				# Capture Card Name
				if ($line -match "^Card name:\s*(.*)$" -or $line -match "Card name:\s*(.*)$") {
					$currentCard = $matches[1].Trim()
					Write-Host "Found card: $currentCard"
				}
				
				if ($currentCard) {
					# Look for DEDICATED VRAM specifically (not Display Memory which includes shared)
					if ($line -match "Dedicated Video Memory:\s*(\d+)\s*MB") {
						$vramMB = [int]$matches[1]
						$vramGB = [math]::Round($vramMB / 1024, 2)
						Write-Host "GPU: $currentCard"
						Write-Host "Dedicated VRAM: $vramMB MB ($vramGB GB)"
						Write-Host ""
						$currentCard = $null
					}
					# Also check for other dedicated memory formats
					elseif ($line -match "Dedicated Memory:\s*(\d+)\s*MB") {
						$vramMB = [int]$matches[1]
						$vramGB = [math]::Round($vramMB / 1024, 2)
						Write-Host "GPU: $currentCard"
						Write-Host "Dedicated VRAM: $vramMB MB ($vramGB GB)"
						Write-Host ""
						$currentCard = $null
					}
				}
			}
			
			Remove-Item $tempFile -ErrorAction SilentlyContinue
		}
	} catch {
		Write-Host "dxdiag method failed: $_"
	}
} else {
	Write-Host "Skipping gpu information fetch...`n"
}

Write-Host 'Choose GPU VRAM tier you would like (pick the number):' -ForegroundColor Yellow
Write-Host ' 1) 4 GB  (Fastest, smallest model, with ok quality)' -ForegroundColor Yellow
Write-Host ' 2) 6-8 GB  (Better quality, gold standard)' -ForegroundColor Yellow
Write-Host ' 3) 10+ GB  (Highest quality - only for good video cards)' -ForegroundColor Yellow
Write-Host ''
Write-Host 'Enter 1, 2 or 3: ' -ForegroundColor Yellow -NoNewline
$choice = Read-Host

switch ($choice) {
    "1" {
        $moshort = "4GB"
        $model_name = "Qwen3-4b-Z-Image-Turbo-AbliteratedV1.Q4_0.gguf"
        $model_url = "https://huggingface.co/BennyDaBall/Qwen3-4b-Z-Image-Turbo-AbliteratedV1/blob/main/Z-Image-AbliteratedV1.Q4_K_S.gguf"
		$zimage_name = "z_image_turbo-Q4_K.gguf"
		$zimage_url = "https://huggingface.co/xtianj/Z-Image-Turbo-GGUF/blob/main/z_image_turbo-Q4_K.gguf"
	}
    "2" {
        $moshort = "6-8GB"
        $model_name = "Qwen3-4b-Z-Image-Turbo-AbliteratedV1.Q6_0.gguf"
        $model_url = "https://huggingface.co/BennyDaBall/Qwen3-4b-Z-Image-Turbo-AbliteratedV1/blob/main/Z-Image-AbliteratedV1.Q6_K.gguf"
		$zimage_name = "z_image_turbo-Q6_K.gguf"
		$zimage_url = "https://huggingface.co/xtianj/Z-Image-Turbo-GGUF/blob/main/z_image_turbo-Q6_K.gguf"
	}
    "3" {
        $moshort = "10+GB"
        $model_name = "Qwen3-4b-Z-Image-Turbo-AbliteratedV1.Q8_0.gguf"
        $model_url = "https://huggingface.co/BennyDaBall/Qwen3-4b-Z-Image-Turbo-AbliteratedV1/blob/main/Z-Image-AbliteratedV1.Q8_0.gguf"
		$zimage_name = "z_image_turbo-Q8_0.gguf"
		$zimage_url = "https://huggingface.co/xtianj/Z-Image-Turbo-GGUF/blob/main/z_image_turbo-Q8_0.gguf"
	}
    default {
        Write-Host "Invalid choice. Please, restart the installer and try again. Exiting."
        exit 1
    }
}

Write-Host ''
Write-Host ("You picked: {0}" -f $moshort)
Write-Host ''

$backend = "cpu"
$rng = "cpu"
$n_gpu_layers = 0
Write-Host 'Run all computations via cpu (C) [works everywhere but slow], cuda (CU) [for nvidia], directml (D) [for amd/intel]? [C/CU/D] ' -ForegroundColor Yellow -NoNewline
$choice = Read-Host
switch ($choice.ToUpper()) {
	'C' {
		$backend = "cpu"
		$rng = "cpu"
		$n_gpu_layers = 0
	}
	'CU' {
		$backend = "cuda"
		$rng = "cuda"
		$n_gpu_layers = -1
	}
	'D' {
		$backend = "directml"
		$rng = "cpu"
		$n_gpu_layers = -1
	}
	default {
		Write-Host "Invalid choice. Please, restart the installer and make a correct choice. Exiting." -ForegroundColor Red
		exit 1
	}
}
Write-Host "Successfully selected $backend" -ForegroundColor Green

# 3. Create venv (if missing)
$venv = Join-Path $root "venv"
if (!(Test-Path $venv)) {
    Write-Host "Creating Python virtual environment..."
    python -m venv venv
} else {
    Write-Host "Virtual environment already exists (venv/).`n"
}

# 4. Use venv python directly (avoids PowerShell execution policy issues with Activate.ps1)
$venvPython = Join-Path $venv "Scripts\python.exe"
if (!(Test-Path $venvPython)) {
    Write-Host "ERROR: venv python not found at: $venvPython"
    exit 1
}

# 5. Upgrade pip safely
Write-Host "Do you want to download and install required dependencies via pip automatically? (Y/N): " -ForegroundColor Yellow -NoNewline
$autoPip = Read-Host

if ($autoPip.ToUpper() -eq "Y") {
	Write-Host "Upgrading pip..."
	& $venvPython -m pip install --upgrade pip

	# 6. Install Python deps for minimal UI
	Write-Host 'Installing Python requirements (gradio, requests...)...'
	& $venvPython -m pip install pillow numpy gradio requests tqdm llama-cpp-python
	
	Write-Host "Dependencies upgraded and installed!`n" -ForegroundColor Green
} else {
	Write-Host "`nTo upgrade and install dependencies via pip run the following commands:" -ForegroundColor Yellow
	Write-Host "  $venvPython -m pip install --upgrade pip" -ForegroundColor Yellow
	Write-Host "  $venvPython -m pip install pillow numpy gradio requests tqdm llama-cpp-python" -ForegroundColor Yellow
	Write-Host "Press Enter once you did it..." -ForegroundColor Yellow
	Read-Host
}

# 7. Check for sd-cli.exe
$sdCliExe = Join-Path $sdBin "sd-cli.exe"

if ((Test-Path $sdCliExe)) {
    Write-Host "Found sd-cli.exe" -ForegroundColor Green
    $sdexe = $sdCliExe
} else {
	Write-Host ""
    Write-Host "A stable-diffusion.cpp Windows binary is REQUIRED to run the model." -ForegroundColor Yellow
    Write-Host "Please download from the official stable-diffusion.cpp releases:" -ForegroundColor Yellow
    Write-Host "    https://github.com/leejet/stable-diffusion.cpp/releases" -ForegroundColor Yellow
	if ($backend -eq "cuda") {
		Write-Host "You should search something close to sd-master-*******-bin-win-cuda12-x64.zip" -ForegroundColor Yellow
		Write-Host "Make sure word 'cuda' exists in file name you download!" -ForegroundColor Yellow
	} elseif ($backend -eq "cpu") {
		Write-Host "You should search something close to sd-master-*******-bin-win-avx2-x64.zip (works for 99% of users)" -ForegroundColor Yellow
		Write-Host "If it doesn't work, try sd-master-*******-bin-win-avx512-x64.zip (for newer CPUs with AVX-512 support)" -ForegroundColor Yellow
		Write-Host "If it still doesn't work, try sd-master-*******-bin-win-avx-x64.zip (older CPUs without AVX2)" -ForegroundColor Yellow
		Write-Host "Last resort: sd-master-*******-bin-win-noavx-x64.zip (very old CPUs, pre-2011)" -ForegroundColor Yellow
	} elseif ($backend -eq "directml") {
		Write-Host "You should search something close to sd-master-*******-bin-win-rocm-7.1.1-x64.zip" -ForegroundColor Yellow
		Write-Host "or sd-master-*******-bin-win-rocm-7.13.0-x64.zip depending on your ROCm version compatibility" -ForegroundColor Yellow
	}
	Write-Host ""
	if ($backend -eq "cuda") {
		Write-Host "Since you are using cuda also download cudart-sd from same page." -ForegroundColor Yellow
		Write-Host "and install cuda toolkit from:" -ForegroundColor Yellow
		Write-Host "    https://developer.nvidia.com/cuda-downloads" -ForegroundColor Yellow
		Write-Host ""
	}
	Write-Host "Extract everything to this path:" -ForegroundColor Yellow
    Write-Host "    $sdBin" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press Enter after you have placed the executable, or Ctrl+C to exit." -ForegroundColor Yellow
    Read-Host
	if (Test-Path $sdCliExe) {
        Write-Host "Found sd-cli.exe after user confirmation" -ForegroundColor Green
        $sdexe = $sdCliExe
    } else {
        Write-Host "Executable still not found in $sdBin. Please restart the installer and try again. Exiting." -ForegroundColor Red
        exit 1
    }
}

if (!(Test-Path $sdexe)) {
    Write-Host "Executable still not found in $sdBin. Please, restart the installer and try again. Exiting." -ForegroundColor Red
    exit 1
}

# 7b. Sanity-check executable (common crash is missing DLL / wrong build)
Write-Host "`nChecking executable. If you see print that --help flag is not found ignore it..."
try {
	Write-Host "$sdexe"
    & $sdexe --help | Out-Null
} catch {
    # swallow - we will check exit code below
}
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Executable failed to start (exit code: $LASTEXITCODE)." -ForegroundColor Red
    Write-Host "This usually means a missing dependency or wrong build."  -ForegroundColor Red
    Write-Host "" 
    Write-Host "Please check:"  -ForegroundColor Red
    Write-Host " 1) You extracted the release ZIP and copied the executable AND any .dll files into:" -ForegroundColor Red
    Write-Host "    $sdBin" -ForegroundColor Red
    Write-Host " 2) Microsoft Visual C++ Redistributable 2015-2022 (x64) is installed" -ForegroundColor Red
    Write-Host " 3) If you downloaded a CUDA build, your NVIDIA driver supports that CUDA version" -ForegroundColor Red
	Write-Host " 4) If you downloaded a CUDA build, make sure you also downloaded cudart-sd and extracted its contents into:" -ForegroundColor Red
	Write-Host "    $sdBin" -ForegroundColor Red
    Write-Host " 5) Try the CPU-only ZIP (sd-...-bin-win-x64.zip) to confirm it works on your PC" -ForegroundColor Red
    Write-Host ""
    Write-Host "Press Enter to exit. Once you fixed the problem, run installer again to continue." -ForegroundColor Red
    Read-Host
    exit 1
}

# 8. Download the chosen quantized GGUF model if it does not exist
$dest = Join-Path $zimageDir $zimage_name
if (Test-Path $dest) {
    Write-Host "Z-Image Turbo already exists: $dest" -ForegroundColor Green
} else {
    Write-Host "Please download the quantized model manually and place it into:" -ForegroundColor Yellow
	Write-Host "  $dest" -ForegroundColor Yellow
	Write-Host "Source URL:" -ForegroundColor Yellow
    Write-Host "  $zimage_url`n" -ForegroundColor Yellow
	Write-Host "Then press Enter to continue." -ForegroundColor Yellow
	Read-Host
	if (!(Test-Path $dest)) {
		Write-Host "Model not found. Please, download it and place to mentioned folder and restart the installer. Exiting." -ForegroundColor Red
		exit 1
	}
	Write-Host "Model successfully found!" -ForegroundColor Green
}

$dest = Join-Path $llmDir $model_name
if (Test-Path $dest) {
    Write-Host "Z-Image Turbo encoder already exists: $dest" -ForegroundColor Green
} else {
    Write-Host "`n`nPlease download the encoder model manually and place it into:" -ForegroundColor Yellow
	Write-Host "  $dest" -ForegroundColor Yellow
	Write-Host "Source URL:" -ForegroundColor Yellow
    Write-Host "  $model_url`n" -ForegroundColor Yellow
	Write-Host "Then press Enter to continue." -ForegroundColor Yellow
	Read-Host
	if (!(Test-Path $dest)) {
		Write-Host "Model not found. Please, download it and place to mentioned folder and restart the installer. Exiting." -ForegroundColor Red
		exit 1
	}
	Write-Host "Model successfully found!" -ForegroundColor Green
}

# 9. Download VAE + LLM (required by Z-Image pipeline)
$vaeName = "ae.safetensors"
$vaeUrl = "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors"
$vaePath = Join-Path $vaeDir $vaeName

$llmName = "Qwen3VL-8B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
$llmUrl = "https://huggingface.co/HauhauCS/Qwen3VL-8B-Uncensored-HauhauCS-Aggressive/blob/main/Qwen3VL-8B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
$llmPath = Join-Path $llmDir $llmName

if (Test-Path $vaePath) {
    Write-Host "VAE already exists: $vaePath" -ForegroundColor Green
} else {
    Write-Host "`nVAE is required but may be restricted for non-logged-in downloads on Hugging Face." -ForegroundColor Yellow
    Write-Host "Please download it manually (login may be required):" -ForegroundColor Yellow
    Write-Host "  $vaeUrl" -ForegroundColor Yellow
    Write-Host "Save it to:" -ForegroundColor Yellow
    Write-Host "  $vaePath" -ForegroundColor Yellow
    Write-Host "`nPress Enter after you have placed ae.safetensors, or Ctrl+C to exit." -ForegroundColor Yellow
    Read-Host
    if (!(Test-Path $vaePath)) {
        Write-Host "VAE not found. Please, download it and place to mentioned folder and restart the installer. Exiting." -ForegroundColor Red
        exit 1
    }
	Write-Host "VAE successfully found!" -ForegroundColor Green
}

if (Test-Path $llmPath) {
    Write-Host "LLM already exists: $llmPath" -ForegroundColor Green
} else {
    Write-Host "Please download the LLM (Qwen) manually and place it into:" -ForegroundColor Yellow
	Write-Host "  $llmPath" -ForegroundColor Yellow
	Write-Host "Source URL:" -ForegroundColor Yellow
    Write-Host "  $llmUrl`n" -ForegroundColor Yellow
	Write-Host "Then press Enter to continue." -ForegroundColor Yellow
	Read-Host
	if (!(Test-Path $llmPath)) {
		Write-Host "LLM not found. Please, download it and place to mentioned folder and restart the installer. Exiting." -ForegroundColor Red
		exit 1
	}
	Write-Host "LLM successfully found!" -ForegroundColor Green
}

$mmprojName = "Qwen3-VL-8B-Instruct-abliterated-v2.mmproj-f16.gguf"
$mmprojUrl = "https://huggingface.co/mradermacher/Qwen3-VL-8B-Instruct-abliterated-v2.0-GGUF/blob/main/Qwen3-VL-8B-Instruct-abliterated-v2.0.mmproj-f16.gguf"
$mmprojPath = Join-Path $llmDir $mmprojName

if (Test-Path $mmprojPath) {
    Write-Host "MMPROJ already exists: $mmprojPath" -ForegroundColor Green
} else {
    Write-Host "Please download MMPROJ manually and place it into:" -ForegroundColor Yellow
    Write-Host "  $mmprojPath" -ForegroundColor Yellow
    Write-Host "Source URL:" -ForegroundColor Yellow
    Write-Host "  $mmprojUrl" -ForegroundColor Yellow
    Write-Host "`nThen press Enter to continue." -ForegroundColor Yellow
    Read-Host
    if (!(Test-Path $mmprojPath)) {
        Write-Host "MMPROJ not found. Please, download it and place to mentioned folder and restart the installer. Exiting." -ForegroundColor Red
        exit 1
    }
	Write-Host "MMPROJ successfully found!" -ForegroundColor Green
}

# Create the function to use in powershell
$zimagePath = Get-Location

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
    Write-Host "`nimggen function already exists in your profile!" -ForegroundColor Yellow
    
    Write-Host "Do you want to (R) replace it, (S) skip, or (V) view existing function? [R/S/V] " -ForegroundColor Yellow -NoNewline
	$choice = Read-Host
    
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
            Write-Host "Replaced imggen function with new version!" -ForegroundColor Green
        }
        'S' {
            Write-Host "Skipping - keeping existing imggen function" -ForegroundColor Green
        }
        'V' {
            Write-Host "`n=== Existing imggen function ==="
            $currentProfile | Select-String -Pattern '(?s)(function imggen\s*\{.*?\n\})' -AllMatches | 
                ForEach-Object { $_.Matches.Value } | 
                ForEach-Object { Write-Host $_ -ForegroundColor Gray }
            Write-Host "=============================`n"
            
			Write-Host "Replace it anyway? [Y/N] " -ForegroundColor Yellow -NoNewline
            $confirm = Read-Host
            if ($confirm.ToUpper() -eq 'Y') {
                # Same replacement logic as 'R' above
                $pattern = '(?s)function imggen\s*\{.*?\n\}'
                $newProfile = $currentProfile -replace $pattern, ''
                $newProfile = $newProfile -replace '(\r?\n){3,}', "`n`n"
                Set-Content -Path $PROFILE -Value $newProfile.Trim()
                Add-Content -Path $PROFILE -Value $functionScript
                Write-Host "Replaced imggen function with new version!" -ForegroundColor Green
            } else {
                Write-Host "Keeping existing function" -ForegroundColor Green
            }
        }
        default {
            Write-Host "Invalid choice. Please, restart the installer and make a correct choice. Exiting." -ForegroundColor Red
            exit 1
        }
    }
} else {
    # No existing function, just append
    Add-Content -Path $PROFILE -Value $functionScript
    Write-Host "Successfully appended imggen function to $PROFILE" -ForegroundColor Green
}

# Prepare run_gradio_ui.py
$content = [System.IO.File]::ReadAllText((Resolve-Path "./run_gradio_ui.py"), [System.Text.UTF8Encoding]::new($false))
$content = $content -replace '(?<=LLM_ENCODER_PATH = str\(ROOT / "models" / "llm" / ")[^"]+(?="\))', $model_name
$content = $content -replace '(?<=DIFFUSION_MODEL_PATH = str\(ROOT / "models" / "zimage" / ")[^"]+(?="\))', $zimage_name
$content = $content -replace '(?<=--backend",\s*")[^"]+(?=")', $backend
$content = $content -replace '(?<=--rng",\s*")[^"]+(?=")', $rng
$content = $content -replace 'n_gpu_layers=\s*\K\d+', $n_gpu_layers
[System.IO.File]::WriteAllText((Resolve-Path "./run_gradio_ui.py"), $content, [System.Text.UTF8Encoding]::new($false))

Write-Host "`nrun_gradio_ui.py successfully updated for your configuration!`n" -ForegroundColor Green

# Creating shortcut
Write-Host "Do you want to create a shortcut on the desktop? [Y/N] " -ForegroundColor Yellow -NoNewline
$choice = Read-Host
if ($choice.ToUpper() -eq "Y") {
	$workingDir = (Resolve-Path ".").Path
	$desktopPath = [Environment]::GetFolderPath("Desktop")
	$shortcutPath = Join-Path $desktopPath -ChildPath "Run Gradio UI.lnk"

	$batPath = Join-Path $workingDir "run_gradio_ui.bat"
	$batContent = '@echo off
cd /d "C:\Distribs\llm-models\123\Z-Image-Turbo-Unified-Interface"
title Gradio UI Launcher
echo ========================================
echo    Gradio UI Launcher
echo ========================================
echo.
echo Checking if server is running on http://localhost:9000...
echo.
powershell -Command "$tcp = New-Object System.Net.Sockets.TcpClient; try { $tcp.ConnectAsync(''localhost'',9000).Wait(2000); exit $tcp.Connected } catch { exit 0 }" > nul 2>&1
if %errorlevel% equ 1 (
    echo Server is already running!
    start http://localhost:9000
    exit /b
)
echo Server not running. Starting Gradio UI...
call venv\Scripts\activate.bat
start /b python run_gradio_ui.py
echo Waiting for server to start...
timeout /t 15 /nobreak > nul
set attempt=0
:check
set /a attempt+=1
powershell -Command "$tcp = New-Object System.Net.Sockets.TcpClient; try { $tcp.ConnectAsync(''localhost'',9000).Wait(3000); exit $tcp.Connected } catch { exit 0 }" > nul 2>&1
if %errorlevel% equ 1 (
    echo Server started! Opening browser...
	echo To stop server simply close this window
    start http://localhost:9000
    exit /b
)
if %attempt% lss 30 (
    timeout /t 3 /nobreak > nul
    goto check
)
echo Could not detect server, opening browser anyway...
start http://localhost:9000'

	[System.IO.File]::WriteAllText($batPath, $batContent, [System.Text.Encoding]::ASCII)

	$WScriptShell = New-Object -ComObject WScript.Shell
	$shortcut = $WScriptShell.CreateShortcut($shortcutPath)
	$shortcut.TargetPath = $batPath
	$shortcut.WorkingDirectory = $workingDir
	$shortcut.Description = "Запуск Gradio UI с виртуальным окружением"
	$shortcut.Save()
	
	Write-Host "Shortcut 'Run Gradio UI' was successfully created in desktop!" -ForegroundColor Green
} else {
	Write-Host "Skipping shortcut creation! You can run service via imggen command from powershell and opening http://localhost:9000 in browser." -ForegroundColor Green
}

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "All done! Press any key to close this window" -ForegroundColor Green
Write-Host "============================================`n" -ForegroundColor Cyan
exit


