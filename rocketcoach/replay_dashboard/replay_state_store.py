from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import threading
import uuid
import traceback
import hashlib
import gzip
import json
import time
from bisect import bisect_right
from pathlib import Path
import os
import socket
from datetime import datetime
from urllib import error, request
import pandas as pd

from rocketcoach.common.persistence import AppDB
from rocketcoach.live_analysis.llm_event_explainer import maybe_rewrite_explanation, maybe_rewrite_explanations_batch
from rocketcoach.live_analysis.mechanic_grader import grade_game_mechanics, summarize_mechanic_scores, explain_mechanic_event
from rocketcoach.live_analysis.recommendation_engine import compute_recommendations
from rocketcoach.replay_dashboard.replay_loader import DEBUG_METRIC_KEYS, METRIC_KEYS, ReplaySession, ensure_player_metrics, load_replay_bytes
from rocketcoach.replay_dashboard.training_catalog import NON_BOT_DRILL_SUMMARIES, build_training_option


class DuplicateReplayError(RuntimeError):
    def __init__(self, message: str, existing_session_id: str = "", existing_replay_name: str = ""):
        super().__init__(message)
        self.existing_session_id = str(existing_session_id or "")
        self.existing_replay_name = str(existing_replay_name or "")


@dataclass
class ReplayJobState:
    session_id: str = ""
    status: str = "idle"
    progress: float = 0.0
    message: str = "No replay loaded."
    error: str = ""
    replay_name: str = ""
    ready: bool = False
    phase: str = "idle"
    checklist: Dict[str, bool] = field(
        default_factory=lambda: {
            "upload_received": False,
            "replay_parsed": False,
            "timeline_ready": False,
            "analysis_ready": False,
            "dashboard_ready": False,
        }
    )
    duplicate: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplaySharedState:
    job: ReplayJobState = field(default_factory=ReplayJobState)
    session: Optional[ReplaySession] = None
    player_metric_jobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    metrics_status: str = "idle"
    metrics_error: str = ""
    metrics_ready_count: int = 0
    metrics_total_count: int = 0
    analysis_player: str = ""
    analysis_locked: bool = False
    analysis_ready: bool = False
    analysis_error: str = ""
    current_user: Dict[str, Any] = field(default_factory=dict)
    recommendations: Dict[str, Any] = field(default_factory=dict)
    mechanics: Dict[str, Any] = field(default_factory=dict)
    last_duplicate_cleanup_removed: int = 0
    explain_progress: Dict[str, Any] = field(default_factory=dict)
    explain_background_session_id: str = ""


class ReplayStateStore:
    def __init__(self, *, db: AppDB):
        self._lock = threading.Lock()
        self._state = ReplaySharedState()
        self._db = db
        self._artifact_root = Path(__file__).resolve().parents[2] / "artifacts" / "replay_library"
        self._artifact_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _discover_replay_dirs() -> list[Path]:
        home = Path.home()
        docs_candidates = [
            home / "Documents",
            home / "OneDrive" / "Documents",
        ]
        one_drive_env = os.environ.get("OneDrive", "").strip()
        if one_drive_env:
            docs_candidates.append(Path(one_drive_env) / "Documents")
        seen = set()
        out: list[Path] = []
        for docs in docs_candidates:
            for rel in (
                Path("My Games") / "Rocket League" / "TAGame" / "DemosEpic",
                Path("My Games") / "Rocket League" / "TAGame" / "Demos Epic",
                Path("My Games") / "Rocket League" / "TAGame" / "Demos",
            ):
                p = (docs / rel).resolve()
                k = str(p).lower()
                if k in seen:
                    continue
                seen.add(k)
                out.append(p)
        return out

    def _find_replay_in_folders(self, replay_name: str) -> Path | None:
        wanted = str(Path(replay_name).name or "").strip()
        if not wanted:
            return None
        wl = wanted.lower()
        for d in self._discover_replay_dirs():
            if not d.exists() or not d.is_dir():
                continue
            direct = d / wanted
            if direct.exists() and direct.is_file():
                return direct
            try:
                for p in d.iterdir():
                    if p.is_file() and p.name.lower() == wl:
                        return p
            except Exception:
                continue
        return None

    @staticmethod
    def _norm_player_name(v: str) -> str:
        return "".join(ch.lower() for ch in str(v or "") if ch.isalnum() or ch in ("_", "-"))

    def _match_profile_player(self, *, players: List[str], profile: Dict[str, Any]) -> str:
        names = [str(profile.get("username", "") or "")]
        names.extend([str(x or "") for x in (profile.get("aliases", []) or [])])
        acceptable = {self._norm_player_name(n) for n in names if str(n or "").strip()}
        if not acceptable:
            return ""
        for p in players or []:
            if self._norm_player_name(str(p)) in acceptable:
                return str(p)
        return ""

    @staticmethod
    def _timed(stage: str, started_at: float) -> None:
        dt = max(0.0, time.time() - float(started_at or time.time()))
        print(f"[replay_perf] {stage} {dt:.3f}s")

    @staticmethod
    def _serialize_prepared_payload(payload: Dict[str, Any]) -> bytes:
        raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        return gzip.compress(raw, compresslevel=6)

    @staticmethod
    def _deserialize_prepared_payload(blob: bytes) -> Dict[str, Any]:
        if not blob:
            return {}
        try:
            raw = gzip.decompress(bytes(blob))
            return dict(json.loads(raw.decode("utf-8")))
        except Exception:
            return {}

    def _persist_prepared_replay(self, *, session: ReplaySession, player: str, mechanics_payload: Dict[str, Any]) -> None:
        profile = self.current_profile()
        if not profile:
            return
        row = self._db.get_replay_session(session_id=session.session_id, user_id=int(profile["id"])) or {}
        prepared = {
            "schema_version": 1,
            "analysis_player": str(player or ""),
            "replay_name": str(session.replay_name or ""),
            "players": [str(p) for p in (session.players or [])],
            "duration_s": float(session.duration_s or 0.0),
            "timeline": list(session.timeline or []),
            "boost_pads": list(session.boost_pads or []),
            "replay_meta": dict(session.replay_meta or {}),
            "metrics_by_player": dict(session.metrics_by_player or {}),
            "events_by_player": dict(session.events_by_player or {}),
            "mechanics": dict(mechanics_payload or {}),
        }
        payload_blob = self._serialize_prepared_payload(prepared)
        self._db.save_replay_session(
            session_id=session.session_id,
            user_id=int(profile["id"]),
            source_type=str((row.get("source_type", "") or "replay_upload")),
            replay_name=str((row.get("replay_name", "") or session.replay_name)),
            map_name=str((row.get("map_name", "") or (session.replay_meta or {}).get("map_name", "soccar"))),
            duration_s=float(row.get("duration_s", session.duration_s or 0.0) or 0.0),
            tracked_player_name=str((row.get("tracked_player_name", "") or player)),
            tracked_player_index=int(row.get("tracked_player_index", 0) or 0),
            artifact_manifest=dict(row.get("artifact_manifest", {}) or {}),
            prepared_payload=payload_blob,
            summary=dict(row.get("summary", {}) or {}),
            created_at=str(row.get("created_at", "")) or None,
        )

    def _load_prepared_replay_into_state(self, *, row: Dict[str, Any]) -> bool:
        payload = self._deserialize_prepared_payload(bytes(row.get("prepared_payload", b"") or b""))
        if not payload:
            return False
        try:
            session = ReplaySession(
                session_id=str(row.get("session_id", "")),
                replay_name=str(payload.get("replay_name", row.get("replay_name", "")) or ""),
                players=[str(p) for p in (payload.get("players", []) or [])],
                timeline=list(payload.get("timeline", []) or []),
                boost_pads=list(payload.get("boost_pads", []) or []),
                replay_meta=dict(payload.get("replay_meta", {}) or {}),
                df=pd.DataFrame(),
                duration_s=float(payload.get("duration_s", row.get("duration_s", 0.0)) or 0.0),
                metrics_by_player=dict(payload.get("metrics_by_player", {}) or {}),
                events_by_player=dict(payload.get("events_by_player", {}) or {}),
            )
            analysis_player = str(payload.get("analysis_player", "") or "")
            mechanics = dict(payload.get("mechanics", {}) or {})
            with self._lock:
                self._state.session = session
                self._state.analysis_player = analysis_player
                self._state.analysis_locked = bool(analysis_player)
                self._state.analysis_ready = bool(analysis_player)
                self._state.analysis_error = ""
                self._state.metrics_status = "ready" if analysis_player else "idle"
                self._state.metrics_error = ""
                self._state.metrics_ready_count = 1 if analysis_player else 0
                self._state.metrics_total_count = 1 if analysis_player else 0
                self._state.mechanics = mechanics
                self._state.player_metric_jobs = {
                    p: {"status": "ready" if p == analysis_player else "idle", "message": "Metrics ready." if p == analysis_player else "Not selected.", "error": ""}
                    for p in (session.players or [])
                }
                self._set_job(
                    session_id=str(session.session_id or ""),
                    status="ready",
                    progress=1.0,
                    message="Replay loaded from cache. Ready to play.",
                    replay_name=str(session.replay_name or ""),
                    phase="ready",
                    checklist={
                        "upload_received": True,
                        "replay_parsed": True,
                        "timeline_ready": True,
                        "analysis_ready": bool(analysis_player),
                        "dashboard_ready": True,
                    },
                )
            return True
        except Exception:
            return False

    def login_profile(self, *, username: str, rank_tier: str, platform: str, aliases: list[str] | None = None) -> Dict[str, Any]:
        profile = self._db.upsert_user(username=username, rank_tier=rank_tier, platform=platform, aliases=aliases)
        removed = int(self._db.prune_duplicate_replay_names(user_id=int(profile["id"])) or 0)
        with self._lock:
            self._state.current_user = dict(profile)
            self._state.last_duplicate_cleanup_removed = removed
        return profile

    def set_current_user(self, profile: Dict[str, Any] | None) -> None:
        with self._lock:
            self._state.current_user = dict(profile or {})

    def clear_current_user(self) -> None:
        with self._lock:
            self._state.current_user = {}

    def clear_current_replay(self) -> None:
        with self._lock:
            self._state.session = None
            self._state.player_metric_jobs = {}
            self._state.metrics_status = "idle"
            self._state.metrics_error = ""
            self._state.metrics_ready_count = 0
            self._state.metrics_total_count = 0
            self._state.analysis_player = ""
            self._state.analysis_locked = False
            self._state.analysis_ready = False
            self._state.analysis_error = ""
            self._state.mechanics = {}
            self._state.explain_progress = {}
            self._state.explain_background_session_id = ""
            self._set_job(
                session_id="",
                status="idle",
                progress=0.0,
                message="No replay loaded.",
                replay_name="",
                phase="idle",
                checklist={
                    "upload_received": False,
                    "replay_parsed": False,
                    "timeline_ready": False,
                    "analysis_ready": False,
                    "dashboard_ready": False,
                },
            )

    def logout_profile(self) -> None:
        self._db.clear_active_user()
        with self._lock:
            self._state.current_user = {}
            self._state.recommendations = {}
            self._state.mechanics = {}
            self._state.explain_progress = {}
            self._state.explain_background_session_id = ""

    def refresh_recommendations(self) -> Dict[str, Any]:
        profile = self._require_user()
        payload = compute_recommendations(self._db, int(profile["id"]), window_size=5)
        with self._lock:
            self._state.recommendations = dict(payload or {})
        return payload

    def current_recommendations(self) -> Dict[str, Any]:
        with self._lock:
            if self._state.recommendations:
                return dict(self._state.recommendations)
        profile = self.current_profile()
        if not profile:
            return {}
        payload = compute_recommendations(self._db, int(profile["id"]), window_size=5)
        with self._lock:
            self._state.recommendations = dict(payload or {})
        return payload

    def current_profile(self) -> Dict[str, Any]:
        with self._lock:
            if self._state.current_user:
                return dict(self._state.current_user)
        profile = self._db.current_user() or {}
        with self._lock:
            self._state.current_user = dict(profile)
        return dict(profile)

    def _require_user(self) -> Dict[str, Any]:
        profile = self.current_profile()
        if not profile:
            raise RuntimeError("Please log in first.")
        return profile

    def _set_job(
        self,
        *,
        session_id: str,
        status: str,
        progress: float,
        message: str,
        error: str = "",
        replay_name: str = "",
        phase: str | None = None,
        checklist: Dict[str, bool] | None = None,
        duplicate: Dict[str, Any] | None = None,
    ) -> None:
        self._state.job = ReplayJobState(
            session_id=session_id,
            status=status,
            progress=max(0.0, min(1.0, progress)),
            message=message,
            error=error,
            replay_name=replay_name,
            ready=status == "ready",
            phase=str(phase or status or "idle"),
            checklist=dict(checklist or {}),
            duplicate=dict(duplicate or {}),
        )

    def _replay_sha1(self, data: bytes) -> str:
        return hashlib.sha1(data).hexdigest()

    def _is_duplicate_replay_hash(self, *, user_id: int, replay_sha1: str) -> bool:
        rows = self._db.list_replay_sessions_detailed(user_id=int(user_id), limit=1000)
        target = str(replay_sha1 or "").strip().lower()
        if not target:
            return False
        for r in rows:
            s = dict(r.get("summary", {}) or {})
            if str(s.get("replay_sha1", "")).strip().lower() == target:
                return True
        return False

    def _duplicate_row_by_hash(self, *, user_id: int, replay_sha1: str) -> Dict[str, Any]:
        rows = self._db.list_replay_sessions_detailed(user_id=int(user_id), limit=1000)
        target = str(replay_sha1 or "").strip().lower()
        for r in rows:
            s = dict(r.get("summary", {}) or {})
            if str(s.get("replay_sha1", "")).strip().lower() == target:
                return dict(r)
        return {}

    def _is_duplicate_replay_name(self, *, user_id: int, replay_name: str) -> bool:
        target = str(replay_name or "").strip().lower()
        if not target:
            return False
        rows = self._db.list_replay_sessions(user_id=int(user_id), limit=1000)
        for r in rows:
            if str(r.get("replay_name", "")).strip().lower() == target:
                return True
        return False

    def start_processing(
        self,
        file_name: str,
        data: bytes,
        rrrocket_override: str | None = None,
        *,
        persist_to_library: bool = True,
    ) -> str:
        profile = self._require_user()
        # Keep DB/library aligned: if not visible in library (no blob), it should not remain saved.
        self._db.delete_replay_sessions_without_blob(user_id=int(profile["id"]))
        # Cleanup legacy duplicates before enforcing current constraints.
        if persist_to_library:
            removed = int(self._db.prune_duplicate_replay_names(user_id=int(profile["id"])) or 0)
            with self._lock:
                self._state.last_duplicate_cleanup_removed = removed
        replay_sha1 = self._replay_sha1(data)
        if persist_to_library and self._is_duplicate_replay_hash(user_id=int(profile["id"]), replay_sha1=replay_sha1):
            drow = self._duplicate_row_by_hash(user_id=int(profile["id"]), replay_sha1=replay_sha1)
            raise DuplicateReplayError(
                "This replay is already in your library.",
                existing_session_id=str(drow.get("session_id", "")),
                existing_replay_name=str(drow.get("replay_name", "")),
            )
        if persist_to_library and self._is_duplicate_replay_name(user_id=int(profile["id"]), replay_name=file_name):
            rows = self._db.list_replay_sessions(user_id=int(profile["id"]), limit=1000)
            match = next((r for r in rows if str(r.get("replay_name", "")).strip().lower() == str(file_name).strip().lower()), {})
            raise DuplicateReplayError(
                "A replay with this name already exists in your library.",
                existing_session_id=str(match.get("session_id", "")),
                existing_replay_name=str(match.get("replay_name", "")),
            )
        session_id = uuid.uuid4().hex
        with self._lock:
            self._set_job(
                session_id=session_id,
                status="parsing",
                progress=0.1,
                message="Preparing replay processing...",
                replay_name=file_name,
                phase="uploading",
                checklist={
                    "upload_received": True,
                    "replay_parsed": False,
                    "timeline_ready": False,
                    "analysis_ready": False,
                    "dashboard_ready": False,
                },
            )
            self._state.session = None
            self._state.player_metric_jobs = {}
            self._state.metrics_status = "idle"
            self._state.metrics_error = ""
            self._state.metrics_ready_count = 0
            self._state.metrics_total_count = 0
            self._state.analysis_player = ""
            self._state.analysis_locked = False
            self._state.analysis_ready = False
            self._state.analysis_error = ""
            self._state.mechanics = {}
            self._state.explain_progress = {}
            self._state.explain_background_session_id = ""

        def _run():
            nonlocal session_id
            t_all = time.time()
            try:
                with self._lock:
                    self._state.job.status = "parsing"
                    self._state.job.progress = 0.25
                    self._state.job.message = "Running rrrocket parser..."
                    self._state.job.phase = "parsing"
                    self._state.job.checklist["upload_received"] = True

                t_parse = time.time()
                session = load_replay_bytes(file_name=file_name, data=data, rrrocket_override=rrrocket_override)
                self._timed("parse_replay_bytes", t_parse)
                session_id = session.session_id
                tracked_name = self._match_profile_player(players=[str(p) for p in (session.players or [])], profile=profile)
                if not tracked_name:
                    wanted = str(profile.get("username", "") or "your account")
                    msg = f"No player with name '{wanted}' found in this replay. Please try another replay."
                    with self._lock:
                        self._state.session = None
                        self._state.player_metric_jobs = {}
                        self._state.analysis_player = ""
                        self._state.analysis_locked = False
                        self._state.analysis_ready = False
                        self._state.mechanics = {}
                        self._set_job(
                            session_id=session_id,
                            status="error",
                            progress=1.0,
                            message=msg,
                            error=msg,
                            replay_name=file_name,
                            phase="error",
                            checklist={
                                "upload_received": True,
                                "replay_parsed": True,
                                "timeline_ready": False,
                                "analysis_ready": False,
                                "dashboard_ready": False,
                            },
                        )
                    return

                replay_dir = self._artifact_root / session_id
                replay_dir.mkdir(parents=True, exist_ok=True)
                replay_path = replay_dir / Path(file_name).name
                replay_path.write_bytes(data)
                with self._lock:
                    self._state.job.checklist["replay_parsed"] = True
                    self._state.job.checklist["timeline_ready"] = True
                    self._state.job.progress = max(self._state.job.progress, 0.8)
                    self._state.job.message = "Replay parsed and timeline built."

                with self._lock:
                    self._state.session = session
                    self._state.player_metric_jobs = {
                        p: {"status": "idle", "message": "Select player and run analysis.", "error": ""} for p in session.players
                    }
                    self._state.metrics_status = "idle"
                    self._state.metrics_error = ""
                    self._state.metrics_ready_count = 0
                    self._state.metrics_total_count = 1 if session.players else 0
                    self._state.analysis_player = tracked_name
                    self._state.analysis_locked = True
                    self._state.analysis_ready = False
                    self._state.analysis_error = ""
                    self._set_job(
                        session_id=session.session_id,
                        status="ready",
                        progress=1.0,
                        message="Replay loaded. Ready to play.",
                        replay_name=session.replay_name,
                        phase="ready",
                        checklist={
                            "upload_received": True,
                            "replay_parsed": True,
                            "timeline_ready": True,
                            "analysis_ready": True,
                            "dashboard_ready": True,
                        },
                    )
                summary = {}
                if session.players:
                    summary["player_count"] = len(session.players)
                summary["replay_sha1"] = replay_sha1
                replay_date_iso = str((session.replay_meta or {}).get("replay_date_iso", "") or "")
                summary["replay_date_iso"] = replay_date_iso
                summary["replay_date_source"] = "replay_meta" if replay_date_iso else "created_at_fallback"
                if persist_to_library:
                    t_save = time.time()
                    self._db.save_replay_session(
                        session_id=session.session_id,
                        user_id=int(profile["id"]),
                        source_type="replay_upload",
                        replay_name=session.replay_name,
                        map_name=str((session.replay_meta or {}).get("map_name", "soccar")),
                        duration_s=float(session.duration_s or 0.0),
                        tracked_player_name=tracked_name,
                        tracked_player_index=0,
                        artifact_manifest={"replay_file": str(replay_path)},
                        replay_blob=data,
                        summary=summary,
                    )
                    self._timed("save_replay_session_blob", t_save)
                    saved = self._db.get_replay_session(session_id=session.session_id, user_id=int(profile["id"])) or {}
                    if not bool(saved.get("has_replay_blob", False)):
                        raise RuntimeError("Replay upload was parsed but could not be persisted to DB blob storage.")
                self._timed("start_processing_total", t_all)
            except Exception as exc:
                trace = traceback.format_exc()
                with self._lock:
                    self._set_job(
                        session_id=session_id,
                        status="error",
                        progress=1.0,
                        message="Replay processing failed.",
                        error=f"{exc}\n{trace}",
                        replay_name=file_name,
                        phase="error",
                    )

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return session_id

    def library_sessions(self) -> Dict[str, Any]:
        profile = self._require_user()
        self._db.delete_replay_sessions_without_blob(user_id=int(profile["id"]))
        removed = int(self._db.prune_duplicate_replay_names(user_id=int(profile["id"])) or 0)
        sessions = self._db.list_replay_sessions(user_id=int(profile["id"]), limit=300)
        with self._lock:
            self._state.last_duplicate_cleanup_removed = removed
        return {
            "profile": profile,
            "sessions": sessions,
            "cleanup": {"duplicate_names_removed": removed},
        }

    def open_saved_replay(self, session_id: str) -> Dict[str, Any]:
        profile = self._require_user()
        row = self._db.get_replay_session(session_id=session_id, user_id=int(profile["id"]))
        if not row:
            raise RuntimeError("Saved replay not found.")
        t_open = time.time()
        if bool(row.get("has_prepared_payload", False)) and row.get("prepared_payload", None):
            if self._load_prepared_replay_into_state(row=row):
                self._timed("open_saved_prepared_payload", t_open)
                sid = str(row.get("session_id", "") or session_id)
                return {
                    "session_id": sid,
                    "opened_from_prepared_cache": True,
                    "opened_from_replay_blob": False,
                    "requires_reanalysis": False,
                    "open_mode": "prepared_cache",
                }
        blob = row.get("replay_blob", None)
        replay_name = str(row.get("replay_name", "") or "")
        if isinstance(blob, (bytes, bytearray)) and len(blob) > 0:
            fallback_name = replay_name or f"{session_id}.replay"
            sid = self.start_processing(file_name=Path(fallback_name).name, data=bytes(blob), persist_to_library=False)
            return {
                "session_id": str(sid or ""),
                "opened_from_prepared_cache": False,
                "opened_from_replay_blob": True,
                "requires_reanalysis": True,
                "open_mode": "replay_blob",
            }
        manifest = row.get("artifact_manifest", {}) or {}
        replay_file = Path(str(manifest.get("replay_file", "")))
        if replay_file.exists() and replay_file.is_file():
            sid = self.start_processing(file_name=replay_file.name, data=replay_file.read_bytes(), persist_to_library=False)
            return {
                "session_id": str(sid or ""),
                "opened_from_prepared_cache": False,
                "opened_from_replay_blob": False,
                "requires_reanalysis": True,
                "open_mode": "artifact_file",
            }
        replay_name = str(replay_name or replay_file.name or "")
        alt = self._find_replay_in_folders(replay_name)
        if alt and alt.exists() and alt.is_file():
            sid = self.start_processing(file_name=alt.name, data=alt.read_bytes(), persist_to_library=False)
            return {
                "session_id": str(sid or ""),
                "opened_from_prepared_cache": False,
                "opened_from_replay_blob": False,
                "requires_reanalysis": True,
                "open_mode": "replay_folder",
            }
        # Stale entry (old non-blob save); remove it to prevent repeated failures.
        self._db.delete_replay_session(session_id=str(session_id), user_id=int(profile["id"]))
        raise RuntimeError("Saved replay not found in artifact path, replay folders, or DB backup.")

    def status_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            j = self._state.job
            return {
                "session_id": j.session_id,
                "status": j.status,
                "progress": j.progress,
                "message": j.message,
                "error": j.error,
                "replay_name": j.replay_name,
                "ready": j.ready,
                "phase": j.phase,
                "checklist": dict(j.checklist or {}),
                "duplicate": dict(j.duplicate or {}),
                "metrics_status": self._state.metrics_status,
                "metrics_error": self._state.metrics_error,
                "metrics_ready_count": self._state.metrics_ready_count,
                "metrics_total_count": self._state.metrics_total_count,
                "analysis_player": self._state.analysis_player,
                "analysis_locked": self._state.analysis_locked,
                "analysis_ready": self._state.analysis_ready,
                "analysis_error": self._state.analysis_error,
                "profile": dict(self._state.current_user or {}),
            }

    def list_players(self) -> list[str]:
        with self._lock:
            if not self._state.session:
                return []
            return list(self._state.session.players)

    def replay_session_data(self) -> Dict[str, Any]:
        with self._lock:
            session = self._state.session
            if not session:
                raise RuntimeError("No replay loaded yet.")
            return {
                "session_id": session.session_id,
                "replay_name": session.replay_name,
                "players": session.players,
                "duration_s": session.duration_s,
                "timeline": session.timeline,
                "boost_pads": session.boost_pads,
                "replay_meta": session.replay_meta,
                "analysis_player": self._state.analysis_player,
                "analysis_locked": self._state.analysis_locked,
                "analysis_ready": self._state.analysis_ready,
                "mechanics_ready": bool(self._state.mechanics),
            }

    def select_analysis_player(self, player: str) -> None:
        with self._lock:
            session = self._state.session
            if not session:
                raise RuntimeError("No replay loaded yet.")
            player = (player or "").strip()
            if player not in session.players:
                raise RuntimeError(f"Unknown player '{player}'")
            if self._state.analysis_locked and self._state.analysis_player and self._state.analysis_player != player:
                raise RuntimeError(f"Analysis is locked to '{self._state.analysis_player}' for this replay.")
            self._state.analysis_player = player
            self._state.analysis_error = ""
            if player not in self._state.player_metric_jobs:
                self._state.player_metric_jobs[player] = {"status": "idle", "message": "Not started.", "error": ""}

    def run_selected_analysis(self) -> None:
        t_analysis = time.time()
        with self._lock:
            session = self._state.session
            if not session:
                raise RuntimeError("No replay loaded yet.")
            player = self._state.analysis_player
            if not player:
                raise RuntimeError("Select analysis player first.")
            self._state.metrics_status = "computing"
            self._state.metrics_error = ""
            self._state.analysis_error = ""
            self._state.analysis_ready = False
            self._state.player_metric_jobs[player] = {"status": "computing", "message": "Computing future-aware metrics...", "error": ""}
        try:
            t_metrics = time.time()
            ensure_player_metrics(session, player)
            self._timed("tracked_player_metrics", t_metrics)
        except Exception as exc:
            with self._lock:
                self._state.player_metric_jobs[player] = {"status": "error", "message": "Metric computation failed.", "error": str(exc)}
                self._state.metrics_status = "error"
                self._state.metrics_error = str(exc)
                self._state.analysis_error = str(exc)
                self._state.analysis_ready = False
            raise
        with self._lock:
            self._state.player_metric_jobs[player] = {"status": "ready", "message": "Metrics ready.", "error": ""}
            self._state.metrics_ready_count = 1
            self._state.metrics_total_count = 1
            self._state.metrics_status = "ready"
            self._state.analysis_ready = True
            self._state.analysis_locked = True
        t_mech = time.time()
        mech_payload = self._compute_mechanics_for_selected_player(session, player)
        self._timed("mechanic_grading", t_mech)
        with self._lock:
            self._state.mechanics = mech_payload
        t_persist = time.time()
        self._persist_analysis_summary(session, player, mech_payload)
        self._persist_prepared_replay(session=session, player=player, mechanics_payload=mech_payload)
        self._timed("persist_analysis_and_prepared_replay", t_persist)
        self._timed("run_selected_analysis_total", t_analysis)

    def analysis_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "analysis_player": self._state.analysis_player,
                "analysis_locked": self._state.analysis_locked,
                "analysis_ready": self._state.analysis_ready,
                "analysis_error": self._state.analysis_error,
                "metrics_status": self._state.metrics_status,
            }

    def start_player_metrics(self, player: str) -> None:
        with self._lock:
            session = self._state.session
            if not session:
                raise RuntimeError("No replay loaded yet.")
            if player not in session.players:
                raise RuntimeError(f"Unknown player '{player}'")
            if self._state.analysis_player and player != self._state.analysis_player:
                raise RuntimeError(f"Metrics are locked to analysis player '{self._state.analysis_player}'.")
            if player in session.metrics_by_player and player in session.events_by_player:
                self._state.player_metric_jobs[player] = {"status": "ready", "message": "Metrics ready.", "error": ""}
                return
            self._state.analysis_player = player
        self.run_selected_analysis()

    def player_metrics_status(self, player: str) -> Dict[str, Any]:
        with self._lock:
            session = self._state.session
            if not session:
                raise RuntimeError("No replay loaded yet.")
            if player not in session.players:
                raise RuntimeError(f"Unknown player '{player}'")
            if self._state.analysis_player and player != self._state.analysis_player:
                raise RuntimeError(f"Metrics are locked to analysis player '{self._state.analysis_player}'.")
            job = self._state.player_metric_jobs.get(player) or {"status": "idle", "message": "Not started.", "error": ""}
            return dict(job)

    def player_metrics_data(self, player: str) -> Dict[str, Any]:
        session = None
        with self._lock:
            session = self._state.session
            if not session:
                raise RuntimeError("No replay loaded yet.")
            if player not in session.players:
                raise RuntimeError(f"Unknown player '{player}'")
            if self._state.analysis_player and player != self._state.analysis_player:
                raise RuntimeError(f"Metrics are locked to analysis player '{self._state.analysis_player}'.")
            if not self._state.analysis_ready:
                raise RuntimeError("Run analysis for the selected player first.")
            if player in session.metrics_by_player and player in session.events_by_player:
                return {
                    "session_id": session.session_id,
                    "replay_name": session.replay_name,
                    "metrics_timeline": session.metrics_by_player[player],
                    "events": session.events_by_player[player],
                }
            self._state.player_metric_jobs[player] = {"status": "computing", "message": "Computing metrics...", "error": ""}

        try:
            ensure_player_metrics(session, player)
        except Exception as exc:
            with self._lock:
                self._state.player_metric_jobs[player] = {
                    "status": "error",
                    "message": "Metric computation failed.",
                    "error": str(exc),
                }
            raise

        with self._lock:
            self._state.player_metric_jobs[player] = {"status": "ready", "message": "Metrics ready.", "error": ""}
            ready = sum(1 for p in session.players if p in session.metrics_by_player and p in session.events_by_player)
            self._state.metrics_ready_count = ready
            self._state.metrics_total_count = len(session.players)
            if self._state.metrics_status != "live":
                self._state.metrics_status = "ready" if ready >= len(session.players) else "computing"
            return {
                "session_id": session.session_id,
                "replay_name": session.replay_name,
                "metrics_timeline": session.metrics_by_player[player],
                "events": session.events_by_player[player],
            }

    def _compute_mechanics_for_selected_player(self, session: ReplaySession, player: str) -> Dict[str, Any]:
        teams = {}
        try:
            teams = dict((session.replay_meta or {}).get("player_teams", {}) or {})
        except Exception:
            teams = {}
        return grade_game_mechanics(session.timeline or [], player, teams)

    def _persist_analysis_summary(self, session: ReplaySession, player: str, mechanics_payload: Dict[str, Any]) -> None:
        profile = self.current_profile()
        if not profile:
            return
        row = self._db.get_replay_session(session_id=session.session_id, user_id=int(profile["id"])) or {}
        summary = dict(row.get("summary", {}) or {})
        mt = (session.metrics_by_player or {}).get(player, []) or []
        if mt:
            last = mt[-1] or {}
            for k in (
                "whiff_rate_per_min",
                "hesitation_percent",
                "approach_efficiency",
                "recovery_time_avg_s",
                "contest_suppressed_whiffs",
                "clear_miss_under_contest",
                "pressure_gated_frames",
            ):
                if k in last:
                    try:
                        summary[k] = float(last.get(k, 0.0) or 0.0)
                    except Exception:
                        pass
        summary["analysis_player"] = str(player or "")
        replay_date_iso = str((session.replay_meta or {}).get("replay_date_iso", "") or "")
        summary["replay_date_iso"] = replay_date_iso
        summary["replay_date_source"] = "replay_meta" if replay_date_iso else "created_at_fallback"
        summary.update(summarize_mechanic_scores(mechanics_payload or {}))
        summary["mechanic_event_count"] = len((mechanics_payload or {}).get("mechanic_events", []) or [])
        self._db.save_replay_session(
            session_id=session.session_id,
            user_id=int(profile["id"]),
            source_type=str((row.get("source_type", "") or "replay_upload")),
            replay_name=str((row.get("replay_name", "") or session.replay_name)),
            map_name=str((row.get("map_name", "") or (session.replay_meta or {}).get("map_name", "soccar"))),
            duration_s=float(row.get("duration_s", session.duration_s or 0.0) or 0.0),
            tracked_player_name=str((row.get("tracked_player_name", "") or player)),
            tracked_player_index=int(row.get("tracked_player_index", 0) or 0),
            artifact_manifest=dict(row.get("artifact_manifest", {}) or {}),
            summary=summary,
            created_at=str(row.get("created_at", "")) or None,
        )

    def current_mechanics(self) -> Dict[str, Any]:
        with self._lock:
            if self._state.mechanics:
                return dict(self._state.mechanics)
            session = self._state.session
            player = self._state.analysis_player
            ready = self._state.analysis_ready
        if not session or not player or not ready:
            return {}
        payload = self._compute_mechanics_for_selected_player(session, player)
        with self._lock:
            self._state.mechanics = dict(payload or {})
        self._persist_analysis_summary(session, player, payload)
        return payload

    def recompute_mechanics(self) -> Dict[str, Any]:
        with self._lock:
            session = self._state.session
            player = self._state.analysis_player
            ready = self._state.analysis_ready
        if not session or not player or not ready:
            raise RuntimeError("Run analysis for the selected player first.")
        payload = self._compute_mechanics_for_selected_player(session, player)
        with self._lock:
            self._state.mechanics = dict(payload or {})
        self._persist_analysis_summary(session, player, payload)
        return payload

    def mechanic_events(self) -> list[Dict[str, Any]]:
        payload = self.current_mechanics() or {}
        return list(payload.get("mechanic_events", []) or [])

    def explain_mechanic_event(self, *, time_s: float, mechanic_id: str = "", include_llm: bool = True) -> Dict[str, Any]:
        with self._lock:
            session = self._state.session
            player = self._state.analysis_player
            ready = self._state.analysis_ready
        if not session or not player or not ready:
            raise RuntimeError("Run analysis for the selected player first.")
        payload = self.current_mechanics() or {}
        evs = list(payload.get("mechanic_events", []) or [])
        if not evs:
            raise RuntimeError("No mechanic events available.")
        target = None
        wanted_mid = str(mechanic_id or "").strip()
        best_dt = float("inf")
        ts = float(time_s)
        for e in evs:
            if wanted_mid and str(e.get("mechanic_id", "")) != wanted_mid:
                continue
            dt = abs(float(e.get("time", 0.0) or 0.0) - ts)
            if dt < best_dt:
                best_dt = dt
                target = e
        if target is None:
            target = min(evs, key=lambda x: abs(float(x.get("time", 0.0) or 0.0) - ts))

        teams = {}
        try:
            teams = dict((session.replay_meta or {}).get("player_teams", {}) or {})
        except Exception:
            teams = {}
        det = explain_mechanic_event(session.timeline or [], player, teams, target)
        llm = {"enabled": False, "text": "", "error": ""}
        if include_llm:
            llm = maybe_rewrite_explanation(det)
        return {
            "event": dict(target or {}),
            "deterministic": det,
            "llm": llm,
        }

    @staticmethod
    def _event_hash_for_cache(*, mechanic_id: str, time_s: float, quality_label: str, score: float, reason: str) -> str:
        payload = {
            "mechanic_id": str(mechanic_id or ""),
            "time_s": float(time_s or 0.0),
            "quality_label": str(quality_label or ""),
            "score": float(score or 0.0),
            "reason": str(reason or ""),
        }
        return hashlib.sha1(str(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def _replay_fingerprint_for_events(events: List[Dict[str, Any]]) -> str:
        slim = []
        for e in events:
            slim.append(
                {
                    "key": str(e.get("key", "") or ""),
                    "event_hash": str(e.get("event_hash", "") or ""),
                }
            )
        return hashlib.sha1(str(slim).encode("utf-8")).hexdigest()

    def explain_progress(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state.explain_progress or {})

    def _maybe_start_explain_background(
        self,
        *,
        session_id: str,
        user_id: int,
        replay_fingerprint: str,
        model_id: str,
        prompt_version: str,
        remaining_inputs: List[Dict[str, Any]],
    ) -> bool:
        if not remaining_inputs:
            return False

        with self._lock:
            running = bool((self._state.explain_progress or {}).get("running"))
            same_session = str(self._state.explain_background_session_id or "") == str(session_id or "")
            if running and same_session:
                return False
            self._state.explain_background_session_id = str(session_id or "")
            self._state.explain_progress = {
                "session_id": str(session_id or ""),
                "running": True,
                "complete": False,
                "generated_count": 0,
                "cached_count": 0,
                "pending_count": len(remaining_inputs),
                "total_count": len(remaining_inputs),
                "message": "Generating remaining event explanations in background...",
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }

        def _run():
            generated = 0
            pending = len(remaining_inputs)
            try:
                chunk_size = 25
                for i in range(0, len(remaining_inputs), chunk_size):
                    chunk = remaining_inputs[i:i + chunk_size]
                    req_inputs = [
                        {
                            "key": str(it.get("key", "") or ""),
                            "mechanic": str(it.get("mechanic", "") or ""),
                            "time_s": float(it.get("time_s", 0.0) or 0.0),
                            "quality_label": str(it.get("quality_label", "") or "neutral"),
                            "score": float(it.get("score", 0.0) or 0.0),
                            "reason": str(it.get("reason", "") or ""),
                        }
                        for it in chunk
                    ]
                    llm_map = maybe_rewrite_explanations_batch(req_inputs)
                    writes = []
                    for it in chunk:
                        key = str(it.get("key", "") or "")
                        txt = str(llm_map.get(key, "") or "").strip()
                        if not key or not txt:
                            continue
                        writes.append(
                            {
                                "event_key": key,
                                "mechanic_id": str(it.get("mechanic", "") or ""),
                                "event_time_s": float(it.get("time_s", 0.0) or 0.0),
                                "event_hash": str(it.get("event_hash", "") or ""),
                                "title": str(it.get("title", "") or ""),
                                "body": txt,
                            }
                        )
                    if writes:
                        self._db.upsert_llm_event_explanations(
                            user_id=int(user_id),
                            replay_fingerprint=str(replay_fingerprint or ""),
                            model_id=str(model_id or ""),
                            prompt_version=str(prompt_version or ""),
                            rows=writes,
                        )
                        generated += len(writes)
                    pending = max(0, pending - len(chunk))
                    with self._lock:
                        self._state.explain_progress = {
                            "session_id": str(session_id or ""),
                            "running": True,
                            "complete": False,
                            "generated_count": generated,
                            "cached_count": 0,
                            "pending_count": pending,
                            "total_count": len(remaining_inputs),
                            "message": f"Generating remaining event explanations... ({generated}/{len(remaining_inputs)})",
                            "updated_at": datetime.utcnow().isoformat() + "Z",
                        }
            finally:
                with self._lock:
                    self._state.explain_progress = {
                        "session_id": str(session_id or ""),
                        "running": False,
                        "complete": True,
                        "generated_count": generated,
                        "cached_count": 0,
                        "pending_count": 0,
                        "total_count": len(remaining_inputs),
                        "message": "Background explanation generation complete.",
                        "updated_at": datetime.utcnow().isoformat() + "Z",
                    }

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return True

    def explain_mechanic_events_batch(
        self,
        *,
        include_llm: bool = True,
        mode: str = "hybrid",
        time_budget_s: float = 20.0,
        preload_limit: int = 20,
    ) -> Dict[str, Any]:
        t_batch = time.time()
        with self._lock:
            session = self._state.session
            ready = self._state.analysis_ready
            player = self._state.analysis_player
        if not session or not ready or not player:
            raise RuntimeError("Run analysis for the selected player first.")
        profile = self.current_profile() or {}
        if not profile:
            raise RuntimeError("Please log in first.")

        payload = self.current_mechanics() or {}
        evs = list(payload.get("mechanic_events", []) or [])
        if not evs:
            out = {
                "items": [],
                "complete": True,
                "generated_count": 0,
                "cached_count": 0,
                "pending_count": 0,
                "background_started": False,
            }
            self._timed("explain_mechanic_events_batch", t_batch)
            return out

        uniq: Dict[str, Dict[str, Any]] = {}
        for e in evs:
            key = f"{str(e.get('mechanic_id', '')).strip()}|{float(e.get('time', 0.0) or 0.0):.3f}"
            if key not in uniq:
                uniq[key] = dict(e or {})
        ordered = sorted(uniq.items(), key=lambda kv: float(kv[1].get("time", 0.0) or 0.0))

        model_id = str(os.environ.get("RLBOT_LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini")
        prompt_version = str(os.environ.get("RLBOT_LLM_PROMPT_VERSION", "v1") or "v1")
        mode_norm = str(mode or "hybrid").strip().lower()
        if mode_norm not in {"hybrid", "full"}:
            mode_norm = "hybrid"
        budget_s = max(0.0, float(time_budget_s or 0.0))
        preload_n = max(1, int(preload_limit or 1))

        items: List[Dict[str, Any]] = []
        items_by_key: Dict[str, Dict[str, Any]] = {}
        llm_inputs: List[Dict[str, Any]] = []
        for key, e in ordered:
            t = float(e.get("time", 0.0) or 0.0)
            mid = str(e.get("mechanic_id", "") or "")
            q = str(e.get("quality_label", "") or "neutral")
            score = float(e.get("score", e.get("quality_score", 0.0)) or 0.0)
            reason = str(e.get("reason", "") or "")
            event_hash = self._event_hash_for_cache(mechanic_id=mid, time_s=t, quality_label=q, score=score, reason=reason)
            title = f"{mid or 'mechanic'} @ {t:.2f}s"
            body = (
                f"At {t:.2f}s, {mid or 'this mechanic'} was {q} ({score:.1f}/100). "
                f"{reason if reason else 'Focus on cleaner setup and faster recovery on the next attempt.'}"
            )
            item = {
                "key": key,
                "time": t,
                "mechanic_id": mid,
                "quality_label": q,
                "score": score,
                "reason": reason,
                "title": title,
                "body": body,
                "event_hash": event_hash,
            }
            items.append(item)
            items_by_key[key] = item
            llm_inputs.append(
                {
                    "key": key,
                    "mechanic": mid,
                    "time_s": t,
                    "quality_label": q,
                    "score": score,
                    "reason": reason,
                    "title": title,
                    "event_hash": event_hash,
                }
            )

        replay_fingerprint = self._replay_fingerprint_for_events(llm_inputs)
        cached = self._db.list_llm_event_explanations(
            user_id=int(profile["id"]),
            replay_fingerprint=replay_fingerprint,
            model_id=model_id,
            prompt_version=prompt_version,
        )
        cached_count = 0
        for key, row in cached.items():
            item = items_by_key.get(key)
            if not item:
                continue
            if str(row.get("event_hash", "")) != str(item.get("event_hash", "")):
                continue
            text = str(row.get("body", "") or "").strip()
            if not text:
                continue
            item["body"] = text
            item["title"] = str(row.get("title", "") or item["title"])
            cached_count += 1

        missing = [x for x in llm_inputs if str(x.get("key", "")) not in {k for k, v in items_by_key.items() if str(v.get("body", "")).strip() != "" and str(v.get("event_hash", "")) == str((cached.get(k) or {}).get("event_hash", ""))}]
        # Remove items already filled from cache by exact event hash.
        missing = [x for x in missing if not (cached.get(str(x.get("key", ""))) and str((cached.get(str(x.get("key", ""))) or {}).get("event_hash", "")) == str(x.get("event_hash", "")))]

        generated_count = 0
        background_started = False

        if include_llm and missing:
            def _quality_rank(inp: Dict[str, Any]) -> int:
                q = str(inp.get("quality_label", "") or "").lower()
                if q.startswith("bad"):
                    return 0
                if q.startswith("neutral"):
                    return 1
                return 2

            prioritized = sorted(
                missing,
                key=lambda x: (
                    _quality_rank(x),
                    float(x.get("score", 0.0) or 0.0),
                    float(x.get("time_s", 0.0) or 0.0),
                ),
            )
            upfront = prioritized if mode_norm == "full" else prioritized[:preload_n]
            upfront_keys = {str(x.get("key", "")) for x in upfront}
            start_ts = datetime.utcnow().timestamp()
            if upfront and (budget_s <= 0.0 or (datetime.utcnow().timestamp() - start_ts) <= budget_s):
                req_inputs = [
                    {
                        "key": str(it.get("key", "") or ""),
                        "mechanic": str(it.get("mechanic", "") or ""),
                        "time_s": float(it.get("time_s", 0.0) or 0.0),
                        "quality_label": str(it.get("quality_label", "") or "neutral"),
                        "score": float(it.get("score", 0.0) or 0.0),
                        "reason": str(it.get("reason", "") or ""),
                    }
                    for it in upfront
                ]
                llm_map = maybe_rewrite_explanations_batch(req_inputs)
                writes = []
                for it in upfront:
                    key = str(it.get("key", "") or "")
                    txt = str(llm_map.get(key, "") or "").strip()
                    if not key or not txt:
                        continue
                    item = items_by_key.get(key)
                    if not item:
                        continue
                    item["body"] = txt
                    writes.append(
                        {
                            "event_key": key,
                            "mechanic_id": str(it.get("mechanic", "") or ""),
                            "event_time_s": float(it.get("time_s", 0.0) or 0.0),
                            "event_hash": str(it.get("event_hash", "") or ""),
                            "title": str(item.get("title", "") or ""),
                            "body": txt,
                        }
                    )
                if writes:
                    self._db.upsert_llm_event_explanations(
                        user_id=int(profile["id"]),
                        replay_fingerprint=replay_fingerprint,
                        model_id=model_id,
                        prompt_version=prompt_version,
                        rows=writes,
                    )
                    generated_count += len(writes)

            if mode_norm == "hybrid":
                remaining = [x for x in missing if str(x.get("key", "")) not in upfront_keys]
                background_started = self._maybe_start_explain_background(
                    session_id=str(session.session_id or ""),
                    user_id=int(profile["id"]),
                    replay_fingerprint=replay_fingerprint,
                    model_id=model_id,
                    prompt_version=prompt_version,
                    remaining_inputs=remaining,
                )

        progress = self.explain_progress()
        pending_count = max(0, int(progress.get("pending_count", 0) or 0))
        complete = not bool(progress.get("running")) and pending_count == 0 and (cached_count + generated_count) >= len(llm_inputs)
        if mode_norm == "full":
            pending_count = 0
            complete = True
            background_started = False

        clean_items = []
        for it in items:
            row = dict(it)
            row.pop("event_hash", None)
            clean_items.append(row)

        out = {
            "items": clean_items,
            "complete": bool(complete),
            "generated_count": int(generated_count),
            "cached_count": int(cached_count),
            "pending_count": int(max(0, pending_count)),
            "background_started": bool(background_started),
        }
        self._timed("explain_mechanic_events_batch", t_batch)
        return out

    def metrics_capabilities(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "seek": False,
                "legacy_player_metrics": True,
                "live_mode": False,
                "analysis_locked": self._state.analysis_locked,
                "analysis_player": self._state.analysis_player,
            }

    def metrics_seek(self, player: str, replay_t: float) -> Dict[str, Any]:
        with self._lock:
            session = self._state.session
            if not session:
                raise RuntimeError("No replay loaded yet.")
            if player not in session.players:
                raise RuntimeError(f"Unknown player '{player}'")

            if self._state.analysis_player and player != self._state.analysis_player:
                raise RuntimeError(f"Metrics are locked to analysis player '{self._state.analysis_player}'.")
            if not self._state.analysis_ready:
                raise RuntimeError("Run analysis for the selected player first.")
            timeline = session.metrics_by_player.get(player) or []
            if not timeline:
                raise RuntimeError("Replay timeline is empty.")
            times = [float(x.get("t", 0.0)) for x in timeline]
            target_idx = max(0, min(len(times) - 1, bisect_right(times, float(replay_t)) - 1))
            point = timeline[target_idx]
            events = session.events_by_player.get(player) or []
            return {
                "session_id": session.session_id,
                "replay_name": session.replay_name,
                "metric_point": point,
                "events": events,
                "idx": target_idx,
            }

    @staticmethod
    def _to_unix(v: str) -> float:
        s = str(v or "").strip()
        if not s:
            return 0.0
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    def profile_progress(self, limit: int = 200) -> Dict[str, Any]:
        profile = self._require_user()
        rows = self._db.list_replay_sessions_detailed(user_id=int(profile["id"]), limit=max(1, int(limit)))
        points = []
        for r in rows:
            summary = dict(r.get("summary", {}) or {})
            replay_iso = str(summary.get("replay_date_iso", "") or "").strip()
            created_at = str(r.get("created_at", "") or "").strip()
            x_iso = replay_iso or created_at
            if not x_iso:
                continue
            mech_raw = dict(summary.get("mechanic_scores", {}) or {})
            mech_scores: Dict[str, float] = {}
            for k, v in mech_raw.items():
                try:
                    mech_scores[str(k)] = float(v)
                except Exception:
                    continue
            points.append(
                {
                    "session_id": str(r.get("session_id", "")),
                    "replay_name": str(r.get("replay_name", "")),
                    "x_time_iso": x_iso,
                    "x_time_unix": float(self._to_unix(x_iso)),
                    "x_time_source": "replay_meta" if replay_iso else "created_at",
                    "overall_mechanics_score": float(summary.get("overall_mechanics_score", 0.0) or 0.0),
                    "mechanic_scores": mech_scores,
                    "whiff_rate_per_min": float(summary.get("whiff_rate_per_min", 0.0) or 0.0),
                    "hesitation_percent": float(summary.get("hesitation_percent", 0.0) or 0.0),
                    "recovery_time_avg_s": float(summary.get("recovery_time_avg_s", 0.0) or 0.0),
                }
            )
        points.sort(key=lambda x: (float(x.get("x_time_unix", 0.0)), str(x.get("session_id", ""))))
        return {"points": points}


_BASE_LOAD_PREPARED_REPLAY_INTO_STATE = ReplayStateStore._load_prepared_replay_into_state
_BASE_EXPLAIN_MECHANIC_EVENTS_BATCH = ReplayStateStore.explain_mechanic_events_batch
_BASE_STATUS_SNAPSHOT = ReplayStateStore.status_snapshot
_BASE_REPLAY_SESSION_DATA = ReplayStateStore.replay_session_data


def _rc_validated_analysis_player(self: ReplayStateStore, *, players: list[str], row: dict | None = None, payload: dict | None = None) -> str:
    valid_players = [str(p) for p in (players or []) if str(p or "").strip()]
    if not valid_players:
        return ""
    valid_set = set(valid_players)
    cached = str((payload or {}).get("analysis_player", "") or "").strip()
    if cached in valid_set:
        return cached
    tracked = str((row or {}).get("tracked_player_name", "") or "").strip()
    if tracked in valid_set:
        return tracked
    profile = self.current_profile() or {}
    matched = self._match_profile_player(players=valid_players, profile=profile)
    if matched in valid_set:
        return matched
    return valid_players[0]


def _rc_apply_validated_replay_state(self: ReplayStateStore, *, session, mechanics: dict | None = None, analysis_player: str = "") -> None:
    players = [str(p) for p in (getattr(session, "players", []) or []) if str(p or "").strip()]
    valid_player = str(analysis_player or "").strip()
    valid = bool(valid_player and valid_player in players)
    mechanics_payload = dict(mechanics or {}) if valid else {}
    with self._lock:
        self._state.session = session
        self._state.analysis_player = valid_player if valid else ""
        self._state.analysis_locked = bool(valid)
        self._state.analysis_ready = bool(valid)
        self._state.analysis_error = ""
        self._state.metrics_status = "ready" if valid else "idle"
        self._state.metrics_error = ""
        self._state.metrics_ready_count = 1 if valid else 0
        self._state.metrics_total_count = 1 if valid else (1 if players else 0)
        self._state.mechanics = mechanics_payload
        self._state.player_metric_jobs = {
            p: {
                "status": "ready" if valid and p == valid_player else "idle",
                "message": "Metrics ready." if valid and p == valid_player else "Not selected.",
                "error": "",
            }
            for p in players
        }


def _rc_ensure_valid_current_replay_state(self: ReplayStateStore) -> dict:
    with self._lock:
        session = self._state.session
        mechanics = dict(self._state.mechanics or {})
        analysis_player = str(self._state.analysis_player or "")
    if not session:
        return {
            "analysis_player": "",
            "analysis_player_valid": False,
            "session_ready": False,
            "mechanics_ready": False,
            "explanations_ready": False,
        }
    players = [str(p) for p in (session.players or []) if str(p or "").strip()]
    candidate = self._validated_analysis_player(players=players, payload={"analysis_player": analysis_player})
    if candidate and candidate != analysis_player:
        self._apply_validated_replay_state(session=session, mechanics=mechanics, analysis_player=candidate)
    analysis_player = candidate if candidate in players else ""
    explain_progress = self.explain_progress() or {}
    mechanic_events = list((mechanics or {}).get("mechanic_events", []) or [])
    explanations_ready = bool(analysis_player) and (not mechanic_events or bool(explain_progress.get("complete")))
    return {
        "analysis_player": analysis_player,
        "analysis_player_valid": bool(analysis_player),
        "session_ready": bool(session and analysis_player),
        "mechanics_ready": bool(analysis_player and mechanics),
        "explanations_ready": bool(explanations_ready),
    }


def _rc_load_prepared_replay_into_state(self: ReplayStateStore, *, row: Dict[str, Any]) -> bool:
    payload = self._deserialize_prepared_payload(bytes(row.get("prepared_payload", b"") or b""))
    if not payload:
        return False
    players = [str(p) for p in (payload.get("players", []) or []) if str(p or "").strip()]
    analysis_player = self._validated_analysis_player(players=players, row=row, payload=payload)
    if not players or not analysis_player:
        return False
    try:
        session = ReplaySession(
            session_id=str(row.get("session_id", "")),
            replay_name=str(payload.get("replay_name", row.get("replay_name", "")) or ""),
            players=players,
            timeline=list(payload.get("timeline", []) or []),
            boost_pads=list(payload.get("boost_pads", []) or []),
            replay_meta=dict(payload.get("replay_meta", {}) or {}),
            df=pd.DataFrame(),
            duration_s=float(payload.get("duration_s", row.get("duration_s", 0.0)) or 0.0),
            metrics_by_player=dict(payload.get("metrics_by_player", {}) or {}),
            events_by_player=dict(payload.get("events_by_player", {}) or {}),
        )
        mechanics = dict(payload.get("mechanics", {}) or {})
        self._apply_validated_replay_state(session=session, mechanics=mechanics, analysis_player=analysis_player)
        with self._lock:
            self._set_job(
                session_id=str(session.session_id or ""),
                status="ready",
                progress=1.0,
                message="Replay loaded from cache. Ready to play.",
                replay_name=str(session.replay_name or ""),
                phase="ready",
                checklist={
                    "upload_received": True,
                    "replay_parsed": True,
                    "timeline_ready": True,
                    "analysis_ready": True,
                    "dashboard_ready": True,
                },
            )
        return True
    except Exception:
        return _BASE_LOAD_PREPARED_REPLAY_INTO_STATE(self, row=row)


def _rc_explain_mechanic_events_batch(self: ReplayStateStore, *, include_llm: bool = True, mode: str = "hybrid", time_budget_s: float = 20.0, preload_limit: int = 20) -> Dict[str, Any]:
    requested_mode = str(mode or "hybrid").strip().lower()
    normalized_mode = requested_mode
    if requested_mode == "initial_fast":
        normalized_mode = "hybrid"
    elif requested_mode == "background_full":
        normalized_mode = "full"
    resp = dict(
        _BASE_EXPLAIN_MECHANIC_EVENTS_BATCH(
            self,
            include_llm=include_llm,
            mode=normalized_mode,
            time_budget_s=time_budget_s,
            preload_limit=preload_limit,
        )
        or {}
    )
    item_count = len(list(resp.get("items", []) or []))
    priority_limit = max(1, min(int(preload_limit or 1), item_count if item_count else max(1, int(preload_limit or 1))))
    priority_generated = int(resp.get("generated_count", 0) or 0) + int(resp.get("cached_count", 0) or 0)
    resp["mode_requested"] = requested_mode
    resp["mode_used"] = normalized_mode
    resp["priority_limit"] = int(priority_limit)
    resp["priority_ready"] = item_count == 0 or priority_generated >= min(priority_limit, item_count)
    resp["all_complete"] = bool(resp.get("complete", False))
    resp["remaining_count"] = max(0, item_count - priority_generated)
    return resp


def _rc_status_snapshot(self: ReplayStateStore) -> Dict[str, Any]:
    payload = dict(_BASE_STATUS_SNAPSHOT(self) or {})
    payload.update(self._ensure_valid_current_replay_state())
    return payload


def _rc_replay_session_data(self: ReplayStateStore) -> Dict[str, Any]:
    payload = dict(_BASE_REPLAY_SESSION_DATA(self) or {})
    payload.update(self._ensure_valid_current_replay_state())
    return payload


def _rc_live_base_url(self: ReplayStateStore) -> str:
    return str(os.environ.get("RLCOACH_LIVE_API_BASE", "http://127.0.0.1:8765")).rstrip("/")


def _rc_post_live_json(self: ReplayStateStore, path: str, payload: dict) -> dict:
    req = request.Request(
        f"{self._live_base_url()}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(body or str(exc)) from exc
    except Exception as exc:
        raise RuntimeError(f"Unable to reach live trainer at {self._live_base_url()}") from exc


def _rc_record_drill_run(self: ReplayStateStore, *, user_id: int, focus_id: str, bot_profile_id: str, scenario_ids: list[str], outcome: dict | None = None) -> int:
    started_at = datetime.utcnow().isoformat()
    payload = json.dumps(dict(outcome or {}), ensure_ascii=True)
    scenario_json = json.dumps(list(scenario_ids or []), ensure_ascii=True)
    with self._db._connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO drill_runs (
                user_id, focus_id, bot_profile_id, scenario_ids_json, started_at, completed_at, outcome_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (int(user_id), str(focus_id), str(bot_profile_id), scenario_json, started_at, "", payload),
        )
        return int(cur.lastrowid or 0)


def _rc_training_plan(self: ReplayStateStore) -> dict:
    profile = self._require_user()
    recs = self.current_recommendations() or {}
    ranked = list(recs.get("recommendations", []) or [])
    items = []
    for idx, rec in enumerate(ranked, start=1):
        focus_id = str(rec.get("focus_id", "") or "").strip()
        option = build_training_option(focus_id)
        if not option:
            continue
        difficulty_profiles = option.get("difficulty_profiles", [])
        default_profile = difficulty_profiles[1] if len(difficulty_profiles) > 1 else (difficulty_profiles[0] if difficulty_profiles else {})
        drill_modes = option.get("drill_mode_options", [])
        items.append(
            {
                "focus_id": focus_id,
                "title": str(rec.get("title", option.get("title", focus_id))),
                "priority_rank": idx,
                "priority_score": float(rec.get("score", 0.0) or 0.0),
                "confidence": float(rec.get("confidence", 0.0) or 0.0),
                "evidence": list(rec.get("evidence", []) or []),
                "bot_required": bool(option.get("bot_required", False)),
                "drill_mode_options": drill_modes,
                "drill_mode_summaries": {mode: NON_BOT_DRILL_SUMMARIES.get(mode, "") for mode in drill_modes},
                "difficulty_profiles": difficulty_profiles,
                "difficulty_default": dict(default_profile),
                "scenario_ids": list(option.get("scenario_ids", [])),
                "bot_profile_ids": list(option.get("bot_profile_ids", [])),
                "player_rank_tier": str(profile.get("rank_tier", "")),
            }
        )
    return {
        "window_size": int(recs.get("window_size", 5) or 5),
        "session_count": int(recs.get("session_count", 0) or 0),
        "recommendations": items,
    }


def _rc_home_summary(self: ReplayStateStore) -> dict:
    profile = self._require_user()
    library = self.library_sessions()
    sessions = list(library.get("sessions", []) or [])
    latest = sessions[0] if sessions else {}
    progress = self.profile_progress(limit=10)
    plan = self.training_plan()
    top_recs = list(plan.get("recommendations", []) or [])[:3]
    quick_launch = top_recs[0] if top_recs else {}
    return {
        "profile": {
            "username": str(profile.get("username", "")),
            "rank_tier": str(profile.get("rank_tier", "")),
            "platform": str(profile.get("platform", "")),
        },
        "latest_replay": latest,
        "progress": progress,
        "recommendations": top_recs,
        "quick_launch": {
            "focus_id": str(quick_launch.get("focus_id", "")),
            "title": str(quick_launch.get("title", "")),
            "difficulty_default": dict(quick_launch.get("difficulty_default", {}) or {}),
            "scenario_ids": list(quick_launch.get("scenario_ids", []) or []),
            "drill_mode_options": list(quick_launch.get("drill_mode_options", []) or []),
        },
    }


def _rc_launch_training(self: ReplayStateStore, *, focus_id: str, difficulty_tier: str, difficulty_value: float, bot_profile_id: str, scenario_ids: list[str], drill_mode: str, bot_required: bool) -> dict:
    profile = self._require_user()
    option = build_training_option(focus_id)
    if not option:
        raise RuntimeError("Unknown focus_id")
    clean_scenarios = [str(x).strip() for x in (scenario_ids or option.get("scenario_ids", [])) if str(x).strip()]
    if not clean_scenarios:
        raise RuntimeError("At least one scenario is required")
    run_id = self._record_drill_run(
        user_id=int(profile["id"]),
        focus_id=str(focus_id),
        bot_profile_id=str(bot_profile_id),
        scenario_ids=clean_scenarios,
        outcome={
            "status": "queued",
            "difficulty_tier": str(difficulty_tier),
            "difficulty_value": float(difficulty_value),
            "drill_mode": str(drill_mode),
            "bot_required": bool(bot_required),
        },
    )
    self._post_live_json(
        "/api/training/launch",
        {
            "focus_id": str(focus_id),
            "difficulty_tier": str(difficulty_tier),
            "difficulty_value": float(difficulty_value),
            "bot_profile_id": str(bot_profile_id),
            "scenario_ids": clean_scenarios,
            "drill_mode": str(drill_mode),
            "bot_required": bool(bot_required),
            "drill_run_id": int(run_id),
        },
    )
    return {"queued": True, "drill_run_id": int(run_id), "focus_id": str(focus_id), "route": "/live"}


def _rc_training_preflight(self: ReplayStateStore) -> dict:
    def _path_exists(candidates: list[str]) -> bool:
        return any(Path(path).exists() for path in candidates if path)

    def _port_open(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            return False

    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    program_files = os.environ.get("ProgramFiles", "").strip()
    rlbot_import_ok = __import__("importlib.util").util.find_spec("rlbot") is not None
    rlbot_gui_detected = _path_exists(
        [
            str(Path(local_appdata) / "RLBotGUIX") if local_appdata else "",
            str(Path(program_files) / "RLBot") if program_files else "",
        ]
    )
    rocket_league_detected = _path_exists(
        [
            str(Path(program_files) / "Epic Games" / "rocketleague") if program_files else "",
            str(Path(program_files) / "Steam" / "steamapps" / "common" / "rocketleague") if program_files else "",
        ]
    )
    scenario_ids = set()
    for focus_id in ["shadow_defense", "challenge", "fifty_fifty_control", "aerial_defense", "aerial_offense", "flicking", "carrying_dribbling"]:
        scenario_ids.update(build_training_option(focus_id).get("scenario_ids", []))
    live_trainer_running = _port_open("127.0.0.1", 8765)
    messages = []
    if not rlbot_import_ok:
        messages.append("Python RLBot package is missing from the current environment.")
    if not rlbot_gui_detected:
        messages.append("RLBot GUI was not detected in the standard Windows install locations.")
    if not rocket_league_detected:
        messages.append("Rocket League was not detected in the standard Windows install locations.")
    if not live_trainer_running:
        messages.append("The live trainer is not running on http://127.0.0.1:8765.")
    return {
        "live_trainer_running": live_trainer_running,
        "python_ready": True,
        "rlbot_import_ok": rlbot_import_ok,
        "rlbot_gui_detected": rlbot_gui_detected,
        "rocket_league_detected": rocket_league_detected,
        "scenario_count": len(scenario_ids),
        "ready_to_launch": bool(rlbot_import_ok and rocket_league_detected and scenario_ids),
        "messages": messages,
    }


ReplayStateStore._validated_analysis_player = _rc_validated_analysis_player
ReplayStateStore._apply_validated_replay_state = _rc_apply_validated_replay_state
ReplayStateStore._ensure_valid_current_replay_state = _rc_ensure_valid_current_replay_state
ReplayStateStore._load_prepared_replay_into_state = _rc_load_prepared_replay_into_state
ReplayStateStore.explain_mechanic_events_batch = _rc_explain_mechanic_events_batch
ReplayStateStore.status_snapshot = _rc_status_snapshot
ReplayStateStore.replay_session_data = _rc_replay_session_data
ReplayStateStore._live_base_url = _rc_live_base_url
ReplayStateStore._post_live_json = _rc_post_live_json
ReplayStateStore._record_drill_run = _rc_record_drill_run
ReplayStateStore.training_plan = _rc_training_plan
ReplayStateStore.home_summary = _rc_home_summary
ReplayStateStore.launch_training = _rc_launch_training
ReplayStateStore.training_preflight = _rc_training_preflight
