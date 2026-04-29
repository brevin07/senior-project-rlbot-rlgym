from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rocketcoach.live_analysis.mechanic_grader import grade_game_mechanics


def _player(
    name: str,
    x: float,
    y: float,
    z: float,
    vx: float,
    vy: float,
    vz: float = 0.0,
    boost: float = 33.0,
    *,
    jump: int = 0,
    double_jump: int = 0,
) -> dict:
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
        "jump": jump,
        "double_jump": double_jump,
    }


def _mechanic_ids(payload: dict) -> list[str]:
    return [str(event.get("mechanic_id", "")) for event in payload.get("mechanic_events", [])]


def _events(payload: dict) -> list[dict]:
    return list(payload.get("mechanic_events", []) or [])


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
                    _player("TestPlayer", -2048.0 + t * 2650.0, -2560.0 + t * 3320.0, 17.0, 1850.0, 2320.0),
                    _player("Opponent", 0.0, 4608.0 - t * 5600.0, 17.0, 0.0, -2550.0),
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


def test_committed_opponent_first_contest_flags_challenge():
    timeline = []
    for i in range(100):
        t = i / 60.0
        impact = t >= 0.58
        ball_x = 0.0
        ball_y = 0.0 if not impact else (t - 0.58) * 850.0
        ball_vx = 0.0
        ball_vy = 0.0 if not impact else 850.0
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 250 - t,
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
                    _player("TestPlayer", -760.0 + t * 1180.0, 0.0, 17.0, 1180.0, 0.0),
                    _player("Opponent", 720.0 - t * 1120.0, 0.0, 17.0, -1120.0, 0.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "fifty_fifty_control" in mids
    assert "challenge" not in mids


def test_center_lane_committed_contest_flags_single_fifty_not_overlapping_challenge():
    timeline = []
    for i in range(120):
        t = i / 60.0
        player_touch = t >= 0.78
        ball_vx = 120.0 if player_touch else 0.0
        ball_vy = 980.0 if player_touch else 0.0
        ball_x = (t - 0.78) * 120.0 if player_touch else 0.0
        ball_y = 620.0 + ((t - 0.78) * 980.0 if player_touch else 0.0)
        if t < 2.35:
            player_x = -1900.0 + t * 2550.0
            opponent_x = 2100.0 - t * 2100.0
        else:
            reset_t = t - 2.35
            player_x = -1900.0 + reset_t * 2550.0
            opponent_x = 2100.0 - reset_t * 2100.0
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
                    _player("TestPlayer", -920.0 + (t * 980.0), 620.0, 17.0, 980.0, 0.0),
                    _player("Opponent", 760.0 - (t * 760.0), 620.0, 17.0, -760.0, 0.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "fifty_fifty_control" in mids
    assert "challenge" not in mids


def test_opponent_first_touch_still_stays_kickoff_when_player_commits():
    timeline = []
    for i in range(150):
        t = i / 60.0
        kickoff_pause = t < 0.35
        opp_first_touch = t >= 0.68
        player_followup = t >= 0.83
        if player_followup:
            ball_x = (t - 0.83) * -40.0
            ball_y = 80.0 + (t - 0.83) * 1180.0
            ball_vx = -40.0
            ball_vy = 1180.0
        elif opp_first_touch:
            ball_x = 35.0 + (t - 0.68) * 30.0
            ball_y = -55.0 + (t - 0.68) * 260.0
            ball_vx = 30.0
            ball_vy = 260.0
        else:
            ball_x = 0.0
            ball_y = 0.0
            ball_vx = 0.0
            ball_vy = 0.0
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 300 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": kickoff_pause,
                "is_inactive_phase": kickoff_pause,
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
                    _player("TestPlayer", -2048.0 + t * 2650.0, -2560.0 + t * 3320.0, 17.0, 1850.0, 2320.0),
                    _player("Opponent", 0.0, 4608.0 - t * 5600.0, 17.0, 0.0, -2550.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "kickoff" in mids
    assert "challenge" not in mids
    assert "fifty_fifty_control" not in mids


def test_player_first_kickoff_touch_flags_even_when_opponent_is_late():
    timeline = []
    for i in range(150):
        t = i / 60.0
        kickoff_pause = t < 0.35
        touch_moment = t >= 0.72
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 300 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": kickoff_pause,
                "is_inactive_phase": kickoff_pause,
                "active_play": not kickoff_pause,
                "ball": {
                    "x": 0.0,
                    "y": (t - 0.72) * 1200.0 if touch_moment else 0.0,
                    "z": 93.0,
                    "vx": 0.0,
                    "vy": 1200.0 if touch_moment else 0.0,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", -2048.0 + t * 2850.0, -2560.0 + t * 3600.0, 17.0, 2050.0, 2600.0),
                    _player("Opponent", 0.0, 4608.0 - t * 1200.0, 17.0, 0.0, -1200.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "kickoff" in mids
    assert "challenge" not in mids
    assert "fifty_fifty_control" not in mids


def test_replay_meta_kickoff_window_drives_detection_and_suppression():
    timeline = []
    for i in range(160):
        t = i / 60.0
        touch_moment = t >= 0.78
        ball_vx = 0.0 if not touch_moment else 220.0
        ball_vy = 0.0 if not touch_moment else 1240.0
        ball_x = 0.0 if not touch_moment else (t - 0.78) * 220.0
        ball_y = 0.0 if not touch_moment else (t - 0.78) * 1240.0
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 300 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": {
                    "x": ball_x,
                    "y": ball_y,
                    "z": 93.0,
                    "vx": ball_vx,
                    "vy": ball_vy,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", -2048.0 + t * 2680.0, -2560.0 + t * 3350.0, 17.0, 1880.0, 2350.0),
                    _player("Opponent", 0.0, 4608.0 - t * 5600.0, 17.0, 0.0, -2550.0),
                ],
            }
        )

    payload = grade_game_mechanics(
        timeline,
        "TestPlayer",
        {"TestPlayer": 0, "Opponent": 1},
        {"kickoff_pause_windows": [{"start_s": 0.10, "end_s": 0.82}]},
    )
    mids = _mechanic_ids(payload)

    assert "kickoff" in mids
    assert "challenge" not in mids
    assert "fifty_fifty_control" not in mids


def test_kickoff_requires_true_center_reset_not_just_metadata_window():
    timeline = []
    for i in range(150):
        t = i / 60.0
        touch_moment = t >= 0.8
        ball_vx = 0.0 if not touch_moment else 1300.0
        ball_vy = 0.0 if not touch_moment else -900.0
        ball_x = 1700.0 + ((t - 0.8) * 1300.0 if touch_moment else 0.0)
        ball_y = -2600.0 + ((t - 0.8) * -900.0 if touch_moment else 0.0)
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 230 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": True,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": {
                    "x": ball_x,
                    "y": ball_y,
                    "z": 105.0,
                    "vx": ball_vx,
                    "vy": ball_vy,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", -700.0 + t * 2300.0, -900.0 - t * 1700.0, 17.0, 2300.0, -1700.0),
                    _player("Opponent", 2100.0 - t * 1200.0, -2500.0 + t * 900.0, 17.0, -1200.0, 900.0),
                ],
            }
        )

    payload = grade_game_mechanics(
        timeline,
        "TestPlayer",
        {"TestPlayer": 0, "Opponent": 1},
        {"kickoff_pause_windows": [{"start_s": 0.0, "end_s": 1.2}]},
    )

    assert "kickoff" not in _mechanic_ids(payload)


def test_center_ball_play_without_kickoff_spawns_is_not_kickoff():
    timeline = []
    for i in range(130):
        t = i / 60.0
        touch_moment = t >= 0.7
        ball_vx = 0.0 if not touch_moment else 700.0
        ball_vy = 0.0 if not touch_moment else 400.0
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 180 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": True,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": {
                    "x": (t - 0.7) * 700.0 if touch_moment else 0.0,
                    "y": (t - 0.7) * 400.0 if touch_moment else 0.0,
                    "z": 93.0,
                    "vx": ball_vx,
                    "vy": ball_vy,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", -600.0 + t * 1150.0, -600.0 + t * 1150.0, 17.0, 1150.0, 1150.0),
                    _player("Opponent", 650.0 - t * 950.0, 650.0 - t * 950.0, 17.0, -950.0, -950.0),
                ],
            }
        )

    payload = grade_game_mechanics(
        timeline,
        "TestPlayer",
        {"TestPlayer": 0, "Opponent": 1},
        {"kickoff_pause_windows": [{"start_s": 0.0, "end_s": 1.1}]},
    )

    assert "kickoff" not in _mechanic_ids(payload)


def test_flip_reset_requires_airborne_reset_then_offensive_use():
    timeline = []
    for i in range(110):
        t = i / 60.0
        if t < 0.25:
            player = _player("TestPlayer", -250.0 + 120.0 * t, 800.0 + 80.0 * t, 17.0, 480.0, 220.0)
            ball = {"x": 0.0, "y": 1100.0, "z": 240.0, "vx": 0.0, "vy": 0.0, "vz": 0.0}
        elif t < 0.6:
            player = _player("TestPlayer", -120.0 + 380.0 * (t - 0.25), 880.0 + 620.0 * (t - 0.25), 180.0 + 280.0 * (t - 0.25), 380.0, 620.0, 520.0, double_jump=0)
            ball = {"x": 20.0, "y": 1260.0 + 250.0 * (t - 0.25), "z": 320.0 + 80.0 * (t - 0.25), "vx": 30.0, "vy": 180.0, "vz": 120.0}
        elif t < 0.72:
            player = _player("TestPlayer", 20.0, 1520.0 + 240.0 * (t - 0.6), 420.0, 140.0, 520.0, 80.0, double_jump=1)
            ball = {"x": 15.0, "y": 1510.0 + 210.0 * (t - 0.6), "z": 360.0, "vx": 10.0, "vy": 210.0, "vz": 0.0}
        else:
            player = _player("TestPlayer", 35.0, 1610.0 + 720.0 * (t - 0.72), 400.0, 200.0, 940.0, -40.0, double_jump=0)
            ball = {"x": 40.0, "y": 1660.0 + 1380.0 * (t - 0.72), "z": 350.0, "vx": 80.0, "vy": 1380.0, "vz": 20.0}
        opponent = _player("Opponent", 80.0, 3100.0, 17.0, 0.0, -300.0)
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 180 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": ball,
                "players": [player, opponent],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    aerials = [event for event in _events(payload) if str(event.get("mechanic_id", "")) == "aerial_offense"]

    assert aerials
    assert any("flip_reset" in list(event.get("mechanic_tags", []) or []) for event in aerials)


def test_ground_flip_hit_does_not_flag_flip_reset():
    timeline = []
    for i in range(90):
        t = i / 60.0
        used_ground_flip = t >= 0.42
        player = _player(
            "TestPlayer",
            -180.0 + 520.0 * t,
            400.0 + 420.0 * t,
            25.0 if t < 0.38 else 115.0,
            520.0,
            420.0,
            140.0 if t >= 0.38 else 0.0,
            double_jump=0 if used_ground_flip else 1,
        )
        ball = {
            "x": 10.0,
            "y": 760.0 + 180.0 * t,
            "z": 150.0 if t < 0.42 else 180.0,
            "vx": 0.0 if t < 0.42 else 220.0,
            "vy": 0.0 if t < 0.42 else 640.0,
            "vz": 0.0 if t < 0.42 else 60.0,
        }
        opponent = _player("Opponent", 40.0, 2500.0, 17.0, 0.0, -200.0)
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 180 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": ball,
                "players": [player, opponent],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    assert all("flip_reset" not in list(event.get("mechanic_tags", []) or []) for event in _events(payload))


def test_flick_requires_controlled_carry_then_flip_release():
    timeline = []
    for i in range(90):
        t = i / 60.0
        if t < 0.28:
            player = _player("TestPlayer", 0.0, 700.0 + 480.0 * t, 17.0, 0.0, 480.0)
            ball = {"x": 0.0, "y": 780.0 + 480.0 * t, "z": 130.0, "vx": 0.0, "vy": 480.0, "vz": 0.0}
        elif t < 0.52:
            player = _player("TestPlayer", 0.0, 834.4 + 430.0 * (t - 0.28), 17.0, 0.0, 430.0, double_jump=1)
            ball = {"x": 8.0, "y": 924.4 + 430.0 * (t - 0.28), "z": 145.0, "vx": 0.0, "vy": 430.0, "vz": 0.0}
        else:
            player = _player("TestPlayer", 0.0, 937.6 + 500.0 * (t - 0.52), 17.0, 0.0, 500.0, double_jump=0)
            ball = {"x": 5.0, "y": 1027.6 + 1180.0 * (t - 0.52), "z": 165.0 + 420.0 * (t - 0.52), "vx": 0.0, "vy": 1180.0, "vz": 420.0}
        opponent = _player("Opponent", 20.0, 2600.0, 17.0, 0.0, -200.0)
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 180 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": ball,
                "players": [player, opponent],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "flicking" in mids


def test_loose_ball_flip_hit_does_not_flag_flick():
    timeline = []
    for i in range(90):
        t = i / 60.0
        player = _player(
            "TestPlayer",
            -260.0 + 620.0 * t,
            800.0 + 420.0 * t,
            17.0 if t < 0.42 else 40.0,
            620.0,
            420.0,
            0.0,
            double_jump=0 if t >= 0.42 else 1,
        )
        ball = {
            "x": 140.0,
            "y": 980.0 + 180.0 * t,
            "z": 110.0 if t < 0.42 else 170.0,
            "vx": 0.0 if t < 0.42 else 180.0,
            "vy": 0.0 if t < 0.42 else 780.0,
            "vz": 0.0 if t < 0.42 else 180.0,
        }
        opponent = _player("Opponent", 60.0, 2600.0, 17.0, 0.0, -200.0)
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 180 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": ball,
                "players": [player, opponent],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "flicking" not in mids


def test_ground_open_net_chance_does_not_become_flick():
    timeline = []
    for i in range(90):
        t = i / 60.0
        shot = t >= 0.45
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 120 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": {
                    "x": 120.0,
                    "y": 3550.0 + (900.0 * (t - 0.45) if shot else 0.0),
                    "z": 105.0,
                    "vx": 0.0,
                    "vy": 900.0 if shot else 0.0,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", 90.0, 3450.0 + 760.0 * t, 17.0, 0.0, 760.0),
                    _player("Opponent", -2600.0, -3500.0, 17.0, 0.0, 0.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "flicking" not in mids


def test_aerial_defense_requires_real_pressure():
    timeline = []
    for i in range(100):
        t = i / 60.0
        touch = t >= 0.48
        timeline.append(
            {
                "t": t,
                "seconds_remaining": 160 - t,
                "is_overtime": False,
                "is_goal_pause": False,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": {
                    "x": -400.0,
                    "y": -1700.0 + (700.0 * (t - 0.48) if touch else 0.0),
                    "z": 420.0,
                    "vx": 0.0,
                    "vy": 700.0 if touch else 120.0,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", -430.0, -1780.0 + 580.0 * t, 260.0, 0.0, 580.0, 40.0),
                    _player("Opponent", 2500.0, 2800.0, 17.0, 0.0, 0.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    mids = _mechanic_ids(payload)

    assert "aerial_defense" not in mids


def test_low_fifty_detects_slightly_delayed_ground_contest():
    timeline = []
    for i in range(100):
        t = i / 60.0
        contest = t >= 0.55
        ball_vx = 0.0 if not contest else 240.0
        ball_vy = 0.0 if not contest else 180.0
        player_y = 1160.0 + 520.0 * t
        opp_y = 2040.0 - 460.0 * t
        timeline.append(
            {
                "t": t,
                "is_kickoff_pause": False,
                "is_inactive_phase": False,
                "active_play": True,
                "ball": {
                    "x": 0.0,
                    "y": 1600.0 + (40.0 if contest else 0.0),
                    "z": 105.0,
                    "vx": ball_vx,
                    "vy": ball_vy,
                    "vz": 0.0,
                },
                "players": [
                    _player("TestPlayer", 0.0, player_y, 17.0, 0.0, 520.0),
                    _player("Opponent", 25.0, opp_y, 17.0, 0.0, -460.0),
                ],
            }
        )

    payload = grade_game_mechanics(timeline, "TestPlayer", {"TestPlayer": 0, "Opponent": 1})
    fifties = [event for event in _events(payload) if str(event.get("mechanic_id", "")) == "fifty_fifty_control"]

    assert fifties
    assert any(str(event.get("event_type", "")) == "low_50" for event in fifties)
