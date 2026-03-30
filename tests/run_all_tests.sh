#!/bin/bash
# Alpha Release KR Test Runner
# Run all tests for Key Results 1-4

echo "==================================="
echo "Alpha Release KR Test Suite"
echo "==================================="
echo ""

echo "Checking prerequisites..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python not found. Please install Python 3.8+"
    exit 1
fi

echo "Python: OK"
echo ""

# Check if pytest is installed
if ! python3 -m pytest --version &> /dev/null; then
    echo "Installing pytest..."
    python3 -m pip install pytest pandas
fi

echo ""
echo "==================================="
echo "Running KR1 Tests (Replay Parsing)"
echo "==================================="
python3 -m pytest tests/test_kr1_replay_parsing.py -v --tb=short
echo ""

echo "==================================="
echo "Running KR2 Tests (Weakness Detection)"
echo "==================================="
python3 -m pytest tests/test_kr2_weakness_detection.py -v --tb=short
echo ""

echo "==================================="
echo "Running KR3 Tests (Visualizer FPS)"
echo "==================================="
python3 -m pytest tests/test_kr3_visualizer_fps.py -v --tb=short
echo ""

echo "==================================="
echo "Running KR4 Tests (Database Storage)"
echo "==================================="
python3 -m pytest tests/test_kr4_database_storage.py -v --tb=short
echo ""

echo "==================================="
echo "Final Attainment Tests Only"
echo "==================================="
python3 -m pytest tests/ -k "attainment" -v
echo ""

echo "==================================="
echo "Test Suite Complete!"
echo "==================================="
