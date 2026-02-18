from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from review_store import ReviewStore
from recommendation_engine import TRAINING_CATALOG, compute_recommendations
from mechanic_grader import grade_game_mechanics
from state_store import StateStore


class _DashboardHandler(BaseHTTPRequestHandler):
    store: StateStore = None
    review_store: ReviewStore = None
    web_dir: Path = None
    collision_mesh_dir: Path = None
    db = None

    def _compute_review_mechanics(self) -> Dict[str, Any]:
        data = self.review_store.session_data()
        players = list(data.get("players", []) or [])
        tracked = str(data.get("tracked_player_name", "") or "").strip()
        if not tracked:
            idx = int(data.get("tracked_player_index", 0) or 0)
            if 0 <= idx < len(players):
                tracked = str(players[idx])
        if not tracked and players:
            tracked = str(players[0])
        if not tracked:
            return {}
        teams = dict((data.get("replay_meta", {}) or {}).get("player_teams", {}) or {})
        return grade_game_mechanics(data.get("timeline", []) or [], tracked, teams)

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_name: str, content_type: str) -> None:
        file_path = self.web_dir / file_name
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._send_file("index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return self._send_file("app.js", "application/javascript; charset=utf-8")
        if path == "/styles.css":
            return self._send_file("styles.css", "text/css; charset=utf-8")
        if path == "/three.min.js":
            local_three = self.web_dir / "three.min.js"
            fallback_three = Path(__file__).resolve().parents[1] / "replay_dashboard" / "web" / "three.min.js"
            src = local_three if local_three.exists() else fallback_three
            if not src.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "three.min.js not found")
                return
            data = src.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/collision_meshes/"):
            rel = path[len("/collision_meshes/") :].strip("/")
            base = (self.collision_mesh_dir or Path(".")).resolve()
            file_path = (base / rel).resolve()
            if base not in file_path.parents and file_path != base:
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid path")
                return
            if not file_path.exists() or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            ext = file_path.suffix.lower()
            content_type = "application/octet-stream"
            if ext == ".obj":
                content_type = "text/plain; charset=utf-8"
            elif ext == ".json":
                content_type = "application/json; charset=utf-8"
            elif ext == ".stl":
                content_type = "model/stl"
            elif ext == ".cmf":
                content_type = "application/octet-stream"
            data = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/health":
            return self._send_json({"ok": True})
        if path == "/api/profile/current":
            try:
                profile = self.db.current_user() if self.db is not None else {}
                self.store.set_current_user(profile or {})
                return self._send_json({"ok": True, "profile": profile or {}})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/profile/history":
            try:
                profile = self.db.current_user() if self.db is not None else {}
                if not profile:
                    return self._send_json({"ok": True, "sessions": []})
                sessions = self.db.list_replay_sessions(user_id=int(profile["id"]), limit=300)
                return self._send_json({"ok": True, "sessions": sessions})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/profile/progress":
            try:
                profile = self.db.current_user() if self.db is not None else {}
                if not profile:
                    return self._send_json({"ok": True, "data": {"points": []}})
                rows = self.db.list_replay_sessions_detailed(user_id=int(profile["id"]), limit=120)
                pts = []
                for r in reversed(rows):
                    s = r.get("summary", {}) or {}
                    pts.append(
                        {
                            "created_at": r.get("created_at", ""),
                            "whiff_rate_per_min": float(s.get("whiff_rate_per_min", 0.0) or 0.0),
                            "hesitation_percent": float(s.get("hesitation_percent", 0.0) or 0.0),
                            "approach_efficiency": float(s.get("approach_efficiency", 0.0) or 0.0),
                            "recovery_time_avg_s": float(s.get("recovery_time_avg_s", 0.0) or 0.0),
                        }
                    )
                return self._send_json({"ok": True, "data": {"points": pts}})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/recommendations/current":
            try:
                snap = self.store.snapshot()
                payload = snap.get("recommendations") or {}
                return self._send_json({"ok": True, "data": payload})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/mechanics/current":
            try:
                snap = self.store.snapshot()
                payload = snap.get("mechanics") or {}
                if not payload:
                    payload = self._compute_review_mechanics()
                    self.store.set_mechanics(payload)
                return self._send_json({"ok": True, "data": payload})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/mechanics/events":
            try:
                snap = self.store.snapshot()
                payload = snap.get("mechanics") or {}
                if not payload:
                    payload = self._compute_review_mechanics()
                    self.store.set_mechanics(payload)
                return self._send_json({"ok": True, "events": list(payload.get("mechanic_events", []) or [])})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/training/catalog":
            return self._send_json({"ok": True, "data": TRAINING_CATALOG})
        if path == "/api/scenarios":
            scenarios = self.store.list_scenarios()
            return self._send_json({"scenarios": [{"name": s.name, "source": s.source} for s in scenarios]})
        if path == "/api/metrics/current":
            snapshot = self.store.snapshot()
            return self._send_json({
                "active_scenario": snapshot["active_scenario"],
                "active_source": snapshot["active_source"],
                "pending_scenario": snapshot["pending_scenario"],
                "spawn_mode": snapshot["spawn_mode"],
                "current": snapshot["current_metrics"],
                "events": snapshot["events"],
            })
        if path == "/api/metrics/history":
            snapshot = self.store.snapshot()
            return self._send_json({"history": snapshot["history"]})
        if path == "/api/review/sessions":
            return self._send_json({"ok": True, "sessions": self.review_store.list_sessions()})
        if path == "/api/review/session/current":
            return self._send_json({"ok": True, "data": self.review_store.current_session()})
        if path == "/api/review/session/data":
            try:
                data = self.review_store.session_data()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/review/events":
            return self._send_json({"ok": True, "events": self.review_store.events()})
        if path == "/api/review/labels":
            return self._send_json({"ok": True, "labels": self.review_store.labels()})
        if path == "/api/arena_meshes":
            base = self.collision_mesh_dir
            if not base or not base.exists():
                return self._send_json({"ok": True, "data": {"available": False, "files": []}})
            map_name = (qs.get("map_name", [""])[0] or "").strip().lower()
            map_key = "".join(ch for ch in map_name if ch.isalnum() or ch in ("_", "-"))
            candidates = []
            if map_key:
                candidates.append(base / map_key)
            candidates.append(base / "soccar")
            candidates.append(base)
            chosen = None
            for cand in candidates:
                if cand.exists() and cand.is_dir():
                    chosen = cand
                    break
            if not chosen:
                return self._send_json({"ok": True, "data": {"available": False, "files": []}})
            files = []
            for p in chosen.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in (".obj", ".json", ".stl", ".cmf"):
                    continue
                rel = p.relative_to(base).as_posix()
                files.append(rel)
            files.sort()
            return self._send_json(
                {"ok": True, "data": {"available": len(files) > 0, "files": files, "folder": chosen.name}}
            )

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)

        if self.path == "/api/scenario/select":
            name = str(body.get("name", "")).strip()
            if not name:
                return self._send_json({"ok": False, "error": "Missing scenario name"}, status=400)

            if not self.store.queue_scenario(name):
                return self._send_json({"ok": False, "error": f"Scenario '{name}' not found"}, status=404)
            return self._send_json({"ok": True, "queued": name})
        if self.path == "/api/profile/login":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            if self.db is None:
                return self._send_json({"ok": False, "error": "DB not configured"}, status=500)
            try:
                profile = self.db.upsert_user(
                    username=str(body.get("username", "")).strip(),
                    rank_tier=str(body.get("rank_tier", "")).strip(),
                    platform=str(body.get("platform", "")).strip(),
                    aliases=[str(x) for x in (body.get("aliases", []) or [])] if isinstance(body.get("aliases", []), list) else [],
                )
                self.store.set_current_user(profile)
                return self._send_json({"ok": True, "profile": profile})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/recommendations/refresh":
            if self.db is None:
                return self._send_json({"ok": False, "error": "DB not configured"}, status=500)
            try:
                profile = self.db.current_user() or {}
                if not profile:
                    return self._send_json({"ok": False, "error": "Please log in first."}, status=400)
                payload = compute_recommendations(self.db, int(profile["id"]), window_size=5)
                self.store.set_recommendations(payload)
                return self._send_json({"ok": True, "data": payload})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/mechanics/recompute":
            try:
                payload = self._compute_review_mechanics()
                self.store.set_mechanics(payload)
                return self._send_json({"ok": True, "data": payload})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/training/queue_focus":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            focus_id = str(body.get("focus_id", "")).strip()
            bot_profile = str(body.get("bot_profile_id", "")).strip()
            scenario_ids = body.get("scenario_ids", []) or []
            if focus_id not in TRAINING_CATALOG:
                return self._send_json({"ok": False, "error": "Unknown focus_id"}, status=400)
            if not isinstance(scenario_ids, list) or not scenario_ids:
                return self._send_json({"ok": False, "error": "Select at least one scenario."}, status=400)
            self.store.queue_training(focus_id=focus_id, bot_profile=bot_profile, scenario_ids=scenario_ids)
            self.store.queue_scenario(str(scenario_ids[0]))
            return self._send_json({"ok": True, "queued": scenario_ids})

        if self.path == "/api/review/session/load":
            sid = str(body.get("session_id", "")).strip() or "latest"
            try:
                data = self.review_store.load_session(sid)
                try:
                    self.store.set_mechanics(self._compute_review_mechanics())
                except Exception:
                    self.store.set_mechanics({})
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/review/events/mark_missed":
            et = str(body.get("type", "")).strip().lower()
            t = float(body.get("t", 0.0))
            note = str(body.get("note", "") or "")
            try:
                evt = self.review_store.mark_missed_event(et, t, note)
                return self._send_json({"ok": True, "event": evt})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/review/labels/upsert":
            event_id = str(body.get("event_id", "")).strip()
            label = str(body.get("label", "")).strip()
            note = str(body.get("note", "") or "")
            author = str(body.get("author", "user") or "user")
            try:
                data = self.review_store.upsert_label(event_id=event_id, label=label, note=note, author=author)
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/review/labels/delete":
            event_id = str(body.get("event_id", "")).strip()
            try:
                self.review_store.delete_label(event_id=event_id)
                return self._send_json({"ok": True})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args) -> None:
        return


class DashboardServer:
    def __init__(self, store: StateStore, review_store: ReviewStore, db=None, host: str = "127.0.0.1", port: int = 8765):
        self.store = store
        self.review_store = review_store
        self.db = db
        self.host = host
        self.port = port
        self.web_dir = Path(__file__).resolve().parent / "web"
        repo_root = Path(__file__).resolve().parents[2]
        self.collision_mesh_dir = repo_root / "collision_meshes"
        self._server = None
        self._thread = None

    def start(self) -> None:
        handler = type("DashboardHandler", (_DashboardHandler,), {})
        handler.store = self.store
        handler.review_store = self.review_store
        handler.web_dir = self.web_dir
        handler.collision_mesh_dir = self.collision_mesh_dir
        handler.db = self.db

        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
