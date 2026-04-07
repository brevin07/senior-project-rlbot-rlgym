from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _candidate_dojo_roots() -> list[Path]:
    candidates: list[Path] = []
    env_override = os.environ.get("ROCKETCOACH_DOJO_SOURCE_ROOT", "").strip()
    if env_override:
        candidates.append(Path(env_override))
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        candidates.append(
            Path(local_appdata)
            / "RLBotGUIX"
            / "RLBotPackDeletable"
            / "RLBotPack-master"
            / "RLBotPack"
            / "RLDojo"
            / "Dojo"
        )
    candidates.append(Path(__file__).resolve().parents[3] / "RLDojo" / "Dojo")
    deduped: list[Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if (candidate / "dojo.py").exists():
            deduped.append(candidate)
    return deduped


def _load_request() -> dict:
    request_path = Path(
        os.environ.get(
            "ROCKETCOACH_DOJO_REQUEST_PATH",
            str(Path(os.environ.get("APPDATA", str(Path.home()))) / "RLBot" / "Dojo" / "startup_request.json"),
        )
    )
    if not request_path.exists():
        return {}
    try:
        payload = json.loads(request_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    try:
        request_path.unlink(missing_ok=True)
    except Exception:
        pass
    return dict(payload or {})


def _import_dojo():
    for dojo_root in _candidate_dojo_roots():
        if str(dojo_root) not in sys.path:
            sys.path.insert(0, str(dojo_root))
        try:
            from dojo import Dojo  # type: ignore

            return Dojo
        except Exception:
            continue
    raise RuntimeError("Could not locate a usable RLDojo source root.")


_BaseDojo = _import_dojo()


class RocketCoachDojo(_BaseDojo):
    def __init__(self):
        super().__init__()
        self._rocketcoach_request = _load_request()
        self._startup_playlist_applied = False

    def _initialize_components(self):
        super()._initialize_components()
        self._apply_startup_playlist()

    def _apply_startup_playlist(self):
        if self._startup_playlist_applied:
            return
        playlist_name = str(self._rocketcoach_request.get("playlist_name", "") or "").strip()
        playlist_id = str(self._rocketcoach_request.get("playlist_id", "") or "").strip()
        if not playlist_name and not playlist_id:
            self._startup_playlist_applied = True
            return
        try:
            # PlaylistRegistry keys playlists by filename stem (e.g. "rc_shadow_defense_advanced").
            # Try playlist_id (filename stem) first; fall back to searching by display name.
            registry = getattr(self, "playlist_registry", None)
            lookup_key = playlist_id or playlist_name
            if registry is not None and lookup_key not in registry.playlists:
                for key, pl in registry.playlists.items():
                    if getattr(pl, "name", key) == playlist_name:
                        lookup_key = key
                        break
            self.set_playlist(lookup_key)
            print(f"[rocketcoach-dojo] preselected playlist: {lookup_key}")
        except Exception as exc:
            print(f"[rocketcoach-dojo] failed to preselect playlist '{playlist_name}' (id={playlist_id}): {exc}")
        finally:
            self._startup_playlist_applied = True


if __name__ == "__main__":
    RocketCoachDojo().run()
