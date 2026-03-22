import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[3]
    entry = root / "rlbot_training" / "rlbot_starting_code.py"
    raise SystemExit(subprocess.call([sys.executable, str(entry)]))


if __name__ == "__main__":
    main()
