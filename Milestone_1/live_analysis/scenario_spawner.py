from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from rlbot.utils.game_state_util import GameState, BallState, CarState, Physics, Rotator, Vector3


def _vec3(raw: Dict[str, float]) -> Vector3:
    return Vector3(float(raw["x"]), float(raw["y"]), float(raw["z"]))


def _rot(raw: Dict[str, float]) -> Rotator:
    return Rotator(float(raw["pitch"]), float(raw["yaw"]), float(raw["roll"]))


def _car_state(raw_car: Dict[str, Any]) -> CarState:
    p = raw_car["physics"]
    return CarState(
        physics=Physics(
            location=_vec3(p["location"]),
            velocity=_vec3(p["velocity"]),
            angular_velocity=_vec3(p["angular_velocity"]),
            rotation=_rot(p["rotation"]),
        ),
        boost_amount=float(raw_car.get("boost_amount", 33.0)),
        jumped=bool(raw_car.get("jumped", False)),
        double_jumped=bool(raw_car.get("double_jumped", False)),
    )


def _ball_state(raw_ball: Dict[str, Any]) -> BallState:
    p = raw_ball["physics"]
    return BallState(
        physics=Physics(
            location=_vec3(p["location"]),
            velocity=_vec3(p["velocity"]),
            angular_velocity=_vec3(p["angular_velocity"]),
            rotation=_rot(p["rotation"]),
        )
    )


def _tucked_car_state() -> CarState:
    return CarState(
        physics=Physics(
            location=Vector3(0.0, 0.0, 2500.0),
            velocity=Vector3(0.0, 0.0, 0.0),
            angular_velocity=Vector3(0.0, 0.0, 0.0),
            rotation=Rotator(0.0, 0.0, 0.0),
        ),
        boost_amount=0.0,
        jumped=False,
        double_jumped=False,
    )


def make_game_state(scenario_payload: Dict[str, Any], no_bot_mode: str = "tuck") -> GameState:
    cars = {0: _car_state(scenario_payload["cars"]["0"])}
    if no_bot_mode == "tuck":
        cars[1] = _tucked_car_state()
    else:
        cars[1] = _car_state(scenario_payload["cars"]["1"])

    ball = _ball_state(scenario_payload["ball"])
    return GameState(cars=cars, ball=ball)


@dataclass
class ScenarioSpawner:
    stabilization_ticks: int = 15
    no_bot_mode: str = "tuck"
    _pending_state: Optional[GameState] = None
    _remaining: int = 0

    def queue(self, payload: Dict[str, Any]) -> None:
        self._pending_state = make_game_state(payload, no_bot_mode=self.no_bot_mode)
        self._remaining = max(1, self.stabilization_ticks)

    def tick(self, game_interface) -> bool:
        if self._pending_state is None or self._remaining <= 0:
            return False
        game_interface.set_game_state(self._pending_state)
        self._remaining -= 1
        if self._remaining <= 0:
            self._pending_state = None
        return True
