"""Compatibility wrapper for replay extraction migration."""

from pathlib import Path
import runpy


def main():
    root = Path(__file__).resolve().parents[2]
    legacy = root / "Milestone_1" / "extract_player_data.py"
    runpy.run_path(str(legacy), run_name="__main__")


if __name__ == "__main__":
    main()
