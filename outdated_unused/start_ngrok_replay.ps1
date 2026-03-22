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

Write-Host "[start_ngrok_replay] deprecated wrapper -> scripts\start_rlcoach_app.ps1"
$argsList = @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $repoRoot "scripts\start_rlcoach_app.ps1"),
    "-Domain", $Domain,
    "-GatewayPort", "$GatewayPort",
    "-StartupWaitSeconds", "$StartupWaitSeconds",
    "-EnvFile", $EnvFile
)
if ($ComposeProjectName) { $argsList += @("-ComposeProjectName", $ComposeProjectName) }
if ($NoBrowser) { $argsList += "-NoBrowser" }
if ($BuildReact) { $argsList += "-BuildReact" }

& powershell @argsList
