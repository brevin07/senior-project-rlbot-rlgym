param(
    [string]$Entry = "",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8775,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

function Resolve-VenvPython {
    $candidates = @(
        ".\venv\Scripts\python.exe",
        ".\venv\bin\python"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    return $null
}

if (-not $Entry) {
    $Entry = "rocketcoach\replay_dashboard\run_replay_dashboard.py"
}

$pythonExe = Resolve-VenvPython
if (-not $pythonExe) {
    throw "Virtual environment not found. Run scripts/bootstrap.ps1 first."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$argsList = @($Entry, "--host", $BindHost, "--port", "$Port")
if ($NoBrowser) {
    $argsList += "--no-browser"
}

& $pythonExe @argsList
