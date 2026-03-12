param(
    [int]$Port = 8888,
    [string]$Domain = ""
)

$ErrorActionPreference = "Stop"

$ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
if (-not $ngrok) {
    throw "ngrok not found in PATH. Install ngrok and try again."
}

Write-Host "[ngrok] exposing http://127.0.0.1:$Port"
if ($Domain) {
    Write-Host "[ngrok] using reserved domain: https://$Domain"
    & $ngrok.Path http $Port --domain $Domain
} else {
    & $ngrok.Path http $Port
}
