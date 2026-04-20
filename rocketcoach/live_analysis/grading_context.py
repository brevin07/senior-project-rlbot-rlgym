from __future__ import annotations

from math import sqrt
from typing import Any, Dict, List


OWN_GOAL_Y = {0: -5120.0, 1: 5120.0}
OPP_GOAL_Y = {0: 5120.0, 1: -5120.0}


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def clamp01(v: float) -> float:
    return clamp(v, 0.0, 1.0)


def norm3(x: float, y: float, z: float) -> float:
    return sqrt(x * x + y * y + z * z)


def player_frame(frame: Dict[str, Any], player: str) -> Dict[str, Any] | None:
    for p in frame.get("players", []) or []:
        if str(p.get("name", "")) == str(player or ""):
            return p
    return None


def team_for_player_name(name: str, player_teams: Dict[str, Any], fallback_team: int) -> int:
    try:
        t = int(player_teams.get(name, fallback_team))
    except Exception:
        t = fallback_team
    return t if t in (0, 1) else fallback_team


def infer_gamemode(frame: Dict[str, Any], player_teams: Dict[str, Any], player: str) -> str:
    p = player_frame(frame, player)
    fallback_team = 0
    if p:
        fallback_team = team_for_player_name(str(p.get("name", "")), player_teams or {}, 0)
    team_counts = {0: 0, 1: 0}
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", "") or "")
        team = team_for_player_name(name, player_teams or {}, fallback_team)
        if team in (0, 1):
            team_counts[team] += 1
    max_per_team = max(team_counts.values()) if team_counts else 1
    if max_per_team <= 1:
        return "1v1"
    if max_per_team == 2:
        return "2v2"
    return "3v3"


def rank_band(rank_tier: str) -> str:
    value = str(rank_tier or "").strip().lower()
    if any(x in value for x in ("bronze", "silver")):
        return "low"
    if any(x in value for x in ("gold", "plat")):
        return "mid"
    if any(x in value for x in ("diamond", "champ")):
        return "high"
    if any(x in value for x in ("grand", "gc", "ssl", "supersonic")):
        return "elite"
    return "mid"


def pressure_level(player_ball_dist: float, nearest_opp_ball_dist: float) -> str:
    if player_ball_dist < 700.0 and nearest_opp_ball_dist < 900.0:
        return "high"
    if player_ball_dist < 1400.0 and nearest_opp_ball_dist < 1400.0:
        return "medium"
    return "low"


def nearest_teammate_dist(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], team: int) -> float:
    me = player_frame(frame, player)
    if not me:
        return 99999.0
    mx = safe_float(me.get("x", 0.0))
    my = safe_float(me.get("y", 0.0))
    mz = safe_float(me.get("z", 0.0))
    best = 99999.0
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", "") or "")
        if name == player:
            continue
        if team_for_player_name(name, player_teams or {}, team) != team:
            continue
        d = norm3(safe_float(pl.get("x", 0.0)) - mx, safe_float(pl.get("y", 0.0)) - my, safe_float(pl.get("z", 0.0)) - mz)
        if d < best:
            best = d
    return best


def coverage_back_count(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], team: int) -> int:
    me = player_frame(frame, player)
    if not me:
        return 0
    my = safe_float(me.get("y", 0.0))
    count = 0
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", "") or "")
        if name == player:
            continue
        if team_for_player_name(name, player_teams or {}, team) != team:
            continue
        py = safe_float(pl.get("y", 0.0))
        if (team == 0 and py < my - 250.0) or (team == 1 and py > my + 250.0):
            count += 1
    return count


def ball_danger_score(frame: Dict[str, Any], team: int) -> float:
    ball = frame.get("ball", {}) or {}
    by = safe_float(ball.get("y", 0.0))
    bx = safe_float(ball.get("x", 0.0))
    vy = safe_float(ball.get("vy", 0.0))
    own_goal_y = OWN_GOAL_Y.get(team, -5120.0)
    goal_dist = abs(by - own_goal_y)
    centrality = 1.0 - clamp01(abs(bx) / 3000.0)
    distance_pressure = 1.0 - clamp01(goal_dist / 5200.0)
    toward_own = clamp01(((-vy) if team == 0 else vy) / 2500.0)
    return round(clamp01(0.45 * distance_pressure + 0.30 * centrality + 0.25 * toward_own), 4)


def possession_score(frame: Dict[str, Any], player_teams: Dict[str, Any], team: int) -> float:
    ball = frame.get("ball", {}) or {}
    bx = safe_float(ball.get("x", 0.0))
    by = safe_float(ball.get("y", 0.0))
    bz = safe_float(ball.get("z", 0.0))
    our_best = 99999.0
    opp_best = 99999.0
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", "") or "")
        d = norm3(safe_float(pl.get("x", 0.0)) - bx, safe_float(pl.get("y", 0.0)) - by, safe_float(pl.get("z", 0.0)) - bz)
        if team_for_player_name(name, player_teams or {}, team) == team:
            our_best = min(our_best, d)
        else:
            opp_best = min(opp_best, d)
    if our_best >= 99999.0 or opp_best >= 99999.0:
        return 0.5
    diff = opp_best - our_best
    return round(clamp01(0.5 + diff / 2400.0), 4)


def recovery_ready_score(frame: Dict[str, Any], player: str) -> float:
    me = player_frame(frame, player)
    if not me:
        return 0.0
    vz = abs(safe_float(me.get("vz", 0.0)))
    pz = safe_float(me.get("z", 0.0))
    boost = clamp01(safe_float(me.get("boost", 0.0)) / 100.0)
    grounded = 1.0 if pz < 120.0 else max(0.0, 1.0 - (pz - 120.0) / 500.0)
    vertical_control = 1.0 - clamp01(vz / 1200.0)
    return round(clamp01(0.45 * grounded + 0.30 * vertical_control + 0.25 * boost), 4)


def last_man_back(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], team: int) -> bool:
    me = player_frame(frame, player)
    if not me:
        return False
    my = safe_float(me.get("y", 0.0))
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", "") or "")
        if name == player:
            continue
        if team_for_player_name(name, player_teams or {}, team) != team:
            continue
        py = safe_float(pl.get("y", 0.0))
        if (team == 0 and py < my - 80.0) or (team == 1 and py > my + 80.0):
            return False
    return True


def frame_context(frame: Dict[str, Any], player: str, player_teams: Dict[str, Any], fallback_team: int = 0) -> Dict[str, Any]:
    me = player_frame(frame, player)
    team = fallback_team
    if me:
        team = team_for_player_name(player, player_teams or {}, fallback_team)
    ball = frame.get("ball", {}) or {}
    bx = safe_float(ball.get("x", 0.0))
    by = safe_float(ball.get("y", 0.0))
    bz = safe_float(ball.get("z", 0.0))
    player_ball_dist = 99999.0
    nearest_opp_ball_dist = 99999.0
    if me:
        player_ball_dist = norm3(safe_float(me.get("x", 0.0)) - bx, safe_float(me.get("y", 0.0)) - by, safe_float(me.get("z", 0.0)) - bz)
    for pl in frame.get("players", []) or []:
        name = str(pl.get("name", "") or "")
        if name == player:
            continue
        if team_for_player_name(name, player_teams or {}, team) == team:
            continue
        nearest_opp_ball_dist = min(
            nearest_opp_ball_dist,
            norm3(safe_float(pl.get("x", 0.0)) - bx, safe_float(pl.get("y", 0.0)) - by, safe_float(pl.get("z", 0.0)) - bz),
        )
    coverage = coverage_back_count(frame, player, player_teams or {}, team)
    teammate_gap = nearest_teammate_dist(frame, player, player_teams or {}, team)
    gamemode = infer_gamemode(frame, player_teams or {}, player)
    return {
        "team": team,
        "gamemode": gamemode,
        "pressure_level": pressure_level(player_ball_dist, nearest_opp_ball_dist),
        "ball_danger_0_1": ball_danger_score(frame, team),
        "possession_score_0_1": possession_score(frame, player_teams or {}, team),
        "recovery_ready_0_1": recovery_ready_score(frame, player),
        "last_man": last_man_back(frame, player, player_teams or {}, team),
        "coverage_back_count": coverage,
        "support_available": coverage > 0,
        "nearest_teammate_dist": round(teammate_gap, 2) if teammate_gap < 99999.0 else None,
        "player_ball_distance": round(player_ball_dist, 2) if player_ball_dist < 99999.0 else None,
        "nearest_opp_ball_distance": round(nearest_opp_ball_dist, 2) if nearest_opp_ball_dist < 99999.0 else None,
    }


def summarize_event_window(
    timeline: List[Dict[str, Any]],
    times: List[float],
    idx: int,
    player: str,
    player_teams: Dict[str, Any],
    *,
    pre_dt: float = 0.35,
    post_dt: float = 1.0,
) -> Dict[str, Any]:
    if not timeline:
        return {}
    idx = max(0, min(idx, len(timeline) - 1))
    t0 = safe_float(times[idx] if idx < len(times) else timeline[idx].get("t", 0.0))
    pre_idx = idx
    while pre_idx > 0 and safe_float(times[pre_idx]) > t0 - pre_dt:
        pre_idx -= 1
    post_idx = idx
    while post_idx + 1 < len(timeline) and safe_float(times[post_idx]) < t0 + post_dt:
        post_idx += 1
    pre_ctx = frame_context(timeline[pre_idx], player, player_teams or {})
    now_ctx = frame_context(timeline[idx], player, player_teams or {})
    post_ctx = frame_context(timeline[post_idx], player, player_teams or {})
    return {
        "pre_index": pre_idx,
        "post_index": post_idx,
        "pre_time_s": round(safe_float(times[pre_idx]), 3),
        "time_s": round(t0, 3),
        "post_time_s": round(safe_float(times[post_idx]), 3),
        "pre": pre_ctx,
        "current": now_ctx,
        "post": post_ctx,
        "danger_delta": round(safe_float(post_ctx.get("ball_danger_0_1", 0.0)) - safe_float(now_ctx.get("ball_danger_0_1", 0.0)), 4),
        "possession_delta": round(safe_float(post_ctx.get("possession_score_0_1", 0.0)) - safe_float(now_ctx.get("possession_score_0_1", 0.0)), 4),
        "recovery_delta": round(safe_float(post_ctx.get("recovery_ready_0_1", 0.0)) - safe_float(now_ctx.get("recovery_ready_0_1", 0.0)), 4),
    }
