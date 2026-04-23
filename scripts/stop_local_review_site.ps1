param(
    [int[]]$Ports = @(8775, 8888)
)

$ErrorActionPreference = "Stop"

$pids = New-Object System.Collections.Generic.HashSet[int]

foreach ($port in $Ports) {
    $lines = netstat -ano | Select-String ":$port"
    foreach ($line in $lines) {
        $parts = ($line.ToString() -split "\s+") | Where-Object { $_ }
        if ($parts.Length -ge 5) {
            $pidValue = 0
            if ([int]::TryParse($parts[-1], [ref]$pidValue)) {
                [void]$pids.Add($pidValue)
            }
        }
    }
}

foreach ($pidValue in $pids) {
    try {
        Stop-Process -Id $pidValue -Force -ErrorAction Stop
        Write-Host "[review] Stopped process $pidValue"
    } catch {
        Write-Warning ("[review] Could not stop process {0}: {1}" -f $pidValue, $_.Exception.Message)
    }
}

if ($pids.Count -eq 0) {
    Write-Host "[review] No local review site processes found on ports $($Ports -join ', ')."
}
