# Quick Start Guide - Alpha KR Tests

Get up and running with the Alpha Release test suite in 3 minutes.

## 🚀 Quick Start (3 steps)

### 1. Install Prerequisites
```bash
# Install pytest (required)
pip install pytest pandas

# Optional: Install rrrocket for KR1 tests (Rocket League replay parser)
# cargo install rrrocket
# OR download from: https://github.com/nickbabcock/rrrocket/releases
```

### 2. Navigate to Project Root
```bash
cd D:\PycharmProjects\RLGym_Bot_Training
```

### 3. Run Tests
```bash
# Run all tests
pytest tests/ -v

# Or use the provided script
tests\run_all_tests.bat          # Windows
./tests/run_all_tests.sh         # Linux/Mac
```

---

## ✅ Quick Test Examples

### Test Individual KRs
```bash
# KR1: Replay Parsing (requires rrrocket)
pytest tests/test_kr1_replay_parsing.py -v

# KR2: Weakness Detection
pytest tests/test_kr2_weakness_detection.py -v

# KR3: Visualizer FPS
pytest tests/test_kr3_visualizer_fps.py -v

# KR4: Database Storage
pytest tests/test_kr4_database_storage.py -v
```

### Test Only Final Attainment Verifications
```bash
pytest tests/ -k "attainment" -v
```

Expected output:
```
test_kr1_attainment_100_percent PASSED ✅ 100%
test_kr2_attainment_95_percent PASSED  ✅ 95%
test_kr3_attainment_85_percent PASSED  ✅ 85%
test_kr4_attainment_90_percent PASSED  ✅ 90%

Overall: 87.5% attainment
```

---

## 📊 What Each Test Does

### KR1 (100%): Replay Parsing
✅ Parses `.replay` files with rrrocket
✅ Extracts telemetry to Pandas DataFrames
✅ Validates ball physics and player data

**Skip if:** No replay files or rrrocket not installed

### KR2 (95%): Weakness Detection
✅ Detects 8 mechanics (exceeds requirement of 3)
✅ Scores weaknesses 0-100
✅ Provides timestamps and recommendations

**Always runs:** Uses synthetic timeline data

### KR3 (85%): 3D Visualizer FPS
✅ Verifies FPS counter implementation
✅ Checks Three.js rendering setup
✅ Validates playback and camera controls

**Always runs:** Tests code structure
**Manual step:** Verify FPS in browser (see KR3 README section)

### KR4 (90%): Database Storage
✅ Tests all CRUD operations
✅ Verifies 100% session storage
✅ Checks query performance

**Always runs:** Uses temporary test database

---

## 🐛 Quick Troubleshooting

### "pytest: command not found"
```bash
pip install pytest
```

### "No replay files found" (KR1 only)
Tests will skip automatically. To test with real data:
```bash
# Ensure replays exist
ls artifacts/replay_library/*/*.replay | head -1
```

### "rrrocket not found" (KR1 only)
KR1 tests will skip. To enable:
```bash
cargo install rrrocket
```

### "ModuleNotFoundError"
Make sure you're in the project root:
```bash
cd D:\PycharmProjects\RLGym_Bot_Training
pytest tests/ -v
```

---

## 📚 More Information

- **Full Documentation:** See `tests/README.md`
- **Alpha Deliverable:** See `Milestone_Alpha_Release_Deliverable.md`
- **Test Files:**
  - `test_kr1_replay_parsing.py` - 11 tests for replay parsing
  - `test_kr2_weakness_detection.py` - 10 tests for weakness detection
  - `test_kr3_visualizer_fps.py` - 16 tests for visualizer performance
  - `test_kr4_database_storage.py` - 11 tests for database operations

**Total: 48 automated tests**

---

## 🎯 Expected Results

All KRs should pass (with some KR1 tests skipping if rrrocket/replays unavailable):

```
============================== test session starts ==============================
collected 48 items

tests/test_kr1_replay_parsing.py ........sss                              [ 22%]
tests/test_kr2_weakness_detection.py ..........                           [ 43%]
tests/test_kr3_visualizer_fps.py ................                         [ 76%]
tests/test_kr4_database_storage.py ...........                            [100%]

===================== 45 passed, 3 skipped in 2.34s ============================
```

*(Some KR1 tests may skip if rrrocket or replay files are not available)*

---

## ✨ That's It!

You're now ready to verify all Alpha Release Key Results.

For detailed test documentation, see `tests/README.md`.

Happy testing! 🎉
