<#
.SYNOPSIS
    boot-logforge.ps1 - One-time initialization and first-time setup for LogForge.

.DESCRIPTION
    Turns a fresh LogForge clone into a ready-to-run installation:
    1. Verifies Python >= 3.12 is installed on the system.
    2. Creates an isolated local virtual environment (.venv).
    3. Installs LogForge and its dependencies into .venv.
    4. Initializes required runtime storage (output/).
    5. Runs an automated smoke test verification.
    6. Starts the LogForge web server and launches the Web UI in the default browser.

    NOTE: This is a FIRST-TIME setup script. Once initialized, Windows reboots
    or subsequent launches should use .\run-logforge.ps1 instead.

.PARAMETER Port
    The TCP port for the FastAPI server (default: 8000).

.PARAMETER Force
    Force recreation of .venv even if it already exists.

.PARAMETER NoBrowser
    Do not automatically open the default browser upon launch.

.EXAMPLE
    .\boot-logforge.ps1
    .\boot-logforge.ps1 -Port 8080
    .\boot-logforge.ps1 -Force
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Force,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  LogForge - One-Time Initialization & First-Time Setup" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

# -------------------------------------------------------------
# 1. Resolve & Validate Working Directory
# -------------------------------------------------------------
Set-Location -Path $RepoRoot

$PyprojectPath = Join-Path $RepoRoot "pyproject.toml"
if (-not (Test-Path $PyprojectPath)) {
    Write-Host "[!] Fatal Error: Could not locate pyproject.toml in '$RepoRoot'." -ForegroundColor Red
    Write-Host "    Make sure you run this script directly from the LogForge repository root." -ForegroundColor Yellow
    exit 1
}

# -------------------------------------------------------------
# 2. Check if Already Initialized
# -------------------------------------------------------------
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvLogforge = Join-Path $VenvDir "Scripts\logforge.exe"

if ((Test-Path $VenvLogforge) -and (-not $Force)) {
    Write-Host "[i] LogForge environment is ALREADY INITIALIZED in '.venv'." -ForegroundColor Green
    Write-Host "    You do not need to run boot-logforge.ps1 again." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "    To start LogForge normally, run:" -ForegroundColor White
    Write-Host "      .\run-logforge.ps1" -ForegroundColor Yellow
    Write-Host "      .\run-logforge.ps1 -Port $Port" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "    (To force a clean reinstall, run: .\boot-logforge.ps1 -Force)" -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

# -------------------------------------------------------------
# 3. Check for Python >= 3.12 (System / Host Environment)
# -------------------------------------------------------------
Write-Host "[+] Checking prerequisites..." -ForegroundColor Cyan

$SystemPython = $null
$PyVerMajor = 0
$PyVerMinor = 0

# Try 'python'
try {
    $pyCmd = Get-Command "python" -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $verStr = (& python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null)
        if ($LASTEXITCODE -eq 0 -and $verStr) {
            $parts = $verStr.Trim().Split('.')
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 12) {
                $SystemPython = "python"
                $PyVerMajor = [int]$parts[0]
                $PyVerMinor = [int]$parts[1]
            }
        }
    }
} catch {}

# Try 'py -3.12' or 'py'
if (-not $SystemPython) {
    try {
        $pyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
        if ($pyLauncher) {
            $verStr = (& py -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $verStr) {
                $SystemPython = "py -3.12"
                $PyVerMajor = 3
                $PyVerMinor = 12
            } else {
                $verStrDef = (& py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null)
                if ($LASTEXITCODE -eq 0 -and $verStrDef) {
                    $parts = $verStrDef.Trim().Split('.')
                    if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 12) {
                        $SystemPython = "py"
                        $PyVerMajor = [int]$parts[0]
                        $PyVerMinor = [int]$parts[1]
                    }
                }
            }
        }
    } catch {}
}

if (-not $SystemPython) {
    Write-Host ""
    Write-Host "[!] Prerequisite Missing: Python 3.12 or newer is required." -ForegroundColor Red
    Write-Host "    LogForge requires modern Python 3.12+ for OCSF 1.4.0 type modeling and pipeline concurrency." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "    Action Required:" -ForegroundColor White
    Write-Host "    1. Download Python 3.12+ from: https://www.python.org/downloads/" -ForegroundColor Cyan
    Write-Host "    2. During Windows installation, check 'Add python.exe to PATH'." -ForegroundColor Cyan
    Write-Host "    3. Restart your terminal and run .\boot-logforge.ps1 again." -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

Write-Host "    Found Python $PyVerMajor.$PyVerMinor ($SystemPython)" -ForegroundColor Green

# -------------------------------------------------------------
# 4. Create Isolated .venv Virtual Environment
# -------------------------------------------------------------
if ($Force -and (Test-Path $VenvDir)) {
    Write-Host "[+] Removing existing .venv (-Force requested)..." -ForegroundColor Yellow
    Remove-Item -Path $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $VenvDir)) {
    Write-Host "[+] Creating isolated virtual environment in .venv..." -ForegroundColor Cyan
    if ($SystemPython -eq "py -3.12") {
        & py -3.12 -m venv "$VenvDir"
    } else {
        & $SystemPython -m venv "$VenvDir"
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        Write-Host "[!] Failed to create virtual environment in '$VenvDir'." -ForegroundColor Red
        exit 1
    }
}

# -------------------------------------------------------------
# 5. Install LogForge into .venv (Zero Global Contamination)
# -------------------------------------------------------------
Write-Host "[+] Installing LogForge and dependencies into .venv..." -ForegroundColor Cyan

# Check if uv is available for ultra-fast sync, otherwise standard pip
$uvCmd = Get-Command "uv" -ErrorAction SilentlyContinue
if ($uvCmd) {
    Write-Host "    Using 'uv' for high-speed package resolution..." -ForegroundColor DarkGray
    & uv pip install -e "$RepoRoot" --python "$VenvPython"
} else {
    Write-Host "    Using pip in virtual environment..." -ForegroundColor DarkGray
    & "$VenvPython" -m pip install --quiet --disable-pip-version-check -e "$RepoRoot"
}

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvLogforge)) {
    Write-Host "[!] Failed to install LogForge into virtual environment." -ForegroundColor Red
    Write-Host "    Ensure you have an active network connection for initial dependency downloads." -ForegroundColor Yellow
    exit 1
}

# -------------------------------------------------------------
# 6. Initialize Runtime Directories
# -------------------------------------------------------------
Write-Host "[+] Initializing runtime storage directories..." -ForegroundColor Cyan
$OutputDir = Join-Path $RepoRoot "output"
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# -------------------------------------------------------------
# 7. Smoke Test Verification
# -------------------------------------------------------------
Write-Host "[+] Verifying installation (smoke test)..." -ForegroundColor Cyan
$smokeHelp = & "$VenvLogforge" --help 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] Verification smoke test failed. CLI exited with code $LASTEXITCODE." -ForegroundColor Red
    Write-Host $smokeHelp -ForegroundColor DarkGray
    exit 1
}
Write-Host "    LogForge CLI verified successfully." -ForegroundColor Green

# -------------------------------------------------------------
# 8. Check Port Availability
# -------------------------------------------------------------
$portInUse = $false
try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    $listener.Start()
    $listener.Stop()
} catch {
    $portInUse = $true
}

if ($portInUse) {
    # Check if existing process on port is already LogForge
    $isAlreadyLogForge = $false
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2 -ErrorAction Stop
        if ($resp.status -eq "ok" -or $resp.version) {
            $isAlreadyLogForge = $true
        }
    } catch {}

    if ($isAlreadyLogForge) {
        Write-Host ""
        Write-Host "[i] LogForge is ALREADY RUNNING on port $Port!" -ForegroundColor Green
        Write-Host "    Web UI:       http://127.0.0.1:$Port" -ForegroundColor Cyan
        Write-Host "    API Docs:     http://127.0.0.1:$Port/docs" -ForegroundColor Cyan
        Write-Host "    Health Check: http://127.0.0.1:$Port/api/health" -ForegroundColor Cyan
        Write-Host ""
        if (-not $NoBrowser) {
            Start-Process "http://127.0.0.1:$Port"
        }
        exit 0
    } else {
        Write-Host ""
        Write-Host "[!] Port $Port is currently in use by another application." -ForegroundColor Yellow
        Write-Host "    Please run with a custom port:" -ForegroundColor White
        Write-Host "      .\run-logforge.ps1 -Port 8080" -ForegroundColor Cyan
        Write-Host ""
        exit 1
    }
}

# -------------------------------------------------------------
# 9. Launch LogForge Web Server & Open Browser
# -------------------------------------------------------------
$WebUrl = "http://127.0.0.1:$Port"
$DocsUrl = "http://127.0.0.1:$Port/docs"
$HealthUrl = "http://127.0.0.1:$Port/api/health"

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  LogForge Engine Initialized & Online" -ForegroundColor Green
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  Web UI:       $WebUrl" -ForegroundColor White
Write-Host "  API Docs:     $DocsUrl" -ForegroundColor White
Write-Host "  Health Check: $HealthUrl" -ForegroundColor White
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  Press Ctrl+C to halt the server." -ForegroundColor DarkGray
Write-Host ""

if (-not $NoBrowser) {
    Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile -Command Start-Sleep -Seconds 2; Start-Process '$WebUrl'"
}

& "$VenvLogforge" serve --host 127.0.0.1 --port $Port
