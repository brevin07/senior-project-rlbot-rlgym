param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

function Resolve-PythonCommand {
    param([string]$Requested)

    if ($Requested) {
        return $Requested
    }

    # Prefer Python 3.11 (best RLBot compatibility), then 3.12, then fallback to python in PATH.
    try {
        & py -3.11 -c "import sys; print(sys.executable)" | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return "py -3.11"
        }
    } catch {}

    try {
        & py -3.12 -c "import sys; print(sys.executable)" | Out-Null
        if ($LASTEXITCODE -eq 0) {
            return "py -3.12"
        }
    } catch {}

    return "python"
}

function Resolve-VenvPython {
    $winPy = ".\venv\Scripts\python.exe"
    if (Test-Path $winPy) { return $winPy }

    $posixPy = ".\venv\bin\python"
    if (Test-Path $posixPy) { return $posixPy }

    return $null
}

function Invoke-CommandString {
    param([string]$CommandString)
    Invoke-Expression $CommandString
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $CommandString"
    }
}

$pythonCmd = Resolve-PythonCommand -Requested $Python
Write-Host "[bootstrap] using interpreter: $pythonCmd"

if (!(Test-Path "venv")) {
    Invoke-CommandString "$pythonCmd -m venv venv"
}

$venvPython = Resolve-VenvPython
if (-not $venvPython) {
    throw "Unable to resolve a Python executable inside .\venv."
}

# If the current venv is not 3.11/3.12, rebuild it with preferred interpreter.
$versionLine = (& $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if ($LASTEXITCODE -ne 0) {
    throw "Unable to detect venv Python version."
}
if ($versionLine -notin @("3.11", "3.12")) {
    Write-Host "[bootstrap] rebuilding venv with supported Python version"
    Invoke-CommandString "$pythonCmd -m venv --clear venv"
    $venvPython = Resolve-VenvPython
    if (-not $venvPython) {
        throw "Unable to resolve python executable inside venv after rebuild."
    }
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }

$requirementsFile = ".\requirements\base.txt"
if (!(Test-Path $requirementsFile)) {
    $requirementsFile = ".\requirements.txt"
}
& $venvPython -m pip install -r $requirementsFile
if ($LASTEXITCODE -ne 0) { throw "requirements installation failed." }

# RLBot currently pins an old flatbuffers build that fails on newer Python runtimes.
& $venvPython -m pip install "flatbuffers>=24.3.25"
if ($LASTEXITCODE -ne 0) { throw "flatbuffers compatibility override failed." }

$importCheck = @'
import importlib.util, sys
mods = ["rlbot", "rlgym", "rlgym_ppo", "rlgym_sim", "matplotlib", "seaborn"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(",".join(missing))
sys.exit(0 if not missing else 1)
'@
$importCheck | & $venvPython -
if ($LASTEXITCODE -ne 0) {
    throw "Bootstrap failed: one or more required imports are missing."
}

Write-Host "Bootstrap complete."
