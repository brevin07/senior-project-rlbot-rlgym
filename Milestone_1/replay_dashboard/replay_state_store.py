from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import threading
import uuid
import traceback
import hashlib
from bisect import bisect_right
from pathlib import Path
import os
import sys
from datetime import datetime

HERE = Path(__file__).resolve().parent
MILESTONE_ROOT = HERE.parent
LIVE_ANALYSIS_DIR = MILESTONE_ROOT / "live_analysis"
for _p in (HERE, MILESTONE_ROOT, LIVE_ANALYSIS_DIR):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

from replay_loader import DEBUG_METRIC_KEYS, METRIC_KEYS, ReplaySession, ensure_player_metrics, load_replay_bytes
from common.persistence import AppDB
from recommendation_engine import compute_recommendations
from mechanic_grader import grade_game_mechanics, summarize_mechanic_scores, explain_mechanic_event
from llm_event_explainer import maybe_rewrite_explanation


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

    def login_profile(self, *, username: str, rank_tier: str, platform: str, aliases: list[str] | None = None) -> Dict[str, Any]:
        profile = self._db.upsert_user(username=username, rank_tier=rank_tier, platform=platform, aliases=aliases)
        removed = int(self._db.prune_duplicate_replay_names(user_id=int(profile["id"])) or 0)
        with self._lock:
            self._state.current_user = dict(profile)
            self._state.last_duplicate_cleanup_removed = removed
        return profile

    def logout_profile(self) -> None:
        self._db.clear_active_user()
        with self._lock:
            self._state.current_user = {}
            self._state.recommendations = {}
            self._state.mechanics = {}

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

        def _run():
            nonlocal session_id
            try:
                with self._lock:
                    self._state.job.status = "parsing"
                    self._state.job.progress = 0.25
                    self._state.job.message = "Running rrrocket parser..."
                    self._state.job.phase = "parsing"
                    self._state.job.checklist["upload_received"] = True

                session = load_replay_bytes(file_name=file_name, data=data, rrrocket_override=rrrocket_override)
                session_id = session.session_id
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
                    target_player = ""
                    try:
                        names = [str(profile.get("username", "") or "")]
                        names.extend([str(x or "") for x in (profile.get("aliases", []) or [])])
                        acceptable = set(
                            "".join(ch.lower() for ch in n if ch.isalnum() or ch in ("_", "-"))
                            for n in names
                            if n
                        )
                        for p in session.players:
                            p_norm = "".join(ch.lower() for ch in str(p) if ch.isalnum() or ch in ("_", "-"))
                            if p_norm and p_norm in acceptable:
                                target_player = str(p)
                                break
                    except Exception:
                        target_player = ""
                    self._state.session = session
                    self._state.player_metric_jobs = {
                        p: {"status": "idle", "message": "Select player and run analysis.", "error": ""} for p in session.players
                    }
                    self._state.metrics_status = "idle"
                    self._state.metrics_error = ""
                    self._state.metrics_ready_count = 0
                    self._state.metrics_total_count = 1 if session.players else 0
                    self._state.analysis_player = target_player
                    self._state.analysis_locked = bool(target_player)
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
                tracked_name = ""
                try:
                    names = [str(profile.get("username", "") or "")]
                    names.extend([str(x or "") for x in (profile.get("aliases", []) or [])])
                    acceptable = set(
                        "".join(ch.lower() for ch in n if ch.isalnum() or ch in ("_", "-"))
                        for n in names
                        if n
                    )
                    for p in session.players:
                        k = "".join(ch.lower() for ch in str(p) if ch.isalnum() or ch in ("_", "-"))
                        if k and k in acceptable:
                            tracked_name = p
                            break
                except Exception:
                    tracked_name = ""
                if not tracked_name and session.players:
                    tracked_name = str(session.players[0])
                summary = {}
                if session.players:
                    summary["player_count"] = len(session.players)
                summary["replay_sha1"] = replay_sha1
                replay_date_iso = str((session.replay_meta or {}).get("replay_date_iso", "") or "")
                summary["replay_date_iso"] = replay_date_iso
                summary["replay_date_source"] = "replay_meta" if replay_date_iso else "created_at_fallback"
                if persist_to_library:
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
        removed = int(self._db.prune_duplicate_replay_names(user_id=int(profile["id"])) or 0)
        with self._lock:
            self._state.last_duplicate_cleanup_removed = removed
        return {
            "profile": profile,
            "sessions": self._db.list_replay_sessions(user_id=int(profile["id"]), limit=300),
            "cleanup": {"duplicate_names_removed": removed},
        }

    def open_saved_replay(self, session_id: str) -> str:
        profile = self._require_user()
        row = self._db.get_replay_session(session_id=session_id, user_id=int(profile["id"]))
        if not row:
            raise RuntimeError("Saved replay not found.")
        manifest = row.get("artifact_manifest", {}) or {}
        replay_file = Path(str(manifest.get("replay_file", "")))
        if replay_file.exists() and replay_file.is_file():
            return self.start_processing(file_name=replay_file.name, data=replay_file.read_bytes(), persist_to_library=False)
        replay_name = str(row.get("replay_name", "") or replay_file.name or "")
        alt = self._find_replay_in_folders(replay_name)
        if alt and alt.exists() and alt.is_file():
            return self.start_processing(file_name=alt.name, data=alt.read_bytes(), persist_to_library=False)
        blob = row.get("replay_blob", None)
        if isinstance(blob, (bytes, bytearray)) and len(blob) > 0:
            fallback_name = replay_name or f"{session_id}.replay"
            return self.start_processing(file_name=Path(fallback_name).name, data=bytes(blob), persist_to_library=False)
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
            ensure_player_metrics(session, player)
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
        mech_payload = self._compute_mechanics_for_selected_player(session, player)
        with self._lock:
            self._state.mechanics = mech_payload
        self._persist_analysis_summary(session, player, mech_payload)

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
