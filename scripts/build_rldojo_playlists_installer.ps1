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
        --name "RLDojoPlaylistsInstaller" `
        ".\scripts\install_rldojo_playlists.py"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    Write-Host "[build_rldojo_playlists_installer] Created dist\RLDojoPlaylistsInstaller.exe"
}
finally {
    Pop-Location
}
