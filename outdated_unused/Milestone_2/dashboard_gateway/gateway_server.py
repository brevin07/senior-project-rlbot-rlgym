from __future__ import annotations

from pathlib import Path
import runpy
import sys


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    target = repo_root / "Milestone_1" / "dashboard_gateway" / "gateway_server.py"
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
