from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rocketcoach.live_analysis.mechanic_grader import grade_game_mechanics


def _player(name: str, x: float, y: float, z: float, vx: float, vy: float, vz: float = 0.0, boost: float = 33.0) -> dict:
    return {
        "name": name,
        "x": x,
        "y": y,
        "z": z,
        "vx": vx,
        "vy": vy,
        "vz": vz,
        "boost": boost,
        "throttle": 1.0,
        "steer": 0.0,
        "handbrake": 0,
        "jump": 0,
        "double_jump": 0,
    }


def _mechanic_ids(payload: dict) -> list[str]:
    return [str(event.get("mechanic_id", "")) for event in payload.get("mechanic_events", [])]


def test_kickoff_context_suppresses_challenge_and_fifty():
    timeline = []
    for i in range(140):
        t = i / 60.0
        kickoff_pause = t < 0.35
        touch_moment = t >= 0.72
        ball_vx = 0.0 if not touch_moment else 240.0
        ball_vy = 0.0 if not touch_moment else 1180.0
        ball_x = 0.0 if not touch_moment else (t - 0.72) * 240.0
        ball_y = 0.0 if not touch_moment else (t - 0.72) * 1180.0
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 300 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": kickoff_pause,
                "is_inactive_phase": False,
                "active_play": not kickoff_pause,
                "ball": {
                    "x": ball_x,
                    "y": ball_y,
                    "z": 93.0,
                    "vx": ball_vx,
                    "vy": ball_vy,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", -1850.0 + t * 2500.0, 0.0, 17.0, 2350.0, 0.0),
                    _player("Opponent", 1850.0 - t * 2500.0, 0.0, 17.0, -2350.0, 0.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "kickoff" in mids
    assert "challenge" not in mids
    assert "fifty_fifty_control" not in mids


def test_rotate_back_past_ball_does_not_flag_challenge():
    timeline = []
    for i in range(90):
        t = i / 60.0
        opp_touch = t >= 0.58
        ball_vx = -1100.0 if opp_touch else 0.0
        ball_vy = 150.0 if opp_touch else 0.0
        ball_x = -(t - 0.58) * 1100.0 if opp_touch else 0.0
        ball_y = (t - 0.58) * 150.0 if opp_touch else 0.0
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 240 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": {
                    "x": ball_x,
                    "y": ball_y,
                    "z": 110.0,
                    "vx": ball_vx,
                    "vy": ball_vy,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", 260.0, -260.0 - (t * 480.0), 17.0, 0.0, -480.0),
                    _player("Opponent", 50.0, 420.0 - (t * 720.0), 17.0, -40.0, -720.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "challenge" not in mids


def test_committed_ground_challenge_still_detects():
    timeline = []
    for i in range(120):
        t = i / 60.0
        player_touch = t >= 0.78
        ball_vx = 120.0 if player_touch else 0.0
        ball_vy = 1280.0 if player_touch else 0.0
        ball_x = (t - 0.78) * 120.0 if player_touch else 0.0
        ball_y = (t - 0.78) * 1280.0 if player_touch else 0.0
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 210 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": {
                    "x": ball_x,
                    "y": ball_y,
                    "z": 95.0,
                    "vx": ball_vx,
                    "vy": ball_vy,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", -920.0 + (t * 980.0), 0.0, 17.0, 980.0, 0.0),
                    _player("Opponent", 760.0 - (t * 760.0), 0.0, 17.0, -760.0, 0.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "challenge" in mids or "fifty_fifty_control" in mids
