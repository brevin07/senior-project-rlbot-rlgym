# How to Run the Tests

This project contains 48 automated tests verifying 4 Key Results (KRs) from the Alpha Release milestone.

---

## Prerequisites

**Python 3.8+** and the following packages:

```bash
pip install pytest pandas
```

- `pytest` — test runner
- `pandas` — required by KR1 replay parsing tests
- `sqlite3` — bundled with Python, required by KR4 database tests
- `rrrocket.exe` — bundled at `Milestone_1/rrrocket.exe`; KR1 tests skip automatically if it is missing

---

## Running Tests

All commands must be run from the **project root** (`RLGym_Bot_Training/`), not from inside the `tests/` folder.

### Run everything

```bash
pytest tests/ -v
```

### Run with visible print output

```bash
pytest tests/ -v -s
```

### Run only the final attainment verification tests

```bash
pytest tests/ -k "attainment" -v
```

### Run each KR individually

```bash
# KR1 — Replay parsing & telemetry extraction (requires replay files + rrrocket.exe)
pytest tests/test_kr1_replay_parsing.py -v

# KR2 — Player weakness detection algorithm
pytest tests/test_kr2_weakness_detection.py -v

# KR3 — 3D visualizer FPS (inspects source code structure)
pytest tests/test_kr3_visualizer_fps.py -v

# KR4 — SQL database CRUD operations
pytest tests/test_kr4_database_storage.py -v
```

### Use the provided scripts

```bat
tests\run_all_tests.bat        # Windows
```
```bash
./tests/run_all_tests.sh       # Linux / macOS
```

---

## What Each Test Suite Covers

| File | KR | Target | Tests | Notes |
|------|----|--------|-------|-------|
| `test_kr1_replay_parsing.py` | KR1 | 100% | 11 | Requires `artifacts/replay_library/` and `Milestone_1/rrrocket.exe` |
| `test_kr2_weakness_detection.py` | KR2 | 95% | 10 | Uses synthetic timeline; always runs |
| `test_kr3_visualizer_fps.py` | KR3 | 85% | 16 | Inspects source files; always runs |
| `test_kr4_database_storage.py` | KR4 | 90% | 11 | Uses a temp SQLite database; always runs |

---

## Expected Output

```
collected 48 items

tests/test_kr1_replay_parsing.py ........sss          [ 22%]
tests/test_kr2_weakness_detection.py ..........        [ 43%]
tests/test_kr3_visualizer_fps.py ................      [ 76%]
tests/test_kr4_database_storage.py ...........         [100%]

=========== 45 passed, 3 skipped in ~2s ===========
```

KR1 tests may be skipped (`s`) if `rrrocket.exe` or replay files are absent — this is expected.

---

## Troubleshooting

**`ModuleNotFoundError`** — You are not in the project root. Run from `RLGym_Bot_Training/`:
```bash
cd D:\PycharmProjects\RLGym_Bot_Training
pytest tests/ -v
```

**KR1 tests skipping** — Confirm the bundled binary and replay files exist:
```bash
# Check binary
ls Milestone_1/rrrocket.exe

# Check replay library
ls artifacts/replay_library/*/*.replay
```

**`pytest: command not found`**:
```bash
pip install pytest
# or
python -m pytest tests/ -v
```

**KR3 manual verification** — Automated tests only check source code structure.
To verify actual FPS in the browser:
1. `cd frontend/dashboard && npm run dev`
2. Load a replay, click the **Debug** button
3. Confirm the FPS counter shows > 30 FPS

---

## More Detail

- Full documentation: `tests/README.md`
- Quick start: `tests/QUICKSTART.md`
- Alpha milestone requirements: `Milestone_Alpha_Release_Deliverable.md`
