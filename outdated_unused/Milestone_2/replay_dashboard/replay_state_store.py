from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib import error, request

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
M1_ROOT = REPO_ROOT / "Milestone_1"
M1_REPLAY = M1_ROOT / "replay_dashboard"
M1_LIVE = M1_ROOT / "live_analysis"
for _p in (REPO_ROOT, M1_ROOT, M1_REPLAY, M1_LIVE):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

from Milestone_1.replay_dashboard.replay_state_store import ReplayStateStore as BaseReplayStateStore

from .training_catalog import NON_BOT_DRILL_SUMMARIES, build_training_option


class ReplayStateStore(BaseReplayStateStore):
    def explain_mechanic_events_batch(
        self,
        *,
        include_llm: bool = True,
        mode: str = "hybrid",
        time_budget_s: float = 20.0,
        preload_limit: int = 20,
    ) -> dict:
        requested_mode = str(mode or "hybrid").strip().lower()
        normalized_mode = requested_mode
        if requested_mode == "initial_fast":
            normalized_mode = "hybrid"
        elif requested_mode == "background_full":
            normalized_mode = "full"
        resp = dict(
            super().explain_mechanic_events_batch(
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
        priority_ready = item_count == 0 or priority_generated >= min(priority_limit, item_count)
        resp["mode_requested"] = requested_mode
        resp["mode_used"] = normalized_mode
        resp["priority_limit"] = int(priority_limit)
        resp["priority_ready"] = bool(priority_ready)
        resp["all_complete"] = bool(resp.get("complete", False))
        resp["remaining_count"] = max(0, item_count - priority_generated)
        return resp

    def _validated_analysis_player(self, *, players: list[str], row: dict | None = None, payload: dict | None = None) -> str:
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

    def _apply_validated_replay_state(self, *, session, mechanics: dict | None = None, analysis_player: str = "") -> None:
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

    def _ensure_valid_current_replay_state(self) -> dict:
        with self._lock:
            session = self._state.session
            mechanics = dict(self._state.mechanics or {})
        if not session:
            return {
                "analysis_player": "",
                "analysis_player_valid": False,
                "session_ready": False,
                "mechanics_ready": False,
                "explanations_ready": False,
            }
        players = [str(p) for p in (session.players or []) if str(p or "").strip()]
        candidate = self._validated_analysis_player(players=players, payload={"analysis_player": getattr(self._state, "analysis_player", "")})
        if candidate and candidate != getattr(self._state, "analysis_player", ""):
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

    def _load_prepared_replay_into_state(self, *, row: dict) -> bool:
        payload = self._deserialize_prepared_payload(bytes(row.get("prepared_payload", b"") or b""))
        if not payload:
            return False
        players = [str(p) for p in (payload.get("players", []) or []) if str(p or "").strip()]
        analysis_player = self._validated_analysis_player(players=players, row=row, payload=payload)
        if not players or not analysis_player:
            return False
        try:
            from replay_loader import ReplaySession

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
            return False

    def _live_base_url(self) -> str:
        return str(os.environ.get("RLCOACH_LIVE_API_BASE", "http://127.0.0.1:8765")).rstrip("/")

    def _post_live_json(self, path: str, payload: dict) -> dict:
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

    def _record_drill_run(self, *, user_id: int, focus_id: str, bot_profile_id: str, scenario_ids: list[str], outcome: dict | None = None) -> int:
        started_at = datetime.utcnow().isoformat()
        completed_at = ""
        payload = json.dumps(dict(outcome or {}), ensure_ascii=True)
        scenario_json = json.dumps(list(scenario_ids or []), ensure_ascii=True)
        with self._db._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO drill_runs (
                    user_id, focus_id, bot_profile_id, scenario_ids_json, started_at, completed_at, outcome_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (int(user_id), str(focus_id), str(bot_profile_id), scenario_json, started_at, completed_at, payload),
            )
            return int(cur.lastrowid or 0)

    def training_plan(self) -> dict:
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

    def home_summary(self) -> dict:
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

    def replay_session_data(self) -> dict:
        payload = dict(super().replay_session_data() or {})
        readiness = self._ensure_valid_current_replay_state()
        payload["analysis_player"] = str(readiness.get("analysis_player", ""))
        payload["analysis_player_valid"] = bool(readiness.get("analysis_player_valid", False))
        payload["session_ready"] = bool(readiness.get("session_ready", False))
        payload["mechanics_ready"] = bool(readiness.get("mechanics_ready", False))
        payload["explanations_ready"] = bool(readiness.get("explanations_ready", False))
        return payload

    def status_snapshot(self) -> dict:
        payload = dict(super().status_snapshot() or {})
        readiness = self._ensure_valid_current_replay_state()
        payload.update(readiness)
        return payload

    def launch_training(
        self,
        *,
        focus_id: str,
        difficulty_tier: str,
        difficulty_value: float,
        bot_profile_id: str,
        scenario_ids: list[str],
        drill_mode: str,
        bot_required: bool,
    ) -> dict:
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
        live_payload = {
            "focus_id": str(focus_id),
            "difficulty_tier": str(difficulty_tier),
            "difficulty_value": float(difficulty_value),
            "bot_profile_id": str(bot_profile_id),
            "scenario_ids": clean_scenarios,
            "drill_mode": str(drill_mode),
            "bot_required": bool(bot_required),
            "drill_run_id": int(run_id),
        }
        live_response = self._post_live_json("/api/training/launch", live_payload)
        return {
            "queued": True,
            "drill_run_id": int(run_id),
            "focus_id": str(focus_id),
            "route": "/live",
            "live_response": live_response,
        }
