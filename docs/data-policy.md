# Data and Artifact Policy

## What stays in git
- Source code.
- Config files.
- Lightweight sample data for tests and docs.
- Artifact pointer metadata under `artifacts/pointers/`.

## What must not be committed
- Model binaries (`.pt`, `.pth`, `.onnx`) unless tiny and explicitly intended sample files.
- Checkpoint folders.
- Replay exports (`.replay`, large `.json`/`.csv` telemetry dumps).
- Experiment logs (`wandb/`, `reward_logs/`, generated plots).
- Local tool binaries (`rlviser`, `rattletrap`, `rrrocket` archives).

## Artifact pointer format
Store pointer files as JSON in `artifacts/pointers/`:
```json
{
  "name": "my_model",
  "version": "v1",
  "uri": "s3://bucket/path/to/model.pt",
  "sha256": "hexhash",
  "source_commit": "gitsha",
  "created_at": "2026-02-12T00:00:00Z",
  "notes": "trained on 1v1 reward mix"
}
```

## History cleanup process
- Use `scripts/history_cleanup.ps1` in a dedicated branch.
- Coordinate with collaborators before force-push.
- After rewrite, all users must re-clone or hard-reset to new history.
