<#
.SYNOPSIS
    run-logforge.ps1 - Normal everyday launcher for an initialized LogForge installation.

.DESCRIPTION
    Launches LogForge quickly without reinstalling packages or checking dependencies:
    1. Verifies that the .venv virtual environment and LogForge CLI exist.
    2. Checks if LogForge is already running on the target port (prevents duplicate instances).
    3. Displays Web UI, API Docs, and Health URLs.
    4. Automatically opens the Web UI in your default web browser.
    5. Starts the FastAPI server.

    NOTE: This is the NORMAL launcher to use after reboots or everyday work.
    If this is your first time using LogForge, run .\boot-logforge.ps1 first.

.PARAMETER Port
    The TCP port for the FastAPI server (default: 8000).

.PARAMETER NoBrowser
    Do not automatically open the default browser upon launch.

.EXAMPLE
    .\run-logforge.ps1
    .\run-logforge.ps1 -Port 8080
    .\run-logforge.ps1 -NoBrowser
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

Set-Location -Path $RepoRoot

# -------------------------------------------------------------
# 1. Environment Verification
# -------------------------------------------------------------
$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvLogforge = Join-Path $VenvDir "Scripts\logforge.exe"

if (-not (Test-Path $VenvLogforge)) {
    Write-Host ""
    Write-Host "[!] LogForge is not initialized." -ForegroundColor Red
    Write-Host "    Virtual environment or LogForge executable missing in '.venv'." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "    Please run the one-time setup script first:" -ForegroundColor White
    Write-Host "      .\boot-logforge.ps1" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# -------------------------------------------------------------
# 2. Port Collision & Running Instance Check
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
    # Check if LogForge is already active on this port
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
            Write-Host "[+] Opening Web UI in default browser..." -ForegroundColor DarkGray
            Start-Process "http://127.0.0.1:$Port"
        }
        exit 0
    } else {
        Write-Host ""
        Write-Host "[!] Port $Port is currently occupied by another application." -ForegroundColor Red
        Write-Host "    Please specify a different port:" -ForegroundColor White
        Write-Host "      .\run-logforge.ps1 -Port 8080" -ForegroundColor Cyan
        Write-Host ""
        exit 1
    }
}

# -------------------------------------------------------------
# 3. Ensure Runtime Output Directory
# -------------------------------------------------------------
$OutputDir = Join-Path $RepoRoot "output"
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# -------------------------------------------------------------
# 4. Launch Server & Open Browser
# -------------------------------------------------------------
$WebUrl = "http://127.0.0.1:$Port"
$DocsUrl = "http://127.0.0.1:$Port/docs"
$HealthUrl = "http://127.0.0.1:$Port/api/health"

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Green
Write-Host "  LogForge Engine Starting" -ForegroundColor Green
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
