param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765,
    [int]$PlayerIndex = 0,
    [double]$TickRate = 30.0,
    [double]$WindowSeconds = 10.0,
    [int]$StabilizationTicks = 15,
    [double]$BotSkill = 1.0,
    [string]$DefaultScenario = "",
    [string]$ScenarioRoot = "",
    [ValidateSet("tuck", "none")] [string]$NoBotMode = "tuck",
    [ValidateSet("epic", "steam", "auto")] [string]$Launcher = "epic",
    [switch]$AttachOnly,
    [switch]$NoBrowser,
    [switch]$SkipBootstrap
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-VenvPython([string]$root) {
    $winPy = Join-Path $root "venv\Scripts\python.exe"
    if (Test-Path $winPy) {
        return $winPy
    }
    $posixPy = Join-Path $root "venv\bin\python"
    if (Test-Path $posixPy) {
        return $posixPy
    }
    return $null
}

Push-Location $repoRoot
try {
    $venvPython = Resolve-VenvPython $repoRoot
    if (!(Test-Path $venvPython)) {
        if ($SkipBootstrap) {
            throw "Virtual environment missing and -SkipBootstrap was provided."
        }
        Write-Host "[launcher] venv not found. Bootstrapping..."
        & powershell -ExecutionPolicy Bypass -File ".\scripts\bootstrap.ps1"
        $venvPython = Resolve-VenvPython $repoRoot
    }
    if (!(Test-Path $venvPython)) {
        throw "Unable to resolve python executable inside venv."
    }

    # Verify minimum runtime imports and self-heal if missing.
    $importCheck = @"
import importlib.util, sys
mods = ["rlbot", "rlgym", "rlgym_ppo", "rlgym_sim", "matplotlib", "seaborn"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(",".join(missing))
sys.exit(0 if not missing else 1)
"@
    $importCheck | & $venvPython -
    if ($LASTEXITCODE -ne 0) {
        if ($SkipBootstrap) {
            throw "Missing required packages and -SkipBootstrap was provided."
        }
        Write-Host "[launcher] Installing required packages..."
        & $venvPython -m pip install -r ".\requirements.txt"
        & $venvPython -m pip install "flatbuffers>=24.3.25"
    }

    $cmd = @(
        "Milestone_1\live_analysis\run_live_analysis.py",
        "--host", $BindHost,
        "--port", "$Port",
        "--player-index", "$PlayerIndex",
        "--tick-rate", "$TickRate",
        "--window-seconds", "$WindowSeconds",
        "--stabilization-ticks", "$StabilizationTicks",
        "--bot-skill", "$BotSkill",
        "--no-bot-mode", "$NoBotMode",
        "--launcher", "$Launcher"
    )
    if ($DefaultScenario) {
        $cmd += @("--default-scenario", "$DefaultScenario")
    }
    if ($ScenarioRoot) {
        $cmd += @("--scenario-root", "$ScenarioRoot")
    }
    if ($AttachOnly) {
        $cmd += "--attach-only"
    }
    if ($NoBrowser) {
        $cmd += "--no-browser"
    }

    $env:RLBOT_LIVE_ANALYSIS_LAUNCHED = "1"
    Write-Host "[launcher] Starting live analysis..."
    Write-Host "[launcher] Dashboard URL: http://$BindHost`:$Port"
    if ($AttachOnly) {
        Write-Host "[launcher] Mode: attach-only"
    } else {
        Write-Host "[launcher] Mode: auto-start match"
    }
    & $venvPython @cmd
}
finally {
    Remove-Item Env:\RLBOT_LIVE_ANALYSIS_LAUNCHED -ErrorAction SilentlyContinue
    Pop-Location
}
