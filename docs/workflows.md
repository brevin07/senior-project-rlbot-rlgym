# Workflows

## 1) Bootstrap
```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

Use this for local Python-based workflows such as `scripts/run_gateway.ps1`, `scripts/replay_dashboard.ps1`, `scripts/train.ps1`, and replay extraction. The packaged RLCoach launcher below does not require a local venv.

Optional Windows installer build:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_rlbot_installer.ps1
```

This builds `dist/RLBotStackInstaller.exe`, which is intended for end users who need a single installer for RLBot GUI, a local `RLBotPack` copy, and the repo's Python/runtime dependencies.

Optional RLDojo playlist-only installer build:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_rldojo_playlists_installer.ps1
```

This builds `dist/RLDojoPlaylistsInstaller.exe`, which installs the RocketCoach RLDojo mechanic playlists into the user's AppData playlist folder.

## 2) Packaged RLCoach App
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_rlcoach_app.ps1
```

Default behavior:
- loads `.env` and validates the required backend/frontend auth settings
- reuses cached Docker images when the relevant inputs are unchanged
- rebuilds only the replay or gateway image that needs it, unless `-RebuildContainers` is passed
- starts the self-contained replay and gateway containers from `docker-compose.rlcoach-app.yml`
- waits for gateway health, then starts ngrok for the dashboard surface

This is the canonical packaged entrypoint for the hosted-style dashboard experience.

Useful refresh flags:
- `-RebuildContainers` forces a rebuild of both images
- `-ResetCompose` removes the compose stack before startup

## 3) RLBot Training Bridge
```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_training_bridge.ps1
```

Use this when you want the dashboard `Training` tab to launch RLBot + RLDojo drills on the Windows host.

The bridge:
- runs on the Windows host at `http://127.0.0.1:8766`
- performs the authoritative RLBot preflight checks for the Training tab
- verifies RLBot GUI, Rocket League, RLBotPack, RLDojo playlists, and mapped bot dependencies
- launches or swaps RLBot/RLDojo sessions when the user presses `Train Against Bot`

The Training tab auto-runs this deep preflight, caches it briefly, and exposes `Re-run Checks` for a manual refresh after the user installs missing dependencies.
When the RocketCoach installer has been run on a machine, the website can also use `Verify Dependencies` to wake the local companion through the registered `rocketcoach://` protocol before polling the bridge for fresh results.

## 4) Train
```powershell
powershell -ExecutionPolicy Bypass -File scripts/train.ps1
```

Default script target:
- `rlbot_training/rlbot_starting_code.py`

## 5) Live Analysis
```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_live_analysis.ps1
```

Default script target:
- `rocketcoach/live_analysis/run_live_analysis.py`

## 6) Replay Extraction / Analysis
```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_extract.ps1
```

Default script target:
- `rocketcoach/extract_player_data.py`

## 7) Replay 3D Dashboard
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
- `scripts/start_rlcoach_app.ps1` is now the canonical packaged startup path; `scripts/run_gateway.ps1` remains the local non-Docker alternative.
- Replay opening no longer waits for all coaching text to finish generating before the studio becomes usable.
- RLBot dependency verification happens on the host training bridge, not inside the replay container.
