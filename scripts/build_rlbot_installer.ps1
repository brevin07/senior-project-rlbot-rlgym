param(
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-VenvPython {
    param([string]$Root)

    $candidates = @(
        (Join-Path $Root "venv\Scripts\python.exe"),
        (Join-Path $Root "venv\bin\python")
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
    $venvPython = Resolve-VenvPython -Root $repoRoot
    if (-not $venvPython) {
        & powershell -ExecutionPolicy Bypass -File ".\scripts\bootstrap.ps1" -Python $Python
        $venvPython = Resolve-VenvPython -Root $repoRoot
    }

    if (-not $venvPython) {
        throw "Unable to resolve python executable inside venv."
    }

    & $venvPython -m pip install -r ".\requirements\installer.txt"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install installer build requirements."
    }

    & $venvPython -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --name "RLBotStackInstaller" `
        --add-data ".\requirements;requirements" `
        --add-data ".\requirements.txt;." `
        --add-data ".\rocketcoach;rocketcoach" `
        --add-data ".\configs;configs" `
        ".\scripts\install_rlbot_stack.py"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    Write-Host "[build_rlbot_installer] Created dist\RLBotStackInstaller.exe"
}
finally {
    Pop-Location
}
