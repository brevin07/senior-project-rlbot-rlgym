"""Compatibility wrapper for training entrypoint migration."""

from pathlib import Path
import runpy


def main():
    root = Path(__file__).resolve().parents[3]
    legacy = root / "rlbot_training" / "rlbot_starting_code.py"
    runpy.run_path(str(legacy), run_name="__main__")


if __name__ == "__main__":
    main()
