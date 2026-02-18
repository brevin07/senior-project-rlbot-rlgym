from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List
import tempfile
import uuid
import sys
import io
import contextlib
import json
from bisect import bisect_right
from datetime import datetime

import pandas as pd

HERE = Path(__file__).resolve().parent
MILESTONE_ROOT = HERE.parent
LIVE_ANALYSIS_DIR = MILESTONE_ROOT / "live_analysis"
for _p in (MILESTONE_ROOT, LIVE_ANALYSIS_DIR, HERE):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)

from extract_player_data import CSV_DIR, _resolve_rrrocket_path, _run_rrrocket_to_json, extract_final
from metrics_engine import LiveMetricsEngine
from future_event_engine import apply_whiff_rate_from_events, refine_events_posthoc

from replay_packet_adapter import ReplayPacketBuilder


METRIC_KEYS = [
    "speed",
    "hesitation_score",
    "hesitation_percent",
    "boost_waste_percent",
    "supersonic_percent",
    "useful_supersonic_percent",
    "pressure_percent",
    "whiff_rate_per_min",
    "approach_efficiency",
    "recovery_time_avg_s",
]

DEBUG_METRIC_KEYS = [
    "contest_suppressed_whiffs",
    "clear_miss_under_contest",
    "pressure_gated_frames",
    "suppressed_whiff_flip_commit",
    "suppressed_whiff_disengage",
    "suppressed_whiff_bump_intent",
    "suppressed_whiff_opponent_first_touch",
    "suppressed_hesitation_reposition",
    "suppressed_hesitation_setup",
    "suppressed_hesitation_spacing",
    "whiff_commit_detected_count",
    "whiff_gateA_count",
    "whiff_gateB_count",
    "whiff_gateC_count",
    "whiff_two_of_three_pass_count",
    "whiff_excluded_fake_challenge",
    "whiff_excluded_bump_demo_intent",
    "whiff_excluded_intentional_reset",
]

SOCCAR_BOOST_PADS = [
    {"x": 0.0, "y": -4240.0, "z": 70.0, "size": "small"},
    {"x": -1792.0, "y": -4184.0, "z": 70.0, "size": "small"},
    {"x": 1792.0, "y": -4184.0, "z": 70.0, "size": "small"},
    {"x": -3072.0, "y": -4096.0, "z": 73.0, "size": "big"},
    {"x": 3072.0, "y": -4096.0, "z": 73.0, "size": "big"},
    {"x": -940.0, "y": -3308.0, "z": 70.0, "size": "small"},
    {"x": 940.0, "y": -3308.0, "z": 70.0, "size": "small"},
    {"x": 0.0, "y": -2816.0, "z": 70.0, "size": "small"},
    {"x": -3584.0, "y": -2484.0, "z": 70.0, "size": "small"},
    {"x": 3584.0, "y": -2484.0, "z": 70.0, "size": "small"},
    {"x": -1788.0, "y": -2300.0, "z": 70.0, "size": "small"},
    {"x": 1788.0, "y": -2300.0, "z": 70.0, "size": "small"},
    {"x": -2048.0, "y": -1036.0, "z": 70.0, "size": "small"},
    {"x": 0.0, "y": -1024.0, "z": 70.0, "size": "small"},
    {"x": 2048.0, "y": -1036.0, "z": 70.0, "size": "small"},
    {"x": -3584.0, "y": 0.0, "z": 73.0, "size": "big"},
    {"x": -1024.0, "y": 0.0, "z": 70.0, "size": "small"},
    {"x": 1024.0, "y": 0.0, "z": 70.0, "size": "small"},
    {"x": 3584.0, "y": 0.0, "z": 73.0, "size": "big"},
    {"x": -2048.0, "y": 1036.0, "z": 70.0, "size": "small"},
    {"x": 0.0, "y": 1024.0, "z": 70.0, "size": "small"},
    {"x": 2048.0, "y": 1036.0, "z": 70.0, "size": "small"},
    {"x": -1788.0, "y": 2300.0, "z": 70.0, "size": "small"},
    {"x": 1788.0, "y": 2300.0, "z": 70.0, "size": "small"},
    {"x": -3584.0, "y": 2484.0, "z": 70.0, "size": "small"},
    {"x": 3584.0, "y": 2484.0, "z": 70.0, "size": "small"},
    {"x": 0.0, "y": 2816.0, "z": 70.0, "size": "small"},
    {"x": -940.0, "y": 3308.0, "z": 70.0, "size": "small"},
    {"x": 940.0, "y": 3308.0, "z": 70.0, "size": "small"},
    {"x": -3072.0, "y": 4096.0, "z": 73.0, "size": "big"},
    {"x": 3072.0, "y": 4096.0, "z": 73.0, "size": "big"},
    {"x": -1792.0, "y": 4184.0, "z": 70.0, "size": "small"},
    {"x": 1792.0, "y": 4184.0, "z": 70.0, "size": "small"},
    {"x": 0.0, "y": 4240.0, "z": 70.0, "size": "small"},
]


@dataclass
class ReplaySession:
    session_id: str
    replay_name: str
    players: List[str]
    timeline: List[Dict]
    boost_pads: List[Dict]
    replay_meta: Dict
    df: pd.DataFrame
    duration_s: float
    metrics_by_player: Dict[str, List[Dict]] = field(default_factory=dict)
    events_by_player: Dict[str, List[Dict]] = field(default_factory=dict)


def _sample_value_at_time(samples: List[Dict], t: float, key: str, default):
    if not samples:
        return default
    cur = default
    for s in samples:
        if float(s.get("time_s", 0.0)) <= float(t):
            cur = s.get(key, cur)
        else:
            break
    return cur


def _seconds_remaining_at_time(samples: List[Dict], t: float, default: float = 300.0) -> float:
    try:
        return max(0.0, float(_sample_value_at_time(samples, t, "seconds_remaining", default)))
    except Exception:
        return float(default)


def _bool_at_time(samples: List[Dict], t: float, key: str, default: bool = False) -> bool:
    return bool(_sample_value_at_time(samples, t, key, default))


def _build_kickoff_pause_windows(
    timeline_start_t: float,
    timeline_end_t: float,
    goal_pause_windows: List[Dict],
    ball_hit_samples: List[Dict],
    timeout_s: float = 4.0,
) -> List[Dict]:
    starts = [float(timeline_start_t)]
    for w in goal_pause_windows:
        starts.append(float(w.get("pause_end_s", 0.0)))
    starts = sorted(set(starts))
    kickoff_windows: List[Dict] = []
    hit_times = sorted(float(s.get("time_s", 0.0)) for s in ball_hit_samples if bool(s.get("ball_has_been_hit", False)))
    for ks in starts:
        if ks > float(timeline_end_t):
            continue
        first_hit = None
        for ht in hit_times:
            if ht >= ks:
                first_hit = ht
                break
        if first_hit is None:
            ke = min(float(timeline_end_t), ks + timeout_s)
        else:
            ke = min(float(timeline_end_t), max(ks, first_hit))
        if ke > ks + 1e-3:
            kickoff_windows.append({"start_s": round(ks, 4), "end_s": round(ke, 4), "first_touch_s": round(ke, 4)})
    return kickoff_windows


def _build_inactive_windows(goal_pause_windows: List[Dict], kickoff_windows: List[Dict]) -> List[Dict]:
    windows: List[Dict] = []
    for w in goal_pause_windows:
        windows.append({"start_s": float(w.get("pause_start_s", 0.0)), "end_s": float(w.get("pause_end_s", 0.0)), "kind": "goal_pause"})
    for w in kickoff_windows:
        windows.append({"start_s": float(w.get("start_s", 0.0)), "end_s": float(w.get("end_s", 0.0)), "kind": "kickoff_pause"})
    windows.sort(key=lambda x: (x["start_s"], x["end_s"]))
    merged: List[Dict] = []
    for w in windows:
        if not merged:
            merged.append(dict(w))
            continue
        prev = merged[-1]
        if w["start_s"] <= prev["end_s"] + 1e-4:
            prev["end_s"] = max(prev["end_s"], w["end_s"])
            prev["kind"] = "inactive"
        else:
            merged.append(dict(w))
    return merged


def _score_at_time(score_samples: List[Dict], t: float) -> Tuple[int, int]:
    if not score_samples:
        return 0, 0
    blue = int(score_samples[0].get("blue", 0) or 0)
    orange = int(score_samples[0].get("orange", 0) or 0)
    for s in score_samples:
        if float(s.get("time_s", 0.0)) <= float(t):
            blue = int(s.get("blue", blue) or blue)
            orange = int(s.get("orange", orange) or orange)
        else:
            break
    return blue, orange


def _annotate_df_game_state(df: pd.DataFrame, replay_meta: Dict) -> pd.DataFrame:
    out = df.copy()
    times = pd.to_numeric(out["time"], errors="coerce").fillna(0.0).to_list()
    clock_samples = list(replay_meta.get("clock_samples", []) or [])
    goal_windows = list(replay_meta.get("goal_pause_windows", []) or [])
    kickoff_windows = list(replay_meta.get("kickoff_pause_windows", []) or [])
    overtime_samples = list(replay_meta.get("overtime_samples", []) or [])
    inactive_windows = list(replay_meta.get("inactive_windows", []) or [])
    state_name_samples = list(replay_meta.get("state_name_samples", []) or [])
    out["seconds_remaining"] = [float(_seconds_remaining_at_time(clock_samples, t)) for t in times]
    out["is_overtime"] = [1 if _bool_at_time(overtime_samples, t, "is_overtime", False) else 0 for t in times]
    out["is_goal_pause"] = [0] * len(times)
    out["is_kickoff_pause"] = [0] * len(times)
    out["is_inactive_phase"] = [0] * len(times)
    for i, t in enumerate(times):
        gp = any(float(w.get("pause_start_s", 0.0)) <= t < float(w.get("pause_end_s", 0.0)) for w in goal_windows)
        kp = any(float(w.get("start_s", 0.0)) <= t < float(w.get("end_s", 0.0)) for w in kickoff_windows)
        ip = any(float(w.get("start_s", 0.0)) <= t < float(w.get("end_s", 0.0)) for w in inactive_windows)
        st = str(_sample_value_at_time(state_name_samples, t, "state_name", "") or "").lower()
        paused_state = any(k in st for k in ("countdown", "post", "replay", "ended", "inactive", "pregame"))
        if paused_state:
            ip = True
        out.at[i, "is_goal_pause"] = 1 if gp else 0
        out.at[i, "is_kickoff_pause"] = 1 if kp else 0
        out.at[i, "is_inactive_phase"] = 1 if ip else 0
    out["active_play"] = ((out["is_goal_pause"] == 0) & (out["is_kickoff_pause"] == 0) & (out["is_inactive_phase"] == 0)).astype(int)
    return out


def _discover_players(df: pd.DataFrame) -> List[str]:
    players: List[str] = []
    for col in df.columns:
        if col.endswith("_x") and not col.startswith("Ball"):
            base = col[:-2]
            if base.endswith("_rot") or base.endswith("_ang_vel") or base.endswith("_vel"):
                continue
            if f"{base}_y" in df.columns and f"{base}_z" in df.columns:
                players.append(base)
    return sorted(set(players))


def _build_timeline(df: pd.DataFrame, players: List[str]) -> List[Dict]:
    out: List[Dict] = []
    for _, row in df.iterrows():
        frame = {
            "t": float(row["time"]),
            "seconds_remaining": float(row.get("seconds_remaining", 0.0)),
            "is_overtime": bool(int(row.get("is_overtime", 0) or 0)),
            "is_goal_pause": bool(int(row.get("is_goal_pause", 0) or 0)),
            "is_kickoff_pause": bool(int(row.get("is_kickoff_pause", 0) or 0)),
            "is_inactive_phase": bool(int(row.get("is_inactive_phase", 0) or 0)),
            "active_play": bool(int(row.get("active_play", 1) or 0)),
            "ball": {
                "x": float(row["Ball_x"]),
                "y": float(row["Ball_y"]),
                "z": float(row["Ball_z"]),
                "qx": float(row.get("Ball_rot_x", 0.0)),
                "qy": float(row.get("Ball_rot_y", 0.0)),
                "qz": float(row.get("Ball_rot_z", 0.0)),
                "qw": float(row.get("Ball_rot_w", 1.0)),
                "wx": float(row.get("Ball_ang_vel_x", 0.0)),
                "wy": float(row.get("Ball_ang_vel_y", 0.0)),
                "wz": float(row.get("Ball_ang_vel_z", 0.0)),
                "vx": float(row.get("Ball_vel_x", 0.0)),
                "vy": float(row.get("Ball_vel_y", 0.0)),
                "vz": float(row.get("Ball_vel_z", 0.0)),
            },
            "players": [],
        }
        for p in players:
            frame["players"].append(
                {
                    "name": p,
                    "x": float(row[f"{p}_x"]),
                    "y": float(row[f"{p}_y"]),
                    "z": float(row[f"{p}_z"]),
                    "boost": float(row.get(f"{p}_boost", 0.0)),
                    "steer": float(row.get(f"{p}_steer", 0.0)),
                    "throttle": float(row.get(f"{p}_throttle", 0.0)),
                    "jump": int(row.get(f"{p}_jump", 0)),
                    "double_jump": int(row.get(f"{p}_double_jump", 0)),
                    "handbrake": int(row.get(f"{p}_handbrake", 0)),
                    "qx": float(row.get(f"{p}_rot_x", 0.0)),
                    "qy": float(row.get(f"{p}_rot_y", 0.0)),
                    "qz": float(row.get(f"{p}_rot_z", 0.0)),
                    "qw": float(row.get(f"{p}_rot_w", 1.0)),
                    "yaw": float(row.get(f"{p}_yaw", 0.0)),
                    "pitch": float(row.get(f"{p}_pitch", 0.0)),
                    "roll": float(row.get(f"{p}_roll", 0.0)),
                    "wx": float(row.get(f"{p}_ang_vel_x", 0.0)),
                    "wy": float(row.get(f"{p}_ang_vel_y", 0.0)),
                    "wz": float(row.get(f"{p}_ang_vel_z", 0.0)),
                    "vx": float(row.get(f"{p}_vel_x", 0.0)),
                    "vy": float(row.get(f"{p}_vel_y", 0.0)),
                    "vz": float(row.get(f"{p}_vel_z", 0.0)),
                }
            )
        out.append(frame)
    return out


def _normalize_player_name(name: str) -> str:
    return "".join(ch.lower() for ch in str(name or "").strip() if ch.isalnum())


def _parse_replay_date_iso(v: Any) -> str:
    raw = str(v or "").strip()
    if not raw:
        return ""
    for fmt in ("%Y-%m-%d %H-%M-%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.isoformat()
        except Exception:
            continue
    return ""


def _extract_replay_meta(json_path: Path, timeline_start_t: float, timeline_end_t: float) -> Dict:
    try:
        with open(json_path, "r", encoding="utf-8", errors="replace") as f:
            payload = json.loads(f.readline())
    except Exception:
        return {
            "map_name": "",
            "team_scores_final": {"blue": 0, "orange": 0},
            "goals": [],
            "clock_samples": [],
            "score_samples": [],
            "goal_pause_windows": [],
            "kickoff_pause_windows": [],
            "inactive_windows": [],
            "overtime_samples": [],
            "ball_hit_samples": [],
            "match_ended_samples": [],
            "state_name_samples": [],
            "ot_start_s": None,
            "replay_date_raw": "",
            "replay_date_iso": "",
        }

    props = payload.get("properties", {}) or {}
    frames = (payload.get("network_frames", {}) or {}).get("frames", []) or []

    goals = []
    player_teams: Dict[str, int] = {}
    record_fps = float(props.get("RecordFPS", 30.0) or 30.0)
    for g in props.get("Goals", []) or []:
        frame_idx = int(g.get("frame", 0) or 0)
        rel_t = frame_idx / max(1e-6, record_fps)
        abs_t = timeline_start_t + rel_t
        goals.append(
            {
                "frame": frame_idx,
                "time_s": float(abs_t),
                "team": int(g.get("PlayerTeam", 0) or 0),
                "scorer": str(g.get("PlayerName", "")),
            }
        )
    goals.sort(key=lambda x: x["time_s"])

    for ps in props.get("PlayerStats", []) or []:
        try:
            name = str(ps.get("Name", "") or "").strip()
            if not name:
                continue
            team = int(ps.get("Team", -1))
            if team in (0, 1):
                player_teams[name] = team
        except Exception:
            continue

    # Pull authoritative countdown updates and score updates from replay frames.
    objects = payload.get("objects", []) or []
    sec_obj_id = None
    overtime_obj_id = None
    ball_hit_obj_id = None
    match_ended_obj_id = None
    state_name_obj_id = None
    try:
        sec_obj_id = int(objects.index("TAGame.GameEvent_Soccar_TA:SecondsRemaining"))
    except ValueError:
        sec_obj_id = 107  # Common id in many rrrocket outputs.
    try:
        overtime_obj_id = int(objects.index("TAGame.GameEvent_Soccar_TA:bOverTime"))
    except ValueError:
        overtime_obj_id = 104
    try:
        ball_hit_obj_id = int(objects.index("TAGame.GameEvent_Soccar_TA:bBallHasBeenHit"))
    except ValueError:
        ball_hit_obj_id = 105
    try:
        match_ended_obj_id = int(objects.index("TAGame.GameEvent_Soccar_TA:bMatchEnded"))
    except ValueError:
        match_ended_obj_id = 101
    try:
        state_name_obj_id = int(objects.index("TAGame.GameEvent_TA:ReplicatedStateName"))
    except ValueError:
        state_name_obj_id = 73

    def _to_seconds(attr: dict) -> float | None:
        if not isinstance(attr, dict) or not attr:
            return None
        if "Int" in attr:
            try:
                return float(attr["Int"])
            except (TypeError, ValueError):
                return None
        for v in attr.values():
            if isinstance(v, (int, float)):
                return float(v)
        return None

    clock_samples: List[Dict] = []
    overtime_samples: List[Dict] = []
    ball_hit_samples: List[Dict] = []
    match_ended_samples: List[Dict] = []
    state_name_samples: List[Dict] = []
    for fr in frames:
        t = float(fr.get("time", 0.0) or 0.0)
        for u in fr.get("updated_actors", []) or []:
            oid = int(u.get("object_id", -1))
            if oid == sec_obj_id:
                sec = _to_seconds(u.get("attribute"))
                if sec is None:
                    continue
                if clock_samples and abs(clock_samples[-1]["time_s"] - t) < 1e-6:
                    clock_samples[-1]["seconds_remaining"] = sec
                else:
                    clock_samples.append({"time_s": t, "seconds_remaining": sec})
                continue
            if oid == overtime_obj_id:
                attr = u.get("attribute", {}) or {}
                raw = next(iter(attr.values())) if attr else False
                overtime_samples.append({"time_s": t, "is_overtime": bool(raw)})
                continue
            if oid == ball_hit_obj_id:
                attr = u.get("attribute", {}) or {}
                raw = next(iter(attr.values())) if attr else False
                ball_hit_samples.append({"time_s": t, "ball_has_been_hit": bool(raw)})
                continue
            if oid == match_ended_obj_id:
                attr = u.get("attribute", {}) or {}
                raw = next(iter(attr.values())) if attr else False
                match_ended_samples.append({"time_s": t, "match_ended": bool(raw)})
                continue
            if oid == state_name_obj_id:
                attr = u.get("attribute", {}) or {}
                raw = next(iter(attr.values())) if attr else ""
                state_name_samples.append({"time_s": t, "state_name": str(raw or "")})
                continue
    # Build scoreboard timeline from official goal list so it only changes on goals.
    score_samples: List[Dict] = [{"time_s": float(timeline_start_t), "blue": 0, "orange": 0}]
    blue = 0
    orange = 0
    for g in goals:
        team = int(g.get("team", -1))
        if team == 0:
            blue += 1
        elif team == 1:
            orange += 1
        else:
            continue
        score_samples.append({"time_s": float(g["time_s"]), "blue": blue, "orange": orange})
    goal_pause_windows: List[Dict] = []
    for s in score_samples[1:]:
        gs = float(s.get("time_s", 0.0))
        ge = min(float(timeline_end_t), gs + 3.0)
        goal_pause_windows.append(
            {
                "pause_start_s": gs,
                "pause_end_s": ge,
                "blue": int(s.get("blue", 0) or 0),
                "orange": int(s.get("orange", 0) or 0),
            }
        )
    kickoff_pause_windows = _build_kickoff_pause_windows(
        timeline_start_t=float(timeline_start_t),
        timeline_end_t=float(timeline_end_t),
        goal_pause_windows=goal_pause_windows,
        ball_hit_samples=ball_hit_samples,
        timeout_s=4.0,
    )
    inactive_windows = _build_inactive_windows(goal_pause_windows=goal_pause_windows, kickoff_windows=kickoff_pause_windows)

    # Fallback for atypical replays without explicit clock updates.
    if not clock_samples:
        duration = max(0.0, timeline_end_t - timeline_start_t)
        clock_samples = [
            {"time_s": float(timeline_start_t), "seconds_remaining": float(max(0.0, 300.0))},
            {"time_s": float(timeline_end_t), "seconds_remaining": float(max(0.0, 300.0 - duration))},
        ]

    ot_start_s = None
    zero_clock_t = None
    for s in clock_samples:
        if float(s.get("seconds_remaining", 9999.0) or 9999.0) <= 0.001:
            zero_clock_t = float(s.get("time_s", 0.0) or 0.0)
            break
    tie_at_zero = False
    if zero_clock_t is not None:
        b0, o0 = _score_at_time(score_samples, zero_clock_t)
        tie_at_zero = b0 == o0
    if zero_clock_t is not None and tie_at_zero:
        for s in overtime_samples:
            if bool(s.get("is_overtime", False)) and float(s.get("time_s", 0.0)) >= (zero_clock_t - 1e-3):
                ot_start_s = float(s.get("time_s", 0.0))
                break

    replay_date_raw = str(props.get("Date", "") or "")
    replay_date_iso = _parse_replay_date_iso(replay_date_raw)

    return {
        "map_name": str(props.get("MapName", "")),
        "team_scores_final": {
            "blue": int(props.get("Team0Score", 0) or 0),
            "orange": int(props.get("Team1Score", 0) or 0),
        },
        "goals": goals,
        "clock_samples": clock_samples,
        "score_samples": score_samples,
        "goal_pause_windows": goal_pause_windows,
        "kickoff_pause_windows": kickoff_pause_windows,
        "inactive_windows": inactive_windows,
        "overtime_samples": overtime_samples,
        "ball_hit_samples": ball_hit_samples,
        "match_ended_samples": match_ended_samples,
        "state_name_samples": state_name_samples,
        "ot_start_s": ot_start_s,
        "zero_clock_t": zero_clock_t,
        "tie_at_zero": bool(tie_at_zero),
        "replay_date_raw": replay_date_raw,
        "replay_date_iso": replay_date_iso,
        "player_teams": player_teams,
    }


def _extract_boost_and_demo_from_json(json_path: Path) -> tuple[Dict[str, List[Dict]], List[Dict]]:
    try:
        with open(json_path, "r", encoding="utf-8", errors="replace") as f:
            payload = json.loads(f.readline())
    except Exception:
        return {}, []

    objects = payload.get("objects", []) or []
    frames = (payload.get("network_frames", {}) or {}).get("frames", []) or []
    object_id_to_name = {i: n for i, n in enumerate(objects)}

    pri_map: Dict[int, str] = {}
    car_pri_map: Dict[int, int] = {}
    comp_to_car_map: Dict[int, int] = {}
    actor_class_map: Dict[int, str] = {}
    boost_component_candidates: set[int] = set()
    unresolved_boost_by_component: Dict[int, List[Dict]] = {}
    unresolved_demo_by_victim_actor: Dict[int, List[Dict]] = {}
    boost_by_player: Dict[str, List[Dict]] = {}
    demo_events: List[Dict] = []

    def _extract_numeric(attr: dict) -> float | None:
        if not isinstance(attr, dict):
            return None
        for k in (
            "boost_amount",
            "ReplicatedBoostAmount",
            "CurrentBoostAmount",
            "ServerConfirmBoostAmount",
            "ClientFixBoostAmount",
            "Byte",
            "Int",
            "Float",
        ):
            v = attr.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        for v in attr.values():
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, dict):
                nested = _extract_numeric(v)
                if nested is not None:
                    return float(nested)
        return None

    def _resolve_player_from_car_actor(car_actor_id: int) -> str:
        pri_id = car_pri_map.get(car_actor_id)
        if not isinstance(pri_id, int) or pri_id < 0:
            return ""
        return str(pri_map.get(pri_id) or "")

    def _append_boost_for_component(component_actor_id: int, time_s: float, boost_pct: float) -> None:
        car_id = comp_to_car_map.get(component_actor_id)
        if isinstance(car_id, int):
            player = _resolve_player_from_car_actor(car_id)
            if player:
                boost_by_player.setdefault(player, []).append({"time_s": float(time_s), "boost": float(boost_pct)})
                return
        unresolved_boost_by_component.setdefault(component_actor_id, []).append(
            {"time_s": float(time_s), "boost": float(boost_pct)}
        )

    def _flush_component_boost(component_actor_id: int) -> None:
        pending = unresolved_boost_by_component.pop(component_actor_id, None)
        if not pending:
            return
        car_id = comp_to_car_map.get(component_actor_id)
        if not isinstance(car_id, int):
            unresolved_boost_by_component[component_actor_id] = pending
            return
        player = _resolve_player_from_car_actor(car_id)
        if not player:
            unresolved_boost_by_component[component_actor_id] = pending
            return
        out = boost_by_player.setdefault(player, [])
        out.extend(pending)

    def _flush_unresolved_demos_for_car(car_actor_id: int) -> None:
        pending = unresolved_demo_by_victim_actor.pop(car_actor_id, None)
        if not pending:
            return
        victim_name = _resolve_player_from_car_actor(car_actor_id)
        for ev in pending:
            ev["victim_player"] = victim_name
            demo_events.append(ev)

    for fr in frames:
        t = float(fr.get("time", 0.0) or 0.0)

        for new_actor in fr.get("new_actors", []) or []:
            actor_id = int(new_actor.get("actor_id", -1))
            object_id = int(new_actor.get("object_id", -1))
            actor_class = object_id_to_name.get(object_id, "")
            actor_class_map[actor_id] = actor_class
            if "CarComponent_Boost" in actor_class:
                boost_component_candidates.add(actor_id)

        for deleted in fr.get("deleted_actors", []) or []:
            did = int(deleted)
            car_pri_map.pop(did, None)
            comp_to_car_map.pop(did, None)
            boost_component_candidates.discard(did)
            unresolved_boost_by_component.pop(did, None)
            unresolved_demo_by_victim_actor.pop(did, None)

        for up in fr.get("updated_actors", []) or []:
            actor_id = int(up.get("actor_id", -1))
            object_id = int(up.get("object_id", -1))
            prop_name = object_id_to_name.get(object_id, "")
            attrs = up.get("attribute", {}) or {}
            val = next(iter(attrs.values())) if attrs else None
            actor_class = actor_class_map.get(actor_id, "")

            if "PlayerName" in prop_name and isinstance(val, str):
                pri_map[actor_id] = val

            if "Pawn:PlayerReplicationInfo" in prop_name:
                actor_class = actor_class_map.get(actor_id, "")
                # Ignore non-car actors which also replicate PRI pointers in some modes.
                if "Car" not in actor_class:
                    continue
                pri_id = None
                if isinstance(val, dict) and "ActiveActor" in attrs:
                    aa = attrs["ActiveActor"]
                    if aa.get("active"):
                        pri_id = aa.get("actor")
                elif isinstance(val, int):
                    pri_id = val
                if isinstance(pri_id, int) and pri_id >= 0:
                    car_pri_map[actor_id] = pri_id
                    _flush_unresolved_demos_for_car(actor_id)
                    for comp_actor_id, car_id in list(comp_to_car_map.items()):
                        if car_id == actor_id:
                            _flush_component_boost(comp_actor_id)

            if "CarComponent_TA:Vehicle" in prop_name:
                car_id = None
                if isinstance(val, dict) and "ActiveActor" in attrs:
                    aa = attrs["ActiveActor"]
                    if aa.get("active"):
                        car_id = aa.get("actor")
                elif isinstance(val, int):
                    car_id = val
                if isinstance(car_id, int) and car_id >= 0 and (
                    "CarComponent_Boost" in actor_class or actor_id in boost_component_candidates or actor_id in unresolved_boost_by_component
                ):
                    comp_to_car_map[actor_id] = car_id
                    _flush_component_boost(actor_id)

            if (
                "ReplicatedBoost" in prop_name
                or "ReplicatedBoostAmount" in prop_name
                or "CurrentBoostAmount" in prop_name
                or "ServerConfirmBoostAmount" in prop_name
                or "ClientFixBoostAmount" in prop_name
            ):
                num = _extract_numeric(attrs)
                if num is None:
                    if isinstance(val, (int, float)):
                        num = float(val)
                    else:
                        continue
                boost_pct = max(0.0, min(100.0, (num / 255.0) * 100.0 if num > 1.0 else num * 100.0))
                boost_component_candidates.add(actor_id)
                _append_boost_for_component(actor_id, t, boost_pct)

            if "ReplicatedDemolishGoalExplosion" in prop_name:
                fx = attrs.get("DemolishFx")
                if not isinstance(fx, dict):
                    continue
                victim_id = None
                attacker_id = None
                if fx.get("victim_flag"):
                    victim_id = fx.get("victim")
                if fx.get("attacker_flag"):
                    attacker_id = fx.get("attacker")
                if not isinstance(victim_id, int):
                    continue
                victim_name = _resolve_player_from_car_actor(victim_id)
                attacker_name = _resolve_player_from_car_actor(attacker_id) if isinstance(attacker_id, int) else ""
                ev = {
                    "time_s": float(t),
                    "victim_actor_id": int(victim_id),
                    "victim_player": str(victim_name or ""),
                    "attacker_actor_id": int(attacker_id) if isinstance(attacker_id, int) else -1,
                    "attacker_player": str(attacker_name or ""),
                }
                if victim_name:
                    demo_events.append(ev)
                else:
                    unresolved_demo_by_victim_actor.setdefault(victim_id, []).append(ev)

            if "ReplicatedDemolishExtended" in prop_name:
                d = attrs.get("DemolishExtended")
                if not isinstance(d, dict):
                    continue
                victim = d.get("victim")
                attacker = d.get("attacker")
                victim_id = victim.get("actor") if isinstance(victim, dict) and victim.get("active") else None
                attacker_id = attacker.get("actor") if isinstance(attacker, dict) and attacker.get("active") else None
                if not isinstance(victim_id, int):
                    continue
                victim_class = actor_class_map.get(victim_id, "")
                if "Car" not in victim_class:
                    continue
                victim_name = _resolve_player_from_car_actor(victim_id)
                attacker_name = _resolve_player_from_car_actor(attacker_id) if isinstance(attacker_id, int) else ""
                ev = {
                    "time_s": float(t),
                    "victim_actor_id": int(victim_id),
                    "victim_player": str(victim_name or ""),
                    "attacker_actor_id": int(attacker_id) if isinstance(attacker_id, int) else -1,
                    "attacker_player": str(attacker_name or ""),
                }
                if victim_name:
                    demo_events.append(ev)
                else:
                    unresolved_demo_by_victim_actor.setdefault(victim_id, []).append(ev)

    # Late flush in case some mappings are only available near end-of-file.
    for comp_actor_id in list(unresolved_boost_by_component.keys()):
        _flush_component_boost(comp_actor_id)
    for victim_actor_id in list(unresolved_demo_by_victim_actor.keys()):
        _flush_unresolved_demos_for_car(victim_actor_id)

    for name, arr in boost_by_player.items():
        arr.sort(key=lambda x: x["time_s"])
        dedup: List[Dict] = []
        for s in arr:
            if dedup and abs(dedup[-1]["time_s"] - s["time_s"]) < 1e-6:
                dedup[-1]["boost"] = float(s["boost"])
            else:
                dedup.append({"time_s": float(s["time_s"]), "boost": float(s["boost"])})
        boost_by_player[name] = dedup
    demo_events.sort(key=lambda x: x["time_s"])
    dedup_demo: List[Dict] = []
    for ev in demo_events:
        if dedup_demo:
            prev = dedup_demo[-1]
            if (
                abs(float(prev["time_s"]) - float(ev["time_s"])) < 1e-4
                and int(prev.get("victim_actor_id", -1)) == int(ev.get("victim_actor_id", -2))
                and int(prev.get("attacker_actor_id", -1)) == int(ev.get("attacker_actor_id", -2))
            ):
                continue
        dedup_demo.append(ev)
    demo_events = dedup_demo
    return boost_by_player, demo_events


def _compute_metrics_for_player(df: pd.DataFrame, players: List[str], player: str, timeline: List[Dict] | None = None) -> tuple[List[Dict], List[Dict]]:
    if player not in players:
        raise RuntimeError(f"Unknown player '{player}'")
    builder = ReplayPacketBuilder(df=df, players=players)
    p_idx = players.index(player)
    engine = LiveMetricsEngine(window_seconds=10.0)
    timeline_metrics: List[Dict] = []
    for i in range(len(df)):
        packet = builder.build(i)
        engine.update(packet, player_index=p_idx)
        current, _, _ = engine.snapshot()
        point = {"t": float(current.get("timestamp", float(df.iloc[i]["time"])))}
        for k in METRIC_KEYS:
            point[k] = float(current.get(k, 0.0))
        for k in DEBUG_METRIC_KEYS:
            point[k] = float(current.get(k, 0.0))
        timeline_metrics.append(point)
    _, _, events = engine.snapshot()
    if timeline:
        events, counts = refine_events_posthoc(timeline, player, events)
        apply_whiff_rate_from_events(timeline_metrics, events, window_s=10.0)
        for pt in timeline_metrics:
            for k, v in counts.items():
                pt[k] = float(v)
    return timeline_metrics, events


def _compute_metrics_for_all_players(df: pd.DataFrame, players: List[str]) -> tuple[Dict[str, List[Dict]], Dict[str, List[Dict]]]:
    if not players:
        return {}, {}
    builder = ReplayPacketBuilder(df=df, players=players)
    engines = [LiveMetricsEngine(window_seconds=10.0) for _ in players]
    timeline_by_player: Dict[str, List[Dict]] = {p: [] for p in players}
    events_by_player: Dict[str, List[Dict]] = {p: [] for p in players}

    for i in range(len(df)):
        packet = builder.build(i)
        row_time = float(df.iloc[i]["time"])
        for p_idx, player in enumerate(players):
            engine = engines[p_idx]
            engine.update(packet, player_index=p_idx)
            current, _, _ = engine.snapshot()
            point = {"t": float(current.get("timestamp", row_time))}
            for k in METRIC_KEYS:
                point[k] = float(current.get(k, 0.0))
            for k in DEBUG_METRIC_KEYS:
                point[k] = float(current.get(k, 0.0))
            timeline_by_player[player].append(point)

    for p_idx, player in enumerate(players):
        _, _, events = engines[p_idx].snapshot()
        events_by_player[player] = events
    return timeline_by_player, events_by_player


def load_replay_bytes(file_name: str, data: bytes, rrrocket_override: str | None = None) -> ReplaySession:
    session_id = uuid.uuid4().hex
    replay_name = Path(file_name).name

    with tempfile.TemporaryDirectory(prefix="rl_replay_dash_") as td:
        td_path = Path(td)
        replay_path = td_path / replay_name
        replay_path.write_bytes(data)

        rr_bin = _resolve_rrrocket_path(rrrocket_override)
        if not rr_bin:
            raise RuntimeError("Could not locate rrrocket binary. Set RRROCKET_BIN to rrrocket.exe.")

        json_path = td_path / f"{replay_path.stem}.json"
        with contextlib.redirect_stdout(io.StringIO()):
            ok = _run_rrrocket_to_json(rr_bin, str(replay_path), str(json_path))
        if not ok:
            raise RuntimeError("rrrocket failed to parse replay.")

        out_csv_name = f"{session_id}.csv"
        with contextlib.redirect_stdout(io.StringIO()):
            extract_final(str(json_path), out_csv_name)

        csv_path = Path(CSV_DIR) / out_csv_name
        if not csv_path.exists():
            raise RuntimeError("CSV extraction failed.")

        df = pd.read_csv(csv_path)
        replay_meta = _extract_replay_meta(
            json_path,
            float(df["time"].iloc[0]) if len(df) else 0.0,
            float(df["time"].iloc[-1]) if len(df) else 0.0,
        )
        json_boost_by_player, demo_events = _extract_boost_and_demo_from_json(json_path)
        replay_meta["demo_events"] = demo_events

        players = _discover_players(df)
        norm_json_boost = {_normalize_player_name(k): v for k, v in json_boost_by_player.items()}
        applied_json_boost: Dict[str, List[Dict]] = {}
        for player in players:
            pnorm = _normalize_player_name(player)
            samples = json_boost_by_player.get(player) or norm_json_boost.get(pnorm) or []
            if not samples:
                continue
            samples = sorted(samples, key=lambda x: float(x.get("time_s", 0.0)))
            times = [float(s.get("time_s", 0.0)) for s in samples]
            vals = [float(s.get("boost", 0.0)) for s in samples]
            boost_col = f"{player}_boost"
            csv_has_boost = boost_col in df.columns
            csv_max = float(pd.to_numeric(df[boost_col], errors="coerce").fillna(0).max()) if csv_has_boost else 0.0
            if (not csv_has_boost) or (csv_max <= 0.0):
                interp_vals: List[float] = []
                for t in df["time"].to_list():
                    i = bisect_right(times, float(t)) - 1
                    interp_vals.append(vals[i] if i >= 0 else 0.0)
                df[boost_col] = interp_vals
            applied_json_boost[player] = samples

        defaulted_boost_players: List[str] = []
        for player in players:
            boost_col = f"{player}_boost"
            if boost_col not in df.columns:
                df[boost_col] = 33.0
                defaulted_boost_players.append(player)
                continue
            col = pd.to_numeric(df[boost_col], errors="coerce").fillna(0.0)
            if float(col.max()) <= 0.0:
                df[boost_col] = 33.0
                defaulted_boost_players.append(player)

        replay_meta["boost_samples_by_player"] = applied_json_boost
        replay_meta["boost_source"] = "json" if applied_json_boost else "csv"
        replay_meta["boost_defaulted_players"] = defaulted_boost_players
        boost_cols = [c for c in df.columns if c.endswith("_boost")]
        replay_meta["boost_unresolved"] = bool(
            boost_cols and all(pd.to_numeric(df[c], errors="coerce").fillna(0).max() <= 0 for c in boost_cols)
        )

    for c in ["time", "Ball_x", "Ball_y", "Ball_z"]:
        if c not in df.columns:
            raise RuntimeError(f"Missing required column in extracted CSV: {c}")

    players = _discover_players(df)
    if not players:
        raise RuntimeError("No player position columns found in extracted replay CSV.")

    df = _annotate_df_game_state(df, replay_meta)
    timeline = _build_timeline(df, players)
    duration_s = float(df["time"].iloc[-1] - df["time"].iloc[0]) if len(df) > 1 else 0.0

    return ReplaySession(
        session_id=session_id,
        replay_name=replay_name,
        players=players,
        timeline=timeline,
        boost_pads=[dict(p) for p in SOCCAR_BOOST_PADS],
        replay_meta=replay_meta,
        df=df,
        duration_s=duration_s,
    )


def ensure_player_metrics(session: ReplaySession, player: str) -> None:
    if player in session.metrics_by_player and player in session.events_by_player:
        return
    metrics, events = _compute_metrics_for_player(session.df, session.players, player, timeline=session.timeline)
    session.metrics_by_player[player] = metrics
    session.events_by_player[player] = events


def ensure_all_player_metrics(session: ReplaySession) -> None:
    if session.players and len(session.metrics_by_player) == len(session.players) and len(session.events_by_player) == len(session.players):
        return
    timelines, events = _compute_metrics_for_all_players(session.df, session.players)
    session.metrics_by_player = timelines
    session.events_by_player = events
