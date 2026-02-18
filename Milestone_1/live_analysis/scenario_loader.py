from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple


APPDATA_RELATIVE_PATH = Path("RLBot") / "Dojo" / "Scenarios"


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_vector3(raw: Dict[str, Any] | None, default: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> Dict[str, float]:
    raw = raw or {}
    return {
        "x": _as_float(raw.get("x", default[0])),
        "y": _as_float(raw.get("y", default[1])),
        "z": _as_float(raw.get("z", default[2])),
    }


def _normalize_rotator(raw: Dict[str, Any] | None) -> Dict[str, float]:
    raw = raw or {}
    return {
        "pitch": _as_float(raw.get("pitch", 0.0)),
        "yaw": _as_float(raw.get("yaw", 0.0)),
        "roll": _as_float(raw.get("roll", 0.0)),
    }


def _normalize_car(raw_car: Dict[str, Any]) -> Dict[str, Any]:
    physics = raw_car.get("physics", {})
    return {
        "physics": {
            "location": _normalize_vector3(physics.get("location"), default=(0.0, 0.0, 17.0)),
            "rotation": _normalize_rotator(physics.get("rotation")),
            "velocity": _normalize_vector3(physics.get("velocity")),
            "angular_velocity": _normalize_vector3(physics.get("angular_velocity")),
        },
        "boost_amount": _as_float(raw_car.get("boost_amount", 33.0)),
        "jumped": bool(raw_car.get("jumped", False)),
        "double_jumped": bool(raw_car.get("double_jumped", False)),
    }


def _normalize_ball(raw_ball: Dict[str, Any]) -> Dict[str, Any]:
    physics = raw_ball.get("physics", {})
    return {
        "physics": {
            "location": _normalize_vector3(physics.get("location"), default=(0.0, 0.0, 93.0)),
            "rotation": _normalize_rotator(physics.get("rotation")),
            "velocity": _normalize_vector3(physics.get("velocity")),
            "angular_velocity": _normalize_vector3(physics.get("angular_velocity")),
        }
    }


def _normalize_scenario_payload(name: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    game_state = raw.get("game_state", raw)
    cars = game_state.get("cars", {})
    ball = game_state.get("ball", {})
    has_car_state = isinstance(cars, dict) and (("0" in cars) or (0 in cars))
    has_ball_state = isinstance(ball, dict) and ("physics" in ball)
    if not (has_car_state and has_ball_state):
        raise ValueError("not a scenario game state payload")

    return {
        "name": name,
        "cars": {
            "0": _normalize_car(cars.get("0", cars.get(0, {}))),
            "1": _normalize_car(cars.get("1", cars.get(1, {}))),
        },
        "ball": _normalize_ball(ball),
    }


def _load_from_directory(base: Path, source_name: str) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    scenarios: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, str] = {}

    if not base.exists():
        return scenarios, sources

    for file_path in sorted(base.glob("*.json")):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8-sig"))
            scenario_name = data.get("name") or file_path.stem
            normalized = _normalize_scenario_payload(scenario_name, data)
            scenarios[scenario_name] = normalized
            sources[scenario_name] = source_name
        except Exception as exc:
            print(f"[scenario_loader] skipped '{file_path}': {exc}")

    return scenarios, sources


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_appdata_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APPDATA_RELATIVE_PATH
    return Path.home() / "AppData" / "Roaming" / APPDATA_RELATIVE_PATH


def _discover_rldojo_dirs() -> list[Path]:
    root = _repo_root()
    candidates = [
        root.parent / "RLDojo" / "Dojo" / "Scenarios",
        root.parent / "RLDojo" / "Scenarios",
        root.parent / "RLDojo" / "Dojo",
    ]
    out: list[Path] = []
    for candidate in candidates:
        if candidate.exists() and candidate not in out:
            out.append(candidate)
    return out


def load_scenarios(extra_dir: str | None = None) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    scenarios: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, str] = {}
    loaded_counts: Dict[str, int] = {"appdata": 0, "extra": 0, "rldojo_repo": 0, "bundled": 0}

    appdata = _resolve_appdata_dir()
    appdata_scenarios, appdata_sources = _load_from_directory(appdata, "appdata")
    scenarios.update(appdata_scenarios)
    sources.update(appdata_sources)
    loaded_counts["appdata"] = len(appdata_scenarios)

    if extra_dir:
        extra = Path(extra_dir).expanduser().resolve()
        extra_scenarios, extra_sources = _load_from_directory(extra, "extra")
        for name, payload in extra_scenarios.items():
            if name not in scenarios:
                scenarios[name] = payload
                sources[name] = extra_sources[name]
        loaded_counts["extra"] = len(extra_scenarios)

    discovered_rldojo = _discover_rldojo_dirs()
    for path in discovered_rldojo:
        repo_scenarios, repo_sources = _load_from_directory(path, "rldojo_repo")
        loaded_counts["rldojo_repo"] += len(repo_scenarios)
        for name, payload in repo_scenarios.items():
            if name not in scenarios:
                scenarios[name] = payload
                sources[name] = repo_sources[name]

    bundled_dir = Path(__file__).resolve().parent / "scenarios"
    bundled_scenarios, bundled_sources = _load_from_directory(bundled_dir, "bundled")
    for name, payload in bundled_scenarios.items():
        if name not in scenarios:
            scenarios[name] = payload
            sources[name] = bundled_sources[name]
    loaded_counts["bundled"] = len(bundled_scenarios)

    print(f"[scenario_loader] checked appdata: {appdata}")
    for path in discovered_rldojo:
        print(f"[scenario_loader] checked rldojo path: {path}")
    print(f"[scenario_loader] checked bundled: {bundled_dir}")
    print(
        "[scenario_loader] loaded counts "
        f"(appdata={loaded_counts['appdata']}, "
        f"extra={loaded_counts['extra']}, "
        f"rldojo_repo={loaded_counts['rldojo_repo']}, "
        f"bundled={loaded_counts['bundled']})"
    )

    return scenarios, sources
