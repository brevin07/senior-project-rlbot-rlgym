param(
    [string]$Domain = "rlcoach.ngrok.app",
    [int]$GatewayPort = 8888,
    [int]$LivePort = 8765,
    [switch]$BuildReact,
    [switch]$NoBrowser,
    [switch]$AttachOnly
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

    $liveArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $repoRoot "scripts\launch_live_analysis.ps1"),
        "-BindHost", "127.0.0.1",
        "-Port", "$LivePort"
    )
    if ($AttachOnly) {
        $liveArgs += "-AttachOnly"
    } else {
        # Default to attach-only to avoid launching Rocket League automatically.
        $liveArgs += "-AttachOnly"
    }
    if ($NoBrowser) { $liveArgs += "-NoBrowser" }

    Write-Host "[start] starting live analysis"
    Start-Process -FilePath powershell -ArgumentList $liveArgs

    Write-Host "[start] starting ngrok"
    & powershell -ExecutionPolicy Bypass -File "scripts\ngrok_dashboard.ps1" -Port $GatewayPort -Domain $Domain
}
finally {
    Pop-Location
}
