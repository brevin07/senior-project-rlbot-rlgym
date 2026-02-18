from __future__ import annotations

from bisect import bisect_left
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional
import gzip
import json
import uuid


SOCCAR_BOOST_PADS = [
    {"x": 0.0, "y": -4240.0, "z": 70.0, "size": "small"},
    {"x": -3072.0, "y": -4096.0, "z": 73.0, "size": "big"},
    {"x": 3072.0, "y": -4096.0, "z": 73.0, "size": "big"},
    {"x": 0.0, "y": -2816.0, "z": 70.0, "size": "small"},
    {"x": -3584.0, "y": 0.0, "z": 73.0, "size": "big"},
    {"x": 3584.0, "y": 0.0, "z": 73.0, "size": "big"},
    {"x": 0.0, "y": 2816.0, "z": 70.0, "size": "small"},
    {"x": -3072.0, "y": 4096.0, "z": 73.0, "size": "big"},
    {"x": 3072.0, "y": 4096.0, "z": 73.0, "size": "big"},
    {"x": 0.0, "y": 4240.0, "z": 70.0, "size": "small"},
]


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


class ReviewStore:
    def __init__(self, session_root: Path, db=None):
        self.session_root = Path(session_root)
        self.session_root.mkdir(parents=True, exist_ok=True)
        self._db = db
        self._lock = Lock()
        self._current_session_id: str = ""
        self._current_manifest: Dict[str, Any] = {}
        self._current_timeline: List[Dict[str, Any]] = []
        self._current_events: List[Dict[str, Any]] = []
        self._current_labels: Dict[str, Dict[str, Any]] = {}
        self._current_metrics_timeline: List[Dict[str, Any]] = []

    def _index_path(self) -> Path:
        return self.session_root / "index.json"

    def _list_sessions_unlocked(self) -> List[Dict[str, Any]]:
        index = self._index_path()
        out: List[Dict[str, Any]] = []
        if index.exists():
            try:
                raw = json.loads(index.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    out = [x for x in raw if isinstance(x, dict)]
            except Exception:
                out = []
        if out:
            return out
        for p in self.session_root.iterdir():
            if not p.is_dir():
                continue
            mf = p / "manifest.json"
            if not mf.exists():
                continue
            try:
                manifest = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                continue
            out.append(
                {
                    "session_id": manifest.get("session_id", p.name),
                    "created_at": manifest.get("created_at", ""),
                    "frame_count": manifest.get("frame_count", 0),
                    "duration_s": manifest.get("duration_s", 0.0),
                    "players": manifest.get("players", []),
                    "tracked_player_index": manifest.get("tracked_player_index", 0),
                }
            )
        out.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return out

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._list_sessions_unlocked()

    def _session_dir(self, session_id: str) -> Path:
        return self.session_root / session_id

    def _read_json(self, path: Path, fallback: Any) -> Any:
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return fallback

    def _read_timeline(self, session_dir: Path, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
        frames_name = manifest.get("files", {}).get("frames", "frames.jsonl.gz")
        frames_path = session_dir / frames_name
        if not frames_path.exists():
            return []
        out: List[Dict[str, Any]] = []
        with gzip.open(frames_path, "rt", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
        return out

    def _read_metrics(self, session_dir: Path, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
        name = manifest.get("files", {}).get("metrics_timeline", "metrics_timeline.json.gz")
        path = session_dir / name
        if not path.exists():
            return []
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fp:
                payload = json.load(fp)
            if isinstance(payload, list):
                return payload
        except Exception:
            return []
        return []

    def load_session(self, requested: str) -> Dict[str, Any]:
        with self._lock:
            sid = requested.strip()
            if sid == "latest":
                sessions = self._list_sessions_unlocked()
                sid = str(sessions[0]["session_id"]) if sessions else ""
            if not sid:
                raise RuntimeError("No review sessions found.")

            session_dir = self._session_dir(sid)
            manifest_path = session_dir / "manifest.json"
            if not manifest_path.exists():
                raise RuntimeError(f"Session '{sid}' not found.")
            manifest = self._read_json(manifest_path, {})
            timeline = self._read_timeline(session_dir, manifest)
            events = self._read_json(session_dir / manifest.get("files", {}).get("events", "events.json"), [])
            labels = self._read_json(session_dir / manifest.get("files", {}).get("labels", "labels.json"), {})
            if self._db is not None:
                try:
                    db_labels = self._db.list_event_labels(session_id=sid)
                    if isinstance(db_labels, dict):
                        labels.update(db_labels)
                except Exception:
                    pass
            metrics_timeline = self._read_metrics(session_dir, manifest)
            if not isinstance(events, list):
                events = []
            if not isinstance(labels, dict):
                labels = {}

            self._current_session_id = sid
            self._current_manifest = manifest
            self._current_timeline = timeline
            self._current_events = events
            self._current_labels = labels
            self._current_metrics_timeline = metrics_timeline
            return {
                "session_id": sid,
                "frame_count": len(timeline),
                "duration_s": manifest.get("duration_s", 0.0),
                "players": manifest.get("players", []),
            }

    def current_session(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "session_id": self._current_session_id,
                "loaded": bool(self._current_session_id),
                "frame_count": len(self._current_timeline),
                "duration_s": self._current_manifest.get("duration_s", 0.0),
                "players": self._current_manifest.get("players", []),
            }

    def _score_samples(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        prev = None
        for fr in self._current_timeline:
            s = fr.get("scores", {}) or {}
            cur = (int(s.get("blue", 0)), int(s.get("orange", 0)))
            if prev is None or cur != prev:
                out.append({"time_s": _safe_float(fr.get("t", 0.0)), "blue": cur[0], "orange": cur[1]})
            prev = cur
        return out

    def _clock_samples(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        prev = None
        for fr in self._current_timeline:
            rem = _safe_float(fr.get("clock_s", 0.0))
            kick = bool(fr.get("is_kickoff_pause", False))
            cur = (rem, kick)
            if prev is None or abs(cur[0] - prev[0]) > 1e-5 or cur[1] != prev[1]:
                out.append(
                    {
                        "time_s": _safe_float(fr.get("t", 0.0)),
                        "seconds_remaining": rem,
                        "is_kickoff_pause": kick,
                        "is_overtime": bool(fr.get("is_overtime", False)),
                    }
                )
            prev = cur
        return out

    def session_data(self) -> Dict[str, Any]:
        with self._lock:
            if not self._current_session_id:
                raise RuntimeError("No review session loaded.")
            return {
                "session_id": self._current_session_id,
                "replay_name": f"live_{self._current_session_id}",
                "players": self._current_manifest.get("players", []),
                "tracked_player_index": int(self._current_manifest.get("tracked_player_index", 0)),
                "tracked_player_name": str(self._current_manifest.get("tracked_player_name", "")),
                "timeline": self._current_timeline,
                "duration_s": self._current_manifest.get("duration_s", 0.0),
                "boost_pads": SOCCAR_BOOST_PADS,
                "replay_meta": {
                    "player_teams": self._current_manifest.get("player_teams", {}),
                    "human_player_name": str(self._current_manifest.get("tracked_player_name", "")),
                    "score_samples": self._score_samples(),
                    "clock_samples": self._clock_samples(),
                    "map_name": self._current_manifest.get("map_name", "soccar"),
                },
                "metrics_timeline": self._current_metrics_timeline,
            }

    def events(self) -> List[Dict[str, Any]]:
        with self._lock:
            if not self._current_session_id:
                return []
            labels = self._current_labels
            out = []
            for e in self._current_events:
                copy_e = dict(e)
                eid = str(copy_e.get("event_id", ""))
                if eid and eid in labels:
                    copy_e["label"] = labels[eid].get("label", "")
                    copy_e["label_note"] = labels[eid].get("note", "")
                out.append(copy_e)
            return out

    def labels(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._current_labels)

    def _persist_labels(self) -> None:
        labels_name = self._current_manifest.get("files", {}).get("labels", "labels.json")
        path = self._session_dir(self._current_session_id) / labels_name
        path.write_text(json.dumps(self._current_labels, indent=2, ensure_ascii=True), encoding="utf-8")
        if self._db is not None and self._current_session_id:
            try:
                for event_id, data in self._current_labels.items():
                    self._db.upsert_event_label(
                        session_id=self._current_session_id,
                        event_id=str(event_id),
                        label=str(data.get("label", "")),
                        note=str(data.get("note", "")),
                        author=str(data.get("author", "user")),
                    )
            except Exception:
                pass

    def _persist_events(self) -> None:
        events_name = self._current_manifest.get("files", {}).get("events", "events.json")
        path = self._session_dir(self._current_session_id) / events_name
        path.write_text(json.dumps(self._current_events, indent=2, ensure_ascii=True), encoding="utf-8")

    def upsert_label(self, event_id: str, label: str, note: str, author: str = "user") -> Dict[str, Any]:
        with self._lock:
            if not self._current_session_id:
                raise RuntimeError("No review session loaded.")
            if not event_id:
                raise RuntimeError("Missing event_id.")
            lbl = label.strip().upper()
            if lbl not in {"TP", "FP", "TN", "FN"}:
                raise RuntimeError("label must be one of TP, FP, TN, FN.")
            self._current_labels[event_id] = {"label": lbl, "note": note or "", "author": author or "user"}
            self._persist_labels()
            return dict(self._current_labels[event_id])

    def delete_label(self, event_id: str) -> None:
        with self._lock:
            if not self._current_session_id:
                raise RuntimeError("No review session loaded.")
            self._current_labels.pop(event_id, None)
            self._persist_labels()

    def _nearest_frame_idx(self, t: float) -> int:
        if not self._current_timeline:
            return 0
        times = [_safe_float(fr.get("t", 0.0)) for fr in self._current_timeline]
        i = bisect_left(times, t)
        if i <= 0:
            return 0
        if i >= len(times):
            return len(times) - 1
        return i if abs(times[i] - t) < abs(times[i - 1] - t) else i - 1

    def mark_missed_event(self, event_type: str, t: float, note: str) -> Dict[str, Any]:
        with self._lock:
            if not self._current_session_id:
                raise RuntimeError("No review session loaded.")
            et = event_type.strip().lower()
            if et not in {"whiff", "hesitation"}:
                raise RuntimeError("event_type must be whiff or hesitation.")
            evt = {
                "event_id": f"manual_{uuid.uuid4().hex[:10]}",
                "source": "manual",
                "manual": True,
                "time": _safe_float(t, 0.0),
                "frame_idx": self._nearest_frame_idx(_safe_float(t, 0.0)),
                "type": et,
                "reason": "user_marked_missed",
                "confidence": 1.0,
                "distance": 0.0,
                "opportunity_score": 1.0,
                "context": ["manual", note or ""],
            }
            self._current_events.append(evt)
            self._current_events.sort(key=lambda e: _safe_float(e.get("time", 0.0)))
            self._persist_events()
            return evt
