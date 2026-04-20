param(
    [string]$BindHost = "127.0.0.1",
    [int]$ReplayPort = 8775,
    [int]$LivePort = 8765,
    [int]$GatewayPort = 8888,
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Wait-HttpReady {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$Attempts = 30,
        [int]$DelaySeconds = 1
    )

    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                return $true
            }
        } catch {
            Start-Sleep -Seconds $DelaySeconds
        }
    }

    return $false
}

$env:ROCKETCOACH_DEV_BYPASS_AUTH = "1"
$env:VITE_DEV_BYPASS_AUTH = "1"

Push-Location $repoRoot
try {
    if (-not $SkipFrontendBuild) {
        Write-Host "[review] Building dashboard frontend..."
        Push-Location (Join-Path $repoRoot "frontend\dashboard")
        try {
            npm run build
        }
        finally {
            Pop-Location
        }
    }

    Write-Host "[review] Starting replay dashboard on http://${BindHost}:$ReplayPort ..."
    Start-Process powershell -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $repoRoot "scripts\replay_dashboard.ps1"),
        "-BindHost", $BindHost,
        "-Port", "$ReplayPort",
        "-NoBrowser"
    )

    Write-Host "[review] Starting gateway on http://${BindHost}:$GatewayPort ..."
    Start-Process powershell -ArgumentList @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $repoRoot "scripts\run_gateway.ps1"),
        "-BindHost", $BindHost,
        "-ReplayPort", "$ReplayPort",
        "-LivePort", "$LivePort",
        "-GatewayPort", "$GatewayPort",
        "-NoBrowser"
    )

    Write-Host "[review] Waiting for local dashboard to come up..."
    $ready = Wait-HttpReady -Url "http://${BindHost}:$GatewayPort/dashboard"
    if ($ready) {
        Write-Host "[review] Local review site is ready at http://${BindHost}:$GatewayPort/dashboard"
        Start-Process "http://${BindHost}:$GatewayPort/dashboard"
    } else {
        Write-Warning "Dashboard did not answer in time. Check the new PowerShell windows for replay/gateway startup errors."
    }
}
finally {
    Pop-Location
}
