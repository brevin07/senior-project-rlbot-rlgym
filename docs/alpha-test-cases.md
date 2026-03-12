# Alpha Test Cases (Proof-Oriented)

This test pack is designed to produce screenshot-friendly evidence for Alpha KR1-KR4.

## Preconditions

- Windows PowerShell from repository root.
- Python env with dependencies installed (including `pandas`).
- `rrrocket.exe` available (either on `PATH`, via `RRROCKET_BIN`, or passed to scripts).
- A valid `.replay` file available locally.

## Test Case Matrix

### TC-KR1-001: Replay parses into queryable Pandas structure
- KR: `KR1`
- Type: Automated
- Command:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/alpha_receipts.ps1 -ReplayPath "C:\path\to\match.replay" -RrrocketPath "C:\path\to\rrrocket.exe"
```
- Expected:
  - `KR1: PASS` in terminal summary.
  - Generated report includes `df_rows > 0`.
  - Required columns exist: `time`, `Ball_x`, `Ball_y`, `Ball_z`.
- Screenshot receipts:
  - Terminal output showing KR1 PASS.
  - Generated report (`artifacts/alpha_receipts/*.md`) KR1 details block.

### TC-KR2-001: Top-3 weaknesses are deterministically derived
- KR: `KR2`
- Type: Automated
- Command:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/alpha_receipts.ps1
```
- Expected:
  - `KR2: PASS` in terminal summary.
  - Report contains `weakest_three` with exactly 3 mechanic IDs and scores.
- Screenshot receipts:
  - Terminal output showing KR2 PASS.
  - Report section listing `weakest_three`.

### TC-KR3-001: Visualizer pauses at mistake timestamps
- KR: `KR3` (pause behavior)
- Type: Manual runtime verification
- Setup:
  - Start replay dashboard and load a replay with mechanic events.
  - In replay studio/visualizer, press play through timeline markers.
- Expected:
  - Playback auto-pauses when crossing mechanic event marker timestamps.
  - Event popup/context appears for the paused event.
- Screenshot receipts:
  - Visualizer paused on event marker with event popup visible.
  - Timeline showing event markers and paused play state.

### TC-KR3-002: Visualizer runtime FPS > 30
- KR: `KR3` (performance)
- Type: Manual runtime benchmark with deterministic pass criterion
- Setup:
  - Launch replay dashboard.
  - Use a replay timeline with active playback.
  - Open legacy debug bubble (`Debug`) where `FPS:` is shown.
- Measurement procedure:
  1. Set playback speed to `1x`.
  2. Let playback run for at least 30 seconds.
  3. Capture 3 screenshots at separated times (e.g., around 10s, 20s, 30s).
- Pass criterion:
  - `FPS` displayed in each capture is `> 30.0`.
- Screenshot receipts:
  - 3 screenshots including `FPS:` line in debug bubble.

### TC-KR4-001: SQL persistence stores and queries replay/user stats
- KR: `KR4`
- Type: Automated
- Command:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/alpha_receipts.ps1
```
- Expected:
  - `KR4: PASS` in terminal summary.
  - Report shows DB tables and row counts.
  - `replay_sessions > 0` and recent session rows include `has_blob=true`.
- Screenshot receipts:
  - Terminal output showing KR4 PASS.
  - Report section with DB row counts and recent sessions.

## Evidence Files

Automated runs write:

- `artifacts/alpha_receipts/alpha_receipts_<timestamp>.json`
- `artifacts/alpha_receipts/alpha_receipts_<timestamp>.md`
- `artifacts/alpha_receipts/kr3_fps_manual_checklist_<timestamp>.md` (from `scripts/run_alpha_test_cases.ps1`)

Attach these files and screenshots in the milestone deliverable as receipts.
