# AGENTS.md

## Purpose Of This File

Every agent working in this repository should read this file before making changes. It is the repo-level operating manual for how to understand the project, where to make changes, what interfaces must remain stable, and what engineering habits are required here.

This project is not a clean greenfield codebase. It is an active Rocket League bot training and analysis workspace with a mix of stable wrappers, milestone-era implementation code, newer `src/` migration targets, and a React dashboard layer. Agents must work from the current reality of the repository, not from idealized assumptions.

## What This Project Is

This repository supports several related workflows:

- Rocket League bot training
- Live in-match analysis
- Replay extraction and replay analysis
- Browser dashboards for live and replay workflows
- A gateway flow that exposes multiple backends behind a single surface

At a high level:

- `rlbot_training/` contains existing training/runtime code and reward logic.
- `Milestone_1/` contains active live-analysis, replay-analysis, dashboard, persistence, and gateway code. Do not assume this directory is archival just because of its name.
- `src/` is the intended long-term package layout for cleaner boundaries.
- `frontend/dashboard/` contains the React + TypeScript frontend.
- `scripts/` contains the operational PowerShell wrappers that users are most likely to run.
- `docs/` contains architecture and workflow notes.
- `tests/` contains milestone verification tests and regression checks.

This repo is in a migration state. Some target architecture exists in `src/`, but important working behavior still lives outside it. Agents must preserve current workflows while improving structure incrementally.

## Canonical Workflows

When referring to how the project is run, prefer the wrapper scripts in `scripts/` unless there is a strong reason to document or edit a lower-level entrypoint.

Primary commands:

- `powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts/train.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts/live_analysis.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts/launch_live_analysis.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts/replay_extract.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts/run_gateway.ps1`

Important note on environments:

- The top-level documentation is not perfectly aligned with all scripts.
- `scripts/bootstrap.ps1` currently creates and manages `venv/`.
- Some wrappers still reference `.\.venv\Scripts\python.exe`, while others resolve `venv\Scripts\python.exe`.
- Agents must verify actual script behavior before repeating environment assumptions in code or docs.
- If fixing environment inconsistencies, do it intentionally and keep all user-facing wrappers coherent.

## Source Of Truth Rules

Use these rules when deciding where to work:

- Treat the actual working scripts and codepaths as the first source of truth for runtime behavior.
- Treat `README.md` and `docs/` as important but potentially stale secondary sources that may need updating after code changes.
- Treat `src/` as the preferred long-term home for cleaner architecture.
- Treat `Milestone_1/` and `rlbot_training/` as active code unless proven otherwise.
- Do not move functionality into `src/` in a way that breaks existing wrapper commands unless the task explicitly includes that migration and compatibility work.

When adding or refactoring code:

- Prefer incremental migration over broad rewrites.
- Preserve wrapper interfaces under `scripts/`.
- Keep the live, replay, training, frontend, and gateway flows working together.
- Call out architectural debt explicitly instead of silently scattering more of it.

## The Agent's Job

An agent working in this repo is expected to:

- Understand the specific subsystem being changed before editing it.
- Make the smallest correct change that improves the project without breaking active workflows.
- Preserve user-facing commands, routes, and operational conventions unless the task explicitly changes them.
- Update nearby docs, tests, and config references when behavior changes.
- Surface mismatches between docs, scripts, and implementation instead of assuming they are aligned.
- Leave the repo in a more coherent state than it was found.

Agents are not here to perform speculative cleanup, rename things for style, or force a migration that the repo has not completed yet.

## Required Working Habits

Before editing:

- Read the relevant entrypoint, wrapper, and nearby docs.
- Search for tests, scripts, configs, and frontend/backend touchpoints affected by the change.
- Check whether the behavior lives in `src/`, `Milestone_1/`, `rlbot_training/`, or multiple layers.

While editing:

- Prefer compatibility-preserving changes.
- Keep public script parameters and route assumptions stable unless changing them is part of the task.
- Add concise comments only where the code would otherwise be hard to follow.
- Avoid large-scale renames unless they solve a concrete problem and all references are updated.

After editing:

- Run the smallest meaningful verification for the changed area.
- If full verification is not possible locally, say exactly what was not verified.
- Update documentation when instructions, setup, commands, or architecture descriptions became outdated because of the change.

## Good Practices For This Repo

- Prefer root PowerShell wrappers for reproducible workflows.
- Preserve Windows-first operability. This repo is clearly optimized for PowerShell-based usage.
- Keep frontend and backend assumptions synchronized when touching dashboards or gateway behavior.
- Treat replay analysis, live analysis, persistence, and UI as connected systems rather than isolated files.
- Keep changes local to the subsystem unless cross-cutting edits are required for correctness.
- Use existing patterns before introducing a new framework, abstraction, or workflow.
- If you find drift between implementation and docs, either fix it or document it in your final handoff.

## Practices To Avoid

- Do not assume `Milestone_1/` is dead code.
- Do not break `scripts/*.ps1` wrappers to make internal structure cleaner.
- Do not commit large generated artifacts, replay dumps, model checkpoints, logs, or exported datasets.
- Do not add new large binaries or bundles to git unless explicitly required.
- Do not make broad architectural moves without checking how training, live analysis, replay analysis, and the React dashboard interact.
- Do not silently change ports, route shapes, auth expectations, or CLI parameters without updating every dependent surface.

## Testing And Verification Expectations

Choose verification based on the subsystem touched.

Examples:

- Training changes: verify the training entrypoint and any affected Python imports or config wiring.
- Live analysis changes: verify the live launcher path, argument handling, and dashboard startup assumptions.
- Replay analysis changes: verify extraction and replay dashboard entrypoints or the affected parsing/storage layer.
- Frontend changes: verify the relevant build, route, and API integration assumptions.
- Database or persistence changes: run the relevant tests under `tests/` and check compatibility with existing callers.

Useful existing test surface:

- `tests/test_kr1_replay_parsing.py`
- `tests/test_kr2_weakness_detection.py`
- `tests/test_kr3_visualizer_fps.py`
- `tests/test_kr4_database_storage.py`

Do not claim full validation if only static inspection was performed.

## Documentation Responsibilities

If your change affects setup, runtime commands, architecture boundaries, or expected behavior:

- update `README.md` if it affects user workflow
- update `docs/architecture.md` if it changes ownership or boundaries
- update `docs/workflows.md` if it changes canonical run paths
- update tests or test docs if verification instructions changed

When docs and code disagree, prefer fixing the disagreement rather than leaving both versions in place.

## Artifact And Data Hygiene

Keep the repository lightweight and reproducible.

Do not commit:

- model binaries
- checkpoints
- replay dumps
- generated csv/json exports unless intentionally tracked and small
- generated plots, logs, or temporary outputs
- local tool bundles unless explicitly part of the project

Use `artifacts/pointers/` for pointer metadata when that pattern is already being used.

## Decision Defaults

If the task does not specify otherwise, default to these decisions:

- preserve existing script interfaces
- prefer incremental fixes over rewrites
- prefer repo reality over stale documentation
- place net-new structured code in `src/` only when it does not create compatibility gaps
- keep legacy working paths operational while migrating
- document important assumptions in the final handoff

## Handoff Expectations

A good handoff from an agent in this repo should include:

- what changed
- what was verified
- what could not be verified
- any doc/code inconsistencies discovered
- any compatibility risk introduced or avoided

Be concrete. Future agents should be able to continue from the handoff without rediscovering the same context.
