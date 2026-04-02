param(
    [string]$Domain = "rlcoach.ngrok.app",
    [int]$GatewayPort = 8888,
    [switch]$BuildReact,
    [switch]$NoBrowser,
    [switch]$RebuildContainers,
    [switch]$ResetCompose,
    [int]$StartupWaitSeconds = 30,
    [string]$EnvFile = ".env",
    [string]$ComposeProjectName = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot "docker-compose.rlcoach-app.yml"
$buildStateDir = Join-Path $repoRoot ".cache\rlcoach"
$buildStateFile = Join-Path $buildStateDir "docker-build-state.json"
$defaultDbDir = Join-Path $repoRoot "artifacts\data"

function Test-CommandAvailable([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-CheckedCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$FailureMessage,
        [hashtable]$EnvironmentOverrides = @{}
    )

    $previousEnv = @{}
    foreach ($entry in $EnvironmentOverrides.GetEnumerator()) {
        $name = [string]$entry.Key
        $previousEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, [string]$entry.Value, "Process")
    }

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $quotedArgs = @()
        foreach ($argument in $Arguments) {
            $text = [string]$argument
            if ($text.Contains('"')) {
                $text = $text.Replace('"', '\"')
            }
            if ($text -match '\s') {
                $quotedArgs += ('"{0}"' -f $text)
            } else {
                $quotedArgs += $text
            }
        }
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $FilePath
        $psi.Arguments = ($quotedArgs -join ' ')
        $psi.WorkingDirectory = $repoRoot
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true

        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $psi
        $process.EnableRaisingEvents = $true
        [void]$process.Start()

        while (-not $process.HasExited) {
            while (-not $process.StandardOutput.EndOfStream) {
                $line = $process.StandardOutput.ReadLine()
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host $line
                }
            }
            while (-not $process.StandardError.EndOfStream) {
                $line = $process.StandardError.ReadLine()
                if (-not [string]::IsNullOrWhiteSpace($line)) {
                    Write-Host $line
                }
            }
            Start-Sleep -Milliseconds 100
        }
        while (-not $process.StandardOutput.EndOfStream) {
            $line = $process.StandardOutput.ReadLine()
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Host $line
            }
        }
        while (-not $process.StandardError.EndOfStream) {
            $line = $process.StandardError.ReadLine()
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Host $line
            }
        }
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    }
    finally {
        $stopwatch.Stop()
        foreach ($name in $previousEnv.Keys) {
            [Environment]::SetEnvironmentVariable($name, $previousEnv[$name], "Process")
        }
    }
    if ($exitCode -ne 0) {
        throw $FailureMessage
    }
    Write-Host ("[start] command finished in {0:n1}s" -f $stopwatch.Elapsed.TotalSeconds)
}

function Invoke-ServiceBuild {
    param(
        [string[]]$ComposeArgs,
        [string]$ServiceName,
        [int]$ServiceIndex,
        [int]$ServiceCount
    )

    $percentBefore = [int](($ServiceIndex / [Math]::Max($ServiceCount, 1)) * 100)
    $percentAfter = [int]((($ServiceIndex + 1) / [Math]::Max($ServiceCount, 1)) * 100)
    Write-Progress -Id 1 -Activity "Building RLCoach Docker Images" -Status "Starting $ServiceName" -PercentComplete $percentBefore
    Write-Host ("[start] building service {0}/{1}: {2}" -f ($ServiceIndex + 1), $ServiceCount, $ServiceName)
    Invoke-CheckedCommand `
        -FilePath "docker" `
        -Arguments @($ComposeArgs + @("build", $ServiceName)) `
        -FailureMessage "docker compose build failed for service '$ServiceName'." `
        -EnvironmentOverrides @{ "DOCKER_BUILDKIT" = "1"; "BUILDKIT_PROGRESS" = "plain" }
    Write-Progress -Id 1 -Activity "Building RLCoach Docker Images" -Status "Finished $ServiceName" -PercentComplete $percentAfter
}

function Import-DotEnvFile([string]$Path) {
    if (!(Test-Path $Path)) {
        throw "Missing env file: $Path"
    }
    foreach ($line in Get-Content $Path) {
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith("#")) {
            continue
        }
        $parts = $trim -split "=", 2
        if ($parts.Length -ne 2) {
            continue
        }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.StartsWith('"') -and $value.EndsWith('"') -and $value.Length -ge 2) {
            $value = $value.Substring(1, $value.Length - 2)
        } elseif ($value.StartsWith("'") -and $value.EndsWith("'") -and $value.Length -ge 2) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Get-RelativeRepoPath([string]$Path) {
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $repoWithSlash = $repoRoot.TrimEnd("\") + "\"
    if ($fullPath.StartsWith($repoWithSlash, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $fullPath.Substring($repoWithSlash.Length).Replace("\", "/")
    }
    return [System.IO.Path]::GetFileName($fullPath)
}

function Get-Sha256ForText([string]$Text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        $hash = $sha.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-FingerprintEntries([string[]]$RelativePaths) {
    $entries = New-Object System.Collections.Generic.List[string]

    foreach ($relativePath in $RelativePaths) {
        $absolutePath = Join-Path $repoRoot $relativePath
        if (!(Test-Path $absolutePath)) {
            $entries.Add("$relativePath|missing")
            continue
        }

        $item = Get-Item $absolutePath
        if ($item.PSIsContainer) {
            $files = Get-ChildItem -Path $absolutePath -File -Recurse | Sort-Object FullName
            if ($files.Count -eq 0) {
                $entries.Add("$relativePath|empty")
            }
            foreach ($file in $files) {
                $hash = (Get-FileHash -Path $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                $entries.Add("$(Get-RelativeRepoPath $file.FullName)|$hash")
            }
            continue
        }

        $singleHash = (Get-FileHash -Path $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $entries.Add("$(Get-RelativeRepoPath $item.FullName)|$singleHash")
    }

    return ($entries | Sort-Object)
}

function Get-BuildFingerprint([string[]]$RelativePaths) {
    $entries = Get-FingerprintEntries -RelativePaths $RelativePaths
    return Get-Sha256ForText -Text (($entries -join "`n") + "`n")
}

function Read-BuildState([string]$Path) {
    if (!(Test-Path $Path)) {
        return @{}
    }
    try {
        $raw = Get-Content -Path $Path -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return @{}
        }
        $parsed = $raw | ConvertFrom-Json
        if ($null -eq $parsed) {
            return @{}
        }
        $state = @{}
        foreach ($property in $parsed.PSObject.Properties) {
            $state[$property.Name] = [string]$property.Value
        }
        return $state
    }
    catch {
        Write-Warning "[start] build state at $Path is unreadable; forcing image rebuilds."
        return @{}
    }
}

function Write-BuildState([string]$Path, [hashtable]$State) {
    $stateDir = Split-Path -Parent $Path
    if ($stateDir) {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    }
    ($State | ConvertTo-Json -Depth 8) | Set-Content -Path $Path -Encoding UTF8
}

function Test-DockerImageExists([string]$ImageName) {
    & docker image inspect $ImageName *> $null
    return ($LASTEXITCODE -eq 0)
}

function Get-ComposeArgs([string]$ComposeFilePath, [string]$EnvFilePath, [string]$ProjectName) {
    $args = @("compose", "--env-file", $EnvFilePath, "-f", $ComposeFilePath)
    if ($ProjectName) {
        $args += @("-p", $ProjectName)
    }
    return $args
}

function Assert-RequiredEnv([string[]]$Names) {
    $missing = @()
    foreach ($name in $Names) {
        $value = [Environment]::GetEnvironmentVariable($name, "Process")
        if ([string]::IsNullOrWhiteSpace($value)) {
            $missing += $name
        }
    }
    if ($missing.Count -gt 0) {
        throw ("Missing required environment variables: " + ($missing -join ", "))
    }
}

Push-Location $repoRoot
try {
    if (-not (Test-CommandAvailable "docker")) {
        throw "docker not found in PATH. Install Docker Desktop and try again."
    }
    if (-not (Test-CommandAvailable "ngrok")) {
        throw "ngrok not found in PATH. Install ngrok and try again."
    }
    if (!(Test-Path $composeFile)) {
        throw "Missing compose file: $composeFile"
    }

    Write-Host "[start] checking Docker daemon availability"
    Invoke-CheckedCommand -FilePath "docker" -Arguments @("info") -FailureMessage "Docker is installed but the daemon is not reachable."

    $resolvedEnvPath = if ([System.IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $repoRoot $EnvFile }
    Write-Host "[start] loading environment from $resolvedEnvPath"
    Import-DotEnvFile -Path $resolvedEnvPath

    $appDataDir = [Environment]::GetEnvironmentVariable("RLBOT_APP_DATA_DIR", "Process")
    if ([string]::IsNullOrWhiteSpace($appDataDir)) {
        $appDataDir = $defaultDbDir
        [Environment]::SetEnvironmentVariable("RLBOT_APP_DATA_DIR", $appDataDir, "Process")
    }
    New-Item -ItemType Directory -Path $appDataDir -Force | Out-Null
    Write-Host "[start] packaged app data is persisted on the host at $appDataDir"
    Write-Host ("[start] shared dashboard database path: " + (Join-Path $appDataDir "app.db"))
    Assert-RequiredEnv -Names @(
        "COGNITO_ISSUER",
        "COGNITO_CLIENT_ID",
        "VITE_COGNITO_AUTHORITY",
        "VITE_COGNITO_USER_POOL_ID",
        "VITE_COGNITO_CLIENT_ID",
        "VITE_COGNITO_SCOPE"
    )

    if ($BuildReact) {
        Write-Warning "[start] -BuildReact is deprecated for app startup. The dashboard build now runs inside Docker."
    }
    if ($NoBrowser) {
        Write-Host "[start] browser auto-open is already disabled for this launcher."
    }

    $composeArgs = Get-ComposeArgs -ComposeFilePath $composeFile -EnvFilePath $resolvedEnvPath -ProjectName $ComposeProjectName

    if ($ResetCompose) {
        Write-Host "[start] resetting docker compose state"
        $composeDownArgs = @($composeArgs + @("down", "--remove-orphans"))
        Invoke-CheckedCommand -FilePath "docker" -Arguments $composeDownArgs -FailureMessage "docker compose down failed."
    } else {
        Write-Host "[start] leaving existing docker compose state intact"
    }

    $replayInputs = @(
        "Dockerfile.replay",
        "docker-compose.rlcoach-app.yml",
        "requirements.txt",
        "requirements",
        "rocketcoach\common",
        "rocketcoach\extract_player_data.py",
        "rocketcoach\live_analysis",
        "rocketcoach\replay_dashboard",
        "collision_meshes"
    )
    $gatewayInputs = @(
        "Dockerfile.gateway",
        "docker-compose.rlcoach-app.yml",
        "rocketcoach\dashboard_gateway",
        "frontend\dashboard\package.json",
        "frontend\dashboard\package-lock.json",
        "frontend\dashboard\index.html",
        "frontend\dashboard\src"
    )

    $buildState = Read-BuildState -Path $buildStateFile
    $currentFingerprints = @{
        replay = Get-BuildFingerprint -RelativePaths $replayInputs
        gateway = Get-BuildFingerprint -RelativePaths $gatewayInputs
    }
    $expectedImages = @{
        replay = "rlcoach-replay:local"
        gateway = "rlcoach-gateway:local"
    }

    $servicesToBuild = New-Object System.Collections.Generic.List[string]
    foreach ($serviceName in @("replay", "gateway")) {
        $imageName = $expectedImages[$serviceName]
        $imageExists = Test-DockerImageExists -ImageName $imageName
        $previousFingerprint = $null
        if ($buildState.ContainsKey($serviceName)) {
            $previousFingerprint = $buildState[$serviceName]
        }

        if ($RebuildContainers) {
            $servicesToBuild.Add($serviceName)
            continue
        }
        if (-not $imageExists) {
            Write-Host "[start] $serviceName image is missing; scheduling build"
            $servicesToBuild.Add($serviceName)
            continue
        }
        if ($null -eq $previousFingerprint -or [string]::IsNullOrWhiteSpace([string]$previousFingerprint)) {
            Write-Host "[start] $serviceName image exists with no cached fingerprint; initializing cache from current inputs"
            continue
        }
        if ($previousFingerprint -ne $currentFingerprints[$serviceName]) {
            Write-Host "[start] $serviceName inputs changed; scheduling rebuild"
            $servicesToBuild.Add($serviceName)
        }
    }

    if ($RebuildContainers) {
        Write-Host "[start] rebuild requested"
    }

    if ($servicesToBuild.Count -gt 0) {
        Write-Host ("[start] building services: " + ($servicesToBuild -join ", "))
        for ($i = 0; $i -lt $servicesToBuild.Count; $i++) {
            Invoke-ServiceBuild -ComposeArgs $composeArgs -ServiceName $servicesToBuild[$i] -ServiceIndex $i -ServiceCount $servicesToBuild.Count
        }
        Write-Progress -Id 1 -Activity "Building RLCoach Docker Images" -Completed
        Write-BuildState -Path $buildStateFile -State $currentFingerprints
    } else {
        Write-Host "[start] reusing cached Docker images"
        Write-BuildState -Path $buildStateFile -State $currentFingerprints
    }

    Write-Host "[start] starting docker compose (gateway + replay)"
    $composeUpArgs = @($composeArgs + @("up", "-d", "--remove-orphans"))
    Invoke-CheckedCommand -FilePath "docker" -Arguments $composeUpArgs -FailureMessage "docker compose up failed."

    Write-Host "[start] waiting for gateway to become reachable..."
    $deadline = (Get-Date).AddSeconds([double]$StartupWaitSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$GatewayPort/api/health" -UseBasicParsing -TimeoutSec 2
            if ($resp.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    if (-not $ready) {
        throw "Gateway did not respond at http://127.0.0.1:$GatewayPort before timeout. Skipping ngrok startup."
    }
    Write-Host "[start] gateway is healthy at http://127.0.0.1:$GatewayPort"

    try {
        $replayResp = Invoke-WebRequest -Uri "http://127.0.0.1:$GatewayPort/api/replay" -UseBasicParsing -TimeoutSec 5
        if ($replayResp.StatusCode -eq 200) {
            Write-Host "[start] replay service is reachable through the gateway"
        }
    } catch {
        Write-Warning "[start] gateway is healthy, but replay health passthrough did not respond yet."
    }

    Write-Host "[start] live analysis / training is optional and not auto-started."
    Write-Host "[start] to run it later: powershell -ExecutionPolicy Bypass -File scripts\launch_live_analysis.ps1 -AttachOnly"
    Write-Host "[start] in the UI, use Home for summary, Replay for review, Improvement for trends, and Training to launch drills."
    Write-Host "[start] local dashboard URL: http://127.0.0.1:$GatewayPort"
    Write-Host "[start] starting ngrok for the dashboard surface"
    & powershell -ExecutionPolicy Bypass -File "scripts\ngrok_dashboard.ps1" -Port $GatewayPort -Domain $Domain
}
finally {
    Pop-Location
}
