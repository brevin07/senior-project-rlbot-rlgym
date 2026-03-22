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
powershell -ExecutionPolicy Bypass -File scripts/launch_live_analysis.ps1
```

Default script target:
- `rocketcoach/live_analysis/run_live_analysis.py`

## 4) Replay Extraction / Analysis
```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_extract.ps1
```

Default script target:
- `rocketcoach/extract_player_data.py`

## 5) Replay 3D Dashboard
```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1
```

Default script target:
- `rocketcoach/replay_dashboard/run_replay_dashboard.py`

Developer dashboard launcher:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dev_dashboard.ps1
```

## Notes
- These wrappers preserve stable team entrypoints while `rocketcoach/` remains the canonical runtime package.
- For project refactors, keep wrapper interfaces stable so team workflows are not broken.
