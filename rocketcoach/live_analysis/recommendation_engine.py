from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
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


def _accumulate_mechanic_signals(sessions: List[Dict[str, Any]]) -> tuple[Dict[str, float], Dict[str, List[str]]]:
    score, evidence = _init_focus_maps()
    # Sessions are newest first. Use small recency weighting.
    for idx, s in enumerate(sessions):
        summary = dict(s.get("summary", {}) or {})
        mech_raw = dict(summary.get("mechanic_scores", {}) or {})
        mech: Dict[str, Any] = {}
        for k, v in mech_raw.items():
            mk = _canon_mech_id(str(k or ""))
            if mk in mech:
                try:
                    mech[mk] = max(float(mech[mk]), float(v))
                except Exception:
                    mech[mk] = mech[mk]
            else:
                mech[mk] = v
        if not mech:
            continue
        weight = max(0.4, 1.0 - 0.12 * idx)
        for focus_id in score.keys():
            raw = mech.get(focus_id)
            if raw is None:
                continue
            try:
                ms = float(raw)
            except Exception:
                continue
            # Deficit relative to "solid" baseline of 75.
            deficit = max(0.0, (75.0 - ms) / 25.0)
            if deficit <= 0.0:
                continue
            score[focus_id] += deficit * weight
            evidence[focus_id].append(f"{s.get('replay_name','session')}: mechanic score {ms:.1f}/100")
    return score, evidence


def _recommend_from_signals(
    label_score: Dict[str, float],
    label_evidence: Dict[str, List[str]],
    mechanic_score: Dict[str, float],
    mechanic_evidence: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    score, evidence = _init_focus_maps()
    for fid in score.keys():
        score[fid] = float(label_score.get(fid, 0.0)) + 1.25 * float(mechanic_score.get(fid, 0.0))
        evidence[fid] = list(label_evidence.get(fid, [])[:3]) + list(mechanic_evidence.get(fid, [])[:3])

    ranked = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
    out: List[Dict[str, Any]] = []
    for focus_id, value in ranked[:3]:
        if value <= 0:
            continue
        out.append(
            {
                "focus_id": focus_id,
                "title": _focus_title(focus_id),
                "score": round(float(value), 3),
                "confidence": round(min(0.99, 0.40 + 0.08 * float(value) + 0.03 * len(evidence.get(focus_id, []))), 3),
                "evidence": evidence.get(focus_id, [])[:5],
                "training": TRAINING_CATALOG.get(focus_id, {}),
            }
        )
    if out:
        return out
    # cold-start fallback
    return [
        {
            "focus_id": "shadow_defense",
            "title": _focus_title("shadow_defense"),
            "score": 0.1,
            "confidence": 0.4,
            "evidence": ["Need more data; using starter recommendation."],
            "training": TRAINING_CATALOG.get("shadow_defense", {}),
        },
        {
            "focus_id": "fifty_fifty_control",
            "title": _focus_title("fifty_fifty_control"),
            "score": 0.1,
            "confidence": 0.4,
            "evidence": ["Need more data; using starter recommendation."],
            "training": TRAINING_CATALOG.get("fifty_fifty_control", {}),
        },
        {
            "focus_id": "flicking",
            "title": _focus_title("flicking"),
            "score": 0.1,
            "confidence": 0.4,
            "evidence": ["Need more data; using starter recommendation."],
            "training": TRAINING_CATALOG.get("flicking", {}),
        },
    ]


def compute_recommendations(db, user_id: int, window_size: int = 5) -> Dict[str, Any]:
    sessions = db.list_replay_sessions_detailed(user_id=int(user_id), limit=max(1, int(window_size)))
    label_score, label_evidence = _accumulate_label_signals(sessions)
    mechanic_score, mechanic_evidence = _accumulate_mechanic_signals(sessions)
    recs = _recommend_from_signals(label_score, label_evidence, mechanic_score, mechanic_evidence)
    return {"window_size": int(window_size), "recommendations": recs, "session_count": len(sessions)}
