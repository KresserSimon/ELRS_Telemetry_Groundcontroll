<#
.SYNOPSIS
    One-time (per machine) dev environment setup for ELRS Ground Station.

.DESCRIPTION
    This project lives inside a OneDrive-synced folder. OneDrive's Files-On-
    Demand sync engine marks every folder in the synced tree as a reparse
    point and can lock files mid-write, which corrupts large, fast-changing,
    machine-specific folders like .venv/, dist/ and build/ (broken venv
    interpreters, aborted pip installs, PyInstaller rmtree PermissionErrors).

    This script keeps those three folders OUTSIDE OneDrive entirely - in
    %LOCALAPPDATA%\ELRS_GroundStation, which OneDrive never syncs - and
    creates NTFS junctions at the usual project-relative paths (.venv/,
    dist/, build/) pointing at them. Everything still works with plain
    relative paths (./.venv/Scripts/python.exe, etc.); OneDrive just never
    sees or locks the real files.

    Run this once after cloning/syncing the project onto a new machine (or
    any time .venv looks broken), then use the project as normal from
    the synced folder.

.NOTES
    Safe to re-run: if the junctions already exist, only the venv package
    install step runs again.
#>

$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$LocalBase = Join-Path $env:LOCALAPPDATA "ELRS_GroundStation"
New-Item -ItemType Directory -Force -Path $LocalBase | Out-Null

function Ensure-Junction {
    param([string]$Name)

    $projectPath = Join-Path $ProjectRoot $Name
    $localPath = Join-Path $LocalBase $Name

    if (Test-Path $projectPath) {
        $item = Get-Item $projectPath -Force
        if ($item.LinkType -eq "Junction") {
            Write-Host "[$Name] already a junction -> $($item.Target)"
            return
        }

        Write-Host "[$Name] moving existing folder out of OneDrive via robocopy..."
        New-Item -ItemType Directory -Force -Path $localPath | Out-Null
        robocopy $projectPath $localPath /E /MOVE /R:3 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
        if (Test-Path $projectPath) {
            Remove-Item -Recurse -Force $projectPath -ErrorAction SilentlyContinue
        }
    }

    New-Item -ItemType Junction -Path $projectPath -Target $localPath | Out-Null
    Write-Host "[$Name] junction created -> $localPath"
}

Ensure-Junction ".venv"
Ensure-Junction "dist"
Ensure-Junction "build"

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..."
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $systemPython) {
        throw "No system Python found on PATH. Install Python 3.10+ first."
    }
    & $systemPython.Source -m venv (Join-Path $ProjectRoot ".venv")
}

Write-Host "Installing requirements..."
& $python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")

Write-Host "Installing dev tooling (PyInstaller, manual generation)..."
& $python -m pip install pyinstaller reportlab pymupdf

Write-Host ""
Write-Host "Done. .venv, dist and build now live at $LocalBase (outside OneDrive)."
Write-Host "Run the app with: .venv\Scripts\python.exe main.py"
