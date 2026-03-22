param(
    [string]$BindHost = "127.0.0.1",
    [int]$ReplayPort = 8775,
    [int]$LivePort = 8765,
    [int]$GatewayPort = 8888
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$env:ROCKETCOACH_DEV_BYPASS_AUTH = "1"
$env:VITE_DEV_BYPASS_AUTH = "1"

Push-Location $repoRoot
try {
    Start-Process powershell -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $repoRoot "scripts\replay_dashboard.ps1"),
        "-BindHost", $BindHost,
        "-Port", "$ReplayPort",
        "-NoBrowser"
    )
    Start-Process powershell -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $repoRoot "scripts\run_gateway.ps1"),
        "-BindHost", $BindHost,
        "-ReplayPort", "$ReplayPort",
        "-LivePort", "$LivePort",
        "-GatewayPort", "$GatewayPort"
    )
    Start-Sleep -Seconds 3
    Start-Process "http://${BindHost}:$GatewayPort/dashboard"
}
finally {
    Pop-Location
}
