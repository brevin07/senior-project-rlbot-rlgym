param(
    [string]$Entry = "rlbot_training\rlbot_starting_code.py",
    [string]$Checkpoint = ""
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

$pythonExe = Resolve-VenvPython
if (-not $pythonExe) {
    throw "Virtual environment not found. Run scripts/bootstrap.ps1 first."
}

$argsList = @($Entry)
if ($Checkpoint) {
    $argsList += @("--checkpoint-load-folder", $Checkpoint)
}

& $pythonExe @argsList
