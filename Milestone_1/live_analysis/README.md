# Live Analysis (RLDojo Scenario Integration)

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_live_analysis.ps1 -DefaultScenario "ground_duel_center"
```

What it does (default behavior):
- Loads RLDojo custom scenarios from `%APPDATA%\RLBot\Dojo\Scenarios`.
- If `%APPDATA%` is missing/empty, attempts RLDojo repo paths, then bundled scenarios.
- Auto-launches Rocket League/RLBot match (Epic-first by default), with state setting + rendering enabled.
- Creates a training-friendly match (unlimited length + disable goal reset mutator).
- Applies a startup/default scenario and keeps it stable for a few ticks.
- Uses no-bot mode by default (`tuck`): opponent is moved above the map.
- Streams live metrics to browser dashboard.

Dashboard:
- `http://127.0.0.1:8765`

Launcher options:
- `-DefaultScenario <name>`
- `-ScenarioRoot <path>`
- `-NoBotMode tuck|none`
- `-Launcher epic|steam|auto`
- `-AttachOnly` (skip auto-start; connect to an existing live session)
- `-NoBrowser`

Dashboard scenario behavior:
- Select a scenario in the web UI and click **Apply Scenario**.
- The selected scenario is queued and then applied in-game via RLBot state setting.

API endpoints:
- `GET /api/health`
- `GET /api/scenarios`
- `POST /api/scenario/select`
- `GET /api/metrics/current`
- `GET /api/metrics/history`
