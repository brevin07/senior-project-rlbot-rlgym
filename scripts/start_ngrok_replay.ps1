param(
    [string]$Domain = "rlcoach.ngrok.app",
    [int]$GatewayPort = 8888,
    [switch]$BuildReact,
    [switch]$NoBrowser,
    [int]$StartupWaitSeconds = 30
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repoRoot
try {
    if ($BuildReact) {
        Write-Host "[start] building React app..."
        Push-Location "frontend\dashboard"
        try {
            & npm install
            & npm run build
        }
        finally {
            Pop-Location
        }
    }

    Write-Host "[start] starting docker compose (gateway + replay)"
    & docker compose up -d

    Write-Host "[start] waiting for gateway to become reachable..."
    $deadline = (Get-Date).AddSeconds([double]$StartupWaitSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$GatewayPort/api/health" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    if (-not $ready) {
        Write-Host "[start] warning: gateway did not respond before timeout."
    }

    Write-Host "[start] starting ngrok"
    & powershell -ExecutionPolicy Bypass -File "scripts\ngrok_dashboard.ps1" -Port $GatewayPort -Domain $Domain
}
finally {
    Pop-Location
}
