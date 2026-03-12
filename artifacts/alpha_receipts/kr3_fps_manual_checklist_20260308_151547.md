# KR3 FPS Manual Verification Checklist

## Goal
Prove runtime visualizer performance is >30 FPS while replay playback is active.

## Steps
1. Launch replay dashboard:
   powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1
2. Load replay and open visualizer.
3. Open debug panel/bubble where FPS: is shown.
4. Set playback speed to 1x and run for at least 30 seconds.
5. Capture screenshots around ~10s, ~20s, ~30s.

## Pass Condition
- Each screenshot shows FPS: <value> where value > 30.0.
- Playback remains stable (no crash).
- Event markers/pause behavior is observable during playback.

## Attach
- 3 FPS screenshots.
- One screenshot showing pause on event marker.
- Latest rtifacts/alpha_receipts/alpha_receipts_*.md.
