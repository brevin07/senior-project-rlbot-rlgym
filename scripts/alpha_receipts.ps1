param(
    [string]$ReplayPath = "",
    [string]$RrrocketPath = "",
    [string]$DbPath = "artifacts\data\app.db",
    [string]$OutputDir = "artifacts\alpha_receipts",
    [switch]$LaunchReplayDashboard,
    [int]$ReplayDashboardPort = 8775
)

$ErrorActionPreference = "Stop"

function Resolve-Python {
    $candidates = @(
        ".\venv\Scripts\python.exe",
        ".\venv_Win\Scripts\python.exe",
        ".\rlbot_training\venv\Scripts\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            return $c
        }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py -3"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    throw "Python not found. Run scripts/bootstrap.ps1 first."
}

$py = Resolve-Python
$scriptPath = "scripts\alpha_receipts.py"
$argsList = @($scriptPath, "--db-path", $DbPath, "--output-dir", $OutputDir)
if (-not [string]::IsNullOrWhiteSpace($ReplayPath)) {
    $argsList += @("--replay", $ReplayPath)
}
if (-not [string]::IsNullOrWhiteSpace($RrrocketPath)) {
    $argsList += @("--rrrocket", $RrrocketPath)
}

Write-Host "[alpha_receipts] Running receipt tests..."
Write-Host "[alpha_receipts] Python: $py"
if ($py -eq "py -3") {
    & py -3 @argsList
} elseif ($py -eq "python") {
    & python @argsList
} else {
    & $py @argsList
}

if ($LaunchReplayDashboard) {
    Write-Host "[alpha_receipts] Launching replay dashboard for KR3 screenshot capture..."
    Write-Host "[alpha_receipts] Open http://127.0.0.1:$ReplayDashboardPort and capture FPS/event-pause screenshots."
    powershell -ExecutionPolicy Bypass -File scripts\replay_dashboard.ps1 -Port $ReplayDashboardPort
}
