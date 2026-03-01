param(
    [string]$BindHost = "127.0.0.1",
    [int]$LivePort = 8765,
    [int]$ReplayPort = 8775,
    [int]$GatewayPort = 8888,
    [switch]$NoBrowser,
    [switch]$AttachOnly,
    [switch]$NoNewWindow,
    [switch]$StartLive,
    [switch]$StartReplay
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-VenvPython([string]$root) {
    $winPy = Join-Path $root "venv\Scripts\python.exe"
    if (Test-Path $winPy) { return $winPy }
    $altPy = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path $altPy) { return $altPy }
    $posixPy = Join-Path $root "venv\bin\python"
    if (Test-Path $posixPy) { return $posixPy }
    return $null
}

Push-Location $repoRoot
try {
    if ($StartLive) {
        $liveArgs = @(
            "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $repoRoot "scripts\launch_live_analysis.ps1"),
            "-BindHost", $BindHost,
            "-Port", "$LivePort"
        )
        # Always attach-only to avoid launching Rocket League automatically.
        $liveArgs += "-AttachOnly"
        if ($AttachOnly) { $liveArgs += "-AttachOnly" }
        if ($NoBrowser) { $liveArgs += "-NoBrowser" }

        if ($NoNewWindow) {
            Start-Process -FilePath powershell -ArgumentList $liveArgs -WindowStyle Normal
        } else {
            Start-Process -FilePath powershell -ArgumentList $liveArgs
        }
    }

    if ($StartReplay) {
        $replayArgs = @(
            "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $repoRoot "scripts\replay_dashboard.ps1"),
            "-BindHost", $BindHost,
            "-Port", "$ReplayPort"
        )
        if ($NoBrowser) { $replayArgs += "-NoBrowser" }

        if ($NoNewWindow) {
            Start-Process -FilePath powershell -ArgumentList $replayArgs -WindowStyle Normal
        } else {
            Start-Process -FilePath powershell -ArgumentList $replayArgs
        }
    }

    $venvPython = Resolve-VenvPython $repoRoot
    if (!(Test-Path $venvPython)) {
        throw "Virtual environment not found. Run scripts/bootstrap.ps1 first."
    }

    $gateway = Join-Path $repoRoot "Milestone_1\dashboard_gateway\gateway_server.py"
    $liveUrl = "http://${BindHost}:$LivePort"
    $replayUrl = "http://${BindHost}:$ReplayPort"
    & $venvPython $gateway --host $BindHost --port $GatewayPort --live $liveUrl --replay $replayUrl
}
finally {
    Pop-Location
}
