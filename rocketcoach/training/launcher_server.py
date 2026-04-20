from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

import psutil

from rocketcoach.training.rldojo_catalog import (
    build_preflight,
    detect_bots,
    detect_dojo_source_root,
    dojo_request_path,
    resolve_launch_profile,
)


def _launcher_preference(launcher_name: str):
    from rlbot.setup_manager import RocketLeagueLauncherPreference

    if launcher_name == "auto":
        return None
    return RocketLeagueLauncherPreference(preferred_launcher=launcher_name, use_login_tricks=True)


def _patch_matchcomms_server() -> None:
    from rlbot import setup_manager as setup_manager_module
    from rlbot.matchcomms import server as matchcomms_server_module

    if getattr(matchcomms_server_module, "_rocketcoach_patched", False):
        return

    def launch_matchcomms_server_compat():
        host = "localhost"
        port = matchcomms_server_module.find_free_port()
        event_loop = asyncio.new_event_loop()
        matchcomms_server = matchcomms_server_module.MatchcommsServer()

        async def start_server():
            return await matchcomms_server_module.websockets.serve(
                matchcomms_server.handle_connection,
                host,
                port,
            )

        asyncio.set_event_loop(event_loop)
        server = event_loop.run_until_complete(start_server())

        def run_loop():
            asyncio.set_event_loop(event_loop)
            event_loop.run_forever()

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        return matchcomms_server_module.MatchcommsServerThread(
            root_url=matchcomms_server_module.URL(
                scheme="ws",
                netloc=f"{host}:{port}",
                path="",
                params="",
                query="",
                fragment="",
            ),
            _server=server,
            _event_loop=event_loop,
            _thread=thread,
        )

    matchcomms_server_module.launch_matchcomms_server = launch_matchcomms_server_compat
    setup_manager_module.launch_matchcomms_server = launch_matchcomms_server_compat
    matchcomms_server_module._rocketcoach_patched = True


def _build_rldojo_match_config(*, bot_config_path: str, dojo_wrapper_config_path_value: str):
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
    match_config.script_configs = [ScriptConfig(Path(dojo_wrapper_config_path_value))]
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


def _write_runtime_dojo_wrapper_config(*, dojo_source_root: str) -> str:
    wrapper_script = Path(__file__).resolve().parents[1] / "live_analysis" / "dojo_playlist_wrapper.py"
    if not wrapper_script.exists():
        raise RuntimeError("RocketCoach Dojo wrapper script is missing.")
    dojo_requirements = Path(dojo_source_root) / "requirements.txt"
    if not dojo_requirements.exists():
        raise RuntimeError("RLDojo requirements.txt was not found on the host machine.")
    runtime_cfg = dojo_request_path().parent / "rocketcoach_dojo_wrapper.cfg"
    runtime_cfg.parent.mkdir(parents=True, exist_ok=True)
    runtime_cfg.write_text(
        "\n".join(
            [
                "[Locations]",
                f"script_file = {wrapper_script}",
                "name = RocketCoach Dojo Playlist Wrapper",
                f"requirements_file = {dojo_requirements}",
                "",
                "[Details]",
                "developer = RocketCoach",
                "description = Launch RLDojo with a preselected RocketCoach playlist.",
                "language = Python",
                "tags = training, dojo, playlist",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return str(runtime_cfg)


def _terminate_windows_processes(process_names: tuple[str, ...]) -> None:
    normalized = {str(name or "").strip().lower() for name in process_names if str(name or "").strip()}
    if not normalized:
        return

    victims = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = str(proc.info.get("name") or "").strip().lower()
            if name in normalized:
                victims.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for proc in victims:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    gone, alive = psutil.wait_procs(victims, timeout=8)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


class TrainingLauncher:
    def __init__(self, *, launcher: str = "auto"):
        self.launcher = str(launcher or "auto")
        self._setup_manager = None
        self._lock = threading.Lock()
        self._active_training: Dict[str, Any] = {}

    def _reset_manager(self, *, quiet: bool = True) -> None:
        manager = self._setup_manager
        if manager is not None:
            try:
                manager.shut_down(time_limit=1, kill_all_pids=True, quiet=quiet)
            except Exception:
                pass
        self._setup_manager = None
        try:
            from rlbot.setup_manager import SetupManager

            SetupManager.has_started = False
        except Exception:
            pass

    def _manager(self):
        if self._setup_manager is None:
            _patch_matchcomms_server()
            from rlbot.setup_manager import SetupManager

            self._setup_manager = SetupManager()
        return self._setup_manager

    def _start_training_match(self, *, manager, match_config, launcher_name: str) -> None:
        manager.load_match_config(match_config)
        manager.connect_to_game(launcher_preference=_launcher_preference(launcher_name))
        manager.launch_early_start_bot_processes()
        manager.start_match()
        manager.launch_bot_processes()
        manager.try_recieve_agent_metadata()

    def _hard_reset_training_processes(self) -> None:
        self._reset_manager(quiet=True)
        _terminate_windows_processes(("RocketLeague.exe", "RLBot.exe"))
        time.sleep(3.0)

    def preflight(self) -> Dict[str, Any]:
        payload = dict(build_preflight(live_host="127.0.0.1", live_port=8766, service_label="local training launcher") or {})
        blocked_bots = [status for status in list(payload.get("bot_statuses", []) or []) if not bool(status.get("ready"))]
        dependency_ready = bool(
            payload.get("shared_dependency_ready")
            and not list(payload.get("missing_bots", []) or [])
            and not blocked_bots
        )
        payload["launcher_kind"] = "training_bridge"
        payload["launcher_running"] = True
        payload["dependency_ready"] = dependency_ready
        payload["ready_to_launch"] = dependency_ready
        return payload

    def launch(self, body: Dict[str, Any]) -> Dict[str, Any]:
        focus_id = str(body.get("focus_id", "") or "").strip()
        difficulty_tier = str(body.get("difficulty_tier", "") or "").strip().lower()
        if not focus_id:
            raise RuntimeError("Missing focus_id")
        if not difficulty_tier:
            raise RuntimeError("Missing difficulty_tier")

        # Resolve launcher from user's platform setting (epic/steam), falling back to
        # the server's default (self.launcher, typically "auto").
        _PLATFORM_TO_LAUNCHER = {"epic": "epic", "steam": "steam"}
        raw_platform = str(body.get("platform", "") or "").strip().lower()
        launcher_name = _PLATFORM_TO_LAUNCHER.get(raw_platform, self.launcher)

        preflight = self.preflight()
        if not bool(preflight.get("dependency_ready")):
            raise RuntimeError("Training dependencies are not ready on this machine.")

        launch_profile = resolve_launch_profile(
            focus_id=focus_id,
            difficulty_tier=difficulty_tier,
            bot_profile_id=str(body.get("bot_profile_id", "") or ""),
        )
        if not launch_profile:
            raise RuntimeError("Unable to resolve the requested training profile.")
        print(
            "[training_launcher] launch request "
            f"focus={focus_id} difficulty={difficulty_tier} "
            f"playlist={str(launch_profile.get('playlist_name', '') or '')} "
            f"bot={str(launch_profile.get('bot_name', '') or launch_profile.get('bot_profile_id', '') or '')} "
            f"platform={raw_platform or 'missing'} "
            f"launcher={launcher_name}",
            flush=True,
        )

        bots = detect_bots()
        bot_details = dict((bots.get("found", {}) or {}).get(str(launch_profile.get("bot_profile_id", "") or ""), {}) or {})
        bot_config_path = str(bot_details.get("config_path", "") or "").strip()
        if not bot_config_path:
            raise RuntimeError(f"Configured bot '{launch_profile.get('bot_profile_id', '')}' is not installed.")

        dojo_source = detect_dojo_source_root()
        dojo_source_root = str(dojo_source.get("path", "") or "").strip()
        if not dojo_source_root:
            raise RuntimeError("RLDojo source files were not found on the host machine.")

        wrapper_cfg = _write_runtime_dojo_wrapper_config(dojo_source_root=dojo_source_root)

        request_path = dojo_request_path()
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(
            json.dumps(
                {
                    "playlist_name": str(launch_profile.get("playlist_name", "") or ""),
                    "playlist_id": str(launch_profile.get("playlist_id", "") or ""),
                    "focus_id": focus_id,
                    "difficulty_tier": difficulty_tier,
                    "requested_at": time.time(),
                },
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )

        replacing_existing = bool(self._active_training)
        result = {
            "queued": False,
            "launcher_kind": "training_bridge",
            "focus_id": focus_id,
            "difficulty_tier": difficulty_tier,
            "bot_profile_id": str(launch_profile.get("bot_profile_id", "") or ""),
            "bot_name": str(launch_profile.get("bot_name", "") or ""),
            "playlist_name": str(launch_profile.get("playlist_name", "") or ""),
            "playlist_file": str(launch_profile.get("playlist_file", "") or ""),
            "playlist_id": str(launch_profile.get("playlist_id", "") or ""),
            "bot_config_path": bot_config_path,
            "dojo_source_root": dojo_source_root,
            "dojo_wrapper_config_path": wrapper_cfg,
            "drill_run_id": int(body.get("drill_run_id", 0) or 0),
            "route": "/training",
            "status_message": (
                "Training swapped to the new drill in Rocket League."
                if replacing_existing
                else "Training drill loaded in Rocket League."
            ),
        }

        # Capture all values needed by the background thread before returning.
        _focus_id = focus_id
        _difficulty_tier = difficulty_tier
        _bot_config_path = bot_config_path
        _dojo_source_root = dojo_source_root
        _request_path = request_path
        _wrapper_cfg = wrapper_cfg
        _launch_profile = launch_profile
        _replacing_existing = replacing_existing
        _launcher_name = launcher_name

        print(
            "[training_launcher] starting launch "
            f"focus={focus_id} difficulty={difficulty_tier} "
            f"playlist={str(launch_profile.get('playlist_name', '') or '')} "
            f"bot={str(launch_profile.get('bot_name', '') or launch_profile.get('bot_profile_id', '') or '')}",
            flush=True,
        )

        with self._lock:
            try:
                import os

                os.environ["ROCKETCOACH_DOJO_SOURCE_ROOT"] = _dojo_source_root
                os.environ["ROCKETCOACH_DOJO_REQUEST_PATH"] = str(_request_path)

                manager = self._manager()
                if _replacing_existing:
                    print(
                        "[training_launcher] replacing active training "
                        f"focus={str(self._active_training.get('focus_id', '') or '')} "
                        f"playlist={str(self._active_training.get('playlist_name', '') or '')}",
                        flush=True,
                    )
                    self._reset_manager(quiet=True)
                    manager = self._manager()
                match_config = _build_rldojo_match_config(
                    bot_config_path=_bot_config_path,
                    dojo_wrapper_config_path_value=_wrapper_cfg,
                )
                _STALE_GATEWAY_MARKERS = (
                    "Rocket League is not running even though we started it once.",
                    "process no longer exists",
                    "Terminating rlbot gateway",
                )
                _EPIC_RELAUNCH_TIMEOUT_MARKERS = (
                    "RLBot took too long to initialize!",
                    "Was Rocket League started with the -rlbot flag?",
                )
                try:
                    self._start_training_match(
                        manager=manager,
                        match_config=match_config,
                        launcher_name=_launcher_name,
                    )
                except Exception as exc:
                    message = str(exc)
                    should_retry = (
                        any(marker in message for marker in _STALE_GATEWAY_MARKERS)
                        or any(marker in message for marker in _EPIC_RELAUNCH_TIMEOUT_MARKERS)
                    )
                    if not should_retry:
                        raise
                    print(
                        "[training_launcher] RLBot launch desynced; "
                        f"resetting local Rocket League / RLBot state and retrying once ({message[:120]})",
                        flush=True,
                    )
                    self._hard_reset_training_processes()
                    manager = self._manager()
                    self._start_training_match(
                        manager=manager,
                        match_config=match_config,
                        launcher_name=_launcher_name,
                    )
                self._active_training = {
                    "focus_id": _focus_id,
                    "difficulty_tier": _difficulty_tier,
                    "playlist_name": str(_launch_profile.get("playlist_name", "") or ""),
                    "bot_name": str(_launch_profile.get("bot_name", "") or ""),
                    "started_at": time.time(),
                }
                print(
                    "[training_launcher] match started "
                    f"focus={_focus_id} difficulty={_difficulty_tier} "
                    f"playlist={str(_launch_profile.get('playlist_name', '') or '')} "
                    f"bot={str(_launch_profile.get('bot_name', '') or _launch_profile.get('bot_profile_id', '') or '')}",
                    flush=True,
                )
            except Exception as exc:
                print(
                    "[training_launcher] launch failed "
                    f"focus={_focus_id} difficulty={_difficulty_tier}: {exc}",
                    flush=True,
                )
                raise RuntimeError(f"RocketCoach could not start the RLBot training drill: {exc}") from exc
        return result


class _Handler(BaseHTTPRequestHandler):
    launcher: TrainingLauncher = None

    def end_headers(self) -> None:
        origin = str(self.headers.get("Origin", "") or "").strip()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        super().end_headers()

    def _send_json(self, payload: Dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/health":
            return self._send_json({"ok": True, "data": {"status": "ok", "launcher_kind": "training_bridge"}})
        if self.path == "/api/training/preflight":
            try:
                return self._send_json({"ok": True, "data": self.launcher.preflight()})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/api/training/launch":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                body = {}
            try:
                return self._send_json({"ok": True, "data": self.launcher.launch(body)})
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self.send_error(HTTPStatus.NOT_FOUND)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Host-side RocketCoach RLBot training launcher.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--launcher", choices=["auto", "epic", "steam"], default="auto")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    launcher = TrainingLauncher(launcher=args.launcher)
    handler = type("RocketCoachTrainingLauncherHandler", (_Handler,), {})
    handler.launcher = launcher
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"[training_launcher] running at http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
