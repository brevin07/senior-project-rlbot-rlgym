from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import cos, sin
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
import gzip
import json

from future_event_engine import apply_whiff_rate_from_events, refine_events_posthoc
import uuid


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _quat_from_euler(pitch: float, yaw: float, roll: float) -> tuple[float, float, float, float]:
    # RLBot rotation values are radians; convert to quaternion for front-end interpolation.
    cy = cos(yaw * 0.5)
    sy = sin(yaw * 0.5)
    cp = cos(pitch * 0.5)
    sp = sin(pitch * 0.5)
    cr = cos(roll * 0.5)
    sr = sin(roll * 0.5)
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    return qx, qy, qz, qw


def _car_name(car: Any, idx: int) -> str:
    raw = getattr(car, "name", "")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    name = str(raw or "").strip()
    return name or f"player_{idx}"


@dataclass
class RecorderPaths:
    session_dir: Path
    frames_file: Path
    events_file: Path
    labels_file: Path
    metrics_file: Path
    manifest_file: Path


class SessionRecorder:
    def __init__(
        self,
        *,
        session_root: Path,
        tick_rate: float,
        tracked_player_index: int,
        enabled: bool = True,
    ) -> None:
        self.enabled = bool(enabled)
        self.session_root = Path(session_root)
        self.tick_rate = float(tick_rate)
        self.tracked_player_index = int(tracked_player_index)
        self.session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.paths = RecorderPaths(
            session_dir=self.session_root / self.session_id,
            frames_file=self.session_root / self.session_id / "frames.jsonl.gz",
            events_file=self.session_root / self.session_id / "events.json",
            labels_file=self.session_root / self.session_id / "labels.json",
            metrics_file=self.session_root / self.session_id / "metrics_timeline.json.gz",
            manifest_file=self.session_root / self.session_id / "manifest.json",
        )
        self._lock = Lock()
        self._started = False
        self._finalized = False
        self._frames_fp = None
        self._frame_count = 0
        self._frame_times: List[float] = []
        self._players: List[str] = []
        self._player_teams: Dict[str, int] = {}
        self._tracked_player_name: str = ""
        self._events: List[Dict[str, Any]] = []
        self._event_seen: set[str] = set()
        self._metrics_timeline: List[Dict[str, Any]] = []

    def start(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._started:
                return
            self.paths.session_dir.mkdir(parents=True, exist_ok=True)
            self._frames_fp = gzip.open(self.paths.frames_file, "wt", encoding="utf-8")
            if not self.paths.labels_file.exists():
                self.paths.labels_file.write_text("{}", encoding="utf-8")
            self._started = True

    def _capture_scores(self, packet: Any) -> Dict[str, int]:
        blue = 0
        orange = 0
        try:
            teams = getattr(packet, "teams", None)
            if teams and len(teams) >= 2:
                blue = _safe_int(getattr(teams[0], "score", 0))
                orange = _safe_int(getattr(teams[1], "score", 0))
        except Exception:
            pass
        return {"blue": blue, "orange": orange}

    def _capture_frame(self, packet: Any) -> Dict[str, Any]:
        now = _safe_float(getattr(getattr(packet, "game_info", None), "seconds_elapsed", 0.0))
        game_info = getattr(packet, "game_info", None)
        ball = getattr(packet, "game_ball", None)
        bp = getattr(getattr(ball, "physics", None), "location", None)
        bv = getattr(getattr(ball, "physics", None), "velocity", None)
        ba = getattr(getattr(ball, "physics", None), "angular_velocity", None)
        brot = getattr(getattr(ball, "physics", None), "rotation", None)
        bpitch = _safe_float(getattr(brot, "pitch", 0.0))
        byaw = _safe_float(getattr(brot, "yaw", 0.0))
        broll = _safe_float(getattr(brot, "roll", 0.0))
        bqx, bqy, bqz, bqw = _quat_from_euler(bpitch, byaw, broll)

        players: List[Dict[str, Any]] = []
        num_cars = _safe_int(getattr(packet, "num_cars", 0))
        tracked_name = ""
        for i in range(num_cars):
            car = packet.game_cars[i]
            physics = getattr(car, "physics", None)
            loc = getattr(physics, "location", None)
            vel = getattr(physics, "velocity", None)
            ang = getattr(physics, "angular_velocity", None)
            rot = getattr(physics, "rotation", None)
            pitch = _safe_float(getattr(rot, "pitch", 0.0))
            yaw = _safe_float(getattr(rot, "yaw", 0.0))
            roll = _safe_float(getattr(rot, "roll", 0.0))
            qx, qy, qz, qw = _quat_from_euler(pitch, yaw, roll)
            name = _car_name(car, i)
            if i == self.tracked_player_index:
                tracked_name = name
            team = _safe_int(getattr(car, "team", i % 2))
            self._player_teams[name] = team
            players.append(
                {
                    "name": name,
                    "team": team,
                    "x": _safe_float(getattr(loc, "x", 0.0)),
                    "y": _safe_float(getattr(loc, "y", 0.0)),
                    "z": _safe_float(getattr(loc, "z", 0.0)),
                    "vx": _safe_float(getattr(vel, "x", 0.0)),
                    "vy": _safe_float(getattr(vel, "y", 0.0)),
                    "vz": _safe_float(getattr(vel, "z", 0.0)),
                    "wx": _safe_float(getattr(ang, "x", 0.0)),
                    "wy": _safe_float(getattr(ang, "y", 0.0)),
                    "wz": _safe_float(getattr(ang, "z", 0.0)),
                    "pitch": pitch,
                    "yaw": yaw,
                    "roll": roll,
                    "qx": qx,
                    "qy": qy,
                    "qz": qz,
                    "qw": qw,
                    "boost": _safe_float(getattr(car, "boost", 0.0)),
                    "is_demolished": bool(getattr(car, "is_demolished", False)),
                    "has_wheel_contact": bool(getattr(car, "has_wheel_contact", False)),
                }
            )

        self._players = [p["name"] for p in players]
        if tracked_name:
            self._tracked_player_name = tracked_name
        return {
            "idx": self._frame_count,
            "t": now,
            "ball": {
                "x": _safe_float(getattr(bp, "x", 0.0)),
                "y": _safe_float(getattr(bp, "y", 0.0)),
                "z": _safe_float(getattr(bp, "z", 0.0)),
                "vx": _safe_float(getattr(bv, "x", 0.0)),
                "vy": _safe_float(getattr(bv, "y", 0.0)),
                "vz": _safe_float(getattr(bv, "z", 0.0)),
                "wx": _safe_float(getattr(ba, "x", 0.0)),
                "wy": _safe_float(getattr(ba, "y", 0.0)),
                "wz": _safe_float(getattr(ba, "z", 0.0)),
                "pitch": bpitch,
                "yaw": byaw,
                "roll": broll,
                "qx": bqx,
                "qy": bqy,
                "qz": bqz,
                "qw": bqw,
            },
            "players": players,
            "scores": self._capture_scores(packet),
            "clock_s": _safe_float(getattr(game_info, "game_time_remaining", 0.0)),
            "is_overtime": bool(getattr(game_info, "is_overtime", False)),
            "is_kickoff_pause": bool(getattr(game_info, "is_kickoff_pause", False)),
        }

    def _event_key(self, evt: Dict[str, Any]) -> str:
        t = round(_safe_float(evt.get("time", 0.0)), 3)
        return f"{evt.get('type','event')}|{evt.get('reason','')}|{t}|{round(_safe_float(evt.get('distance', 0.0)), 2)}"

    def record(self, packet: Any, current_metrics: Dict[str, Any], events: List[Dict[str, Any]]) -> None:
        if not self.enabled:
            return
        with self._lock:
            if not self._started or self._finalized:
                return
            frame = self._capture_frame(packet)
            self._frames_fp.write(json.dumps(frame, ensure_ascii=True) + "\n")
            self._frame_count += 1
            self._frame_times.append(_safe_float(frame.get("t", 0.0)))

            pt = _safe_float(current_metrics.get("timestamp", frame["t"]))
            metric_point = {"t": pt}
            for k, v in current_metrics.items():
                if isinstance(v, (int, float)):
                    metric_point[k] = float(v)
            self._metrics_timeline.append(metric_point)

            for evt in events or []:
                key = self._event_key(evt)
                if key in self._event_seen:
                    continue
                self._event_seen.add(key)
                evt_time = _safe_float(evt.get("time", frame["t"]))
                self._events.append(
                    {
                        "event_id": f"evt_{len(self._events)+1:05d}",
                        "source": "model",
                        "time": evt_time,
                        "frame_idx": max(0, self._frame_count - 1),
                        "type": str(evt.get("type", "event")),
                        "reason": str(evt.get("reason", "")),
                        "confidence": _safe_float(evt.get("confidence", 0.0)),
                        "distance": _safe_float(evt.get("distance", 0.0)),
                        "opportunity_score": _safe_float(evt.get("opportunity_score", 0.0)),
                        "context": list(evt.get("context", []) or []),
                    }
                )

    def _write_index(self, manifest: Dict[str, Any]) -> None:
        index_path = self.session_root / "index.json"
        existing: List[Dict[str, Any]] = []
        if index_path.exists():
            try:
                existing = json.loads(index_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        existing = [x for x in existing if x.get("session_id") != self.session_id]
        existing.insert(
            0,
            {
                "session_id": self.session_id,
                "created_at": manifest["created_at"],
                "frame_count": manifest["frame_count"],
                "duration_s": manifest["duration_s"],
                "players": manifest["players"],
                "tracked_player_index": self.tracked_player_index,
            },
        )
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(existing, indent=2, ensure_ascii=True), encoding="utf-8")

    def finalize(self) -> Optional[Path]:
        if not self.enabled:
            return None
        with self._lock:
            if not self._started or self._finalized:
                return self.paths.session_dir
            self._finalized = True
            if self._frames_fp is not None:
                self._frames_fp.close()
                self._frames_fp = None

            timeline: List[Dict[str, Any]] = []
            try:
                with gzip.open(self.paths.frames_file, "rt", encoding="utf-8") as fp:
                    for line in fp:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            timeline.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                timeline = []

            if timeline and self._tracked_player_name:
                refined, counts = refine_events_posthoc(timeline, self._tracked_player_name, self._events)
                self._events = refined
                apply_whiff_rate_from_events(self._metrics_timeline, self._events, window_s=10.0)
                for p in self._metrics_timeline:
                    for k, v in counts.items():
                        p[k] = float(v)

            self._events.sort(key=lambda e: float(e.get("time", 0.0)))
            self.paths.events_file.write_text(json.dumps(self._events, indent=2, ensure_ascii=True), encoding="utf-8")

            with gzip.open(self.paths.metrics_file, "wt", encoding="utf-8") as fp:
                json.dump(self._metrics_timeline, fp, ensure_ascii=True)

            duration_s = 0.0
            if self._frame_times:
                duration_s = max(0.0, self._frame_times[-1] - self._frame_times[0])
            manifest = {
                "schema_version": 1,
                "session_id": self.session_id,
                "created_at": _utc_now_iso(),
                "map_name": "soccar",
                "tick_rate": self.tick_rate,
                "tracked_player_index": self.tracked_player_index,
                "tracked_player_name": self._tracked_player_name,
                "players": self._players,
                "player_teams": self._player_teams,
                "frame_count": self._frame_count,
                "duration_s": duration_s,
                "files": {
                    "frames": self.paths.frames_file.name,
                    "events": self.paths.events_file.name,
                    "labels": self.paths.labels_file.name,
                    "metrics_timeline": self.paths.metrics_file.name,
                },
            }
            self.paths.manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
            self._write_index(manifest)
            return self.paths.session_dir
