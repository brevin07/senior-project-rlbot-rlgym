from __future__ import annotations

from bisect import bisect_left
from math import sqrt
from typing import Any, Dict, List, Tuple

WHIFF_WINDOW_PRE_S = 0.4
WHIFF_WINDOW_POST_S = 1.0
WHIFF_CONTACT_RADIUS = 220.0
WHIFF_TOUCH_RADIUS = 180.0
WHIFF_COOLDOWN_S = 0.8

WHIFF_BUMP_SELF_TO_OTHER_MAX = 520.0
WHIFF_BUMP_OTHER_TO_BALL_MIN = 700.0


def _norm3(x: float, y: float, z: float) -> float:
    return sqrt(x * x + y * y + z * z)


def _nearest_idx(times: List[float], t: float) -> int:
    if not times:
        return 0
    i = bisect_left(times, t)
    if i <= 0:
        return 0
    if i >= len(times):
        return len(times) - 1
    return i if abs(times[i] - t) < abs(times[i - 1] - t) else i - 1


def _window_indices(times: List[float], center_t: float, pre_s: float, post_s: float) -> tuple[int, int]:
    if not times:
        return 0, 0
    t0 = center_t - pre_s
    t1 = center_t + post_s
    i0 = max(0, bisect_left(times, t0))
    i1 = min(len(times) - 1, bisect_left(times, t1))
    if i1 < i0:
        i1 = i0
    return i0, i1


def _player_frame(frame: Dict[str, Any], player: str) -> Dict[str, Any] | None:
    for p in frame.get("players", []) or []:
        if p.get("name") == player:
            return p
    return None


def _nearest_opponent_stats(frame: Dict[str, Any], player: str) -> Tuple[float, float]:
    pself = _player_frame(frame, player)
    if not pself:
        return 99999.0, 99999.0
    bx = float(frame.get("ball", {}).get("x", 0.0))
    by = float(frame.get("ball", {}).get("y", 0.0))
    bz = float(frame.get("ball", {}).get("z", 0.0))
    sx = float(pself.get("x", 0.0))
    sy = float(pself.get("y", 0.0))
    sz = float(pself.get("z", 0.0))
    nearest_self = 99999.0
    nearest_ball = 99999.0
    for op in frame.get("players", []) or []:
        if op.get("name") == player:
            continue
        ox = float(op.get("x", 0.0))
        oy = float(op.get("y", 0.0))
        oz = float(op.get("z", 0.0))
        d_self = _norm3(ox - sx, oy - sy, oz - sz)
        d_ball = _norm3(ox - bx, oy - by, oz - bz)
        if d_self < nearest_self:
            nearest_self = d_self
        if d_ball < nearest_ball:
            nearest_ball = d_ball
    return nearest_self, nearest_ball


def _player_ball_dist(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 99999.0
    b = frame.get("ball", {}) or {}
    return _norm3(
        float(p.get("x", 0.0)) - float(b.get("x", 0.0)),
        float(p.get("y", 0.0)) - float(b.get("y", 0.0)),
        float(p.get("z", 0.0)) - float(b.get("z", 0.0)),
    )


def _ball_speed(frame: Dict[str, Any]) -> float:
    b = frame.get("ball", {}) or {}
    return _norm3(float(b.get("vx", 0.0)), float(b.get("vy", 0.0)), float(b.get("vz", 0.0)))


def _player_speed(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 0.0
    return _norm3(float(p.get("vx", 0.0)), float(p.get("vy", 0.0)), float(p.get("vz", 0.0)))


def _player_ang_speed(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 0.0
    return _norm3(float(p.get("wx", 0.0)), float(p.get("wy", 0.0)), float(p.get("wz", 0.0)))


def _lateral_speed_to_ball(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 0.0
    b = frame.get("ball", {}) or {}
    to_ball = (
        float(b.get("x", 0.0)) - float(p.get("x", 0.0)),
        float(b.get("y", 0.0)) - float(p.get("y", 0.0)),
        float(b.get("z", 0.0)) - float(p.get("z", 0.0)),
    )
    mag = _norm3(*to_ball)
    if mag <= 1e-6:
        return 0.0
    dirv = (to_ball[0] / mag, to_ball[1] / mag, to_ball[2] / mag)
    vel = (float(p.get("vx", 0.0)), float(p.get("vy", 0.0)), float(p.get("vz", 0.0)))
    toward = vel[0] * dirv[0] + vel[1] * dirv[1] + vel[2] * dirv[2]
    speed = _norm3(*vel)
    lat_sq = max(0.0, speed * speed - toward * toward)
    return lat_sq ** 0.5


def _commit_signal(start_frame: Dict[str, Any], prev_frame: Dict[str, Any], player: str, reason: str) -> str:
    p0 = _player_frame(start_frame, player) or {}
    pp = _player_frame(prev_frame, player) or {}
    reason_low = (reason or "").lower()
    if "flip" in reason_low:
        return "flip"
    if int(p0.get("double_jump", 0)) > 0 or _player_ang_speed(start_frame, player) > 4.8:
        return "flip"
    if int(p0.get("jump", 0)) > 0 or float(p0.get("vz", 0.0)) > 240.0 or (float(p0.get("z", 0.0)) - float(pp.get("z", 0.0))) > 25.0:
        return "jump"
    d_prev = _player_ball_dist(prev_frame, player)
    d_now = _player_ball_dist(start_frame, player)
    if _player_speed(start_frame, player) > 800.0 and (d_prev - d_now) > 70.0:
        return "fast_close_drive"
    return ""


def _nearest_dist_in_window(timeline: List[Dict[str, Any]], i0: int, i1: int, player: str) -> float:
    out = 99999.0
    for i in range(i0, i1 + 1):
        out = min(out, _player_ball_dist(timeline[i], player))
    return out


def _boost(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player) or {}
    return float(p.get("boost", 0.0))


def _empty_counts() -> Dict[str, int]:
    return {
        "suppressed_whiff_flip_commit": 0,
        "suppressed_whiff_disengage": 0,
        "suppressed_whiff_bump_intent": 0,
        "suppressed_whiff_opponent_first_touch": 0,
        "suppressed_hesitation_reposition": 0,
        "suppressed_hesitation_setup": 0,
        "suppressed_hesitation_spacing": 0,
        "whiff_commit_detected_count": 0,
        "whiff_gateA_count": 0,
        "whiff_gateB_count": 0,
        "whiff_gateC_count": 0,
        "whiff_two_of_three_pass_count": 0,
        "whiff_excluded_fake_challenge": 0,
        "whiff_excluded_bump_demo_intent": 0,
        "whiff_excluded_intentional_reset": 0,
    }


def refine_events_posthoc(
    timeline: List[Dict[str, Any]],
    player: str,
    events: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    if not timeline or not events or not player:
        return list(events or []), _empty_counts()

    times = [float(fr.get("t", 0.0)) for fr in timeline]
    kept: List[Dict[str, Any]] = []
    counts = _empty_counts()
    last_kept_whiff_t = -999.0

    for evt in events:
        et = str(evt.get("type", "")).lower()
        t = float(evt.get("time", 0.0))
        i0, i1 = _window_indices(times, t, WHIFF_WINDOW_PRE_S, WHIFF_WINDOW_POST_S)
        ic = _nearest_idx(times, t)
        ip = max(0, i0 - 1)
        f0 = timeline[ic]
        f1 = timeline[i1]
        fp = timeline[ip]

        d0 = _player_ball_dist(f0, player)
        d1 = _player_ball_dist(f1, player)
        dmin_future = _nearest_dist_in_window(timeline, i0, i1, player)
        moving_away = d1 - d0 > 180.0
        near_other_self, near_other_ball = _nearest_opponent_stats(f0, player)
        near_other_ball_next = _nearest_opponent_stats(f1, player)[1]

        p0 = _player_frame(f0, player) or {}
        commit = _commit_signal(f0, fp, player, str(evt.get("reason", "")))
        wall_setup = abs(float(p0.get("y", 0.0))) > 4300.0 or float(p0.get("z", 0.0)) > 260.0

        suppressed_reason = ""
        if et == "whiff":
            if not commit:
                counts["whiff_excluded_fake_challenge"] += 1
                suppressed_reason = "fake_challenge"
            elif near_other_self < WHIFF_BUMP_SELF_TO_OTHER_MAX and near_other_ball > WHIFF_BUMP_OTHER_TO_BALL_MIN:
                counts["suppressed_whiff_bump_intent"] += 1
                counts["whiff_excluded_bump_demo_intent"] += 1
                suppressed_reason = "bump_demo_intent"
            elif moving_away and (_boost(f1, player) - _boost(f0, player)) > 8.0:
                counts["suppressed_whiff_disengage"] += 1
                counts["whiff_excluded_intentional_reset"] += 1
                suppressed_reason = "intentional_reset"
            elif moving_away and near_other_ball_next + 80.0 < d1 and _ball_speed(f1) - _ball_speed(fp) > 220.0:
                counts["suppressed_whiff_opponent_first_touch"] += 1
                suppressed_reason = "opponent_first_touch"
            else:
                counts["whiff_commit_detected_count"] += 1
                gate_a = dmin_future > WHIFF_CONTACT_RADIUS
                gate_b = (d1 - dmin_future) > 140.0
                gate_c = moving_away and dmin_future > WHIFF_TOUCH_RADIUS and _player_speed(f1, player) > 260.0
                if gate_a:
                    counts["whiff_gateA_count"] += 1
                if gate_b:
                    counts["whiff_gateB_count"] += 1
                if gate_c:
                    counts["whiff_gateC_count"] += 1
                gates = int(gate_a) + int(gate_b) + int(gate_c)
                if gates < 2:
                    suppressed_reason = "miss_gates_not_met"
                elif (t - last_kept_whiff_t) < WHIFF_COOLDOWN_S:
                    suppressed_reason = "cooldown"
                else:
                    counts["whiff_two_of_three_pass_count"] += 1
        elif et == "hesitation":
            lat = _lateral_speed_to_ball(f0, player)
            spd = _player_speed(f0, player)
            if lat > 260.0 and spd > 320.0 and (d1 - d0) < 280.0:
                counts["suppressed_hesitation_reposition"] += 1
                suppressed_reason = "repositioning"
            elif wall_setup and spd < 950.0:
                counts["suppressed_hesitation_setup"] += 1
                suppressed_reason = "wall_setup"
            elif moving_away and near_other_ball + 120.0 < d0 and spd > 380.0:
                counts["suppressed_hesitation_spacing"] += 1
                suppressed_reason = "spacing_adjust"

        if suppressed_reason:
            continue

        out = dict(evt)
        out.setdefault("suppression_reason", "")
        out.setdefault("opportunity_blocked", False)
        out.setdefault("intent_flags", [])
        if et == "whiff":
            out["sequence_window_start"] = float(times[i0])
            out["sequence_window_end"] = float(times[i1])
            out["contact_radius_used"] = float(WHIFF_CONTACT_RADIUS)
            out["commit_signal"] = commit
            out["decision_version"] = "whiff_v2_windowed"
            if commit:
                out["intent_flags"] = list(set(list(out.get("intent_flags") or []) + [commit]))
        kept.append(out)
        if et == "whiff":
            last_kept_whiff_t = t

    kept.sort(key=lambda e: float(e.get("time", 0.0)))
    return kept, counts


def apply_whiff_rate_from_events(metrics_timeline: List[Dict[str, Any]], events: List[Dict[str, Any]], window_s: float = 10.0) -> None:
    if not metrics_timeline:
        return
    whiff_times = [float(e.get("time", 0.0)) for e in events if str(e.get("type", "")).lower() == "whiff"]
    whiff_times.sort()
    j = 0
    for point in metrics_timeline:
        t = float(point.get("t", 0.0))
        while j < len(whiff_times) and whiff_times[j] < (t - window_s):
            j += 1
        k = j
        while k < len(whiff_times) and whiff_times[k] <= t:
            k += 1
        count = k - j
        point["whiff_rate_per_min"] = float(count) * (60.0 / max(1e-6, float(window_s)))
