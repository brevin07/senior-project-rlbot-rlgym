# Workflows

## 1) Bootstrap
```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

## 2) Train
```powershell
powershell -ExecutionPolicy Bypass -File scripts/train.ps1
```

Default script target:
- `rlbot_training/rlbot_starting_code.py`

## 3) Live Analysis
```powershell
powershell -ExecutionPolicy Bypass -File scripts/live_analysis.ps1
```

One-click launcher:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_live_analysis.ps1
```

Default script target:
- `Milestone_1/live_analysis/run_live_analysis.py`

## 4) Replay Extraction / Analysis
```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_extract.ps1
```

Default script target:
- `Milestone_1/extract_player_data.py`

## 5) Replay 3D Dashboard
```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1
```

Default script target:
- `Milestone_1/replay_dashboard/run_replay_dashboard.py`

## Notes
- These wrappers preserve current behavior while the codebase is migrated to a cleaner `src/` layout.
- For project refactors, keep wrapper interfaces stable so team workflows are not broken.
