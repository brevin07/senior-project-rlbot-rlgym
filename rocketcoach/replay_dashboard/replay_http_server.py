from __future__ import annotations

import json
import os
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from typing import Any, Dict
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

try:
    import jwt
except Exception:  # pragma: no cover - optional import guard
    jwt = None

from rocketcoach.replay_dashboard.replay_state_store import DuplicateReplayError, ReplayStateStore


class _ReplayDashboardHandler(BaseHTTPRequestHandler):
    store: ReplayStateStore = None
    web_dir: Path = None
    collision_mesh_dir: Path = None
    session_cookie = "rlcoach_session"
    cognito_issuer: str = os.environ.get("COGNITO_ISSUER", "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_5hkzGscoV")
    cognito_client_id: str = os.environ.get("COGNITO_CLIENT_ID", "63i8m61hqnkapc5s401grl144p")
    cognito_jwt_leeway_seconds: int = int(os.environ.get("COGNITO_JWT_LEEWAY_SECONDS", "120") or "120")
    _jwks_cache: Dict[str, Any] = {"exp": 0.0, "keys": {}}

    def _get_session_id(self) -> str:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        cookie = SimpleCookie()
        cookie.load(raw)
        if self.session_cookie in cookie:
            return str(cookie[self.session_cookie].value or "")
        return ""

    def _set_session_cookie(self, session_id: str) -> None:
        cookie = SimpleCookie()
        cookie[self.session_cookie] = str(session_id)
        cookie[self.session_cookie]["path"] = "/"
        cookie[self.session_cookie]["httponly"] = True
        self.send_header("Set-Cookie", cookie.output(header="").strip())

    def _clear_session_cookie(self) -> None:
        cookie = SimpleCookie()
        cookie[self.session_cookie] = ""
        cookie[self.session_cookie]["path"] = "/"
        cookie[self.session_cookie]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        cookie[self.session_cookie]["httponly"] = True
        self.send_header("Set-Cookie", cookie.output(header="").strip())

    def _require_auth(self) -> Dict[str, Any]:
        sid = self._get_session_id()
        auth = self.store._db.get_auth_user_by_session(session_id=sid) if sid else None
        if not auth:
            if str(os.environ.get("ROCKETCOACH_DEV_BYPASS_AUTH", "")).strip() == "1":
                return self._ensure_dev_profile()
            raise RuntimeError("Please log in first.")
        profile = self.store._db.get_profile_by_auth_user(auth_user_id=int(auth["id"])) or {}
        self.store.set_current_user(profile)
        return {"auth": auth, "profile": profile}

    @classmethod
    def _jwks_uri(cls) -> str:
        base = str(cls.cognito_issuer or "").rstrip("/")
        return f"{base}/.well-known/jwks.json"

    @classmethod
    def _load_jwks(cls) -> Dict[str, Any]:
        now = time.time()
        if cls._jwks_cache.get("keys") and float(cls._jwks_cache.get("exp", 0.0)) > now:
            return cls._jwks_cache["keys"]
        with urlopen(cls._jwks_uri(), timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        keys = {str(k.get("kid")): k for k in (payload.get("keys") or []) if k.get("kid")}
        cls._jwks_cache = {"exp": now + 3600.0, "keys": keys}
        return keys

    @classmethod
    def _verify_cognito_id_token(cls, token: str) -> Dict[str, Any]:
        if jwt is None:
            raise RuntimeError("Missing dependency: PyJWT. Install requirements/base.txt.")
        if not token:
            raise RuntimeError("Missing id_token")
        header = jwt.get_unverified_header(token)
        kid = str(header.get("kid") or "")
        if not kid:
            raise RuntimeError("Invalid token header")
        keys = cls._load_jwks()
        jwk = keys.get(kid)
        if not jwk:
            cls._jwks_cache = {"exp": 0.0, "keys": {}}
            keys = cls._load_jwks()
            jwk = keys.get(kid)
            if not jwk:
                raise RuntimeError("Unable to verify token signature (unknown key id)")
        key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=str(cls.cognito_client_id or ""),
            issuer=str(cls.cognito_issuer or ""),
            leeway=max(0, int(cls.cognito_jwt_leeway_seconds)),
        )
        token_use = str(claims.get("token_use") or "")
        if token_use and token_use != "id":
            raise RuntimeError("Expected Cognito ID token")
        return claims

    @staticmethod
    def _platform_prefers_demos_epic(platform_hint: str = "") -> bool:
        normalized = str(platform_hint or "").strip().lower()
        return normalized in {"epic", "epic games"}

    @staticmethod
    def _discover_replay_folder(platform_hint: str = "") -> Path:
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
        standard_candidates = []
        prefers_epic = _ReplayDashboardHandler._platform_prefers_demos_epic(platform_hint)
        for docs in clean_docs:
            epic_candidates = [
                docs / "My Games" / "Rocket League" / "TAGame" / "DemosEpic",
                docs / "My Games" / "Rocket League" / "TAGame" / "Demos Epic",
            ]
            standard_candidate = docs / "My Games" / "Rocket League" / "TAGame" / "Demos"
            standard_candidates.append(standard_candidate)
            if prefers_epic:
                replay_candidates.extend(epic_candidates)
                replay_candidates.append(standard_candidate)
            else:
                replay_candidates.append(standard_candidate)
                replay_candidates.extend(epic_candidates)

        for p in replay_candidates:
            if p.exists() and p.is_dir():
                return p
        for p in standard_candidates:
            if p.parent.exists() and p.parent.is_dir():
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
        try:
            sid = self._get_session_id()
            if sid:
                auth = self.store._db.get_auth_user_by_session(session_id=sid)
                if auth:
                    profile = self.store._db.get_profile_by_auth_user(auth_user_id=int(auth["id"])) or {}
                    self.store.set_current_user(profile)
        except Exception:
            pass
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
        if path == "/api/auth/me":
            try:
                sid = self._get_session_id()
                auth = self.store._db.get_auth_user_by_session(session_id=sid) if sid else None
                if not auth:
                    return self._send_json({"ok": False, "auth": None, "profile": None})
                profile = self.store._db.get_profile_by_auth_user(auth_user_id=int(auth["id"])) or {}
                self.store.set_current_user(profile)
                return self._send_json({"ok": True, "auth": auth, "profile": profile})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/profile":
            try:
                ctx = self._require_auth()
                return self._send_json({"ok": True, "profile": ctx.get("profile") or {}})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/profile/current":
            try:
                ctx = self._require_auth()
                return self._send_json({"ok": True, "profile": ctx.get("profile") or {}})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/replay/library":
            try:
                data = self.store.library_sessions()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if path == "/api/replay/mechanic-feedback":
            try:
                feedback_file = Path(__file__).resolve().parents[2] / "artifacts" / "data" / "mechanic_feedback.jsonl"
                if not feedback_file.exists():
                    return self._send_json({"ok": True, "entries": []})
                entries = []
                with open(feedback_file, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                return self._send_json({"ok": True, "entries": entries})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=500)
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
        if path == "/api/mechanics/explain_progress":
            try:
                data = self.store.explain_progress()
                return self._send_json({"ok": True, "data": data})
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
        try:
            sid = self._get_session_id()
            if sid:
                auth = self.store._db.get_auth_user_by_session(session_id=sid)
                if auth:
                    profile = self.store._db.get_profile_by_auth_user(auth_user_id=int(auth["id"])) or {}
                    self.store.set_current_user(profile)
        except Exception:
            pass
        if self.path == "/api/auth/cognito/login":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                claims = self._verify_cognito_id_token(str(body.get("id_token", "")).strip())
                auth = self.store._db.upsert_auth_user_from_cognito(
                    cognito_sub=str(claims.get("sub", "")).strip(),
                    email=str(claims.get("email", "")).strip(),
                )
                sid = self.store._db.create_session(user_id=int(auth["id"]))
                profile = self.store._db.get_profile_by_auth_user(auth_user_id=int(auth["id"])) or {}
                self.store.set_current_user(profile)
                self.store.clear_current_replay()
                self.send_response(HTTPStatus.OK)
                self._set_session_cookie(sid)
                self.send_header("Content-Type", "application/json")
                payload = json.dumps({"ok": True, "auth": auth, "profile": profile}).encode("utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=401)
        if self.path == "/api/auth/signup":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                email = str(body.get("email", "")).strip()
                password = str(body.get("password", "")).strip()
                auth = self.store._db.create_auth_user(email=email, password=password)
                sid = self.store._db.create_session(user_id=int(auth["id"]))
                profile = self.store._db.get_profile_by_auth_user(auth_user_id=int(auth["id"])) or {}
                self.store.clear_current_replay()
                self.send_response(HTTPStatus.OK)
                self._set_session_cookie(sid)
                self.send_header("Content-Type", "application/json")
                payload = json.dumps({"ok": True, "auth": auth, "profile": profile}).encode("utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/auth/login":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                auth = self.store._db.authenticate(
                    email=str(body.get("email", "")).strip(),
                    password=str(body.get("password", "")).strip(),
                )
                sid = self.store._db.create_session(user_id=int(auth["id"]))
                profile = self.store._db.get_profile_by_auth_user(auth_user_id=int(auth["id"])) or {}
                self.store.set_current_user(profile)
                self.store.clear_current_replay()
                self.send_response(HTTPStatus.OK)
                self._set_session_cookie(sid)
                self.send_header("Content-Type", "application/json")
                payload = json.dumps({"ok": True, "auth": auth, "profile": profile}).encode("utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/auth/logout":
            sid = self._get_session_id()
            if sid:
                try:
                    self.store._db.delete_session(session_id=sid)
                except Exception:
                    pass
            self.send_response(HTTPStatus.OK)
            self._clear_session_cookie()
            self.send_header("Content-Type", "application/json")
            payload = json.dumps({"ok": True}).encode("utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/api/profile/setup":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                ctx = self._require_auth()
                auth = ctx["auth"]
                profile = self.store._db.upsert_user(
                    username=str(body.get("username", "")).strip(),
                    rank_tier=str(body.get("rank_tier", "")).strip(),
                    platform=str(body.get("platform", "")).strip(),
                    aliases=[str(x) for x in (body.get("aliases", []) or [])] if isinstance(body.get("aliases", []), list) else [],
                    auth_user_id=int(auth["id"]),
                )
                self.store.set_current_user(profile)
                self.store.clear_current_replay()
                return self._send_json({"ok": True, "profile": profile})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/profile/update":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                ctx = self._require_auth()
                auth = ctx["auth"]
                profile = self.store._db.upsert_user(
                    username=str(body.get("username", "")).strip(),
                    rank_tier=str(body.get("rank_tier", "")).strip(),
                    platform=str(body.get("platform", "")).strip(),
                    aliases=[str(x) for x in (body.get("aliases", []) or [])] if isinstance(body.get("aliases", []), list) else [],
                    auth_user_id=int(auth["id"]),
                )
                self.store.set_current_user(profile)
                return self._send_json({"ok": True, "profile": profile})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

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
        if self.path == "/api/replay/clear_current":
            try:
                self.store.clear_current_replay()
                return self._send_json({"ok": True})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/replay/open_default_folder":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                target = self._discover_replay_folder(str(body.get("platform", "")).strip())
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
                return self._send_json({"ok": False, "error": "Use /api/auth/login and /api/profile/setup instead."}, status=400)
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/profile/logout":
            try:
                return self._send_json({"ok": False, "error": "Use /api/auth/logout instead."}, status=400)
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
        if self.path == "/api/mechanics/explain_batch":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                include_llm = bool(body.get("include_llm", True))
                mode = str(body.get("mode", "hybrid") or "hybrid")
                time_budget_s = float(body.get("time_budget_s", 20.0) or 20.0)
                preload_limit = int(body.get("preload_limit", 20) or 20)
                data = self.store.explain_mechanic_events_batch(
                    include_llm=include_llm,
                    mode=mode,
                    time_budget_s=time_budget_s,
                    preload_limit=preload_limit,
                )
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
                result = self.store.open_saved_replay(sid)
                return self._send_json({"ok": True, **dict(result or {})})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/replay/library/recompute":
            try:
                data = self.store.recompute_library_replays()
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)

        if self.path == "/api/replay/delete":
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
                result = self.store.delete_saved_replay(sid)
                return self._send_json({"ok": True, **dict(result or {})})
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

        if self.path == "/api/replay/mechanic-feedback":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            note = str(body.get("note", "")).strip()
            if not note:
                return self._send_json({"ok": False, "error": "Note is required"}, status=400)
            entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "replay_name": str(body.get("replay_name", "unknown")),
                "event_time": float(body.get("event_time", 0.0)),
                "mechanic_id": str(body.get("mechanic_id", "")),
                "quality_label": str(body.get("quality_label", "")),
                "quality_score": float(body.get("quality_score", 0.0)),
                "reason": str(body.get("reason", "")),
                "note": note,
            }
            feedback_file = Path(__file__).resolve().parents[2] / "artifacts" / "data" / "mechanic_feedback.jsonl"
            feedback_file.parent.mkdir(parents=True, exist_ok=True)
            with open(feedback_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
            return self._send_json({"ok": True})

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


_BaseReplayDashboardHandler = _ReplayDashboardHandler
_BaseReplayDashboardServer = ReplayDashboardServer


class _ReplayDashboardHandler(_BaseReplayDashboardHandler):
    def _external_base_url(self) -> str:
        host = str(self.headers.get("X-Forwarded-Host", "") or self.headers.get("Host", "") or "").strip()
        if not host:
            host = f"{self.server.server_address[0]}:{self.server.server_address[1]}"
        proto = str(self.headers.get("X-Forwarded-Proto", "") or "").strip().lower()
        if not proto:
            proto = "https" if host.endswith(".ngrok.app") else "http"
        return f"{proto}://{host}"

    def _ensure_dev_profile(self) -> Dict[str, Any]:
        auth = self.store._db.get_auth_user_by_email(email="brevintating1@gmail.com")
        if not auth:
            auth = self.store._db.create_auth_user(email="brevintating1@gmail.com", password="dev-bypass-only")
        profile = self.store._db.get_profile_by_auth_user(auth_user_id=int(auth["id"])) or {}
        if not profile:
            profile = self.store._db.upsert_user(
                username="brevintating1",
                rank_tier="diamond_1",
                platform="epic",
                aliases=[],
                auth_user_id=int(auth["id"]),
            )
        self.store.set_current_user(profile)
        return {"auth": auth, "profile": profile}

    def _require_auth(self) -> Dict[str, Any]:
        sid = self._get_session_id()
        auth = self.store._db.get_auth_user_by_session(session_id=sid) if sid else None
        if auth:
            profile = self.store._db.get_profile_by_auth_user(auth_user_id=int(auth["id"])) or {}
            self.store.set_current_user(profile)
            return {"auth": auth, "profile": profile}
        if str(os.environ.get("ROCKETCOACH_DEV_BYPASS_AUTH", "")).strip() == "1":
            return self._ensure_dev_profile()
        raise RuntimeError("Please log in first.")

    def do_GET(self):
        if self.path == "/api/auth/me":
            try:
                ctx = self._require_auth()
                return self._send_json({"ok": True, "auth": ctx.get("auth"), "profile": ctx.get("profile")})
            except Exception:
                return self._send_json({"ok": False, "auth": None, "profile": None})
        if self.path == "/api/home/summary":
            try:
                ctx = self._require_auth()
                self.store.set_current_user(ctx.get("profile") or {})
                return self._send_json({"ok": True, "data": self.store.home_summary()})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/training/plan":
            try:
                ctx = self._require_auth()
                self.store.set_current_user(ctx.get("profile") or {})
                return self._send_json({"ok": True, "data": self.store.training_plan()})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/training/preflight":
            try:
                ctx = self._require_auth()
                auth = ctx["auth"]
                cached = self.store.latest_training_preflight_for_auth_user(auth_user_id=int(auth["id"])) or {}
                if cached:
                    return self._send_json({"ok": True, "data": cached})
                return self._send_json(
                    {
                        "ok": True,
                        "data": {
                            "host_checks_available": False,
                            "launcher_kind": "training_bridge",
                            "launcher_running": False,
                            "dependency_ready": False,
                            "shared_dependency_ready": False,
                            "python_ready": False,
                            "rlbot_import_ok": False,
                            "rlbot_gui_detected": False,
                            "rlbot_gui_path": "",
                            "rlbot_gui_detection_source": "not_checked_yet",
                            "rocket_league_detected": False,
                            "last_checked_at": 0,
                            "scenario_count": 0,
                            "bot_statuses": [],
                            "ready_to_launch": False,
                            "messages": [
                                "RocketCoach has not verified this machine yet.",
                                "Use Verify Dependencies to start the local companion and scan this machine.",
                            ],
                        },
                    }
                )
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path.startswith("/api/training/bridge_session/status"):
            token = str((parse_qs(urlparse(self.path).query).get("token", [""])[0] or "")).strip()
            if not token:
                return self._send_json({"ok": False, "error": "Missing token"}, status=400)
            try:
                data = self.store.get_training_bridge_session(token=token)
                if not data:
                    return self._send_json({"ok": False, "error": "Unknown token"}, status=404)
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/installer/info":
            repo_root = Path(__file__).resolve().parents[2]
            installer_path = repo_root / "dist" / "RLBotStackInstaller.exe"
            if installer_path.exists():
                size_mb = round(installer_path.stat().st_size / (1024 * 1024), 1)
                return self._send_json({"ok": True, "data": {"available": True, "filename": "RLBotStackInstaller.exe", "size_mb": size_mb}})
            return self._send_json({"ok": True, "data": {"available": False}})
        if self.path == "/api/installer/download":
            repo_root = Path(__file__).resolve().parents[2]
            installer_path = repo_root / "dist" / "RLBotStackInstaller.exe"
            if not installer_path.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "Installer not found")
                return
            data = installer_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="RLBotStackInstaller.exe"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/auth/delete_account":
            try:
                ctx = self._require_auth()
                auth = ctx["auth"]
                self.store.clear_current_replay()
                self.store._db.delete_account(auth_user_id=int(auth["id"]))
                self.send_response(HTTPStatus.OK)
                self._clear_session_cookie()
                self.send_header("Content-Type", "application/json")
                payload = json.dumps({"ok": True}).encode("utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
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
                    platform=str(body.get("platform", "")).strip(),
                )
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path == "/api/training/bridge_session/start":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                ctx = self._require_auth()
                auth = ctx["auth"]
                action = str(body.get("action", "")).strip().lower()
                if action not in {"verify", "launch"}:
                    raise RuntimeError("Unsupported bridge session action.")
                payload = dict(body.get("payload", {}) or {})
                session = self.store.start_training_bridge_session(
                    auth_user_id=int(auth["id"]),
                    action=action,
                    payload=payload,
                )
                token = str(session.get("token", "") or "")
                callback_url = f"{self._external_base_url()}/api/replay/training/bridge_session/callback?token={token}"
                return self._send_json({"ok": True, "data": {"token": token, "action": action, "callback_url": callback_url}})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        if self.path.startswith("/api/training/bridge_session/callback"):
            token = str((parse_qs(urlparse(self.path).query).get("token", [""])[0] or "")).strip()
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            try:
                data = self.store.complete_training_bridge_session(
                    token=token,
                    ok=bool(body.get("ok", False)),
                    payload=dict(body.get("payload", {}) or {}),
                    error_message=str(body.get("error", "") or ""),
                )
                return self._send_json({"ok": True, "data": data})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        return super().do_POST()


class ReplayDashboardServer(_BaseReplayDashboardServer):
    def start(self) -> None:
        handler = type("RocketCoachReplayDashboardHandler", (_ReplayDashboardHandler,), {})
        handler.store = self.store
        handler.web_dir = self.web_dir
        handler.collision_mesh_dir = self.collision_mesh_dir
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
