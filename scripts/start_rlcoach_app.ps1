param(
    [string]$Domain = "rlcoach.ngrok.app",
    [int]$GatewayPort = 8888,
    [switch]$BuildReact,
    [switch]$NoBrowser,
    [int]$StartupWaitSeconds = 30,
    [string]$EnvFile = ".env",
    [string]$ComposeProjectName = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Test-CommandAvailable([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Import-DotEnvFile([string]$Path) {
    if (!(Test-Path $Path)) {
        throw "Missing env file: $Path"
    }
    foreach ($line in Get-Content $Path) {
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith("#")) {
            continue
        }
        $parts = $trim -split "=", 2
        if ($parts.Length -ne 2) {
            continue
        }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.StartsWith('"') -and $value.EndsWith('"') -and $value.Length -ge 2) {
            $value = $value.Substring(1, $value.Length - 2)
        } elseif ($value.StartsWith("'") -and $value.EndsWith("'") -and $value.Length -ge 2) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Assert-RequiredEnv([string[]]$Names) {
    $missing = @()
    foreach ($name in $Names) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ([string]::IsNullOrWhiteSpace($value)) {
            $missing += $name
        }
    }
    if ($missing.Count -gt 0) {
        throw ("Missing required environment variables: " + ($missing -join ", "))
    }
}

Push-Location $repoRoot
try {
    if (-not (Test-CommandAvailable "docker")) {
        throw "docker not found in PATH. Install Docker Desktop and try again."
    }
    if (-not (Test-CommandAvailable "ngrok")) {
        throw "ngrok not found in PATH. Install ngrok and try again."
    }
    if ($BuildReact -and -not (Test-CommandAvailable "npm")) {
        throw "npm not found in PATH, but -BuildReact was provided."
    }

    $resolvedEnvPath = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $repoRoot $EnvFile }
    Write-Host "[start] loading environment from $resolvedEnvPath"
    Import-DotEnvFile -Path $resolvedEnvPath
    $dbPath = [Environment]::GetEnvironmentVariable("RLBOT_APP_DB_PATH", "Process")
    if ([string]::IsNullOrWhiteSpace($dbPath)) {
        $dbPath = Join-Path $repoRoot "artifacts\data\app.db"
        [Environment]::SetEnvironmentVariable("RLBOT_APP_DB_PATH", $dbPath, "Process")
    }
    $dbDir = Split-Path -Parent $dbPath
    if (-not [string]::IsNullOrWhiteSpace($dbDir)) {
        New-Item -ItemType Directory -Path $dbDir -Force | Out-Null
    }
    Write-Host "[start] app database path: $dbPath"
    Assert-RequiredEnv -Names @("COGNITO_ISSUER", "COGNITO_CLIENT_ID")
    if ($BuildReact) {
        Assert-RequiredEnv -Names @(
            "VITE_COGNITO_AUTHORITY",
            "VITE_COGNITO_USER_POOL_ID",
            "VITE_COGNITO_CLIENT_ID",
            "VITE_COGNITO_SCOPE"
        )
    }

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

    Write-Host "[start] resetting docker compose state"
    $composeArgs = @("compose")
    if ($ComposeProjectName) {
        $composeArgs += @("-p", $ComposeProjectName)
    }
    $composeDownArgs = @($composeArgs + @("down", "--remove-orphans"))
    & docker @composeDownArgs

    Write-Host "[start] starting docker compose (gateway + replay)"
    $composeUpArgs = @($composeArgs + @("up", "-d", "--build"))
    & docker @composeUpArgs

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
        throw "Gateway did not respond at http://127.0.0.1:$GatewayPort before timeout. Skipping ngrok startup."
    }
    Write-Host "[start] gateway is healthy at http://127.0.0.1:$GatewayPort"

    Write-Host "[start] live analysis / training is optional and not auto-started."
    Write-Host "[start] to run it later: powershell -ExecutionPolicy Bypass -File scripts\launch_live_analysis.ps1 -AttachOnly"
    Write-Host "[start] in the UI, use Home for summary, Replay for review, Improvement for trends, and Training to launch drills."

    Write-Host "[start] starting ngrok"
    & powershell -ExecutionPolicy Bypass -File "scripts\ngrok_dashboard.ps1" -Port $GatewayPort -Domain $Domain
}
finally {
    Pop-Location
}
