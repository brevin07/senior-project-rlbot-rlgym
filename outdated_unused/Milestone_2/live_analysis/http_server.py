from __future__ import annotations

import json
import sys
from http import HTTPStatus
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
M1_ROOT = REPO_ROOT / "Milestone_1"
M1_LIVE = M1_ROOT / "live_analysis"
for _p in (REPO_ROOT, M1_ROOT, M1_LIVE):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

from Milestone_1.live_analysis.http_server import (
    DashboardServer as BaseDashboardServer,
    _DashboardHandler as BaseDashboardHandler,
)


class _DashboardHandler(BaseDashboardHandler):
    def do_GET(self):
        if self.path == "/api/training/current":
            try:
                return self._send_json({"ok": True, "data": self.store.current_training_launch()})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/training/launch":
            return super().do_POST()
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            body = {}

        focus_id = str(body.get("focus_id", "")).strip()
        scenario_ids = [str(x).strip() for x in (body.get("scenario_ids", []) or []) if str(x).strip()]
        if not focus_id:
            return self._send_json({"ok": False, "error": "Missing focus_id"}, status=400)
        if not scenario_ids:
            return self._send_json({"ok": False, "error": "Select at least one scenario."}, status=400)
        self.store.queue_training_launch(body)
        self.store.queue_scenario(str(scenario_ids[0]))
        return self._send_json({"ok": True, "queued": scenario_ids, "focus_id": focus_id})


class DashboardServer(BaseDashboardServer):
    def start(self) -> None:
        handler = type("Milestone2DashboardHandler", (_DashboardHandler,), {})
        handler.store = self.store
        handler.review_store = self.review_store
        handler.web_dir = self.web_dir
        handler.collision_mesh_dir = self.collision_mesh_dir
        handler.db = self.db
        from http.server import ThreadingHTTPServer
        import threading

        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
