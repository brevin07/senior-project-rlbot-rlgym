from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import subprocess
import time
import webbrowser
from pathlib import Path

from rocketcoach.training.rldojo_catalog import dojo_request_path

LAUNCH_ENV_FLAG = "RLBOT_LIVE_ANALYSIS_LAUNCHED"


def parse_args():
    parser = argparse.ArgumentParser(description="Live scenario analysis with RLDojo scenario support")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--player-index", type=int, default=0)
    parser.add_argument("--tick-rate", type=float, default=30.0)
    parser.add_argument("--window-seconds", type=float, default=10.0)
    parser.add_argument("--stabilization-ticks", type=int, default=15)
    parser.add_argument("--default-scenario", default="")
    parser.add_argument("--scenario-root", default="")
    parser.add_argument("--no-bot-mode", choices=["tuck", "none"], default="tuck")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--launcher", choices=["epic", "steam", "auto"], default="epic")
    parser.add_argument("--bot-skill", type=float, default=1.0)
    parser.add_argument("--session-dir", default="")
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--load-review-session", default="")
    parser.add_argument("--record-session", dest="record_session", action="store_true")
    parser.add_argument("--no-record-session", dest="record_session", action="store_false")
    parser.set_defaults(record_session=True)

    parser.set_defaults(auto_start_match=True)
    parser.add_argument(
        "--auto-start-match",
        action="store_true",
        dest="auto_start_match",
        help="Automatically launch/start a live RL match before analysis.",
    )
    parser.add_argument(
        "--attach-only",
        action="store_false",
        dest="auto_start_match",
        help="Attach to an already-running RLBot/Rocket League session.",
    )

    return parser.parse_args()


def _is_wsl() -> bool:
    return "microsoft" in platform.release().lower()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _to_windows_path(path: Path) -> str:
    if os.name == "nt":
        return str(path)
    if _is_wsl():
        try:
            result = subprocess.run(
                ["wslpath", "-w", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return str(path)
    return str(path)


def _build_powershell_command(args) -> list[str]:
    script_path = _repo_root() / "scripts" / "launch_live_analysis.ps1"
    cmd = [
        "powershell" if os.name == "nt" else "powershell.exe",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        _to_windows_path(script_path),
        "-BindHost",
        str(args.host),
        "-Port",
        str(args.port),
        "-PlayerIndex",
        str(args.player_index),
        "-TickRate",
        str(args.tick_rate),
        "-WindowSeconds",
        str(args.window_seconds),
        "-StabilizationTicks",
        str(args.stabilization_ticks),
        "-NoBotMode",
        str(args.no_bot_mode),
        "-Launcher",
        str(args.launcher),
        "-BotSkill",
        str(args.bot_skill),
    ]
    if args.default_scenario:
        cmd += ["-DefaultScenario", str(args.default_scenario)]
    if args.scenario_root:
        cmd += ["-ScenarioRoot", str(args.scenario_root)]
    if not args.auto_start_match:
        cmd += ["-AttachOnly"]
    if args.no_browser:
        cmd += ["-NoBrowser"]
    return cmd


def _apply_profile_launcher(args) -> None:
    try:
        from rocketcoach.common.persistence import AppDB
    except Exception:
        return
    try:
        profile = AppDB().current_user() or {}
        platform_name = str(profile.get("platform", "")).strip().lower()
        if platform_name in {"epic", "steam"}:
            args.launcher = platform_name
    except Exception:
        return


def _maybe_delegate_to_powershell(args) -> None:
    if os.environ.get(LAUNCH_ENV_FLAG) == "1":
        return
    if args.review_only or args.session_dir or args.load_review_session or (not args.record_session):
        # Advanced review/recording options are handled directly in Python mode.
        return

    cmd = _build_powershell_command(args)
    print("[live_analysis] delegating launch to PowerShell wrapper")
    result = subprocess.run(cmd, cwd=str(_repo_root()))
    raise SystemExit(result.returncode)


def _resolve_startup_scenario(scenarios: dict[str, dict], preferred_name: str) -> str | None:
    if not scenarios:
        return None
    if preferred_name and preferred_name in scenarios:
        return preferred_name
    if preferred_name and preferred_name not in scenarios:
        print(f"[live_analysis] warning: default scenario '{preferred_name}' not found")
    return sorted(scenarios.keys())[0]


def _build_match_config(bot_skill: float):
    from rlbot.matchconfig.match_config import MatchConfig, PlayerConfig, Team

    match_config = MatchConfig()
    # RLBot expects networking_role to always be a valid NetworkingRole enum key.
    # Leaving this unset can cause KeyError in SetupManager.ensure_rlbot_gateway_started.
    match_config.networking_role = "none"
    match_config.network_address = "127.0.0.1"

    human = PlayerConfig()
    human.bot = False
    human.rlbot_controlled = False
    human.human_index = 0
    human.team = Team.BLUE.value
    human.name = "Human"

    orange_bot = PlayerConfig()
    orange_bot.bot = True
    orange_bot.rlbot_controlled = False
    orange_bot.bot_skill = max(0.0, min(1.0, bot_skill))
    orange_bot.team = Team.ORANGE.value
    orange_bot.name = "Psyonix"

    match_config.player_configs = [human, orange_bot]
    match_config.game_mode = "Soccer"
    match_config.game_map = "DFHStadium"
    match_config.instant_start = True
    match_config.skip_replays = True
    match_config.enable_rendering = True
    match_config.enable_state_setting = True
    match_config.existing_match_behavior = "Restart"

    match_config.mutators.match_length = "Unlimited"
    match_config.mutators.respawn_time = "Disable Goal Reset"

    return match_config


def _build_rldojo_match_config(*, bot_config_path: str, dojo_wrapper_config_path: str):
    from rlbot.matchconfig.match_config import MatchConfig, PlayerConfig, ScriptConfig, Team

    match_config = MatchConfig()
    match_config.networking_role = "none"
    match_config.network_address = "127.0.0.1"

    human = PlayerConfig()
    human.bot = False
    human.rlbot_controlled = False
    human.human_index = 0
    human.team = Team.BLUE.value
    human.name = "Human"

    orange_bot = PlayerConfig.bot_config(Path(bot_config_path), Team.ORANGE)
    orange_bot.name = str(getattr(orange_bot, "name", "") or "Training Bot")

    match_config.player_configs = [human, orange_bot]
    match_config.script_configs = [ScriptConfig(Path(dojo_wrapper_config_path))]
    match_config.game_mode = "Soccer"
    match_config.game_map = "DFHStadium"
    match_config.instant_start = True
    match_config.skip_replays = True
    match_config.enable_rendering = True
    match_config.enable_state_setting = True
    match_config.existing_match_behavior = "Restart"
    match_config.mutators.match_length = "Unlimited"
    match_config.mutators.respawn_time = "Disable Goal Reset"
    return match_config


def _launcher_preference(launcher_name: str):
    from rlbot.setup_manager import RocketLeagueLauncherPreference

    if launcher_name == "auto":
        return None
    return RocketLeagueLauncherPreference(preferred_launcher=launcher_name, use_login_tricks=True)


def _connect_for_live_analysis(manager: SetupManager, args) -> None:
    if args.auto_start_match:
        match_config = _build_match_config(args.bot_skill)
        manager.load_match_config(match_config)
        manager.connect_to_game(launcher_preference=_launcher_preference(args.launcher))
        manager.start_match()
        print("[live_analysis] auto-started live match")
    else:
        manager.connect_to_game(launcher_preference=_launcher_preference(args.launcher))
        print("[live_analysis] attached to live Rocket League session")


def _launch_rldojo_training(manager: SetupManager, args, launch: dict) -> None:
    playlist_name = str(launch.get("playlist_name", "") or "").strip()
    bot_config_path = str(launch.get("bot_config_path", "") or "").strip()
    dojo_source_root = str(launch.get("dojo_source_root", "") or "").strip()
    dojo_wrapper_config_path = str(launch.get("dojo_wrapper_config_path", "") or "").strip()
    if not playlist_name:
        raise RuntimeError("Training launch is missing playlist_name.")
    if not bot_config_path or not Path(bot_config_path).exists():
        raise RuntimeError(f"Training bot config was not found: {bot_config_path}")
    if not dojo_source_root or not Path(dojo_source_root).exists():
        raise RuntimeError(f"RLDojo source root was not found: {dojo_source_root}")
    if not dojo_wrapper_config_path or not Path(dojo_wrapper_config_path).exists():
        raise RuntimeError(f"Dojo wrapper config was not found: {dojo_wrapper_config_path}")

    request_path = dojo_request_path()
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps(
            {
                "playlist_name": playlist_name,
                "focus_id": str(launch.get("focus_id", "") or ""),
                "difficulty_tier": str(launch.get("difficulty_tier", "") or ""),
                "requested_at": time.time(),
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    os.environ["ROCKETCOACH_DOJO_SOURCE_ROOT"] = dojo_source_root
    os.environ["ROCKETCOACH_DOJO_REQUEST_PATH"] = str(request_path)

    match_config = _build_rldojo_match_config(
        bot_config_path=bot_config_path,
        dojo_wrapper_config_path=dojo_wrapper_config_path,
    )
    manager.load_match_config(match_config)
    manager.connect_to_game(launcher_preference=_launcher_preference(args.launcher))
    manager.start_match()
    print(
        f"[live_analysis] launched RLDojo playlist '{playlist_name}' against "
        f"{str(launch.get('bot_name', '') or Path(bot_config_path).stem)}"
    )


def main():
    args = parse_args()
    _apply_profile_launcher(args)
    _maybe_delegate_to_powershell(args)

    from rocketcoach.common.persistence import AppDB
    from rocketcoach.live_analysis.http_server import DashboardServer
    from rocketcoach.live_analysis.mechanic_grader import grade_game_mechanics, summarize_mechanic_scores
    from rocketcoach.live_analysis.metrics_engine import LiveMetricsEngine
    from rocketcoach.live_analysis.review_store import ReviewStore
    from rocketcoach.live_analysis.session_recorder import SessionRecorder
    from rocketcoach.live_analysis.state_store import StateStore

    store = StateStore()
    store.set_spawn_mode(args.no_bot_mode)
    db = AppDB()
    session_root = Path(args.session_dir).resolve() if args.session_dir else (_repo_root() / "artifacts" / "live_sessions")
    review_store = ReviewStore(session_root=session_root, db=db)

    if args.review_only:
        scenarios, sources = {}, {}
    else:
        from rocketcoach.live_analysis.scenario_loader import load_scenarios

        scenarios, sources = load_scenarios(extra_dir=args.scenario_root or None)
    store.set_scenarios(scenarios, sources)

    metrics = LiveMetricsEngine(window_seconds=args.window_seconds)
    spawner = None
    if not args.review_only:
        from rocketcoach.live_analysis.scenario_spawner import ScenarioSpawner

        spawner = ScenarioSpawner(stabilization_ticks=args.stabilization_ticks, no_bot_mode=args.no_bot_mode)

    startup_scenario = _resolve_startup_scenario(scenarios, args.default_scenario.strip())
    if startup_scenario:
        store.queue_scenario(startup_scenario)
        print(f"[live_analysis] startup scenario: {startup_scenario}")
    else:
        print("[live_analysis] warning: no scenarios available to spawn")

    server = DashboardServer(store=store, review_store=review_store, db=db, host=args.host, port=args.port)
    server.start()

    dashboard_url = f"http://{args.host}:{args.port}"
    print(f"[live_analysis] dashboard: {dashboard_url}")
    print(f"[live_analysis] loaded scenarios: {len(scenarios)}")
    print(f"[live_analysis] spawn mode: {args.no_bot_mode}")
    print(f"[live_analysis] auto start match: {args.auto_start_match}")

    manager = None
    recorder = None
    if args.load_review_session:
        try:
            loaded = review_store.load_session(args.load_review_session)
            print(f"[live_analysis] loaded review session: {loaded.get('session_id','')}")
        except Exception as exc:
            print(f"[live_analysis] review preload failed: {exc}")

    if not args.review_only:
        from rlbot.setup_manager import SetupManager
        from rlbot.utils.structures.game_data_struct import GameTickPacket

        manager = SetupManager()
        _connect_for_live_analysis(manager, args)
        print("[live_analysis] connected to Rocket League")
        recorder = SessionRecorder(
            session_root=session_root,
            tick_rate=args.tick_rate,
            tracked_player_index=args.player_index,
            enabled=bool(args.record_session),
        )
        recorder.start()
        if recorder.enabled:
            print(f"[live_analysis] recording session to: {recorder.paths.session_dir}")
    else:
        print("[live_analysis] review-only mode: Rocket League connection disabled")

    if not args.no_browser:
        try:
            webbrowser.open(dashboard_url)
        except Exception:
            pass

    running = True

    def _stop(_sig=None, _frame=None):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    sleep_s = 1.0 / max(1.0, args.tick_rate)

    try:
        while running:
            if args.review_only:
                time.sleep(0.1)
                continue

            pending_launch = store.pop_pending_training_launch()
            if pending_launch and str(pending_launch.get("launcher_kind", "") or "").strip().lower() == "rldojo":
                try:
                    _launch_rldojo_training(manager, args, pending_launch)
                except Exception as exc:
                    print(f"[live_analysis] RLDojo training launch failed: {exc}")

            pending_name = store.pop_pending_scenario()
            if not pending_name:
                nxt = store.pop_next_training()
                if nxt:
                    sid = str(nxt.get("scenario_id", "")).strip()
                    if sid:
                        store.queue_scenario(sid)
                        pending_name = sid
            if pending_name:
                payload = store.get_scenario(pending_name)
                if payload:
                    spawner.queue(payload)
                    store.set_active_scenario(pending_name)
                    print(f"[live_analysis] queued scenario: {pending_name}")

            spawner.tick(manager.game_interface)

            packet = GameTickPacket()
            manager.game_interface.update_live_data_packet(packet)

            if packet.num_cars > args.player_index:
                metrics.update(packet, player_index=args.player_index)
                current, history, events = metrics.snapshot()
                # Future-aware event detection is post-session only.
                live_current = dict(current)
                live_current["whiff_rate_per_min"] = 0.0
                live_current["whiff_events_recent"] = 0
                live_current["hesitation_events_recent"] = 0
                store.set_metrics(live_current, history, [])
                if recorder:
                    recorder.record(packet, current, events)

            time.sleep(sleep_s)
    finally:
        if recorder:
            try:
                out = recorder.finalize()
                if out:
                    print(f"[live_analysis] session saved: {out}")
                    profile = db.current_user() or {}
                    if profile:
                        manifest_path = Path(out) / "manifest.json"
                        manifest = {}
                        if manifest_path.exists():
                            import json
                            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        summary = {
                            "frame_count": int(manifest.get("frame_count", 0) or 0),
                            "players": list(manifest.get("players", []) or []),
                        }
                        try:
                            import gzip
                            import json as _json

                            metrics_path = Path(out) / str((manifest.get("files", {}) or {}).get("metrics_timeline", "metrics_timeline.json.gz"))
                            if metrics_path.exists():
                                with gzip.open(metrics_path, "rt", encoding="utf-8") as fp:
                                    mts = _json.load(fp)
                                if isinstance(mts, list) and mts:
                                    last = mts[-1]
                                    for k in ("whiff_rate_per_min", "hesitation_percent", "approach_efficiency", "recovery_time_avg_s"):
                                        if k in last:
                                            summary[k] = float(last.get(k, 0.0) or 0.0)
                        except Exception:
                            pass
                        try:
                            import gzip
                            import json as _json

                            frames_file = str((manifest.get("files", {}) or {}).get("frames", "frames.jsonl.gz"))
                            frames_path = Path(out) / frames_file
                            if frames_path.exists():
                                timeline = []
                                with gzip.open(frames_path, "rt", encoding="utf-8") as fp:
                                    for line in fp:
                                        line = line.strip()
                                        if not line:
                                            continue
                                        try:
                                            timeline.append(_json.loads(line))
                                        except Exception:
                                            continue
                                tracked = str(manifest.get("tracked_player_name", "") or "")
                                player_teams = dict(manifest.get("player_teams", {}) or {})
                                if timeline and tracked:
                                    mech_payload = grade_game_mechanics(timeline, tracked, player_teams)
                                    summary.update(summarize_mechanic_scores(mech_payload))
                                    summary["mechanic_event_count"] = len((mech_payload or {}).get("mechanic_events", []) or [])
                        except Exception:
                            pass
                        db.save_replay_session(
                            session_id=str(manifest.get("session_id", Path(out).name)),
                            user_id=int(profile["id"]),
                            source_type="live",
                            replay_name=f"live_{manifest.get('session_id', Path(out).name)}",
                            map_name=str(manifest.get("map_name", "soccar")),
                            duration_s=float(manifest.get("duration_s", 0.0) or 0.0),
                            tracked_player_name=str(manifest.get("tracked_player_name", "")),
                            tracked_player_index=int(manifest.get("tracked_player_index", 0) or 0),
                            artifact_manifest={
                                "session_dir": str(Path(out).resolve()),
                                "manifest_file": str(manifest_path.resolve()),
                            },
                            summary=summary,
                            created_at=str(manifest.get("created_at", "")),
                        )
            except Exception as exc:
                print(f"[live_analysis] session save failed: {exc}")
        server.stop()
        print("[live_analysis] stopped")


if __name__ == "__main__":
    main()
