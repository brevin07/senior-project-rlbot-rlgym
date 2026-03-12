param(
    [string]$ReplayPath = "",
    [string]$RrrocketPath = "",
    [string]$DbPath = "artifacts\data\app.db",
    [string]$OutputDir = "artifacts\alpha_receipts"
)

$ErrorActionPreference = "Stop"

Write-Host "[alpha_tests] Running automated KR tests (KR1/KR2/KR3-code/KR4)..."
$receiptArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "scripts\alpha_receipts.ps1",
    "-DbPath", $DbPath,
    "-OutputDir", $OutputDir
)
if (-not [string]::IsNullOrWhiteSpace($ReplayPath)) {
    $receiptArgs += @("-ReplayPath", $ReplayPath)
}
if (-not [string]::IsNullOrWhiteSpace($RrrocketPath)) {
    $receiptArgs += @("-RrrocketPath", $RrrocketPath)
}
powershell @receiptArgs

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$manualPath = Join-Path $OutputDir ("kr3_fps_manual_checklist_{0}.md" -f $ts)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$manual = @"
# KR3 FPS Manual Verification Checklist

## Goal
Prove runtime visualizer performance is >30 FPS while replay playback is active.

## Steps
1. Launch replay dashboard:
   `powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1`
2. Load replay and open visualizer.
3. Open debug panel/bubble where `FPS:` is shown.
4. Set playback speed to 1x and run for at least 30 seconds.
5. Capture screenshots around ~10s, ~20s, ~30s.

## Pass Condition
- Each screenshot shows `FPS: <value>` where value > 30.0.
- Playback remains stable (no crash).
- Event markers/pause behavior is observable during playback.

## Attach
- 3 FPS screenshots.
- One screenshot showing pause on event marker.
- Latest `artifacts/alpha_receipts/alpha_receipts_*.md`.
"@

Set-Content -Path $manualPath -Value $manual -Encoding UTF8
Write-Host "[alpha_tests] Wrote KR3 manual checklist: $manualPath"
Write-Host "[alpha_tests] See docs/alpha-test-cases.md for full case matrix."
