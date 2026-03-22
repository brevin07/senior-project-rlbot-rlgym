from __future__ import annotations

from math import exp, sqrt
from statistics import mean, pstdev
from typing import Any, Dict, List, Tuple


MECHANIC_ALIASES = {
    "flicking_carry_offense": "flicking",
}

MECHANICS = [
    "kickoff",
    "shadow_defense",
    "challenge",
    "fifty_fifty_control",
    "aerial_offense",
    "aerial_defense",
    "flicking",
    "carrying_dribbling",
]

MECH_SHORT = {
    "kickoff": "KO",
    "shadow_defense": "SHD",
    "challenge": "CHAL",
    "fifty_fifty_control": "5050",
    "aerial_offense": "AOF",
    "aerial_defense": "ADF",
    "flicking": "FLK",
    "carrying_dribbling": "DRB",
}

MECH_TITLE = {
    "kickoff": "Kickoff",
    "shadow_defense": "Shadow Defense",
    "challenge": "Challenge",
    "fifty_fifty_control": "50/50 Control",
    "aerial_offense": "Aerial Offense",
    "aerial_defense": "Aerial Defense",
    "flicking": "Flicks",
    "carrying_dribbling": "Carries / Dribbles",
}

KICKOFF_CENTER_MAX_DIST = 240.0
KICKOFF_BALL_SPEED_MAX = 120.0
KICKOFF_WINDOW_TIMEOUT = 4.0
KICKOFF_ATTEMPT_DIST = 1800.0
KICKOFF_ATTEMPT_CLOSING_SPEED = 900.0
KICKOFF_ATTEMPT_SUSTAIN_S = 0.25
KICKOFF_TOUCH_MAX_S = 2.2


def _canonical_mid(mid: str) -> str:
    m = str(mid or "").strip()
    return MECHANIC_ALIASES.get(m, m)


def _norm3(x: float, y: float, z: float) -> float:
    return sqrt(x * x + y * y + z * z)


def _dot3(ax: float, ay: float, az: float, bx: float, by: float, bz: float) -> float:
    return ax * bx + ay * by + az * bz


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _clamp01(v: float) -> float:
    return _clamp(v, 0.0, 1.0)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _player_frame(frame: Dict[str, Any], player: str) -> Dict[str, Any] | None:
    for p in frame.get("players", []) or []:
        if str(p.get("name", "")) == player:
            return p
    return None


def _player_team(player: str, player_teams: Dict[str, Any]) -> int:
    try:
        t = int(player_teams.get(player, -1))
    except Exception:
        t = -1
    return t


def _own_goal_y(team: int) -> float:
    return -5120.0 if team == 0 else 5120.0


def _opp_goal_y(team: int) -> float:
    return 5120.0 if team == 0 else -5120.0


def _team_for_player_name(name: str, player_teams: Dict[str, Any], fallback_team: int) -> int:
    try:
        t = int(player_teams.get(name, fallback_team))
    except Exception:
        t = fallback_team
    return t if t in (0, 1) else fallback_team


def _player_ball_dist(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 99999.0
    b = frame.get("ball", {}) or {}
    return _norm3(
        _safe_float(p.get("x", 0.0)) - _safe_float(b.get("x", 0.0)),
        _safe_float(p.get("y", 0.0)) - _safe_float(b.get("y", 0.0)),
        _safe_float(p.get("z", 0.0)) - _safe_float(b.get("z", 0.0)),
    )


def _ball_speed(frame: Dict[str, Any]) -> float:
    b = frame.get("ball", {}) or {}
    return _norm3(_safe_float(b.get("vx", 0.0)), _safe_float(b.get("vy", 0.0)), _safe_float(b.get("vz", 0.0)))


def _player_speed(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 0.0
    return _norm3(_safe_float(p.get("vx", 0.0)), _safe_float(p.get("vy", 0.0)), _safe_float(p.get("vz", 0.0)))


def _rel_speed_player_ball(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 99999.0
    b = frame.get("ball", {}) or {}
    return _norm3(
        _safe_float(p.get("vx", 0.0)) - _safe_float(b.get("vx", 0.0)),
        _safe_float(p.get("vy", 0.0)) - _safe_float(b.get("vy", 0.0)),
        _safe_float(p.get("vz", 0.0)) - _safe_float(b.get("vz", 0.0)),
    )


def _nearest_opponent_dist_ball(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], tracked_team: int) -> float:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    best = 99999.0
    for op in frame.get("players", []) or []:
        name = str(op.get("name", ""))
        if name == player:
            continue
        if _team_for_player_name(name, player_teams, tracked_team) == tracked_team:
            continue
        d = _norm3(_safe_float(op.get("x", 0.0)) - bx, _safe_float(op.get("y", 0.0)) - by, _safe_float(op.get("z", 0.0)) - bz)
        if d < best:
            best = d
    return best


def _nearest_opponent_speed(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], tracked_team: int) -> float:
    pself = _player_frame(frame, player)
    if not pself:
        return 0.0
    sx = _safe_float(pself.get("x", 0.0))
    sy = _safe_float(pself.get("y", 0.0))
    sz = _safe_float(pself.get("z", 0.0))
    best_d = 99999.0
    best_speed = 0.0
    for op in frame.get("players", []) or []:
        name = str(op.get("name", ""))
        if name == player:
            continue
        if _team_for_player_name(name, player_teams, tracked_team) == tracked_team:
            continue
        d = _norm3(_safe_float(op.get("x", 0.0)) - sx, _safe_float(op.get("y", 0.0)) - sy, _safe_float(op.get("z", 0.0)) - sz)
        if d < best_d:
            best_d = d
            best_speed = _norm3(_safe_float(op.get("vx", 0.0)), _safe_float(op.get("vy", 0.0)), _safe_float(op.get("vz", 0.0)))
    return best_speed


def _best_team_ball_dist(frame: Dict[str, Any], player_teams: Dict[str, Any], team: int) -> float:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    best = 99999.0
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", ""))
        if _team_for_player_name(name, player_teams, team) != team:
            continue
        d = _norm3(_safe_float(pl.get("x", 0.0)) - bx, _safe_float(pl.get("y", 0.0)) - by, _safe_float(pl.get("z", 0.0)) - bz)
        if d < best:
            best = d
    return best


def _teammate_double_commit(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], tracked_team: int, tracked_d_pb: float) -> bool:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", ""))
        if name == player:
            continue
        if _team_for_player_name(name, player_teams, tracked_team) != tracked_team:
            continue
        d = _norm3(_safe_float(pl.get("x", 0.0)) - bx, _safe_float(pl.get("y", 0.0)) - by, _safe_float(pl.get("z", 0.0)) - bz)
        if d <= 850.0 and d <= tracked_d_pb + 120.0:
            return True
    return False


def _find_next_idx_by_time(times: List[float], idx: int, dt: float) -> int:
    t = times[idx] + max(0.0, dt)
    j = idx
    while j + 1 < len(times) and times[j] < t:
        j += 1
    return j


def _ball_forward_speed_to_opp(frame: Dict[str, Any], team: int) -> float:
    vy = _safe_float((frame.get("ball", {}) or {}).get("vy", 0.0))
    return vy if team == 0 else -vy


def _ball_toward_own_goal_fast(f0: Dict[str, Any], f1: Dict[str, Any], team: int) -> bool:
    b0 = f0.get("ball", {}) or {}
    b1 = f1.get("ball", {}) or {}
    y0 = _safe_float(b0.get("y", 0.0))
    y1 = _safe_float(b1.get("y", 0.0))
    vy1 = _safe_float(b1.get("vy", 0.0))
    toward_own = (team == 0 and y1 < y0 - 100.0 and vy1 <= -900.0) or (team == 1 and y1 > y0 + 100.0 and vy1 >= 900.0)
    center_lane = abs(_safe_float(b1.get("x", 0.0))) < 1800.0
    return bool(toward_own and center_lane)


def _ball_dir_flip(frame0: Dict[str, Any], frame1: Dict[str, Any]) -> bool:
    b0 = frame0.get("ball", {}) or {}
    b1 = frame1.get("ball", {}) or {}
    vx0 = _safe_float(b0.get("vx", 0.0))
    vy0 = _safe_float(b0.get("vy", 0.0))
    vz0 = _safe_float(b0.get("vz", 0.0))
    vx1 = _safe_float(b1.get("vx", 0.0))
    vy1 = _safe_float(b1.get("vy", 0.0))
    vz1 = _safe_float(b1.get("vz", 0.0))
    s0 = _norm3(vx0, vy0, vz0)
    s1 = _norm3(vx1, vy1, vz1)
    if s0 < 250.0 or s1 < 250.0:
        return False
    cos_th = _dot3(vx0, vy0, vz0, vx1, vy1, vz1) / max(1e-6, s0 * s1)
    return cos_th < -0.2


def _touch_confidence(frame0: Dict[str, Any], frame1: Dict[str, Any], p: Dict[str, Any]) -> float:
    b0 = frame0.get("ball", {}) or {}
    b1 = frame1.get("ball", {}) or {}
    px = _safe_float(p.get("x", 0.0))
    py = _safe_float(p.get("y", 0.0))
    pz = _safe_float(p.get("z", 0.0))
    bx = _safe_float(b0.get("x", 0.0))
    by = _safe_float(b0.get("y", 0.0))
    bz = _safe_float(b0.get("z", 0.0))
    d = _norm3(px - bx, py - by, pz - bz)
    if d > 260.0:
        return 0.0
    dvx = _safe_float(b1.get("vx", 0.0)) - _safe_float(b0.get("vx", 0.0))
    dvy = _safe_float(b1.get("vy", 0.0)) - _safe_float(b0.get("vy", 0.0))
    dvz = _safe_float(b1.get("vz", 0.0)) - _safe_float(b0.get("vz", 0.0))
    to_ball_x = bx - px
    to_ball_y = by - py
    to_ball_z = bz - pz
    to_mag = max(1e-6, _norm3(to_ball_x, to_ball_y, to_ball_z))
    dv_mag = _norm3(dvx, dvy, dvz)
    align = 0.0 if dv_mag < 1e-6 else _dot3(to_ball_x / to_mag, to_ball_y / to_mag, to_ball_z / to_mag, dvx / dv_mag, dvy / dv_mag, dvz / dv_mag)
    prox = _clamp01((260.0 - d) / 260.0)
    align01 = _clamp01((align + 1.0) * 0.5)
    return _clamp01(0.65 * prox + 0.35 * align01)


def _add_event(events: List[Dict[str, Any]], mechanic: str, t: float, score: float, reason: str) -> None:
    q = _clamp01(score)
    label = "good" if q >= 0.66 else ("bad" if q < 0.42 else "neutral")
    events.append(
        {
            "mechanic_id": mechanic,
            "short": MECH_SHORT.get(mechanic, mechanic[:4].upper()),
            "time": float(t),
            "quality_score": round(float(q), 4),
            "quality_label": label,
            "reason": reason,
        }
    )


def _closing_speed_toward_ball(frame: Dict[str, Any], player: str) -> float:
    p = _player_frame(frame, player)
    if not p:
        return 0.0
    b = frame.get("ball", {}) or {}
    tx = _safe_float(b.get("x", 0.0)) - _safe_float(p.get("x", 0.0))
    ty = _safe_float(b.get("y", 0.0)) - _safe_float(p.get("y", 0.0))
    tz = _safe_float(b.get("z", 0.0)) - _safe_float(p.get("z", 0.0))
    mag = max(1e-6, _norm3(tx, ty, tz))
    ux, uy, uz = tx / mag, ty / mag, tz / mag
    vx = _safe_float(p.get("vx", 0.0))
    vy = _safe_float(p.get("vy", 0.0))
    vz = _safe_float(p.get("vz", 0.0))
    return _dot3(vx, vy, vz, ux, uy, uz)


def _ball_center_slow(frame: Dict[str, Any]) -> bool:
    b = frame.get("ball", {}) or {}
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    dist = _norm3(bx, by, bz - 93.0)
    return dist <= KICKOFF_CENTER_MAX_DIST and _ball_speed(frame) <= KICKOFF_BALL_SPEED_MAX


def _first_touch_in_window(timeline: List[Dict[str, Any]], times: List[float], start_idx: int, end_t: float) -> Tuple[int, str, float]:
    pnames = [str(p.get("name", "")) for p in (timeline[start_idx].get("players", []) or [])]
    for i in range(start_idx, len(timeline) - 1):
        if times[i] > end_t:
            break
        fr = timeline[i]
        fr2 = timeline[min(i + 1, len(timeline) - 1)]
        best_player = ""
        best_conf = 0.0
        for pn in pnames:
            p = _player_frame(fr, pn)
            if not p:
                continue
            conf = _touch_confidence(fr, fr2, p)
            if conf > best_conf:
                best_conf = conf
                best_player = pn
        if best_player and best_conf >= 0.55:
            return i, best_player, times[i]
    return -1, "", 0.0


def _attempted_kickoff_before_touch(
    timeline: List[Dict[str, Any]],
    times: List[float],
    player: str,
    start_idx: int,
    touch_idx: int,
) -> bool:
    reached_proximity = False
    sustain = 0.0
    last_t = times[start_idx]
    for i in range(start_idx, max(start_idx + 1, touch_idx + 1)):
        fr = timeline[i]
        t = times[i]
        d = _player_ball_dist(fr, player)
        if d <= KICKOFF_ATTEMPT_DIST:
            reached_proximity = True
        cs = _closing_speed_toward_ball(fr, player)
        dt = max(0.0, t - last_t)
        if cs >= KICKOFF_ATTEMPT_CLOSING_SPEED:
            sustain += dt
        else:
            sustain = 0.0
        if reached_proximity and sustain >= KICKOFF_ATTEMPT_SUSTAIN_S:
            return True
        last_t = t
    return False


def _detect_kickoff_events(timeline: List[Dict[str, Any]], times: List[float], player_teams: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not timeline:
        return events
    i = 0
    last_kickoff_end_t = -999.0
    while i < len(timeline):
        fr = timeline[i]
        t = times[i]
        if t < last_kickoff_end_t:
            i += 1
            continue
        if not _ball_center_slow(fr):
            i += 1
            continue
        start_idx = i
        start_t = t
        end_t = min(times[-1], start_t + KICKOFF_WINDOW_TIMEOUT)
        touch_idx, touch_player, touch_t = _first_touch_in_window(timeline, times, start_idx, end_t)
        if touch_idx < 0:
            i += 1
            continue
        players = [str(p.get("name", "")) for p in (timeline[start_idx].get("players", []) or [])]
        attempts = {
            pn: _attempted_kickoff_before_touch(timeline, times, pn, start_idx, touch_idx)
            for pn in players
            if pn
        }
        if not any(attempts.values()):
            i = touch_idx + 1
            continue
        if (touch_t - start_t) > KICKOFF_TOUCH_MAX_S:
            i = touch_idx + 1
            continue
        if not attempts.get(touch_player, False):
            i = touch_idx + 1
            continue

        team = _team_for_player_name(touch_player, player_teams, 0)
        j_mid = _find_next_idx_by_time(times, touch_idx, 0.65)
        j_out = _find_next_idx_by_time(times, touch_idx, 1.20)
        fr_mid = timeline[j_mid]
        fr_out = timeline[j_out]
        our_mid = _best_team_ball_dist(fr_mid, player_teams, team)
        opp_mid = _best_team_ball_dist(fr_mid, player_teams, 1 - team)
        our_out = _best_team_ball_dist(fr_out, player_teams, team)
        opp_out = _best_team_ball_dist(fr_out, player_teams, 1 - team)
        win_possession = (our_out + 120.0 < opp_out) or (our_mid + 100.0 < opp_mid)
        safe_exit = not _ball_toward_own_goal_fast(timeline[touch_idx], fr_out, team)
        q = 0.35 + 0.4 * (1.0 if win_possession else 0.0) + 0.25 * (1.0 if safe_exit else 0.2)
        q = _clamp01(q)
        reason = "kickoff won with follow-up control" if win_possession else ("kickoff neutral but safe" if safe_exit else "kickoff lost into pressure")
        _add_event(events, "kickoff", touch_t, q, reason)
        events[-1]["player"] = touch_player
        events[-1]["kickoff_window_start"] = round(start_t, 3)
        events[-1]["kickoff_window_end"] = round(min(end_t, touch_t), 3)
        last_kickoff_end_t = touch_t
        i = touch_idx + 1
    return events


def _detect_mechanic_events(timeline: List[Dict[str, Any]], player: str, player_teams: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not timeline or not player:
        return []
    team = _player_team(player, player_teams or {})
    if team not in (0, 1):
        team = 0
    own_goal = _own_goal_y(team)
    opp_goal = _opp_goal_y(team)
    events: List[Dict[str, Any]] = []
    times = [_safe_float(fr.get("t", 0.0)) for fr in timeline]

    last_t_by_mech: Dict[str, float] = {m: -9999.0 for m in MECHANICS}
    cooldown = {
        "shadow_defense": 1.2,
        "challenge": 0.9,
        "fifty_fifty_control": 1.0,
        "aerial_offense": 1.8,
        "aerial_defense": 1.8,
        "flicking": 1.3,
        "carrying_dribbling": 1.0,
    }

    carry_active = False
    carry_start_idx = 0
    carry_min_opp_dist = 99999.0
    kickoff_events = _detect_kickoff_events(timeline, times, player_teams)
    events.extend(kickoff_events)
    for k in kickoff_events:
        last_t_by_mech["kickoff"] = max(last_t_by_mech["kickoff"], _safe_float(k.get("time", -9999.0)))

    for i, fr in enumerate(timeline):
        t = times[i]
        p = _player_frame(fr, player)
        if not p:
            continue
        b = fr.get("ball", {}) or {}
        py = _safe_float(p.get("y", 0.0))
        pz = _safe_float(p.get("z", 0.0))
        by = _safe_float(b.get("y", 0.0))
        bz = _safe_float(b.get("z", 0.0))
        d_pb = _player_ball_dist(fr, player)
        opp_db = _nearest_opponent_dist_ball(fr, player, player_teams, team)
        p_speed = _player_speed(fr, player)
        b_speed = _ball_speed(fr)
        attacking_half = (team == 0 and by > 200.0) or (team == 1 and by < -200.0)
        defending_half = (team == 0 and by < -300.0) or (team == 1 and by > 300.0)

        own_goal_dist_player = abs(py - own_goal)
        own_goal_dist_ball = abs(by - own_goal)
        goal_side = own_goal_dist_player < own_goal_dist_ball
        opp_has_control = opp_db + 120.0 < d_pb
        spacing_band = 500.0 <= d_pb <= 1500.0
        opp_speed = _nearest_opponent_speed(fr, player, player_teams, team)
        speed_match = abs(p_speed - opp_speed) < 650.0
        if defending_half and opp_has_control and goal_side and spacing_band and speed_match and (t - last_t_by_mech["shadow_defense"]) >= cooldown["shadow_defense"]:
            j = _find_next_idx_by_time(times, i, 1.0)
            fr2 = timeline[j]
            b2 = fr2.get("ball", {}) or {}
            bx = _safe_float(b.get("x", 0.0))
            bx2 = _safe_float(b2.get("x", 0.0))
            wide = abs(bx2) > abs(bx) + 220.0
            deny_shot_lane = not _ball_toward_own_goal_fast(fr, fr2, team)
            q = _clamp01(0.30 + 0.25 * (1.0 if goal_side else 0.0) + 0.20 * (1.0 if wide else 0.35) + 0.25 * (1.0 if deny_shot_lane else 0.2))
            _add_event(events, "shadow_defense", t, q, "goal-side shadow spacing and delay quality")
            last_t_by_mech["shadow_defense"] = t

        challenge_candidate = d_pb <= 900.0 and opp_db <= 900.0 and bz <= 320.0 and abs(d_pb - opp_db) <= 280.0
        if challenge_candidate and (t - last_t_by_mech["challenge"]) >= cooldown["challenge"]:
            j_touch = _find_next_idx_by_time(times, i, 0.35)
            j_mid = _find_next_idx_by_time(times, i, 0.60)
            j_out = _find_next_idx_by_time(times, i, 1.20)
            fr_touch = timeline[j_touch]
            fr_mid = timeline[j_mid]
            fr_out = timeline[j_out]
            p_touch = _player_frame(fr_touch, player) or p
            contact_like = _touch_confidence(fr, fr_touch, p_touch) >= 0.45 or _ball_dir_flip(fr, fr_touch)
            if not contact_like:
                continue
            our_mid = _best_team_ball_dist(fr_mid, player_teams, team)
            opp_mid = _best_team_ball_dist(fr_mid, player_teams, 1 - team)
            our_out = _best_team_ball_dist(fr_out, player_teams, team)
            opp_out = _best_team_ball_dist(fr_out, player_teams, 1 - team)
            opp_had_control = opp_db + 80.0 < d_pb
            win_possession = (our_out + 120.0 < opp_out) or (our_mid + 120.0 < opp_mid)
            force_bad_touch = opp_had_control and ((opp_mid - opp_db) > 140.0 or (our_mid + 120.0 < opp_mid))
            easy_counter = _ball_toward_own_goal_fast(fr, fr_out, team) and (opp_out + 180.0 < our_out)
            double_commit = _teammate_double_commit(fr, player, player_teams, team, d_pb)
            d_touch = _player_ball_dist(fr_touch, player)
            close_gain = _clamp01((d_pb - d_touch) / max(1.0, d_pb))
            success = (win_possession or force_bad_touch) and (not easy_counter)
            q = 0.32 + 0.40 * (1.0 if success else 0.0) + 0.12 * (1.0 if win_possession else 0.0) + 0.10 * (1.0 if force_bad_touch else 0.0)
            q += 0.10 * close_gain
            if easy_counter:
                q -= 0.40
            if double_commit:
                q -= 0.15
            if (opp_out + 150.0 < our_out) and (d_touch > d_pb):
                q -= 0.10
            q = _clamp01(q)
            if easy_counter:
                reason = "challenge conceded easy counter"
            elif win_possession:
                reason = "won possession after challenge"
            elif force_bad_touch:
                reason = "forced weak opponent touch"
            else:
                reason = "challenge failed to improve outcome"
            _add_event(events, "challenge", t, q, reason)
            last_t_by_mech["challenge"] = t

        if d_pb < 300.0 and opp_db < 300.0 and bz < 260.0 and (t - last_t_by_mech["fifty_fifty_control"]) >= cooldown["fifty_fifty_control"]:
            j = _find_next_idx_by_time(times, i, 0.20)
            k = _find_next_idx_by_time(times, i, 0.80)
            frj = timeline[j]
            frk = timeline[k]
            impact = _ball_dir_flip(fr, frj) or abs(_ball_speed(frj) - b_speed) > 250.0
            if impact:
                our_k = _best_team_ball_dist(frk, player_teams, team)
                opp_k = _best_team_ball_dist(frk, player_teams, 1 - team)
                b_k = frk.get("ball", {}) or {}
                by_k = _safe_float(b_k.get("y", 0.0))
                own_d = abs(by_k - own_goal)
                opp_d = abs(by_k - opp_goal)
                if our_k + 100.0 < opp_k and (opp_d < own_d or own_d > 2600.0):
                    q = 0.76
                    reason = "50/50 won to team control"
                elif opp_k + 100.0 < our_k and own_d < 2500.0:
                    q = 0.24
                    reason = "50/50 lost into danger"
                else:
                    q = 0.50
                    reason = "50/50 neutral outcome"
                _add_event(events, "fifty_fifty_control", t, q, reason)
                last_t_by_mech["fifty_fifty_control"] = t

        if attacking_half and pz > 150.0 and bz > 300.0 and d_pb < 950.0 and (t - last_t_by_mech["aerial_offense"]) >= cooldown["aerial_offense"]:
            j = _find_next_idx_by_time(times, i, 0.90)
            fr2 = timeline[j]
            b2 = fr2.get("ball", {}) or {}
            by2 = _safe_float(b2.get("y", 0.0))
            toward_opp_goal = abs(by2 - opp_goal) < abs(by - opp_goal)
            our_out = _best_team_ball_dist(fr2, player_teams, team)
            opp_out = _best_team_ball_dist(fr2, player_teams, 1 - team)
            retain = our_out <= opp_out + 60.0
            q = _clamp01(0.35 + 0.30 * (1.0 if toward_opp_goal else 0.25) + 0.25 * (1.0 if retain else 0.3) + 0.10 * _clamp01(p_speed / 2100.0))
            reason = "air touch created attacking value" if q >= 0.5 else "aerial touch gave up pressure"
            _add_event(events, "aerial_offense", t, q, reason)
            last_t_by_mech["aerial_offense"] = t

        threat_zone = abs(by - own_goal) < 2600.0
        if defending_half and threat_zone and pz > 150.0 and bz > 260.0 and d_pb < 1200.0 and (t - last_t_by_mech["aerial_defense"]) >= cooldown["aerial_defense"]:
            j = _find_next_idx_by_time(times, i, 1.00)
            fr2 = timeline[j]
            b2 = fr2.get("ball", {}) or {}
            by2 = _safe_float(b2.get("y", 0.0))
            bx = _safe_float(b.get("x", 0.0))
            bx2 = _safe_float(b2.get("x", 0.0))
            away = abs(by2 - own_goal) > abs(by - own_goal)
            center_clear = abs(bx2) > abs(bx) + 180.0
            double_commit = _teammate_double_commit(fr, player, player_teams, team, d_pb)
            q = 0.35 + 0.35 * (1.0 if away else 0.2) + 0.20 * (1.0 if center_clear else 0.35) + 0.10 * (0.2 if double_commit else 1.0)
            _add_event(events, "aerial_defense", t, _clamp01(q), "aerial defensive clear quality")
            last_t_by_mech["aerial_defense"] = t

        rel_v = _rel_speed_player_ball(fr, player)
        jump = int(_safe_float(p.get("jump", 0.0)))
        djump = int(_safe_float(p.get("double_jump", 0.0)))
        carry_like = d_pb <= 200.0 and bz < 250.0 and rel_v < 700.0
        if carry_like and (jump > 0 or djump > 0) and (t - last_t_by_mech["flicking"]) >= cooldown["flicking"]:
            j = _find_next_idx_by_time(times, i, 0.35)
            fr2 = timeline[j]
            b2 = fr2.get("ball", {}) or {}
            bz2 = _safe_float(b2.get("z", 0.0))
            up_spike = (bz2 - bz) > 120.0 or (_safe_float(b2.get("vz", 0.0)) - _safe_float(b.get("vz", 0.0))) > 220.0
            fwd0 = _ball_forward_speed_to_opp(fr, team)
            fwd1 = _ball_forward_speed_to_opp(fr2, team)
            forward_spike = (fwd1 - fwd0) > 260.0
            power = _ball_speed(fr2) > b_speed + 300.0
            if up_spike and forward_spike:
                q = _clamp01(0.35 + 0.25 * (1.0 if power else 0.4) + 0.25 * _clamp01((fwd1 - fwd0) / 900.0) + 0.15 * _clamp01((bz2 - bz) / 240.0))
                reason = "flick generated threatening ball launch" if q >= 0.5 else "flick lacked threat or power"
                _add_event(events, "flicking", t, q, reason)
                last_t_by_mech["flicking"] = t

        in_carry_state = d_pb <= 200.0 and bz < 250.0 and rel_v < 700.0
        if in_carry_state:
            if not carry_active:
                carry_active = True
                carry_start_idx = i
                carry_min_opp_dist = opp_db
            else:
                carry_min_opp_dist = min(carry_min_opp_dist, opp_db)
        else:
            if carry_active:
                t0 = times[carry_start_idx]
                duration = max(0.0, t - t0)
                if duration >= 1.0 and (t - last_t_by_mech["carrying_dribbling"]) >= cooldown["carrying_dribbling"]:
                    end_idx = i
                    j = _find_next_idx_by_time(times, end_idx, 0.80)
                    fr_end = timeline[end_idx]
                    fr2 = timeline[j]
                    our_end = _best_team_ball_dist(fr_end, player_teams, team)
                    opp_end = _best_team_ball_dist(fr_end, player_teams, 1 - team)
                    our_after = _best_team_ball_dist(fr2, player_teams, team)
                    opp_after = _best_team_ball_dist(fr2, player_teams, 1 - team)
                    pressure_hold = carry_min_opp_dist < 900.0 and our_after <= opp_after + 80.0
                    immediate_loss = opp_after + 120.0 < our_after
                    b_end = fr_end.get("ball", {}) or {}
                    b_after = fr2.get("ball", {}) or {}
                    created_play = abs(_safe_float(b_after.get("y", 0.0)) - opp_goal) < abs(_safe_float(b_end.get("y", 0.0)) - opp_goal)
                    q = 0.35 + 0.25 * _clamp01(duration / 2.4) + 0.20 * (1.0 if pressure_hold else 0.35) + 0.20 * (1.0 if created_play else 0.30)
                    if immediate_loss:
                        q -= 0.30
                    q = _clamp01(q)
                    reason = "carry kept control and progressed play" if q >= 0.5 else "carry lost value before creating threat"
                    _add_event(events, "carrying_dribbling", t0, q, reason)
                    last_t_by_mech["carrying_dribbling"] = t
                carry_active = False
                carry_start_idx = 0
                carry_min_opp_dist = 99999.0

    return events


def _grade_one(mechanic: str, evs: List[Dict[str, Any]]) -> Dict[str, Any]:
    qs = [_safe_float(e.get("quality_score", 0.5), 0.5) for e in evs]
    n = len(qs)
    if n == 0:
        return {
            "mechanic_id": mechanic,
            "title": MECH_TITLE.get(mechanic, mechanic),
            "score_0_100": 50.0,
            "confidence_0_1": 0.2,
            "event_count": 0,
            "good_count": 0,
            "neutral_count": 0,
            "bad_count": 0,
            "subscores": {"mean_quality": 0.5, "stability": 0.0},
            "evidence_events": [],
            "recommendation_hint": "insufficient_sample",
        }
    m = _clamp01(mean(qs))
    sigma = pstdev(qs) if n >= 2 else 0.0
    stability = _clamp01(1.0 - sigma / 0.35)
    score = _clamp(100.0 * (0.15 + 0.85 * m), 0.0, 100.0)
    conf_n = 1.0 - exp(-float(n) / 6.0)
    conf = _clamp(0.2 + 0.78 * conf_n * (0.7 + 0.3 * stability), 0.2, 0.98)
    good = sum(1 for q in qs if q >= 0.66)
    bad = sum(1 for q in qs if q < 0.42)
    neutral = max(0, n - good - bad)
    ev = sorted(evs, key=lambda x: _safe_float(x.get("quality_score", 0.5), 0.5))
    evidence = [
        {"time": round(_safe_float(e.get("time", 0.0)), 3), "quality": round(_safe_float(e.get("quality_score", 0.0)), 3), "reason": str(e.get("reason", ""))}
        for e in (ev[:2] + (ev[-1:] if len(ev) > 2 else []))
    ]
    hint = "good_progress" if score >= 75 else ("priority_improvement" if score < 60 else "keep_training")
    return {
        "mechanic_id": mechanic,
        "title": MECH_TITLE.get(mechanic, mechanic),
        "score_0_100": round(score, 2),
        "confidence_0_1": round(conf, 3),
        "event_count": n,
        "good_count": good,
        "neutral_count": neutral,
        "bad_count": bad,
        "subscores": {"mean_quality": round(m, 3), "stability": round(stability, 3)},
        "evidence_events": evidence,
        "recommendation_hint": hint,
    }


def grade_game_mechanics(timeline: List[Dict[str, Any]], player: str, player_teams: Dict[str, Any] | None = None) -> Dict[str, Any]:
    mechanic_events = _detect_mechanic_events(timeline or [], str(player or ""), player_teams or {})
    grades: List[Dict[str, Any]] = []
    for m in MECHANICS:
        evs = [e for e in mechanic_events if str(e.get("mechanic_id", "")) == m]
        grades.append(_grade_one(m, evs))
    grades.sort(key=lambda x: float(x.get("score_0_100", 50.0)))
    overall = mean([float(g.get("score_0_100", 50.0)) for g in grades]) if grades else 50.0
    return {
        "grading_version": "mechanic_v2_pdf_defs",
        "player": str(player or ""),
        "overall_mechanics_score": round(float(overall), 2),
        "sample_size_meta": {"total_frames": len(timeline or []), "event_count": len(mechanic_events)},
        "game_mechanics": grades,
        "mechanic_events": mechanic_events,
    }


def summarize_mechanic_scores(payload: Dict[str, Any]) -> Dict[str, Any]:
    out_scores: Dict[str, float] = {}
    out_conf: Dict[str, float] = {}
    for g in payload.get("game_mechanics", []) or []:
        mid = _canonical_mid(str(g.get("mechanic_id", "")))
        out_scores[mid] = float(g.get("score_0_100", 50.0))
        out_conf[mid] = float(g.get("confidence_0_1", 0.2))
    return {
        "overall_mechanics_score": float(payload.get("overall_mechanics_score", 50.0)),
        "mechanic_scores": out_scores,
        "mechanic_confidence": out_conf,
        "mechanic_grading_version": str(payload.get("grading_version", "mechanic_v2_pdf_defs")),
    }


def _nearest_frame_idx(timeline: List[Dict[str, Any]], t: float) -> int:
    if not timeline:
        return 0
    best_i = 0
    best_dt = abs(_safe_float(timeline[0].get("t", 0.0)) - float(t))
    for i in range(1, len(timeline)):
        dt = abs(_safe_float(timeline[i].get("t", 0.0)) - float(t))
        if dt < best_dt:
            best_dt = dt
            best_i = i
    return best_i


def explain_mechanic_event(
    timeline: List[Dict[str, Any]],
    player: str,
    player_teams: Dict[str, Any] | None,
    event: Dict[str, Any],
) -> Dict[str, Any]:
    timeline = timeline or []
    if not timeline:
        return {
            "ok": False,
            "error": "empty_timeline",
            "deterministic_summary": "No timeline available for explanation.",
            "thresholds": [],
            "observed": {},
            "breakdown": [],
        }
    mid = _canonical_mid(str(event.get("mechanic_id", "") or ""))
    t = _safe_float(event.get("time", 0.0))
    i = _nearest_frame_idx(timeline, t)
    fr = timeline[i]
    team = _player_team(player, player_teams or {})
    if team not in (0, 1):
        team = 0
    own_goal = _own_goal_y(team)
    opp_goal = _opp_goal_y(team)
    p = _player_frame(fr, player) or {}
    b = fr.get("ball", {}) or {}
    j = _find_next_idx_by_time([_safe_float(x.get("t", 0.0)) for x in timeline], i, 1.0)
    fr2 = timeline[j]

    px = _safe_float(p.get("x", 0.0))
    py = _safe_float(p.get("y", 0.0))
    pz = _safe_float(p.get("z", 0.0))
    bx = _safe_float(b.get("x", 0.0))
    by = _safe_float(b.get("y", 0.0))
    bz = _safe_float(b.get("z", 0.0))
    d_pb = _player_ball_dist(fr, player)
    opp_db = _nearest_opponent_dist_ball(fr, player, player_teams or {}, team)
    p_speed = _player_speed(fr, player)
    b_speed = _ball_speed(fr)
    q = _safe_float(event.get("quality_score", 0.5))

    thresholds: List[Dict[str, Any]] = []
    observed: Dict[str, Any] = {
        "frame_time_s": round(_safe_float(fr.get("t", t)), 3),
        "player_ball_distance": round(d_pb, 2),
        "nearest_opp_ball_distance": round(opp_db, 2),
        "player_speed": round(p_speed, 2),
        "ball_speed": round(b_speed, 2),
        "player_pos": {"x": round(px, 1), "y": round(py, 1), "z": round(pz, 1)},
        "ball_pos": {"x": round(bx, 1), "y": round(by, 1), "z": round(bz, 1)},
    }
    breakdown: List[Dict[str, Any]] = []

    def add_thr(name: str, cond: str, val: Any, ok: bool) -> None:
        thresholds.append({"name": name, "condition": cond, "value": val, "met": bool(ok)})

    role = "neutral"
    if mid in {"shadow_defense", "aerial_defense", "challenge"}:
        role = "defense"
    elif mid in {"aerial_offense", "flicking", "carrying_dribbling"}:
        role = "offense"

    pressure_proxy = "high" if (d_pb < 900 and opp_db < 1200) else ("medium" if d_pb < 1700 else "low")
    distance_band = "close" if d_pb < 600 else ("mid" if d_pb < 1800 else "far")
    actionable_hints: List[str] = []

    if mid == "kickoff":
        start_t = _safe_float(event.get("kickoff_window_start", t))
        touch_dt = max(0.0, t - start_t)
        add_thr("kickoff_entry_time", "first touch arrives within kickoff window", round(touch_dt, 3), touch_dt <= KICKOFF_TOUCH_MAX_S)
        add_thr("attempt_requirements", "approach reached contest speed and range before touch", True, True)
        breakdown = [
            {"component": "first_touch_execution", "weight": 0.4},
            {"component": "post_touch_control", "weight": 0.4},
            {"component": "defensive_safety", "weight": 0.2},
        ]
        actionable_hints = [
            "Accelerate into the ball early enough to arrive in your first touch window.",
            "If you cannot win cleanly, angle your touch so the opponent cannot launch an instant counter.",
        ]
    elif mid == "challenge":
        fr_out = fr2
        our_out = _best_team_ball_dist(fr_out, player_teams or {}, team)
        opp_out = _best_team_ball_dist(fr_out, player_teams or {}, 1 - team)
        easy_counter = _ball_toward_own_goal_fast(fr, fr_out, team) and (opp_out + 180.0 < our_out)
        win_poss = our_out + 120.0 < opp_out
        add_thr("contest_proximity", "player and opponent both within challenge range", {"you": round(d_pb, 1), "opp": round(opp_db, 1)}, d_pb <= 900 and opp_db <= 900)
        add_thr("possession_outcome", "team gains first access after challenge", round(opp_out - our_out, 1), win_poss)
        add_thr("counterattack_risk", "no easy counter toward own net", easy_counter, not easy_counter)
        breakdown = [
            {"component": "possession_or_pressure_outcome", "weight": 0.5},
            {"component": "counterattack_safety", "weight": 0.4},
            {"component": "entry_execution", "weight": 0.1},
        ]
        actionable_hints = [
            "Challenge when you can still recover goal-side if the ball slips through.",
            "If you cannot win cleanly, angle contact so opponent loses control instead of breaking out.",
        ]
    elif mid == "fifty_fifty_control":
        our_out = _best_team_ball_dist(fr2, player_teams or {}, team)
        opp_out = _best_team_ball_dist(fr2, player_teams or {}, 1 - team)
        add_thr("simultaneous_contest", "both players in contact range", {"you": round(d_pb, 1), "opp": round(opp_db, 1)}, d_pb < 300 and opp_db < 300)
        add_thr("post_5050_access", "team exits with equal or better access", round(opp_out - our_out, 1), our_out <= opp_out + 80.0)
        breakdown = [
            {"component": "outcome_direction", "weight": 0.4},
            {"component": "followup_access", "weight": 0.35},
            {"component": "contact_quality_proxy", "weight": 0.25},
        ]
        actionable_hints = [
            "Drive through the center of the ball so the outcome stays neutral or favorable.",
            "Plan your landing to reach the next touch before the opponent.",
        ]
    elif mid == "aerial_offense":
        b2 = fr2.get("ball", {}) or {}
        by2 = _safe_float(b2.get("y", 0.0))
        toward_opp = abs(by2 - opp_goal) < abs(by - opp_goal)
        add_thr("airborne_setup", "player and ball are airborne in attack", {"player_z": round(pz, 1), "ball_z": round(bz, 1)}, pz > 150 and bz > 300)
        add_thr("threat_direction", "touch moves ball toward opponent goal", round(abs(by - opp_goal) - abs(by2 - opp_goal), 1), toward_opp)
        breakdown = [
            {"component": "attacking_touch_quality", "weight": 0.45},
            {"component": "followup_possession", "weight": 0.35},
            {"component": "execution_speed", "weight": 0.2},
        ]
        actionable_hints = [
            "Meet the ball earlier in the air so your touch has forward intent, not just contact.",
            "Recover quickly after the hit so your team keeps the next play.",
        ]
    elif mid == "aerial_defense":
        b2 = fr2.get("ball", {}) or {}
        by2 = _safe_float(b2.get("y", 0.0))
        away = abs(by2 - own_goal) > abs(by - own_goal)
        add_thr("defensive_air_context", "airborne defensive contest", {"player_z": round(pz, 1), "ball_z": round(bz, 1)}, pz > 150 and bz > 260)
        add_thr("clear_direction", "touch sends ball away from own net", round(abs(by2 - own_goal) - abs(by - own_goal), 1), away)
        breakdown = [
            {"component": "danger_reduction", "weight": 0.5},
            {"component": "center_lane_avoidance", "weight": 0.3},
            {"component": "recovery_and_spacing", "weight": 0.2},
        ]
        actionable_hints = [
            "Prioritize clears that remove danger first, then look for distance.",
            "Avoid centering the ball after the save; use side lanes when possible.",
        ]
    elif mid == "shadow_defense":
        goal_side = abs(py - own_goal) < abs(by - own_goal)
        add_thr("goal_side", "stay between ball and own net", round(abs(by - own_goal) - abs(py - own_goal), 1), goal_side)
        add_thr("distance_window", "controlled shadow spacing (500-1500)", round(d_pb, 1), 500 <= d_pb <= 1500)
        breakdown = [
            {"component": "goal_side_discipline", "weight": 0.45},
            {"component": "spacing_control", "weight": 0.35},
            {"component": "shot_delay_effect", "weight": 0.2},
        ]
        actionable_hints = [
            "Keep enough spacing to react to flicks without giving a free shot lane.",
            "Match attacker pace and wait for the safe challenge window.",
        ]
    elif mid == "flicking":
        b2 = fr2.get("ball", {}) or {}
        vz_gain = _safe_float(b2.get("vz", 0.0)) - _safe_float(b.get("vz", 0.0))
        fwd_gain = _ball_forward_speed_to_opp(fr2, team) - _ball_forward_speed_to_opp(fr, team)
        add_thr("dribble_control", "ball controlled near car before flick", {"distance": round(d_pb, 1), "ball_z": round(bz, 1)}, d_pb <= 200 and bz < 250)
        add_thr("launch_spike", "upward and forward velocity increase", {"up_gain": round(vz_gain, 1), "forward_gain": round(fwd_gain, 1)}, vz_gain > 200 and fwd_gain > 240)
        breakdown = [
            {"component": "launch_power", "weight": 0.4},
            {"component": "threat_direction", "weight": 0.35},
            {"component": "setup_control", "weight": 0.25},
        ]
        actionable_hints = [
            "Stabilize the dribble first, then flick with a sharper forward release.",
            "Use flick timing when the defender commits so the touch creates immediate threat.",
        ]
    elif mid == "carrying_dribbling":
        add_thr("carry_state", "close, low, controlled carry state", {"distance": round(d_pb, 1), "ball_z": round(bz, 1), "relative_speed": round(_rel_speed_player_ball(fr, player), 1)}, d_pb <= 200 and bz < 250)
        breakdown = [
            {"component": "control_duration", "weight": 0.35},
            {"component": "pressure_retention", "weight": 0.35},
            {"component": "transition_to_threat", "weight": 0.3},
        ]
        actionable_hints = [
            "Keep the ball close enough to react before the first challenge arrives.",
            "Transition carry into a flick, pass, or shot before pressure closes space.",
        ]
    else:
        breakdown = [{"component": "quality_score", "weight": 1.0}]
        actionable_hints = ["Review approach timing and spacing before committing."]

    summary = (
        f"{MECH_TITLE.get(mid, mid)} scored {round(q * 100.0, 1)}/100 "
        f"({str(event.get('quality_label', 'neutral'))}). "
        f"{sum(1 for x in thresholds if x.get('met'))}/{len(thresholds)} trigger checks matched."
    )
    confidence_note = "Confidence is higher when outcome and safety checks point in the same direction."
    return {
        "ok": True,
        "mechanic_id": mid,
        "title": MECH_TITLE.get(mid, mid),
        "short": str(event.get("short", MECH_SHORT.get(mid, "MECH"))),
        "event_time_s": round(t, 3),
        "quality_score_0_1": round(q, 4),
        "quality_score_0_100": round(q * 100.0, 2),
        "quality_label": str(event.get("quality_label", "neutral")),
        "reason": str(event.get("reason", "")),
        "thresholds": thresholds,
        "observed": observed,
        "breakdown": breakdown,
        "coaching_context": {
            "role": role,
            "pressure_proxy": pressure_proxy,
            "distance_band": distance_band,
        },
        "actionable_hints": actionable_hints[:2],
        "confidence_note": confidence_note,
        "deterministic_summary": summary,
    }
