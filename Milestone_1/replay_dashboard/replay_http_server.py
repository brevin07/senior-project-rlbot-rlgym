from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from typing import Any, Dict
import re
from urllib.parse import parse_qs, urlparse

from replay_state_store import DuplicateReplayError, ReplayStateStore


class _ReplayDashboardHandler(BaseHTTPRequestHandler):
    store: ReplayStateStore = None
    web_dir: Path = None
    collision_mesh_dir: Path = None

    @staticmethod
    def _discover_replay_folder() -> Path:
        home = Path.home()
        docs_candidates = []
        docs_candidates.append(home / "Documents")
        docs_candidates.append(home / "OneDrive" / "Documents")
        one_drive_env = os.environ.get("OneDrive", "").strip()
        if one_drive_env:
            docs_candidates.append(Path(one_drive_env) / "Documents")

        clean_docs = []
        seen = set()
        for d in docs_candidates:
            k = str(d).lower()
            if k in seen:
                continue
            seen.add(k)
            clean_docs.append(d)

        replay_candidates = []
        for docs in clean_docs:
            replay_candidates.append(docs / "My Games" / "Rocket League" / "TAGame" / "DemosEpic")
            replay_candidates.append(docs / "My Games" / "Rocket League" / "TAGame" / "Demos Epic")
            replay_candidates.append(docs / "My Games" / "Rocket League" / "TAGame" / "Demos")

        for p in replay_candidates:
            if p.exists() and p.is_dir():
                return p
        for p in replay_candidates:
            parent = p.parent
            if parent.exists() and parent.is_dir():
                return parent
        return clean_docs[0] if clean_docs else home

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

    def _parse_upload(self) -> tuple[str, bytes]:
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise RuntimeError("Empty upload request.")

        m = re.search(r"boundary=([^;]+)", content_type)
        if not m:
            raise RuntimeError("Invalid multipart upload (missing boundary).")
        boundary = m.group(1).strip().strip('"')
        body = self.rfile.read(content_length)
        delimiter = ("--" + boundary).encode("utf-8")

        for part in body.split(delimiter):
            if b'name="file"' not in part:
                continue
            if b"Content-Disposition" not in part:
                continue
            sep = b"\r\n\r\n"
            if sep not in part:
                continue
            header_block, payload = part.split(sep, 1)
            filename_match = re.search(rb'filename="([^"]+)"', header_block)
            if not filename_match:
                raise RuntimeError("No file selected.")
            file_name = filename_match.group(1).decode("utf-8", errors="replace")
            payload = payload.strip(b"\r\n")
            if not payload:
                raise RuntimeError("Uploaded file is empty.")
            return file_name, payload

        raise RuntimeError("Missing 'file' field in upload.")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._send_file("index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return self._send_file("app.js", "application/javascript; charset=utf-8")
        if path == "/three.min.js":
            return self._send_file("three.min.js", "application/javascript; charset=utf-8")
        if path.startswith("/assets/"):
            rel = path[len("/assets/") :].strip("/")
            file_path = self.web_dir / "assets" / rel
            if not file_path.exists() or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            ext = file_path.suffix.lower()
            content_type = "application/octet-stream"
            if ext == ".glb":
                content_type = "model/gltf-binary"
            elif ext == ".gltf":
                content_type = "model/gltf+json"
            elif ext == ".png":
                content_type = "image/png"
            elif ext in (".jpg", ".jpeg"):
                content_type = "image/jpeg"
            data = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
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
        if path == "/styles.css":
            return self._send_file("styles.css", "text/css; charset=utf-8")

        if path == "/api/health":
            return self._send_json({"ok": True})
        if path == "/api/profile/current":
            try:
                profile = self.store.current_profile()
                return self._send_json({"ok": True, "profile": profile})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/replay/library":
            try:
                data = self.store.library_sessions()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/recommendations/current":
            try:
                data = self.store.current_recommendations()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/mechanics/current":
            try:
                data = self.store.current_mechanics()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/mechanics/events":
            try:
                data = self.store.mechanic_events()
                return self._send_json({"ok": True, "events": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/profile/history":
            try:
                data = self.store.library_sessions()
                return self._send_json({"ok": True, "sessions": data.get("sessions", [])})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/profile/progress":
            try:
                data = self.store.profile_progress(limit=240)
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/replay/status":
            return self._send_json(self.store.status_snapshot())
        if path == "/api/replay/players":
            players = self.store.list_players()
            return self._send_json({"players": players})
        if path == "/api/replay/session":
            try:
                data = self.store.replay_session_data()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/replay/metrics/capabilities":
            try:
                data = self.store.metrics_capabilities()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/replay/analysis/status":
            try:
                data = self.store.analysis_status()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/replay/player_metrics/status":
            player = (qs.get("player", [""])[0] or "").strip()
            if not player:
                return self._send_json({"ok": False, "error": "Missing query parameter: player"}, status=400)
            try:
                data = self.store.player_metrics_status(player)
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/replay/player_metrics/data":
            player = (qs.get("player", [""])[0] or "").strip()
            if not player:
                return self._send_json({"ok": False, "error": "Missing query parameter: player"}, status=400)
            try:
                data = self.store.player_metrics_data(player)
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
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
        if self.path == "/api/replay/upload":
            try:
                file_name, data = self._parse_upload()
                if not file_name.lower().endswith(".replay"):
                    return self._send_json({"ok": False, "error": "Please upload a .replay file."}, status=400)
                session_id = self.store.start_processing(file_name=file_name, data=data)
                return self._send_json({"ok": True, "session_id": session_id})
            except DuplicateReplayError as exc:
                return self._send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                        "code": "duplicate_replay",
                        "existing_session_id": exc.existing_session_id,
                        "existing_replay_name": exc.existing_replay_name,
                    },
                    status=400,
                )
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/replay/open_default_folder":
            try:
                target = self._discover_replay_folder()
                if hasattr(os, "startfile"):
                    os.startfile(str(target))
                return self._send_json({"ok": True, "path": str(target)})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/profile/login":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                profile = self.store.login_profile(
                    username=str(body.get("username", "")).strip(),
                    rank_tier=str(body.get("rank_tier", "")).strip(),
                    platform=str(body.get("platform", "")).strip(),
                    aliases=[str(x) for x in (body.get("aliases", []) or [])] if isinstance(body.get("aliases", []), list) else [],
                )
                return self._send_json({"ok": True, "profile": profile})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/profile/logout":
            try:
                self.store.logout_profile()
                return self._send_json({"ok": True})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/recommendations/refresh":
            try:
                data = self.store.refresh_recommendations()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/mechanics/recompute":
            try:
                data = self.store.recompute_mechanics()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/mechanics/explain":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                t = float(body.get("time_s", 0.0))
                mid = str(body.get("mechanic_id", "") or "")
                include_llm = bool(body.get("include_llm", True))
                data = self.store.explain_mechanic_event(time_s=t, mechanic_id=mid, include_llm=include_llm)
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/replay/open_saved":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            sid = str(body.get("session_id", "")).strip()
            if not sid:
                return self._send_json({"ok": False, "error": "Missing session_id"}, status=400)
            try:
                new_sid = self.store.open_saved_replay(sid)
                return self._send_json({"ok": True, "session_id": new_sid})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/replay/metrics/seek":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            player = str(body.get("player", "")).strip()
            replay_t = body.get("t", 0.0)
            if not player:
                return self._send_json({"ok": False, "error": "Missing player"}, status=400)
            try:
                data = self.store.metrics_seek(player, float(replay_t))
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/replay/player_metrics/start":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            player = str(body.get("player", "")).strip()
            if not player:
                return self._send_json({"ok": False, "error": "Missing player"}, status=400)
            try:
                self.store.start_player_metrics(player)
                return self._send_json({"ok": True, "player": player})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/replay/analysis/select_player":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            player = str(body.get("player", "")).strip()
            if not player:
                return self._send_json({"ok": False, "error": "Missing player"}, status=400)
            try:
                self.store.select_analysis_player(player)
                return self._send_json({"ok": True, "player": player})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/replay/analysis/run":
            try:
                self.store.run_selected_analysis()
                return self._send_json({"ok": True})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args) -> None:
        return


class ReplayDashboardServer:
    def __init__(self, store: ReplayStateStore, host: str = "127.0.0.1", port: int = 8775):
        self.store = store
        self.host = host
        self.port = port
        self.web_dir = Path(__file__).resolve().parent / "web"
        repo_root = Path(__file__).resolve().parents[2]
        self.collision_mesh_dir = repo_root / "collision_meshes"
        self._server = None
        self._thread = None

    def start(self) -> None:
        handler = type("ReplayDashboardHandler", (_ReplayDashboardHandler,), {})
        handler.store = self.store
        handler.web_dir = self.web_dir
        handler.collision_mesh_dir = self.collision_mesh_dir
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
