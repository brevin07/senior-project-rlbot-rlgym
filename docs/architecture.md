# Architecture

## Goals
- Keep this repository code-first and reproducible.
- Separate training, live analysis, and replay analysis concerns.
- Keep heavy artifacts out of git and reference them with pointer metadata.

## Current Runtime Components
- `rlbot_training/rlbot_starting_code.py`: PPO training entrypoint.
- `rlbot_training/reward_funcs/reward_functions.py`: reward library and experiments.
- `Milestone_1/extract_player_data.py`: rrrocket JSON -> gameplay CSV extraction.
- `Milestone_1/heuristic_analysis/analyzer.py`: offline heuristic analysis.
- `Milestone_1/heuristic_analysis/live_dashboard.py`: live telemetry dashboard.

## Target Logical Boundaries
- `src/rlbot_training/train/*`: training pipeline and env builders.
- `src/live_analysis/*`: live, in-match metric analysis and dashboards.
- `src/replay_analysis/*`: replay parsing and offline analysis.

## Artifact Policy
- Do not commit model binaries, checkpoint folders, replay dumps, or generated plots/csvs.
- Store external artifacts in a remote store and track only metadata pointers under `artifacts/pointers/`.

## Migration Strategy
1. Stabilize current scripts with wrappers under `scripts/`.
2. Add docs, ignore rules, and guardrails (pre-commit + large-file checks).
3. Incrementally move code into `src/` while keeping wrapper compatibility.
4. Perform history rewrite using `scripts/history_cleanup.ps1` after team coordination.
