# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

Creates/rebuilds `venv/` (not `.venv`), installs `requirements/base.txt`, and verifies imports. Bootstrap prefers Python 3.11, then 3.12.

### Workflows

```powershell
# Bot training
powershell -ExecutionPolicy Bypass -File scripts/train.ps1

# Live analysis dashboard (http://127.0.0.1:8765)
powershell -ExecutionPolicy Bypass -File scripts/live_analysis.ps1
powershell -ExecutionPolicy Bypass -File scripts/launch_live_analysis.ps1  # one-click with self-heal

# Replay extraction
powershell -ExecutionPolicy Bypass -File scripts/replay_extract.ps1

# Replay 3D dashboard (http://127.0.0.1:8775)
powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1

# Gateway server (http://127.0.0.1:8888) — starts live + replay + gateway
powershell -ExecutionPolicy Bypass -File scripts/run_gateway.ps1

# Full RLCoach startup (loads .env, starts Docker replay+gateway, then ngrok)
powershell -ExecutionPolicy Bypass -File scripts/start_rlcoach_app.ps1 -BuildReact
```

### Frontend (React/Vite)

```bash
cd frontend/dashboard
npm install
npm run dev     # dev server
npm run build   # production build for gateway to serve
```

### Testing

Run from project root, not from inside `tests/`:

```bash
pytest tests/ -v                        # all 48 tests
pytest tests/ -v -s                     # with print output
pytest tests/ -k "attainment" -v        # attainment verification only
pytest tests/test_kr1_replay_parsing.py -v   # KR1: replay parsing (needs rrrocket.exe + replay files)
pytest tests/test_kr2_weakness_detection.py -v  # KR2: weakness detection
pytest tests/test_kr3_visualizer_fps.py -v   # KR3: visualizer FPS (inspects source structure)
pytest tests/test_kr4_database_storage.py -v # KR4: SQLite CRUD
```

KR1 tests skip automatically if `Milestone_1/rrrocket.exe` or `artifacts/replay_library/` are absent.

## Architecture

This repo is in active migration from milestone-era structure toward a cleaner `src/` layout. **`Milestone_1/` is not archival** — it contains active live analysis, replay analysis, dashboard, persistence, and gateway code.

### Runtime Components

| Component | Location | Purpose |
|-----------|----------|---------|
| PPO training entrypoint | `rlbot_training/rlbot_starting_code.py` | Bot training |
| Reward functions | `rlbot_training/reward_funcs/reward_functions.py` | Reward library |
| Replay extraction | `Milestone_1/extract_player_data.py` | rrrocket JSON → gameplay CSV |
| Live analysis server | `Milestone_1/live_analysis/run_live_analysis.py` | Live telemetry HTTP server |
| Live dashboard web | `Milestone_1/live_analysis/web/` | Browser UI for live mode |
| Replay dashboard server | `Milestone_1/replay_dashboard/run_replay_dashboard.py` | Replay HTTP server |
| Replay dashboard web | `Milestone_1/replay_dashboard/web/` | Browser UI for replay mode |
| Gateway server | `Milestone_1/dashboard_gateway/gateway_server.py` | Proxies live+replay behind a single URL |
| React frontend | `frontend/dashboard/` | Vite + React + TypeScript + Three.js UI |
| Heuristic analyzer | `Milestone_1/heuristic_analysis/analyzer.py` | Offline analysis |
| LLM explainer | `Milestone_1/live_analysis/llm_event_explainer.py` | OpenAI-based event explanations |

### URL/Port Map

- Live analysis: `http://127.0.0.1:8765`
- Replay dashboard: `http://127.0.0.1:8775`
- Gateway (all routes): `http://127.0.0.1:8888`
  - React routes: `/live`, `/replay`
  - Legacy UIs: `/legacy/live/`, `/legacy/replay/`

### React Frontend

The frontend (`frontend/dashboard/`) is built with Vite + React 18 + TypeScript + Three.js (for 3D replay visualization). It authenticates via AWS Cognito (email/password directly from the UI, then exchanges the ID token with the backend at `/api/replay/auth/cognito/login`).

Required `.env` values for frontend (copy from `.env.example`):
- `VITE_COGNITO_AUTHORITY`, `VITE_COGNITO_USER_POOL_ID`, `VITE_COGNITO_CLIENT_ID`, `VITE_COGNITO_SCOPE`

Backend token verification uses: `COGNITO_ISSUER`, `COGNITO_CLIENT_ID`.

### Data/Persistence

- `artifacts/data/app.db` — SQLite database used by the replay dashboard
- `artifacts/pointers/` — pointer metadata for large external artifacts (do not commit binaries)
- `data/` — lightweight tracked data only

### Migration State

- `src/` is the intended long-term home for cleaner architecture but is not fully populated yet
- Keep wrapper scripts in `scripts/` working at all times
- Prefer incremental migration over rewrites; call out architectural debt explicitly

## Key Constraints

- **Windows-first**: All operational workflows use PowerShell wrappers. Do not break `scripts/*.ps1`.
- **Never commit**: model binaries, checkpoints, replay dumps, generated CSVs/plots/logs, or large tool bundles.
- **Do not silently change**: ports, route shapes, auth expectations, or CLI parameters without updating all dependent surfaces.
- **Verify actual script behavior** before repeating environment assumptions — some wrappers still reference `.\.venv\Scripts\python.exe` while others use `venv\Scripts\python.exe`.
- `rrrocket.exe` is bundled at `Milestone_1/rrrocket.exe` and is used for `.replay` → JSON parsing.
