param(
    [string]$Entry = "Milestone_1\extract_player_data.py",
    [string]$ReplayPath = ""
)

$ErrorActionPreference = "Stop"

if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    throw "Virtual environment not found. Run scripts/bootstrap.ps1 first."
}

function Resolve-InitialReplayDirectory {
    $documentRoots = @()

    $knownDocs = [Environment]::GetFolderPath("MyDocuments")
    if (-not [string]::IsNullOrWhiteSpace($knownDocs)) {
        $documentRoots += $knownDocs
    }

    if (-not [string]::IsNullOrWhiteSpace($env:OneDrive)) {
        $documentRoots += (Join-Path $env:OneDrive "Documents")
    }
    if (-not [string]::IsNullOrWhiteSpace($env:OneDriveCommercial)) {
        $documentRoots += (Join-Path $env:OneDriveCommercial "Documents")
    }
    if (-not [string]::IsNullOrWhiteSpace($env:OneDriveConsumer)) {
        $documentRoots += (Join-Path $env:OneDriveConsumer "Documents")
    }

    if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        $userOneDriveDirs = Get-ChildItem -Path $env:USERPROFILE -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "OneDrive*" } |
            Select-Object -ExpandProperty FullName
        foreach ($dir in $userOneDriveDirs) {
            $documentRoots += (Join-Path $dir "Documents")
        }
        $documentRoots += (Join-Path $env:USERPROFILE "Documents")
    }

    $documentRoots = $documentRoots | Where-Object { $_ } | Select-Object -Unique

    $demosEpicCandidates = @()
    $demosCandidates = @()
    foreach ($docs in $documentRoots) {
        $demosEpicCandidates += (Join-Path $docs "My Games\Rocket League\TAGame\DemosEpic")
        $demosEpicCandidates += (Join-Path $docs "My Games\Rocket League\TAGame\Demos Epic")
        $demosCandidates += (Join-Path $docs "My Games\Rocket League\TAGame\Demos")
    }

    $candidates = @()
    $candidates += $demosEpicCandidates
    $candidates += $demosCandidates
    $candidates += $documentRoots
    $candidates += (Get-Location).Path

    foreach ($path in $candidates) {
        if ($path -and (Test-Path -Path $path -PathType Container)) {
            return $path
        }
    }

    return (Get-Location).Path
}

if ([string]::IsNullOrWhiteSpace($ReplayPath)) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Select a Rocket League replay file"
    $dialog.Filter = "Rocket League Replays (*.replay)|*.replay|All Files (*.*)|*.*"
    $dialog.InitialDirectory = Resolve-InitialReplayDirectory
    $dialog.Multiselect = $false

    $result = $dialog.ShowDialog()
    if ($result -ne [System.Windows.Forms.DialogResult]::OK -or [string]::IsNullOrWhiteSpace($dialog.FileName)) {
        Write-Host "Replay selection canceled. Exiting."
        exit 0
    }

    $ReplayPath = $dialog.FileName
}

if (!(Test-Path -Path $ReplayPath -PathType Leaf)) {
    throw "Replay file not found: $ReplayPath"
}

& .\.venv\Scripts\python.exe $Entry --replay $ReplayPath
