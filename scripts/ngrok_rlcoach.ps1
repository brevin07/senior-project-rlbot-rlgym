param(
    [string]$Domain = "rlcoach.ngrok.app",
    [int]$Port = 8888
)

$ErrorActionPreference = "Stop"

$ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
if (-not $ngrok) {
    throw "ngrok not found in PATH. Install ngrok and try again."
}

Write-Host "[ngrok] exposing http://127.0.0.1:$Port as https://$Domain"
& $ngrok.Path http $Port --domain $Domain
