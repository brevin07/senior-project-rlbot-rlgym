from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import datetime as dt
import json


FOCUS_CATALOG = [
    {"focus_id": "shadow_defense", "title": "Shadow Defense", "description": "Track the attacker and force low-value touches."},
    {"focus_id": "challenge", "title": "Challenge", "description": "Win possession or force weak opponent touches without giving counters."},
    {"focus_id": "flicking", "title": "Flicks", "description": "Turn controlled dribbles into threatening flick touches."},
    {"focus_id": "carrying_dribbling", "title": "Carries / Dribbles", "description": "Sustain close control and transition into a threatening play."},
    {"focus_id": "aerial_offense", "title": "Aerial Offense", "description": "Attack in the air with cleaner contact setups."},
    {"focus_id": "aerial_defense", "title": "Aerial Defense", "description": "Read and clear aerial threats faster."},
    {"focus_id": "fifty_fifty_control", "title": "50/50 Control", "description": "Win or neutralize contested challenges."},
]


TRAINING_CATALOG = {
    "shadow_defense": {
        "role": "defense",
        "bot_profiles": ["hard_shadow_bot_v1", "front_intercept_bot_v1"],
        "scenarios": ["shadow_defense_near", "shadow_defense_far"],
    },
    "challenge": {
        "role": "defense",
        "bot_profiles": ["front_intercept_bot_v1", "pressure_breakout_bot_v1"],
        "scenarios": ["early_challenge_front", "early_challenge_recovering"],
    },
    "flicking": {
        "role": "offense",
        "bot_profiles": ["goalie_pressure_bot_v1", "shadow_block_bot_v1"],
        "scenarios": ["flick_under_pressure", "carry_into_flick"],
    },
    "carrying_dribbling": {
        "role": "offense",
        "bot_profiles": ["goalie_pressure_bot_v1", "shadow_block_bot_v1"],
        "scenarios": ["carry_into_flick", "carry_under_pressure"],
    },
    "aerial_offense": {
        "role": "offense",
        "bot_profiles": ["aerial_defense_bot_v1", "backboard_block_bot_v1"],
        "scenarios": ["aerial_shot_setup", "double_touch_setup"],
    },
    "aerial_defense": {
        "role": "defense",
        "bot_profiles": ["aerial_attack_bot_v1", "redirect_attack_bot_v1"],
        "scenarios": ["aerial_save_net", "backboard_defense"],
    },
    "fifty_fifty_control": {
        "role": "neutral",
        "bot_profiles": ["fifty_fifty_bot_v1", "challenge_timing_bot_v1"],
        "scenarios": ["midfield_fifty", "corner_fifty"],
    },
}

_MIN_MECH_CONFIDENCE = 0.30  # below this = mechanic not played (score=50, conf=0.2 from grader)

MECH_SCORE_ALIASES = {
    "early_challenge_timing": "challenge",
    "flicking_carry_offense": "flicking",
}


def _canon_mech_id(mid: str) -> str:
    m = str(mid or "").strip()
    return MECH_SCORE_ALIASES.get(m, m)


def _safe_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _focus_title(focus_id: str) -> str:
    for x in FOCUS_CATALOG:
        if x["focus_id"] == focus_id:
            return x["title"]
    return focus_id


def _replay_label(session: Dict[str, Any]) -> str:
    summary = dict(session.get("summary", {}) or {})
    for candidate in [summary.get("replay_date_iso"), session.get("created_at")]:
        raw = str(candidate or "").strip()
        if not raw:
            continue
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            continue
        return f"{parsed.month}-{parsed.day}-{str(parsed.year)[-2:]}.replay"
    replay_name = str(session.get("replay_name", "") or "").strip()
    return replay_name or "Replay.replay"


def _init_focus_maps() -> tuple[Dict[str, float], Dict[str, List[str]]]:
    score: Dict[str, float] = {x["focus_id"]: 0.0 for x in FOCUS_CATALOG}
    evidence: Dict[str, List[str]] = {x["focus_id"]: [] for x in FOCUS_CATALOG}
    return score, evidence


def _accumulate_label_signals(sessions: List[Dict[str, Any]]) -> tuple[Dict[str, float], Dict[str, List[str]]]:
    score, evidence = _init_focus_maps()
    for s in sessions:
        manifest = s.get("artifact_manifest", {}) or {}
        session_dir = Path(str(manifest.get("session_dir", "")))
        if not session_dir.exists():
            continue
        labels = _safe_json(session_dir / "labels.json", {})
        events = _safe_json(session_dir / "events.json", [])
        by_id = {str(e.get("event_id", "")): e for e in events if isinstance(e, dict)}
        for eid, payload in labels.items():
            if not isinstance(payload, dict):
                continue
            if str(payload.get("label", "")).upper() != "FP":
                continue
            evt = by_id.get(str(eid), {})
            et = str(evt.get("type", "")).lower()
            reason = str(evt.get("reason", "")).lower()
            note = str(payload.get("note", "")).lower()

            if et == "whiff":
                score["fifty_fifty_control"] += 1.0
                evidence["fifty_fifty_control"].append(f"{eid}: whiff FP")
                if "flip" in reason or "flip" in note or "flick" in note:
                    score["flicking"] += 1.2
                    evidence["flicking"].append(f"{eid}: flip/flick FP trend")
            elif et == "hesitation":
                score["challenge"] += 1.0
                evidence["challenge"].append(f"{eid}: hesitation FP")
                if "reposition" in note or "driving away" in note or "boost" in note:
                    score["shadow_defense"] += 0.8
                    evidence["shadow_defense"].append(f"{eid}: reposition/disengage under pressure")

            if "aerial" in note or "air" in reason:
                score["aerial_defense"] += 0.7
                score["aerial_offense"] += 0.7
    return score, evidence


def _accumulate_mechanic_signals(
    sessions: List[Dict[str, Any]],
) -> tuple[Dict[str, float], Dict[str, int], Dict[str, List[str]]]:
    """Return (weighted_avg_scores, n_valid, evidence).

    Mechanics with confidence < _MIN_MECH_CONFIDENCE are skipped — they
    represent mechanics not actually played in the replay (event_count=0 →
    grader assigns score=50, confidence=0.2).
    """
    _, evidence = _init_focus_maps()
    numerator: Dict[str, float] = {x["focus_id"]: 0.0 for x in FOCUS_CATALOG}
    denominator: Dict[str, float] = {x["focus_id"]: 0.0 for x in FOCUS_CATALOG}
    n_valid: Dict[str, int] = {x["focus_id"]: 0 for x in FOCUS_CATALOG}

    # Sessions are newest first. Use small recency weighting.
    for idx, s in enumerate(sessions):
        summary = dict(s.get("summary", {}) or {})
        mech_raw = dict(summary.get("mechanic_scores", {}) or {})
        conf_raw = dict(summary.get("mechanic_confidence", {}) or {})

        # Canonicalise aliases, taking max on collision for both score and conf.
        mech: Dict[str, float] = {}
        conf: Dict[str, float] = {}
        for k, v in mech_raw.items():
            mk = _canon_mech_id(str(k or ""))
            try:
                fv = float(v)
            except Exception:
                continue
            mech[mk] = max(mech[mk], fv) if mk in mech else fv
        for k, v in conf_raw.items():
            mk = _canon_mech_id(str(k or ""))
            try:
                fv = float(v)
            except Exception:
                continue
            conf[mk] = max(conf[mk], fv) if mk in conf else fv

        if not mech:
            continue

        weight = max(0.4, 1.0 - 0.12 * idx)
        replay_name = _replay_label(s)

        for focus_id in numerator.keys():
            ms = mech.get(focus_id)
            if ms is None:
                continue
            c = conf.get(focus_id, 0.0)  # missing conf key → treat as not-played
            if c < _MIN_MECH_CONFIDENCE:
                continue
            numerator[focus_id] += ms * weight
            denominator[focus_id] += weight
            n_valid[focus_id] += 1
            evidence[focus_id].append(f"{replay_name}: mechanic score {ms:.1f}/100 (conf {c:.2f})")

    weighted_avg: Dict[str, float] = {}
    for focus_id in numerator.keys():
        if denominator[focus_id] > 0.0:
            weighted_avg[focus_id] = numerator[focus_id] / denominator[focus_id]
        else:
            weighted_avg[focus_id] = 0.0

    return weighted_avg, n_valid, evidence


_COLD_START_ORDER = ["shadow_defense", "fifty_fifty_control", "flicking"]


def _cold_start_entry(focus_id: str) -> Dict[str, Any]:
    return {
        "focus_id": focus_id,
        "title": _focus_title(focus_id),
        "score": 50.0,
        "confidence": 0.35,
        "evidence": ["Need more data; using starter recommendation."],
        "training": TRAINING_CATALOG.get(focus_id, {}),
    }


def _recommend_from_signals(
    label_score: Dict[str, float],
    label_evidence: Dict[str, List[str]],
    mechanic_avg: Dict[str, float],
    n_valid: Dict[str, int],
    mechanic_evidence: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    # Build candidates from mechanics that were actually played (n_valid > 0).
    candidates = [
        (fid, mechanic_avg[fid], n_valid[fid])
        for fid in mechanic_avg
        if n_valid.get(fid, 0) > 0
    ]
    # Lowest score = highest need → rank ascending.
    candidates.sort(key=lambda t: t[1])

    out: List[Dict[str, Any]] = []
    used: set = set()
    for focus_id, avg_score, nv in candidates[:3]:
        ev = list(label_evidence.get(focus_id, [])[:3]) + list(mechanic_evidence.get(focus_id, [])[:3])
        out.append(
            {
                "focus_id": focus_id,
                "title": _focus_title(focus_id),
                "score": round(float(avg_score), 2),
                "confidence": round(min(0.99, 0.35 + 0.12 * nv), 3),
                "evidence": ev[:5],
                "training": TRAINING_CATALOG.get(focus_id, {}),
            }
        )
        used.add(focus_id)

    # Pad to 3 with cold-start defaults.
    for fid in _COLD_START_ORDER:
        if len(out) >= 3:
            break
        if fid not in used:
            out.append(_cold_start_entry(fid))
            used.add(fid)

    return out


def compute_recommendations(db, user_id: int, window_size: int = 5) -> Dict[str, Any]:
    sessions = db.list_replay_sessions_detailed(user_id=int(user_id), limit=max(1, int(window_size)))
    if not sessions:
        return {"window_size": int(window_size), "recommendations": [], "session_count": 0}
    label_score, label_evidence = _accumulate_label_signals(sessions)
    mechanic_avg, n_valid, mechanic_evidence = _accumulate_mechanic_signals(sessions)
    recs = _recommend_from_signals(label_score, label_evidence, mechanic_avg, n_valid, mechanic_evidence)
    return {"window_size": int(window_size), "recommendations": recs, "session_count": len(sessions)}
