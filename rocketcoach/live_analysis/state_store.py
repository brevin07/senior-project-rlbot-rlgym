from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import threading


@dataclass
class ScenarioRef:
    name: str
    source: str


@dataclass
class TrainingLaunch:
    launcher_kind: str = ""
    focus_id: str = ""
    difficulty_tier: str = ""
    difficulty_value: float = 0.0
    bot_profile_id: str = ""
    bot_name: str = ""
    bot_config_path: str = ""
    playlist_name: str = ""
    playlist_file: str = ""
    playlist_id: str = ""
    dojo_source_root: str = ""
    dojo_wrapper_config_path: str = ""
    scenario_ids: List[str] = field(default_factory=list)
    drill_mode: str = ""
    bot_required: bool = False
    drill_run_id: int = 0


@dataclass
class SharedState:
    scenarios: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    scenario_sources: Dict[str, str] = field(default_factory=dict)
    active_scenario: Optional[str] = None
    pending_scenario: Optional[str] = None
    current_metrics: Dict[str, Any] = field(default_factory=dict)
    metric_history: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    event_log: List[Dict[str, Any]] = field(default_factory=list)
    spawn_mode: str = "tuck"
    current_user: Dict[str, Any] = field(default_factory=dict)
    recommendations: Dict[str, Any] = field(default_factory=dict)
    mechanics: Dict[str, Any] = field(default_factory=dict)
    training_queue: List[Dict[str, Any]] = field(default_factory=list)
    active_focus: str = ""
    active_bot_profile: str = ""
    training_launch: TrainingLaunch = field(default_factory=TrainingLaunch)
    pending_training_launch: Optional[TrainingLaunch] = None


class StateStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = SharedState()

    def set_scenarios(self, scenarios: Dict[str, Dict[str, Any]], sources: Dict[str, str]) -> None:
        with self._lock:
            self._state.scenarios = scenarios
            self._state.scenario_sources = sources

    def set_spawn_mode(self, spawn_mode: str) -> None:
        with self._lock:
            self._state.spawn_mode = spawn_mode

    def set_current_user(self, user: Dict[str, Any]) -> None:
        with self._lock:
            self._state.current_user = dict(user or {})

    def set_recommendations(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._state.recommendations = dict(payload or {})

    def set_mechanics(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            self._state.mechanics = dict(payload or {})

    def queue_training(self, *, focus_id: str, bot_profile: str, scenario_ids: List[str]) -> None:
        with self._lock:
            clean_ids = [str(x) for x in (scenario_ids or []) if str(x).strip()]
            for sid in clean_ids:
                self._state.training_queue.append(
                    {
                        "focus_id": str(focus_id or ""),
                        "bot_profile": str(bot_profile or ""),
                        "scenario_id": sid,
                    }
                )
            self._state.active_focus = str(focus_id or "")
            self._state.active_bot_profile = str(bot_profile or "")

    def queue_training_launch(self, payload: Dict[str, Any]) -> None:
        clean_ids = [str(x).strip() for x in (payload.get("scenario_ids", []) or []) if str(x).strip()]
        with self._lock:
            self._state.training_launch = TrainingLaunch(
                launcher_kind=str(payload.get("launcher_kind", "") or ""),
                focus_id=str(payload.get("focus_id", "") or ""),
                difficulty_tier=str(payload.get("difficulty_tier", "") or ""),
                difficulty_value=float(payload.get("difficulty_value", 0.0) or 0.0),
                bot_profile_id=str(payload.get("bot_profile_id", "") or ""),
                bot_name=str(payload.get("bot_name", "") or ""),
                bot_config_path=str(payload.get("bot_config_path", "") or ""),
                playlist_name=str(payload.get("playlist_name", "") or ""),
                playlist_file=str(payload.get("playlist_file", "") or ""),
                playlist_id=str(payload.get("playlist_id", "") or ""),
                dojo_source_root=str(payload.get("dojo_source_root", "") or ""),
                dojo_wrapper_config_path=str(payload.get("dojo_wrapper_config_path", "") or ""),
                scenario_ids=clean_ids,
                drill_mode=str(payload.get("drill_mode", "") or ""),
                bot_required=bool(payload.get("bot_required", False)),
                drill_run_id=int(payload.get("drill_run_id", 0) or 0),
            )
            self._state.pending_training_launch = TrainingLaunch(**self._state.training_launch.__dict__)
        if clean_ids and str(payload.get("launcher_kind", "") or "").strip().lower() != "rldojo":
            self.queue_training(
                focus_id=self._state.training_launch.focus_id,
                bot_profile=self._state.training_launch.bot_profile_id,
                scenario_ids=clean_ids,
            )

    def current_training_launch(self) -> Dict[str, Any]:
        with self._lock:
            launch = self._state.training_launch
            return {
                "launcher_kind": launch.launcher_kind,
                "focus_id": launch.focus_id,
                "difficulty_tier": launch.difficulty_tier,
                "difficulty_value": launch.difficulty_value,
                "bot_profile_id": launch.bot_profile_id,
                "bot_name": launch.bot_name,
                "bot_config_path": launch.bot_config_path,
                "playlist_name": launch.playlist_name,
                "playlist_file": launch.playlist_file,
                "playlist_id": launch.playlist_id,
                "dojo_source_root": launch.dojo_source_root,
                "dojo_wrapper_config_path": launch.dojo_wrapper_config_path,
                "scenario_ids": list(launch.scenario_ids),
                "drill_mode": launch.drill_mode,
                "bot_required": launch.bot_required,
                "drill_run_id": launch.drill_run_id,
            }

    def pop_pending_training_launch(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            launch = self._state.pending_training_launch
            self._state.pending_training_launch = None
            if not launch:
                return None
            return {
                "launcher_kind": launch.launcher_kind,
                "focus_id": launch.focus_id,
                "difficulty_tier": launch.difficulty_tier,
                "difficulty_value": launch.difficulty_value,
                "bot_profile_id": launch.bot_profile_id,
                "bot_name": launch.bot_name,
                "bot_config_path": launch.bot_config_path,
                "playlist_name": launch.playlist_name,
                "playlist_file": launch.playlist_file,
                "playlist_id": launch.playlist_id,
                "dojo_source_root": launch.dojo_source_root,
                "dojo_wrapper_config_path": launch.dojo_wrapper_config_path,
                "scenario_ids": list(launch.scenario_ids),
                "drill_mode": launch.drill_mode,
                "bot_required": launch.bot_required,
                "drill_run_id": launch.drill_run_id,
            }

    def list_scenarios(self) -> List[ScenarioRef]:
        with self._lock:
            out = []
            for name in sorted(self._state.scenarios.keys()):
                out.append(ScenarioRef(name=name, source=self._state.scenario_sources.get(name, "unknown")))
            return out

    def get_scenario(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._state.scenarios.get(name)

    def queue_scenario(self, name: str) -> bool:
        with self._lock:
            if name not in self._state.scenarios:
                return False
            self._state.pending_scenario = name
            return True

    def pop_pending_scenario(self) -> Optional[str]:
        with self._lock:
            name = self._state.pending_scenario
            self._state.pending_scenario = None
            return name

    def pop_next_training(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._state.training_queue:
                return None
            return self._state.training_queue.pop(0)

    def set_active_scenario(self, name: str) -> None:
        with self._lock:
            self._state.active_scenario = name

    def set_metrics(self, current_metrics: Dict[str, Any], history: Dict[str, List[Dict[str, Any]]], events: List[Dict[str, Any]]) -> None:
        with self._lock:
            self._state.current_metrics = current_metrics
            self._state.metric_history = history
            self._state.event_log = events

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            active_source = None
            if self._state.active_scenario:
                active_source = self._state.scenario_sources.get(self._state.active_scenario, "unknown")
            return {
                "active_scenario": self._state.active_scenario,
                "active_source": active_source,
                "pending_scenario": self._state.pending_scenario,
                "spawn_mode": self._state.spawn_mode,
                "profile": dict(self._state.current_user or {}),
                "current_metrics": self._state.current_metrics,
                "history": self._state.metric_history,
                "events": self._state.event_log,
                "recommendations": dict(self._state.recommendations or {}),
                "mechanics": dict(self._state.mechanics or {}),
                "training_queue": list(self._state.training_queue),
                "active_focus": self._state.active_focus,
                "active_bot_profile": self._state.active_bot_profile,
                "training_launch": self.current_training_launch(),
            }
