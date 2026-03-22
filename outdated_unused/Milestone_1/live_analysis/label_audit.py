from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


KEYWORDS = {
    "reposition": ["reposition", "repositioning", "adjustment", "turn", "slowed", "wiggled"],
    "flip_flick": ["flip", "flipping", "flick", "air", "aerial"],
    "disengage": ["drove away", "going in", "no point", "safe", "leave"],
    "bump_demo": ["bump", "demo", "opponent"],
}


def _read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _load_frames(session_dir: Path) -> List[Dict[str, Any]]:
    frames_path = session_dir / "frames.jsonl.gz"
    if not frames_path.exists():
        return []
    out = []
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


def _keyword_tags(note: str) -> List[str]:
    low = (note or "").lower()
    tags = []
    for k, words in KEYWORDS.items():
        if any(w in low for w in words):
            tags.append(k)
    return tags


def _iter_sessions(root: Path, session_id: str | None) -> Iterable[Path]:
    if session_id:
        p = root / session_id
        if p.exists() and p.is_dir():
            yield p
        return
    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in dirs:
        yield p


def audit_session(session_dir: Path) -> Dict[str, Any]:
    labels = _read_json(session_dir / "labels.json", {})
    events = _read_json(session_dir / "events.json", [])
    manifest = _read_json(session_dir / "manifest.json", {})
    frames = _load_frames(session_dir)
    by_id = {str(e.get("event_id", "")): e for e in events if isinstance(e, dict)}

    label_counts = Counter()
    type_label_counts = Counter()
    type_reason_counts = Counter()
    note_tag_counts = Counter()
    fp_details = []
    missing_labels = 0

    for eid, payload in labels.items():
        if not isinstance(payload, dict):
            continue
        lbl = str(payload.get("label", "")).upper().strip()
        if not lbl:
            continue
        evt = by_id.get(str(eid), {})
        ev_type = str(evt.get("type", "unknown"))
        reason = str(evt.get("reason", ""))
        note = str(payload.get("note", "") or "")
        tags = _keyword_tags(note)

        label_counts[lbl] += 1
        type_label_counts[(ev_type, lbl)] += 1
        if reason:
            type_reason_counts[(ev_type, reason, lbl)] += 1
        for t in tags:
            note_tag_counts[(lbl, t)] += 1

        if lbl == "FP":
            fp_details.append(
                {
                    "event_id": eid,
                    "type": ev_type,
                    "reason": reason,
                    "time": evt.get("time"),
                    "distance": evt.get("distance"),
                    "confidence": evt.get("confidence"),
                    "opportunity_score": evt.get("opportunity_score"),
                    "note": note,
                    "note_tags": tags,
                }
            )
    for e in events:
        if str(e.get("event_id", "")) not in labels:
            missing_labels += 1

    return {
        "session_id": manifest.get("session_id", session_dir.name),
        "frame_count": len(frames),
        "event_count": len(events),
        "labeled_event_count": sum(label_counts.values()),
        "unlabeled_event_count": missing_labels,
        "labels": dict(label_counts),
        "type_label": {f"{k[0]}::{k[1]}": v for k, v in type_label_counts.items()},
        "type_reason_label": {f"{k[0]}::{k[1]}::{k[2]}": v for k, v in type_reason_counts.items()},
        "note_tags": {f"{k[0]}::{k[1]}": v for k, v in note_tag_counts.items()},
        "fp_details": fp_details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit labeled review sessions for FP/TP patterns.")
    parser.add_argument("--session-root", default="", help="Path to artifacts/live_sessions.")
    parser.add_argument("--session-id", default="", help="Specific session folder name.")
    parser.add_argument("--out", default="", help="Optional output JSON file path.")
    parser.add_argument("--max-sessions", type=int, default=1, help="Number of sessions to audit when --session-id omitted.")
    args = parser.parse_args()

    root = Path(args.session_root).resolve() if args.session_root else (Path(__file__).resolve().parents[2] / "artifacts" / "live_sessions")
    if not root.exists():
        raise SystemExit(f"Session root not found: {root}")

    summaries = []
    for i, p in enumerate(_iter_sessions(root, args.session_id.strip() or None)):
        if i >= max(1, int(args.max_sessions)):
            break
        summaries.append(audit_session(p))

    report = {"session_root": str(root), "summaries": summaries}
    text = json.dumps(report, indent=2, ensure_ascii=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote report: {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
