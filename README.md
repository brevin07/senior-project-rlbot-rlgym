# RLGym_Bot_Training

Rocket League bot training and analysis workspace with two dashboards:

- Live Analysis Dashboard (while running/attaching to a match)
- Replay 3D Dashboard (post-game replay analysis)

## What You Can Run

- `scripts/bootstrap.ps1`: create venv and install dependencies
- `scripts/train.ps1`: run training entrypoint
- `scripts/live_analysis.ps1`: launch live analysis workflow
- `scripts/launch_live_analysis.ps1`: one-click live launcher with dependency self-heal
- `scripts/replay_extract.ps1`: pick a `.replay` and extract replay data
- `scripts/replay_dashboard.ps1`: launch replay dashboard web app

## Prerequisites

- Windows PowerShell
- Python 3.11 or 3.12 installed (`py` launcher recommended)
- Rocket League installed (for live analysis mode)

Notes:
- Bootstrap prefers Python 3.11, then 3.12.
- The project uses `venv/` (not `.venv`) for runtime scripts.

## Setup

From repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

This will:

- create/rebuild `venv/` if needed
- install `requirements/base.txt`
- apply a `flatbuffers` compatibility override
- verify required imports

Dependency files are organized in `requirements/`:

- `requirements/base.txt`: runtime dependencies
- `requirements/dev.txt`: developer tooling
- `requirements/tensorflow.txt`: optional isolated TensorFlow env

## Run Live Analysis Dashboard

Quick start:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/live_analysis.ps1
```

or directly use the launcher:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_live_analysis.ps1
```

Default URL:

- `http://127.0.0.1:8765`

Useful options:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/live_analysis.ps1 -AttachOnly
powershell -ExecutionPolicy Bypass -File scripts/live_analysis.ps1 -Launcher auto
powershell -ExecutionPolicy Bypass -File scripts/live_analysis.ps1 -NoBrowser
powershell -ExecutionPolicy Bypass -File scripts/live_analysis.ps1 -NoBotMode none
```

What these do:

- `-AttachOnly`: attach to an existing RL session instead of auto-starting a match
- `-Launcher epic|steam|auto`: choose RL launcher mode
- `-NoBrowser`: do not auto-open browser
- `-NoBotMode tuck|none`: choose no-bot spawn behavior

## Run Replay 3D Dashboard

Start server:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1
```

Default URL:

- `http://127.0.0.1:8775`

Optional flags:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1 -Port 8776
powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1 -NoBrowser
```

## Replay Extraction

Use file picker:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_extract.ps1
```

Or pass a replay directly:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_extract.ps1 -ReplayPath "C:\path\to\match.replay"
```

## Training

```powershell
powershell -ExecutionPolicy Bypass -File scripts/train.ps1
```

## Common Troubleshooting

- `Virtual environment not found`:
  - Run `scripts/bootstrap.ps1` first.
- Browser did not open:
  - Open the URL manually (`8765` for live, `8775` for replay dashboard).
- Port already in use:
  - Pass `-Port` to the script and use a different port.
- Live mode fails to start match:
  - Try `-AttachOnly` and connect to an already running session.

## Repository Layout

```text
.
|-- artifacts/               # External artifact pointers and generated outputs
|-- configs/                 # Config stubs
|-- data/                    # Lightweight tracked data only
|-- docs/                    # Architecture/workflow notes
|-- scripts/                 # PowerShell workflow wrappers
|-- src/                     # Migration scaffold
|-- Milestone_1/             # Live/replay analysis apps and tooling
`-- rlbot_training/          # Training/runtime code
```

## Artifact Policy

Do not commit large generated artifacts:

- model binaries/checkpoints
- replay dumps and large json/csv exports
- generated plots/logs
- local tool binaries/bundles

Keep pointer metadata under `artifacts/pointers/` when needed.
