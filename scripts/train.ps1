param(
    [string]$Entry = "rlbot_training\rlbot_starting_code.py"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    throw "Virtual environment not found. Run scripts/bootstrap.ps1 first."
}

& .\.venv\Scripts\python.exe $Entry
