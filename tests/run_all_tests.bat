@echo off
REM Alpha Release KR Test Runner
REM Run all tests for Key Results 1-4

echo ===================================
echo Alpha Release KR Test Suite
echo ===================================
echo.

echo Checking prerequisites...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

echo Python: OK
echo.

REM Check if pytest is installed
python -m pytest --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing pytest...
    python -m pip install pytest pandas
)

echo.
echo ===================================
echo Running KR1 Tests (Replay Parsing)
echo ===================================
python -m pytest tests/test_kr1_replay_parsing.py -v --tb=short
echo.

echo ===================================
echo Running KR2 Tests (Weakness Detection)
echo ===================================
python -m pytest tests/test_kr2_weakness_detection.py -v --tb=short
echo.

echo ===================================
echo Running KR3 Tests (Visualizer FPS)
echo ===================================
python -m pytest tests/test_kr3_visualizer_fps.py -v --tb=short
echo.

echo ===================================
echo Running KR4 Tests (Database Storage)
echo ===================================
python -m pytest tests/test_kr4_database_storage.py -v --tb=short
echo.

echo ===================================
echo Final Attainment Tests Only
echo ===================================
python -m pytest tests/ -k "attainment" -v
echo.

echo ===================================
echo Test Suite Complete!
echo ===================================
pause
