from pathlib import Path
import threading
import sys
import time

import pandas as pd


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rocketcoach.common.persistence.db import AppDB
from rocketcoach.live_analysis.mechanic_grader import GRADING_VERSION
from rocketcoach.replay_dashboard.replay_loader import ReplaySession
from rocketcoach.replay_dashboard.replay_state_store import ReplayStateStore


def _player(
    name: str,
    x: float,
    y: float,
    z: float,
    vx: float,
    vy: float,
    vz: float = 0.0,
) -> dict:
    return {
        "name": name,
        "x": x,
        "y": y,
        "z": z,
        "vx": vx,
        "vy": vy,
        "vz": vz,
        "boost": 33.0,
        "throttle": 1.0,
        "steer": 0.0,
        "handbrake": 0,
        "jump": 0,
        "double_jump": 0,
    }


def test_recompute_library_replays_refreshes_saved_mechanics(tmp_path):
    db = AppDB(tmp_path / "app.db")
    user = db.upsert_user(username="ReplayUser", rank_tier="diamond_2", platform="epic")
    store = ReplayStateStore(db=db)
    store.set_current_user(user)

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
                    _player("ReplayUser", -920.0 + (t * 980.0), 0.0, 17.0, 980.0, 0.0),
                    _player("Opponent", 760.0 - (t * 760.0), 0.0, 17.0, -760.0, 0.0),
                ],
            }
        )

    prepared = {
        "schema_version": 1,
        "analysis_player": "ReplayUser",
        "replay_name": "SavedReplay.replay",
        "players": ["ReplayUser", "Opponent"],
        "duration_s": 120.0,
        "timeline": timeline,
        "boost_pads": [],
        "replay_meta": {
            "player_teams": {"ReplayUser": 0, "Opponent": 1},
            "team_scores_final": {"blue": 3, "orange": 1},
        },
        "metrics_by_player": {},
        "events_by_player": {},
        "mechanics": {"mechanic_events": []},
    }

    db.save_replay_session(
        session_id="saved-session-1",
        user_id=int(user["id"]),
        source_type="replay_upload",
        replay_name="SavedReplay.replay",
        map_name="soccar",
        duration_s=120.0,
        tracked_player_name="ReplayUser",
        tracked_player_index=0,
        artifact_manifest={},
        replay_blob=b"stub",
        prepared_payload=store._serialize_prepared_payload(prepared),
        summary={"analysis_player": "ReplayUser"},
    )

    result = store.recompute_library_replays()

    assert result["total_sessions"] == 1
    assert result["updated_sessions"] == 1
    assert result["failed_sessions"] == 0

    row = db.get_replay_session(session_id="saved-session-1", user_id=int(user["id"]))
    assert row is not None
    refreshed = store._deserialize_prepared_payload(row["prepared_payload"])
    assert refreshed.get("mechanics", {}).get("grading_version") == GRADING_VERSION
    assert row["summary"].get("analysis_player") == "ReplayUser"
    assert row["summary"].get("player_teams") == {"ReplayUser": 0, "Opponent": 1}
    assert row["summary"].get("team_scores_final") == {"blue": 3, "orange": 1}


def test_parallel_metrics_and_mechanics_share_one_selected_analysis(tmp_path):
    db = AppDB(tmp_path / "app.db")
    user = db.upsert_user(username="ReplayUser", rank_tier="diamond_2", platform="epic")
    store = ReplayStateStore(db=db)
    store.set_current_user(user)

    session = ReplaySession(
        session_id="parallel-session",
        replay_name="Parallel.replay",
        players=["ReplayUser", "Opponent"],
        timeline=[{"t": 0.0, "players": [], "ball": {}}],
        boost_pads=[],
        replay_meta={"player_teams": {"ReplayUser": 0, "Opponent": 1}},
        df=pd.DataFrame(),
        duration_s=1.0,
    )
    store._state.session = session
    store._state.analysis_player = "ReplayUser"
    store._state.analysis_locked = True
    store._state.player_metric_jobs = {
        "ReplayUser": {"status": "idle", "message": "Not started.", "error": ""},
        "Opponent": {"status": "idle", "message": "Not started.", "error": ""},
    }

    ensure_calls: list[float] = []

    def fake_ensure_player_metrics(session_obj, player):
        ensure_calls.append(time.time())
        time.sleep(0.15)
        session_obj.metrics_by_player[player] = [{"t": 0.0, "speed": 0.0}]
        session_obj.events_by_player[player] = [{"t": 0.0, "event": "touch"}]

    def fake_compute_mechanics(session_obj, player):
        return {"grading_version": "test", "mechanic_events": [{"mechanic_id": "kickoff"}]}

    store._persist_analysis_summary = lambda *args, **kwargs: None
    store._persist_prepared_replay = lambda *args, **kwargs: None

    import rocketcoach.replay_dashboard.replay_state_store as replay_state_store_module

    original_ensure = replay_state_store_module.ensure_player_metrics
    replay_state_store_module.ensure_player_metrics = fake_ensure_player_metrics
    store._compute_mechanics_for_selected_player = fake_compute_mechanics
    try:
        results: dict[str, object] = {}
        errors: list[BaseException] = []

        def load_metrics():
            try:
                results["metrics"] = store.player_metrics_data("ReplayUser")
            except BaseException as exc:
                errors.append(exc)

        def load_mechanics():
            try:
                results["mechanics"] = store.current_mechanics()
            except BaseException as exc:
                errors.append(exc)

        metric_thread = threading.Thread(target=load_metrics)
        mechanic_thread = threading.Thread(target=load_mechanics)
        metric_thread.start()
        mechanic_thread.start()
        metric_thread.join(timeout=2)
        mechanic_thread.join(timeout=2)

        assert not errors
        assert len(ensure_calls) == 1
        assert results["metrics"]["metrics_timeline"][0]["t"] == 0.0
        assert results["mechanics"]["mechanic_events"][0]["mechanic_id"] == "kickoff"
        assert store._state.analysis_ready is True
    finally:
        replay_state_store_module.ensure_player_metrics = original_ensure


def test_profile_progress_prefers_replay_date_metadata(tmp_path):
    db = AppDB(tmp_path / "app.db")
    user = db.upsert_user(username="ReplayUser", rank_tier="diamond_2", platform="epic")
    store = ReplayStateStore(db=db)
    store.set_current_user(user)

    db.save_replay_session(
        session_id="progress-session-1",
        user_id=int(user["id"]),
        source_type="replay_upload",
        replay_name="ABC123.replay",
        map_name="soccar",
        duration_s=120.0,
        tracked_player_name="ReplayUser",
        tracked_player_index=0,
        artifact_manifest={},
        replay_blob=b"stub",
        prepared_payload=b"",
        summary={
            "analysis_player": "ReplayUser",
            "replay_date_iso": "2026-04-10T00:00:00+00:00",
            "overall_mechanics_score": 81.5,
            "mechanic_scores": {"kickoff": 84.0},
        },
    )

    payload = store.profile_progress(limit=10)

    assert payload["points"][0]["replay_date_iso"] == "2026-04-10T00:00:00+00:00"
    assert payload["points"][0]["x_time_source"] == "replay_meta"
