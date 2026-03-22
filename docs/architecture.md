# Architecture

## Goals
- Keep this repository code-first and reproducible.
- Separate training, live analysis, and replay analysis concerns.
- Keep heavy artifacts out of git and reference them with pointer metadata.

## Current Runtime Components
- `rlbot_training/rlbot_starting_code.py`: PPO training entrypoint.
- `rlbot_training/reward_funcs/reward_functions.py`: reward library and experiments.
- `rocketcoach/extract_player_data.py`: rrrocket JSON -> gameplay CSV extraction.
- `rocketcoach/replay_dashboard/run_replay_dashboard.py`: replay dashboard entrypoint.
- `rocketcoach/live_analysis/run_live_analysis.py`: live telemetry dashboard / analysis entrypoint.

## Target Logical Boundaries
- `rocketcoach/common/*`: persistence, shared contracts, and backend utilities.
- `rocketcoach/live_analysis/*`: live, in-match metric analysis and dashboards.
- `rocketcoach/replay_dashboard/*`: replay parsing, replay APIs, and coaching workflows.
- `src/*`: thin compatibility entrypoints only.

## Artifact Policy
- Do not commit model binaries, checkpoint folders, replay dumps, or generated plots/csvs.
- Store external artifacts in a remote store and track only metadata pointers under `artifacts/pointers/`.

## Migration Strategy
1. Stabilize current scripts with wrappers under `scripts/`.
2. Add docs, ignore rules, and guardrails (pre-commit + large-file checks).
3. Keep `rocketcoach/` as the canonical runtime package and limit `src/` to thin compatibility wrappers.
4. Perform history rewrite using `scripts/history_cleanup.ps1` after team coordination.
