param(
    [string]$Entry = "",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8775,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-VenvPython {
    param(
        [string]$root
    )

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

if (-not $Entry) {
    $Entry = "rocketcoach.replay_dashboard.run_replay_dashboard"
}

Push-Location $repoRoot
try {
    $pythonExe = Resolve-VenvPython $repoRoot
    if (-not $pythonExe) {
        throw "Virtual environment not found. Run scripts/bootstrap.ps1 first."
    }

    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONPATH = $repoRoot

    $argsList = @("-m", $Entry, "--host", $BindHost, "--port", "$Port")
    if ($NoBrowser) {
        $argsList += "--no-browser"
    }

    & $pythonExe @argsList
}
finally {
    Pop-Location
}
