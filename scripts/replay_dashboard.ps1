param(
    [string]$Entry = "Milestone_1\replay_dashboard\run_replay_dashboard.py",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8775,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    throw "Virtual environment not found. Run scripts/bootstrap.ps1 first."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$argsList = @($Entry, "--host", $BindHost, "--port", "$Port")
if ($NoBrowser) {
    $argsList += "--no-browser"
}

& .\.venv\Scripts\python.exe @argsList
