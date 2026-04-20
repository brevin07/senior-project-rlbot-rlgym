from __future__ import annotations

import ast
import configparser
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List


NON_BOT_DRILL_SUMMARIES: Dict[str, str] = {
    "bot_duel": "Train the mechanic in a live 1v1 situation against the mapped RLBot bot.",
}

BOT_NAME_ALIASES: Dict[str, List[str]] = {
    "noob_blue": ["Noob Blue"],
    "botimus_prime": ["Botimus Prime"],
    "aether": ["Aether"],
    "necto": ["Necto"],
    "nexto": ["Nexto"],
}

BOT_PATH_HINTS: Dict[str, List[str]] = {
    "noob_blue": ["noob_blue\\src\\bot.cfg", "noob_blue/src/bot.cfg"],
    "botimus_prime": ["botimus&bumblebee\\botimus.cfg", "botimus&bumblebee/botimus.cfg"],
    "aether": ["aether\\src\\bot.cfg", "aether/src/bot.cfg"],
    "necto": ["necto\\necto\\bot.cfg", "necto/necto/bot.cfg"],
    "nexto": ["necto\\nexto\\bot.cfg", "necto/nexto/bot.cfg"],
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    return _repo_root() / "configs" / "rldojo_training_map.json"


@lru_cache(maxsize=1)
def load_training_map() -> Dict[str, Any]:
    return json.loads(config_path().read_text(encoding="utf-8"))


def difficulty_tiers() -> Dict[str, Dict[str, Any]]:
    return dict(load_training_map().get("difficulties", {}) or {})


def mechanic_catalog() -> Dict[str, Dict[str, Any]]:
    return dict(load_training_map().get("mechanics", {}) or {})


def focus_meta(focus_id: str) -> Dict[str, Any]:
    return dict(mechanic_catalog().get(str(focus_id or "").strip(), {}) or {})


def _difficulty_profile(focus_id: str, tier: str) -> Dict[str, Any]:
    meta = focus_meta(focus_id)
    tier_key = str(tier or "").strip().lower()
    tier_meta = dict(difficulty_tiers().get(tier_key, {}) or {})
    focus_tier = dict(meta.get("difficulties", {}).get(tier_key, {}) or {})
    if not tier_meta or not focus_tier:
        return {}
    playlist_file = str(focus_tier.get("playlist_file", "") or "").strip()
    return {
        "tier": tier_key,
        "label": str(tier_meta.get("label", tier_key.title())),
        "difficulty_value": float(focus_tier.get("difficulty_value", tier_meta.get("difficulty_value", 0.5)) or 0.5),
        "summary": str(focus_tier.get("summary", tier_meta.get("summary", "")) or ""),
        "bot_profile_id": str(focus_tier.get("bot_profile_id", "") or ""),
        "bot_name": str(focus_tier.get("bot_name", "") or ""),
        "playlist_name": str(focus_tier.get("playlist_name", "") or ""),
        "playlist_file": playlist_file,
        "playlist_id": Path(playlist_file).stem if playlist_file else "",
    }


def difficulty_profiles_for_focus(focus_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for tier in difficulty_tiers().keys():
        profile = _difficulty_profile(focus_id, tier)
        if profile:
            out.append(profile)
    return out


def build_training_option(focus_id: str) -> Dict[str, Any]:
    meta = focus_meta(focus_id)
    if not meta:
        return {}
    profiles = difficulty_profiles_for_focus(focus_id)
    marker_ids = [str(focus_id)] if profiles else []
    return {
        "focus_id": str(focus_id),
        "title": str(meta.get("title", focus_id)),
        "bot_required": bool(meta.get("bot_required", True)),
        "drill_mode_options": list(meta.get("drill_mode_options", ["bot_duel"])),
        "scenario_ids": marker_ids,
        "difficulty_profiles": profiles,
        "bot_profile_ids": [str(x.get("bot_profile_id", "")) for x in profiles if str(x.get("bot_profile_id", "")).strip()],
    }


def expected_playlist_files() -> List[str]:
    files: List[str] = []
    for focus_id in mechanic_catalog().keys():
        for profile in difficulty_profiles_for_focus(focus_id):
            playlist_file = str(profile.get("playlist_file", "") or "").strip()
            if playlist_file:
                files.append(playlist_file)
    return sorted(set(files))


def required_bot_profile_ids() -> List[str]:
    out: List[str] = []
    for focus_id in mechanic_catalog().keys():
        for profile in difficulty_profiles_for_focus(focus_id):
            bot_profile_id = str(profile.get("bot_profile_id", "") or "").strip()
            if bot_profile_id:
                out.append(bot_profile_id)
    return sorted(set(out))


def resolve_launch_profile(focus_id: str, difficulty_tier: str, bot_profile_id: str = "") -> Dict[str, Any]:
    option = build_training_option(focus_id)
    if not option:
        return {}
    tier_key = str(difficulty_tier or "").strip().lower()
    profile = _difficulty_profile(focus_id, tier_key)
    if not profile:
        return {}
    requested_bot_profile = str(bot_profile_id or "").strip().lower()
    resolved_bot_profile = str(profile.get("bot_profile_id", "")).strip().lower()
    if requested_bot_profile and resolved_bot_profile and requested_bot_profile != resolved_bot_profile:
        raise RuntimeError(
            f"Requested bot profile '{bot_profile_id}' does not match the configured '{profile.get('bot_profile_id', '')}' "
            f"for {focus_id}:{tier_key}."
        )
    return {
        "focus_id": str(focus_id),
        "title": str(option.get("title", focus_id)),
        "difficulty_tier": tier_key,
        "difficulty_value": float(profile.get("difficulty_value", 0.5) or 0.5),
        "bot_profile_id": str(profile.get("bot_profile_id", "") or ""),
        "bot_name": str(profile.get("bot_name", "") or ""),
        "playlist_name": str(profile.get("playlist_name", "") or ""),
        "playlist_file": str(profile.get("playlist_file", "") or ""),
        "playlist_id": str(profile.get("playlist_id", "") or ""),
        "scenario_ids": [str(profile.get("playlist_id", "") or focus_id)],
    }


def rank_to_default_difficulty(rank_tier: str) -> str:
    value = str(rank_tier or "").strip().lower()
    if any(x in value for x in ("bronze", "silver")):
        return "beginner"
    if any(x in value for x in ("gold", "plat")):
        return "intermediate"
    if any(x in value for x in ("diamond", "champ")):
        return "advanced"
    if any(x in value for x in ("grand_champion", "grandchamp", "gc", "ssl", "supersonic")):
        return "expert"
    return "intermediate"


def playlist_root() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "RLBot" / "Dojo" / "Playlists"


def dojo_request_path() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "RLBot" / "Dojo" / "startup_request.json"


def resolve_runtime_python(repo_root: Path | None = None) -> Path | None:
    base = Path(repo_root or _repo_root())
    for rel in (
        Path("venv") / "Scripts" / "python.exe",
        Path(".venv") / "Scripts" / "python.exe",
        Path("venv") / "bin" / "python",
        Path(".venv") / "bin" / "python",
    ):
        candidate = (base / rel).resolve()
        if candidate.exists():
            return candidate
    current = Path(sys.executable)
    return current if current.exists() else None


def _run_import_probe(python_path: Path, modules: Iterable[str]) -> List[str]:
    mod_list = [str(x).strip() for x in modules if str(x).strip()]
    if not python_path or not python_path.exists():
        return mod_list
    probe = (
        "import importlib.util, json\n"
        f"mods = {json.dumps(mod_list)}\n"
        "missing = [m for m in mods if importlib.util.find_spec(m) is None]\n"
        "print(json.dumps(missing))\n"
    )
    try:
        proc = subprocess.run(
            [str(python_path), "-c", probe],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode not in (0, 1):
            return mod_list
        return list(json.loads(str(proc.stdout or "[]").strip() or "[]"))
    except Exception:
        return mod_list


def _run_import_probe_with_paths(python_path: Path, modules: Iterable[str], extra_paths: Iterable[Path]) -> List[str]:
    mod_list = [str(x).strip() for x in modules if str(x).strip()]
    if not python_path or not python_path.exists():
        return mod_list
    path_list = [str(Path(path).resolve()) for path in extra_paths if Path(path).exists()]
    probe = (
        "import importlib.util, json, sys\n"
        f"mods = {json.dumps(mod_list)}\n"
        f"extra_paths = {json.dumps(path_list)}\n"
        "for path in reversed(extra_paths):\n"
        "    if path not in sys.path:\n"
        "        sys.path.insert(0, path)\n"
        "missing = [m for m in mods if importlib.util.find_spec(m) is None]\n"
        "print(json.dumps(missing))\n"
    )
    try:
        proc = subprocess.run(
            [str(python_path), "-c", probe],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode not in (0, 1):
            return mod_list
        return list(json.loads(str(proc.stdout or "[]").strip() or "[]"))
    except Exception:
        return mod_list


def _existing_path(path_value: str) -> str:
    candidate = str(path_value or "").strip()
    if not candidate:
        return ""
    try:
        path = Path(candidate)
        if path.exists():
            return str(path)
    except Exception:
        return ""
    return ""


def _parse_bot_config(config_path: Path) -> configparser.RawConfigParser | None:
    parser = configparser.RawConfigParser()
    try:
        parser.read(config_path, encoding="utf-8")
        return parser
    except Exception:
        return None


def _resolve_cfg_path(config_path: Path, parser: configparser.RawConfigParser | None, option_name: str) -> str:
    if parser is None:
        return ""
    try:
        if not parser.has_option("Locations", option_name):
            return ""
        raw_value = str(parser.get("Locations", option_name) or "").strip()
    except Exception:
        return ""
    if not raw_value:
        return ""
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return str(candidate) if candidate.exists() else ""
    resolved = (config_path.parent / candidate).resolve()
    return str(resolved) if resolved.exists() else ""


def _collect_python_imports(python_file: Path) -> List[str]:
    try:
        tree = ast.parse(python_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = str(alias.name or "").split(".", 1)[0].strip()
                if root and root != "__future__":
                    modules.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            root = str(node.module or "").split(".", 1)[0].strip()
            if root and root != "__future__":
                modules.add(root)
    return sorted(modules)


def _verify_bot_runtime(*, runtime_python: Path | None, bot_profile_id: str, bot_name: str, config_path: str) -> Dict[str, Any]:
    result = {
        "bot_profile_id": str(bot_profile_id or ""),
        "bot_name": str(bot_name or bot_profile_id or ""),
        "config_path": str(config_path or ""),
        "python_file": "",
        "requirements_file": "",
        "ready": False,
        "missing_modules": [],
        "messages": [],
    }
    config_file = Path(str(config_path or ""))
    if not config_file.exists():
        result["messages"].append("Bot config file is missing.")
        return result
    parser = _parse_bot_config(config_file)
    if parser is None:
        result["messages"].append("Bot config file could not be parsed.")
        return result
    python_file = _resolve_cfg_path(config_file, parser, "python_file")
    requirements_file = _resolve_cfg_path(config_file, parser, "requirements_file")
    result["python_file"] = python_file
    result["requirements_file"] = requirements_file
    if not python_file:
        result["messages"].append("Bot python entrypoint is missing from the config or could not be resolved.")
        return result
    import_modules = _collect_python_imports(Path(python_file))
    if not import_modules:
        result["ready"] = True
        return result
    extra_paths = [config_file.parent, config_file.parent.parent]
    missing_modules = _run_import_probe_with_paths(runtime_python, import_modules, extra_paths)
    result["missing_modules"] = missing_modules
    if requirements_file and not Path(requirements_file).exists():
        result["messages"].append("Bot requirements file is configured but missing on disk.")
    if missing_modules:
        result["messages"].append("Missing bot runtime modules: " + ", ".join(missing_modules) + ".")
        return result
    result["ready"] = True
    if requirements_file:
        result["messages"].append("Bot requirements file resolved successfully.")
    return result


def _detect_rlbot_gui() -> Dict[str, Any]:
    override = _existing_path(os.environ.get("RLBOT_GUI_PATH", ""))
    if override:
        return {"detected": True, "path": override, "source": "env"}
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    program_files = os.environ.get("ProgramFiles", "").strip()
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "").strip()
    for source, raw_path in (
        ("localappdata", str(Path(local_appdata) / "RLBotGUIX") if local_appdata else ""),
        ("program_files", str(Path(program_files) / "RLBot") if program_files else ""),
        ("program_files_x86", str(Path(program_files_x86) / "RLBot") if program_files_x86 else ""),
    ):
        existing = _existing_path(raw_path)
        if existing:
            return {"detected": True, "path": existing, "source": source}
    return {"detected": False, "path": "", "source": "not_found"}


def _detect_rocket_league() -> Dict[str, Any]:
    override = _existing_path(os.environ.get("ROCKET_LEAGUE_PATH", ""))
    if override:
        override_path = Path(override)
        if override_path.is_dir():
            exe_candidate = override_path / "Binaries" / "Win64" / "RocketLeague.exe"
            if exe_candidate.exists():
                return {"detected": True, "path": str(exe_candidate)}
        return {"detected": True, "path": override}

    epic_manifest_dir = Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests")
    if epic_manifest_dir.exists():
        for manifest_path in epic_manifest_dir.glob("*.item"):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            display_name = str(payload.get("DisplayName", "") or "")
            app_name = str(payload.get("AppName", "") or "")
            install_location = str(payload.get("InstallLocation", "") or "")
            launch_executable = str(payload.get("LaunchExecutable", "") or "")
            combined = f"{display_name} {app_name}".lower()
            if "rocket league" in combined or app_name.lower() == "sugar":
                install_root = Path(install_location) if install_location else None
                if install_root and launch_executable:
                    candidate = (install_root / Path(launch_executable)).resolve()
                    if candidate.exists():
                        return {"detected": True, "path": str(candidate)}
                if install_root:
                    fallback = install_root / "Binaries" / "Win64" / "RocketLeague.exe"
                    if fallback.exists():
                        return {"detected": True, "path": str(fallback)}
    candidates = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name, "").strip()
        if not root:
            continue
        candidates.extend(
            [
                Path(root) / "Epic Games" / "rocketleague" / "Binaries" / "Win64" / "RocketLeague.exe",
                Path(root) / "Steam" / "steamapps" / "common" / "rocketleague" / "Binaries" / "Win64" / "RocketLeague.exe",
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return {"detected": True, "path": str(candidate)}
    return {"detected": False, "path": ""}


def botpack_roots() -> List[Path]:
    roots: List[Path] = []
    env_override = os.environ.get("RLBOTPACK_ROOT", "").strip()
    if env_override:
        roots.append(Path(env_override))
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    appdata = os.environ.get("APPDATA", "").strip()
    if local_appdata:
        roots.append(Path(local_appdata) / "RLBotGUIX" / "RLBotPackDeletable" / "RLBotPack-master" / "RLBotPack")
    if appdata:
        roots.append(Path(appdata) / "RLBot" / "RLBotPack")
    roots.append(_repo_root() / "artifacts" / "installer_downloads" / "RLBotPack" / "RLBotPack")
    deduped: List[Path] = []
    seen = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        if root.exists():
            deduped.append(root)
    return deduped


def _scan_bot_configs(botpack_root: Path) -> Dict[str, Dict[str, str]]:
    try:
        from rlbot.parsing.directory_scanner import scan_directory_for_bot_configs
    except Exception:
        return _scan_bot_configs_fallback(botpack_root)
    found: Dict[str, Dict[str, str]] = {}
    try:
        bundles = scan_directory_for_bot_configs(botpack_root)
    except Exception:
        return _scan_bot_configs_fallback(botpack_root)
    for bundle in bundles:
        bundle_name = str(getattr(bundle, "name", "") or "").strip()
        config_path = str(getattr(bundle, "config_path", "") or "").strip()
        if not bundle_name or not config_path:
            continue
        lower_name = bundle_name.lower()
        for profile_id, names in BOT_NAME_ALIASES.items():
            if any(lower_name == name.lower() for name in names):
                found[profile_id] = {"name": bundle_name, "config_path": config_path}
    return found


def _scan_bot_configs_fallback(botpack_root: Path) -> Dict[str, Dict[str, str]]:
    found: Dict[str, Dict[str, str]] = {}
    try:
        for config_path in botpack_root.rglob("*.cfg"):
            lower_path = str(config_path).lower()
            for profile_id, hints in BOT_PATH_HINTS.items():
                if profile_id in found:
                    continue
                if any(hint in lower_path for hint in hints):
                    found[profile_id] = {
                        "name": BOT_NAME_ALIASES.get(profile_id, [profile_id])[0],
                        "config_path": str(config_path),
                    }
    except Exception:
        return found
    return found


def detect_bots() -> Dict[str, Any]:
    roots = botpack_roots()
    found: Dict[str, Dict[str, str]] = {}
    for root in roots:
        found.update(_scan_bot_configs(root))
    missing = [profile_id for profile_id in required_bot_profile_ids() if profile_id not in found]
    return {
        "detected": bool(found),
        "roots": [str(root) for root in roots],
        "found": found,
        "missing": missing,
    }


def detect_dojo_source_root() -> Dict[str, Any]:
    candidates = []
    env_override = os.environ.get("ROCKETCOACH_DOJO_SOURCE_ROOT", "").strip()
    if env_override:
        candidates.append(("env", Path(env_override)))
    for root in botpack_roots():
        candidates.append(("rlbotpack", root / "RLDojo" / "Dojo"))
    candidates.append(("sibling_repo", _repo_root().parent / "RLDojo" / "Dojo"))
    seen = set()
    for source, candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if (candidate / "dojo.py").exists():
            return {"detected": True, "path": str(candidate), "source": source}
    return {"detected": False, "path": "", "source": "not_found"}


def dojo_wrapper_config_path() -> Path:
    return _repo_root() / "rocketcoach" / "live_analysis" / "dojo_playlist_wrapper.cfg"


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def build_preflight(*, live_host: str = "127.0.0.1", live_port: int = 8765, service_label: str = "live trainer") -> Dict[str, Any]:
    runtime_python = resolve_runtime_python()
    runtime_python_str = str(runtime_python) if runtime_python else ""
    missing_modules = _run_import_probe(
        runtime_python,
        ["rlbot", "keyboard", "numpy", "matplotlib", "pydantic", "pydantic_core"],
    ) if runtime_python else ["rlbot", "keyboard", "numpy", "matplotlib", "pydantic", "pydantic_core"]
    rlbot_import_ok = "rlbot" not in missing_modules
    rlbot_gui = _detect_rlbot_gui()
    rocket_league = _detect_rocket_league()
    bots = detect_bots()
    dojo_root = detect_dojo_source_root()
    wrapper_cfg = dojo_wrapper_config_path()
    playlists_dir = playlist_root()
    expected_playlists = expected_playlist_files()
    existing_playlists = {p.name for p in playlists_dir.glob("*.json")} if playlists_dir.exists() else set()
    missing_playlists = [name for name in expected_playlists if name not in existing_playlists]
    live_trainer_running = _port_open(live_host, live_port)
    bot_statuses = []
    for bot_profile_id in required_bot_profile_ids():
        bot_details = dict((bots.get("found", {}) or {}).get(bot_profile_id, {}) or {})
        bot_statuses.append(
            _verify_bot_runtime(
                runtime_python=runtime_python,
                bot_profile_id=bot_profile_id,
                bot_name=str(bot_details.get("name", "") or BOT_NAME_ALIASES.get(bot_profile_id, [bot_profile_id])[0]),
                config_path=str(bot_details.get("config_path", "") or ""),
            )
        )
    blocked_bots = [status for status in bot_statuses if not bool(status.get("ready"))]

    messages: List[str] = []
    if not runtime_python:
        messages.append(f"RocketCoach could not find the repo Python runtime used by the {service_label}.")
    if missing_modules:
        messages.append(
            f"The {service_label} runtime is missing Python modules: " + ", ".join(missing_modules) + "."
        )
    if not rocket_league.get("detected"):
        messages.append("Rocket League was not detected in the standard Windows install locations.")
    if not bots.get("detected"):
        messages.append("No RLBot bot configs were found in the detected RLBotPack locations.")
    elif bots.get("missing"):
        messages.append("Some mapped training bots are missing: " + ", ".join(bots["missing"]) + ".")
    if blocked_bots:
        bot_parts = []
        for status in blocked_bots[:6]:
            missing = ", ".join(list(status.get("missing_modules", []) or [])[:3])
            if missing:
                bot_parts.append(f"{status.get('bot_name', status.get('bot_profile_id', 'bot'))} missing {missing}")
            else:
                bot_parts.append(f"{status.get('bot_name', status.get('bot_profile_id', 'bot'))} is not launchable")
        messages.append("Some mapped bots are not launch-ready: " + "; ".join(bot_parts) + ".")
    if not dojo_root.get("detected"):
        messages.append("RLDojo source files were not detected in the installed RLBotPack or sibling RLDojo folder.")
    if not wrapper_cfg.exists():
        messages.append("RocketCoach's Dojo wrapper config is missing from the repo.")
    if missing_playlists:
        messages.append("Some RocketCoach RLDojo playlists are missing: " + ", ".join(missing_playlists[:6]) + ".")
    if not live_trainer_running:
        messages.append(f"The {service_label} is not running on http://{live_host}:{live_port}.")
    if not rlbot_gui.get("detected"):
        messages.append("RLBot GUI was not auto-detected. Direct launch can still work, but GUI features may be unavailable.")

    shared_dependency_ready = bool(
        runtime_python
        and rlbot_import_ok
        and not missing_modules
        and rocket_league.get("detected")
        and dojo_root.get("detected")
        and wrapper_cfg.exists()
        and not missing_playlists
    )
    ready_to_launch = bool(
        shared_dependency_ready
        and not blocked_bots
        and live_trainer_running
    )
    return {
        "host_checks_available": True,
        "last_checked_at": int(time.time()),
        "live_trainer_running": live_trainer_running,
        "shared_dependency_ready": shared_dependency_ready,
        "python_ready": bool(runtime_python),
        "runtime_python": runtime_python_str,
        "runtime_missing_modules": missing_modules,
        "rlbot_import_ok": rlbot_import_ok,
        "rlbot_gui_detected": bool(rlbot_gui.get("detected")),
        "rlbot_gui_path": str(rlbot_gui.get("path", "") or ""),
        "rlbot_gui_detection_source": str(rlbot_gui.get("source", "not_found") or "not_found"),
        "rocket_league_detected": bool(rocket_league.get("detected")),
        "rocket_league_path": str(rocket_league.get("path", "") or ""),
        "playlist_root": str(playlists_dir),
        "playlist_count": len(existing_playlists),
        "scenario_count": len(expected_playlists),
        "missing_playlists": missing_playlists,
        "dojo_source_detected": bool(dojo_root.get("detected")),
        "dojo_source_root": str(dojo_root.get("path", "") or ""),
        "dojo_source": str(dojo_root.get("source", "not_found") or "not_found"),
        "dojo_wrapper_config_path": str(wrapper_cfg),
        "botpack_roots": list(bots.get("roots", []) or []),
        "bot_configs_found": dict(bots.get("found", {}) or {}),
        "missing_bots": list(bots.get("missing", []) or []),
        "bot_statuses": bot_statuses,
        "ready_to_launch": ready_to_launch,
        "messages": messages,
    }
