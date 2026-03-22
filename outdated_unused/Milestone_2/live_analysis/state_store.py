from __future__ import annotations

from dataclasses import dataclass, field
import sys
from typing import Any, Dict, List
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
M1_ROOT = REPO_ROOT / "Milestone_1"
M1_LIVE = M1_ROOT / "live_analysis"
for _p in (REPO_ROOT, M1_ROOT, M1_LIVE):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

from Milestone_1.live_analysis.state_store import StateStore as BaseStateStore


@dataclass
class TrainingLaunch:
    focus_id: str = ""
    difficulty_tier: str = ""
    difficulty_value: float = 0.0
    bot_profile_id: str = ""
    scenario_ids: List[str] = field(default_factory=list)
    drill_mode: str = ""
    bot_required: bool = False
    drill_run_id: int = 0


class StateStore(BaseStateStore):
    def __init__(self):
        super().__init__()
        self._training_launch = TrainingLaunch()

    def queue_training_launch(self, payload: Dict[str, Any]) -> None:
        clean_ids = [str(x).strip() for x in (payload.get("scenario_ids", []) or []) if str(x).strip()]
        with self._lock:
            self._training_launch = TrainingLaunch(
                focus_id=str(payload.get("focus_id", "") or ""),
                difficulty_tier=str(payload.get("difficulty_tier", "") or ""),
                difficulty_value=float(payload.get("difficulty_value", 0.0) or 0.0),
                bot_profile_id=str(payload.get("bot_profile_id", "") or ""),
                scenario_ids=clean_ids,
                drill_mode=str(payload.get("drill_mode", "") or ""),
                bot_required=bool(payload.get("bot_required", False)),
                drill_run_id=int(payload.get("drill_run_id", 0) or 0),
            )
        if clean_ids:
            self.queue_training(
                focus_id=self._training_launch.focus_id,
                bot_profile=self._training_launch.bot_profile_id,
                scenario_ids=clean_ids,
            )

    def current_training_launch(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "focus_id": self._training_launch.focus_id,
                "difficulty_tier": self._training_launch.difficulty_tier,
                "difficulty_value": self._training_launch.difficulty_value,
                "bot_profile_id": self._training_launch.bot_profile_id,
                "scenario_ids": list(self._training_launch.scenario_ids),
                "drill_mode": self._training_launch.drill_mode,
                "bot_required": self._training_launch.bot_required,
                "drill_run_id": self._training_launch.drill_run_id,
            }

    def snapshot(self) -> Dict[str, Any]:
        snap = super().snapshot()
        snap["training_launch"] = self.current_training_launch()
        return snap
