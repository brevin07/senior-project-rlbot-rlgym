$ready = $false
$tries = 0
while ($tries -lt 20) {
    docker info 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Write-Host "Waiting for Docker... attempt $tries"
    Start-Sleep -Seconds 3
    $tries++
}
if ($ready) { Write-Host "Docker is ready!" } else { Write-Host "Docker timed out" }
