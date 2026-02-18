# RLGym_Bot_Training

Code-first Rocket League bot training and analysis workspace.

This repository now prioritizes:
- reproducible code workflows,
- minimal git bloat,
- clean separation of training, live analysis, and replay analysis,
- external storage for heavy artifacts (models, checkpoints, replay dumps).

## Quick Start

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

### Run Training
```powershell
powershell -ExecutionPolicy Bypass -File scripts/train.ps1
```

### Run Live Analysis
```powershell
powershell -ExecutionPolicy Bypass -File scripts/live_analysis.ps1
```

One-click launcher (auto-bootstrap + dependency self-heal):
```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_live_analysis.ps1
```

### Run Replay Extraction
```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_extract.ps1
```

### Run Replay 3D Dashboard
```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1
```

## Repository Layout

```text
.
├─ artifacts/
│  └─ pointers/                  # Metadata pointers to external models/checkpoints
├─ configs/                      # Default YAML config stubs
├─ data/                         # Lightweight tracked samples only
├─ docs/
│  ├─ architecture.md
│  ├─ workflows.md
│  └─ data-policy.md
├─ scripts/                      # Stable PowerShell workflow wrappers + maintenance
├─ src/                          # Migration scaffold for package-based layout
├─ Milestone_1/                  # Existing replay + heuristic tooling
└─ rlbot_training/               # Existing training/runtime code
```

## Artifact Policy

Do not commit:
- model binaries (`.pt`, `.pth`, etc.),
- checkpoint folders,
- replay dumps (`.replay`, large json/csv exports),
- generated plots and logs (`wandb`, `reward_logs`, analysis outputs),
- local binaries (rlviser, rattletrap, rrrocket bundles).

Use external storage and keep only pointer metadata in `artifacts/pointers/`.

## Pre-commit Guardrails

A local pre-commit config is included:
- basic file hygiene checks,
- staged file size gate (`scripts/check_no_large_files.py`, 10 MB limit).

Install:
```powershell
.\.venv\Scripts\python.exe -m pip install pre-commit
.\.venv\Scripts\pre-commit.exe install
```

## History Cleanup (Large Blob Rewrite)

If needed, run:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/history_cleanup.ps1
```

This rewrites git history locally. Coordinate with collaborators before force-pushing.

## Notes

- Existing entrypoints are still preserved to avoid breaking your current workflow.
- `src/` modules are compatibility wrappers to enable gradual migration.
