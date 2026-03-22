from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import sys
import time
import webbrowser


def _ensure_import_paths() -> None:
    here = Path(__file__).resolve().parent
    milestone_root = here.parent
    for p in (here, milestone_root):
        p_str = str(p)
        if p_str not in sys.path:
            sys.path.insert(0, p_str)


def parse_args():
    parser = argparse.ArgumentParser(description="Replay 3D dashboard with live-analysis metrics")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8775)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def _configure_utf8_output() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main():
    _configure_utf8_output()
    _ensure_import_paths()
    from replay_http_server import ReplayDashboardServer
    from replay_state_store import ReplayStateStore
    from common.persistence import AppDB

    args = parse_args()
    db = AppDB()
    store = ReplayStateStore(db=db)
    server = ReplayDashboardServer(store=store, host=args.host, port=args.port)
    server.start()

    url = f"http://{args.host}:{args.port}"
    print(f"[replay_dashboard] running at {url}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    running = True

    def _stop(_sig=None, _frame=None):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        while running:
            time.sleep(0.25)
    finally:
        server.stop()
        print("[replay_dashboard] stopped")


if __name__ == "__main__":
    main()
