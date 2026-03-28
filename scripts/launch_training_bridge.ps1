param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8766,
    [ValidateSet("epic", "steam", "auto")] [string]$Launcher = "auto",
    [switch]$SkipBootstrap
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-VenvPython([string]$root) {
    $candidates = @(
        (Join-Path $root "venv\Scripts\python.exe"),
        (Join-Path $root "venv\bin\python")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

Push-Location $repoRoot
try {
    $venvPython = Resolve-VenvPython $repoRoot
    if (-not $venvPython) {
        if ($SkipBootstrap) {
            throw "Virtual environment missing and -SkipBootstrap was provided."
        }
        Write-Host "[training_launcher] venv not found. Bootstrapping..."
        & powershell -ExecutionPolicy Bypass -File ".\scripts\bootstrap.ps1"
        $venvPython = Resolve-VenvPython $repoRoot
    }
    if (-not $venvPython) {
        throw "Unable to resolve python executable inside venv."
    }

    Write-Host "[training_launcher] Starting host training bridge..."
    & $venvPython -m rocketcoach.training.launcher_server --host $BindHost --port $Port --launcher $Launcher
}
finally {
    Pop-Location
}
