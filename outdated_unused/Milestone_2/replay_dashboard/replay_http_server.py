from __future__ import annotations

import json
import sys
from http import HTTPStatus
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
M1_ROOT = REPO_ROOT / "Milestone_1"
M1_REPLAY = M1_ROOT / "replay_dashboard"
for _p in (REPO_ROOT, M1_ROOT, M1_REPLAY):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

from Milestone_1.replay_dashboard.replay_http_server import (
    ReplayDashboardServer as BaseReplayDashboardServer,
    _ReplayDashboardHandler as BaseReplayDashboardHandler,
)


class _ReplayDashboardHandler(BaseReplayDashboardHandler):
    def do_GET(self):
        if self.path == "/api/home/summary":
            try:
                ctx = self._require_auth()
                self.store.set_current_user(ctx.get("profile") or {})
                data = self.store.home_summary()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/training/plan":
            try:
                ctx = self._require_auth()
                self.store.set_current_user(ctx.get("profile") or {})
                data = self.store.training_plan()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/training/launch":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                ctx = self._require_auth()
                self.store.set_current_user(ctx.get("profile") or {})
                data = self.store.launch_training(
                    focus_id=str(body.get("focus_id", "")).strip(),
                    difficulty_tier=str(body.get("difficulty_tier", "")).strip(),
                    difficulty_value=float(body.get("difficulty_value", 0.0) or 0.0),
                    bot_profile_id=str(body.get("bot_profile_id", "")).strip(),
                    scenario_ids=[str(x) for x in (body.get("scenario_ids", []) or [])],
                    drill_mode=str(body.get("drill_mode", "")).strip(),
                    bot_required=bool(body.get("bot_required", False)),
                )
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        return super().do_POST()


class ReplayDashboardServer(BaseReplayDashboardServer):
    def start(self) -> None:
        handler = type("Milestone2ReplayDashboardHandler", (_ReplayDashboardHandler,), {})
        handler.store = self.store
        handler.web_dir = self.web_dir
        handler.collision_mesh_dir = self.collision_mesh_dir
        self._server = self._server.__class__((self.host, self.port), handler) if self._server else None
        if self._server is None:
            from http.server import ThreadingHTTPServer
            import threading

            self._server = ThreadingHTTPServer((self.host, self.port), handler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
