# bootstrap.ps1 — Gillsystems AI Stack Updater: first-run bootstrap
#
# Called by update-ai-stack.bat after elevation.
# Handles everything needed before the agent can run:
#   1. Finds Python 3.11+ (py launcher, PATH, common paths)
#   2. Downloads and silently installs Python 3.12 if nothing found
#   3. Adds Python dirs to PATH (current session + user registry)
#   4. Upgrades pip and installs requirements.txt
#   5. Launches src.main with real-time output AND log file (Tee-Object)
#
# Usage: bootstrap.ps1 [args passed through to src.main]

$ROOT = $PSScriptRoot


$AppArgs = $args   # pass-through to src.main (e.g. --dry-run, --check-only)

# ── Windows Unicode support ────────────────────────────────────────────────
# PYTHONUTF8 tells Python 3.12+ to use UTF-8 for all stdio.
# Without this, Rich box-drawing characters get mangled when piped through
# PowerShell 5.1's Tee-Object (which transcodes to the OEM code page).
$env:PYTHONUTF8 = '1'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    # PowerShell 5.1 uses the console's OEM output encoding by default.
    # Force UTF-8 so Rich Unicode glyphs survive the Tee-Object pipe.
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}

# ── Helpers ────────────────────────────────────────────────────────────────
function Write-Step([string]$msg, [string]$color = 'Cyan') {
    Write-Host "  $msg" -ForegroundColor $color
}

function Add-ToPath([string]$dir) {
    if (-not $dir -or -not (Test-Path $dir)) { return }
    # Current session
    if (($env:PATH -split ';') -notcontains $dir) {
        $env:PATH = "$dir;$env:PATH"
    }
    # User registry (persistent)
    $cur = ([Environment]::GetEnvironmentVariable('PATH', 'User') -split ';') |
           Where-Object { $_ -ne '' }
    if ($cur -notcontains $dir) {
        $cur = @($dir) + $cur
        [Environment]::SetEnvironmentVariable('PATH', ($cur -join ';'), 'User')
    }
}

# ── Step 1: Find Python 3.11+ ──────────────────────────────────────────────
function Find-Python {
    # 1a. py launcher — most reliable on Windows
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in '3.13', '3.12', '3.11', '3.14') {
            try {
                $null = py "-$v" --version 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $exePath = (py "-$v" -c 'import sys; print(sys.executable)' 2>&1).Trim()
                    if ($exePath -and (Test-Path $exePath)) { return $exePath }
                }
            } catch { }
        }
    }

    # 1b. 'python' already on PATH
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try {
            $null = python -c 'import sys; exit(0 if sys.version_info>=(3,11) else 1)' 2>&1
            if ($LASTEXITCODE -eq 0) {
                $exePath = (python -c 'import sys; print(sys.executable)' 2>&1).Trim()
                if ($exePath -and (Test-Path $exePath)) { return $exePath }
            }
        } catch { }
    }

    # 1c. Scan common install locations
    $locations = @(
        "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        'C:\Program Files\Python313\python.exe',
        'C:\Program Files\Python312\python.exe',
        'C:\Program Files\Python311\python.exe',
        'C:\Python313\python.exe',
        'C:\Python312\python.exe',
        'C:\Python311\python.exe'
    )
    foreach ($loc in $locations) {
        if (Test-Path $loc) { return $loc }
    }

    return $null
}

# ── Step 1d: Download + silent install Python 3.12 ─────────────────────────
function Install-Python312 {
    $url = 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe'
    $installer = "$env:TEMP\python-3.12.9-setup.exe"

    Write-Step 'Downloading Python 3.12.9 from python.org...'
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing

    Write-Step 'Installing silently (this takes about a minute, please wait)...'
    $installArgs = '/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1'
    Start-Process -FilePath $installer -ArgumentList $installArgs -Wait

    Remove-Item $installer -Force -ErrorAction SilentlyContinue

    $installed = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    if (Test-Path $installed) {
        Write-Step 'Python 3.12 installed successfully.' 'Green'
        return $installed
    }
    return $null
}

# ── Main ───────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '  ================================================' -ForegroundColor Blue
Write-Host '   Gillsystems AI Stack Updater' -ForegroundColor White
Write-Host '  ================================================' -ForegroundColor Blue
Write-Host ''

# 1. Find Python
Write-Step '[1/4] Locating Python 3.11+...'
$python = Find-Python

if (-not $python) {
    Write-Host ''
    Write-Step '[1/4] Python 3.11+ not found. Fetching installer...' 'Yellow'
    Write-Host ''
    $python = Install-Python312
}

if (-not $python -or -not (Test-Path $python)) {
    Write-Host ''
    Write-Host '  ERROR: Could not find or install Python 3.11+.' -ForegroundColor Red
    Write-Host '  Please install Python 3.12+ from https://python.org and rerun.' -ForegroundColor Red
    Write-Host ''
    exit 1
}

$pyVer = (& $python --version 2>&1).ToString().Trim()
Write-Step "[1/4] Found: $pyVer  ($python)" 'Green'

# 2. Add Python dirs to PATH
$pyDir     = Split-Path $python
$pyScripts = Join-Path $pyDir 'Scripts'   # always <pythondir>\Scripts on Windows

Add-ToPath $pyDir
Add-ToPath $pyScripts

# 3. pip + dependencies
Write-Step '[2/4] Ensuring pip is current...'
& $python -m pip install --upgrade pip --quiet 2>&1 | Out-Null

Write-Step '[3/4] Checking dependencies...'
$depsCheck = & $python -c 'import rich, pydantic, httpx, yaml, packaging' 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Step '[3/4] Dependencies already satisfied.' 'Green'
} else {
    Write-Step '[3/4] Installing dependencies from requirements.txt...'
    & $python -m pip install -r (Join-Path $ROOT 'requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host '  ERROR: Failed to install Python dependencies.' -ForegroundColor Red
        Write-Host "  Try manually: $python -m pip install -r requirements.txt" -ForegroundColor Yellow
        Write-Host ''
        exit 1
    }
    Write-Step '[3/4] Dependencies installed.' 'Green'
}

# 4. Launch the agent
$logFile = Join-Path $ROOT 'gillsystems_run.log'
Write-Step "[4/4] Launching agent...  (log: $logFile)"
Write-Host ''

Push-Location $ROOT
try {
    # CRITICAL FIX: Stderr → log file ONLY (avoids PowerShell 5.1 NativeCommandError noise).
    # Stdout → both console AND log via Tee-Object (Append to avoid double-write).
    # PowerShell 5.1 treats stderr bytes as errors and wraps them in red
    # NativeCommandError decorations — httpx INFO logs via stderr trigger this.
    # By sending stderr directly to the log file and only piping stdout through
    # Tee-Object, the console stays clean while the log has full detail.
    if ($AppArgs.Count -gt 0) {
        & $python -u -m src.main @AppArgs 2>>$logFile | Tee-Object -FilePath $logFile -Append
    } else {
        & $python -u -m src.main 2>>$logFile | Tee-Object -FilePath $logFile -Append
    }
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ''
if ($exitCode -eq 0) {
    Write-Host '  Completed successfully.' -ForegroundColor Green
} elseif ($exitCode -eq 130) {
    Write-Host '  Cancelled by user.' -ForegroundColor Yellow
} else {
    Write-Host "  *** FAILED ***  Exit code: $exitCode" -ForegroundColor Red
    Write-Host "  Full log: $logFile" -ForegroundColor Yellow
}

exit $exitCode
