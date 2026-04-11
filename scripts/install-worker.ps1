# TinyAgentOS worker installer — Windows PowerShell
# Mirror of scripts/install-worker.sh for Windows 10/11 hosts.
#
# Usage:
#     iwr -useb https://raw.githubusercontent.com/jaylfc/tinyagentos/master/scripts/install-worker.ps1 | iex
#
# or with arguments:
#     $env:TAOS_CONTROLLER_URL = 'http://10.0.0.5:6969'
#     iwr -useb https://raw.githubusercontent.com/jaylfc/tinyagentos/master/scripts/install-worker.ps1 | iex
#
# Environment / parameter overrides (matches the bash version):
#     TAOS_CONTROLLER_URL     controller URL (required)
#     TAOS_WORKER_NAME        worker display name (default: $env:COMPUTERNAME)
#     TAOS_INSTALL_DIR        install dir (default: %LOCALAPPDATA%\tinyagentos-worker)
#     TAOS_BRANCH             git branch or tag (default: master)
#     TAOS_REPO               git remote
#     TAOS_SKIP_BENCHMARK     if set, skip the on-join benchmark run
#     TAOS_SERVICE            install as service: auto (default), task, skip

[CmdletBinding()]
param(
    [string]$ControllerUrl = $env:TAOS_CONTROLLER_URL,
    [string]$WorkerName = $env:TAOS_WORKER_NAME,
    [string]$InstallDir = $env:TAOS_INSTALL_DIR,
    [string]$Branch = $env:TAOS_BRANCH,
    [string]$Repo = $env:TAOS_REPO,
    [switch]$SkipBenchmark,
    [string]$ServiceMode = $env:TAOS_SERVICE
)

$ErrorActionPreference = 'Stop'

if (-not $ControllerUrl) {
    Write-Error "controller URL required. pass -ControllerUrl or set TAOS_CONTROLLER_URL"
    exit 2
}

if (-not $WorkerName) { $WorkerName = $env:COMPUTERNAME }
if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA 'tinyagentos-worker' }
if (-not $Branch) { $Branch = 'master' }
if (-not $Repo) { $Repo = 'https://github.com/jaylfc/tinyagentos' }
if (-not $ServiceMode) { $ServiceMode = 'auto' }
if ($env:TAOS_SKIP_BENCHMARK) { $SkipBenchmark = $true }

function Log($m) { Write-Host "[worker-install] $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[worker-install] $m" -ForegroundColor Yellow }
function Die($m) { Write-Host "[worker-install] $m" -ForegroundColor Red; exit 1 }

Log "os=Windows arch=$env:PROCESSOR_ARCHITECTURE controller=$ControllerUrl name=$WorkerName"
Log "install_dir=$InstallDir branch=$Branch"

# --- system dependencies --------------------------------------------------

function Ensure-Winget-Package([string]$id, [string]$friendly) {
    $installed = $false
    try {
        $installed = (winget list --id $id -e 2>$null) -match $id
    } catch { }
    if (-not $installed) {
        Log "installing $friendly via winget"
        winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements | Out-Null
    }
}

# Python 3 check
$pythonCmd = $null
foreach ($candidate in @('python3.12', 'python3', 'python', 'py')) {
    try {
        $v = & $candidate --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $v -match 'Python 3\.\d+') {
            $pythonCmd = $candidate
            break
        }
    } catch { }
}

if (-not $pythonCmd) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Ensure-Winget-Package 'Python.Python.3.12' 'Python 3.12'
        $pythonCmd = 'python'
    } else {
        Die "python 3 not found and winget unavailable. install python 3.12 from https://python.org first"
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Ensure-Winget-Package 'Git.Git' 'Git for Windows'
    } else {
        Die "git not found and winget unavailable. install git first"
    }
}

# --- clone / update the repo ---------------------------------------------

if (-not (Test-Path (Join-Path $InstallDir '.git'))) {
    Log "cloning $Repo into $InstallDir"
    New-Item -ItemType Directory -Force -Path (Split-Path $InstallDir) | Out-Null
    git clone --depth 1 --branch $Branch $Repo $InstallDir
} else {
    Log "updating existing checkout"
    Push-Location $InstallDir
    git fetch --depth 1 origin $Branch
    git reset --hard "origin/$Branch"
    Pop-Location
}

Set-Location $InstallDir

# --- venv + deps ---------------------------------------------------------

$venvDir = Join-Path $InstallDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Log "creating venv"
    & $pythonCmd -m venv $venvDir
}

Log "installing worker python deps into .venv"
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet httpx pydantic psutil fastapi uvicorn pyyaml pillow

# --- first-boot benchmark -----------------------------------------------

if (-not $SkipBenchmark) {
    Log "running initial worker benchmark (first-join only — subsequent runs are manual)"
    try {
        & $venvPython -m tinyagentos.benchmark.runner --report-to $ControllerUrl --worker-name $WorkerName --first-join
    } catch {
        Warn "benchmark runner not available yet — skipping (worker will run without baseline scores)"
    }
}

# --- install as scheduled task / service --------------------------------

function Install-ScheduledTask {
    $taskName = 'TinyAgentOSWorker'
    $action = New-ScheduledTaskAction `
        -Execute $venvPython `
        -Argument "-m tinyagentos.worker $ControllerUrl --name $WorkerName" `
        -WorkingDirectory $InstallDir
    $trigger = New-ScheduledTaskTrigger -AtLogon -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -RestartCount 999
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description 'TinyAgentOS worker daemon — connects to the controller and serves inference work' | Out-Null

    Start-ScheduledTask -TaskName $taskName
    Log "worker registered as Scheduled Task '$taskName' (starts at logon, auto-restarts)"
    Log "check: Get-ScheduledTask -TaskName $taskName"
    Log "logs:  ~/.local/share/tinyagentos-worker/worker.log (if redirection enabled)"
}

if ($ServiceMode -eq 'skip') {
    Log "TAOS_SERVICE=skip — not installing a service"
    Log "run manually: cd $InstallDir; .\.venv\Scripts\python.exe -m tinyagentos.worker $ControllerUrl --name $WorkerName"
} else {
    Install-ScheduledTask
}

Log "install complete"
Log "worker name: $WorkerName"
Log "controller:  $ControllerUrl"
Log "install dir: $InstallDir"
Log "to upgrade later: cd $InstallDir; git pull; Restart-ScheduledTask -TaskName TinyAgentOSWorker"
