from __future__ import annotations

import importlib
from pathlib import Path
import runpy
import sys


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    milestone2_live = Path(__file__).resolve().parent
    milestone2_root = milestone2_live.parent
    for p in (repo_root, milestone2_root, milestone2_live):
        p_str = str(p)
        if p_str not in sys.path:
            sys.path.insert(0, p_str)

    from Milestone_2.live_analysis import http_server as milestone2_http_server
    from Milestone_2.live_analysis import state_store as milestone2_state_store

    sys.modules["http_server"] = milestone2_http_server
    sys.modules["state_store"] = milestone2_state_store
    sys.modules.setdefault("Milestone_1.live_analysis.http_server", importlib.import_module("Milestone_1.live_analysis.http_server"))
    sys.modules.setdefault("Milestone_1.live_analysis.state_store", importlib.import_module("Milestone_1.live_analysis.state_store"))
    target = repo_root / "Milestone_1" / "live_analysis" / "run_live_analysis.py"
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
