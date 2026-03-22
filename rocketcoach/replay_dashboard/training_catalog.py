from __future__ import annotations

from typing import Any, Dict, List


DIFFICULTY_TIERS: Dict[str, Dict[str, Any]] = {
    "beginner": {
        "label": "Beginner",
        "difficulty_value": 0.3,
        "summary": "More forgiving pressure and slower opponent reactions.",
    },
    "intermediate": {
        "label": "Intermediate",
        "difficulty_value": 0.6,
        "summary": "Balanced pressure, reads, and challenge timing.",
    },
    "expert": {
        "label": "Expert",
        "difficulty_value": 0.9,
        "summary": "Fast reads, tighter pressure windows, and cleaner recoveries.",
    },
}


FOCUS_CATALOG: Dict[str, Dict[str, Any]] = {
    "shadow_defense": {
        "title": "Shadow Defense",
        "bot_required": True,
        "drill_mode_options": ["bot_duel"],
        "scenario_ids": ["shadow_defense_lane"],
        "bot_family": "shadow_defense_bot",
    },
    "challenge": {
        "title": "Challenge Timing",
        "bot_required": True,
        "drill_mode_options": ["bot_duel"],
        "scenario_ids": ["ground_duel_center"],
        "bot_family": "challenge_timing_bot",
    },
    "fifty_fifty_control": {
        "title": "50/50 Control",
        "bot_required": True,
        "drill_mode_options": ["bot_duel"],
        "scenario_ids": ["ground_duel_center"],
        "bot_family": "fifty_fifty_bot",
    },
    "aerial_defense": {
        "title": "Aerial Defense",
        "bot_required": True,
        "drill_mode_options": ["bot_duel"],
        "scenario_ids": ["aerial_recovery_test"],
        "bot_family": "aerial_defense_bot",
    },
    "aerial_offense": {
        "title": "Aerial Offense",
        "bot_required": True,
        "drill_mode_options": ["bot_duel"],
        "scenario_ids": ["aerial_recovery_test"],
        "bot_family": "aerial_pressure_bot",
    },
    "flicking": {
        "title": "Flicks",
        "bot_required": False,
        "drill_mode_options": ["solo_execution", "ghost_pressure"],
        "scenario_ids": ["ground_duel_center"],
        "bot_family": "goalie_pressure_bot",
    },
    "carrying_dribbling": {
        "title": "Carry + Dribble",
        "bot_required": False,
        "drill_mode_options": ["solo_execution", "ghost_pressure", "boost_route_repetition"],
        "scenario_ids": ["ground_duel_center"],
        "bot_family": "goalie_pressure_bot",
    },
}


BOT_PROFILES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "shadow_defense_bot": {
        "beginner": {"bot_profile_id": "shadow_defense_bot_beginner", "difficulty_value": 0.3, "play_style": "conservative_shadow"},
        "intermediate": {"bot_profile_id": "shadow_defense_bot_intermediate", "difficulty_value": 0.6, "play_style": "pressure_shadow"},
        "expert": {"bot_profile_id": "shadow_defense_bot_expert", "difficulty_value": 0.9, "play_style": "tight_shadow"},
    },
    "challenge_timing_bot": {
        "beginner": {"bot_profile_id": "challenge_timing_bot_beginner", "difficulty_value": 0.3, "play_style": "delayed_challenge"},
        "intermediate": {"bot_profile_id": "challenge_timing_bot_intermediate", "difficulty_value": 0.6, "play_style": "balanced_challenge"},
        "expert": {"bot_profile_id": "challenge_timing_bot_expert", "difficulty_value": 0.9, "play_style": "instant_challenge"},
    },
    "fifty_fifty_bot": {
        "beginner": {"bot_profile_id": "fifty_fifty_bot_beginner", "difficulty_value": 0.3, "play_style": "slow_commit"},
        "intermediate": {"bot_profile_id": "fifty_fifty_bot_intermediate", "difficulty_value": 0.6, "play_style": "balanced_commit"},
        "expert": {"bot_profile_id": "fifty_fifty_bot_expert", "difficulty_value": 0.9, "play_style": "fast_commit"},
    },
    "aerial_defense_bot": {
        "beginner": {"bot_profile_id": "aerial_defense_bot_beginner", "difficulty_value": 0.3, "play_style": "late_aerial"},
        "intermediate": {"bot_profile_id": "aerial_defense_bot_intermediate", "difficulty_value": 0.6, "play_style": "standard_aerial"},
        "expert": {"bot_profile_id": "aerial_defense_bot_expert", "difficulty_value": 0.9, "play_style": "fast_aerial"},
    },
    "aerial_pressure_bot": {
        "beginner": {"bot_profile_id": "aerial_pressure_bot_beginner", "difficulty_value": 0.3, "play_style": "floaty_pressure"},
        "intermediate": {"bot_profile_id": "aerial_pressure_bot_intermediate", "difficulty_value": 0.6, "play_style": "steady_pressure"},
        "expert": {"bot_profile_id": "aerial_pressure_bot_expert", "difficulty_value": 0.9, "play_style": "aggressive_pressure"},
    },
    "goalie_pressure_bot": {
        "beginner": {"bot_profile_id": "goalie_pressure_bot_beginner", "difficulty_value": 0.3, "play_style": "late_save"},
        "intermediate": {"bot_profile_id": "goalie_pressure_bot_intermediate", "difficulty_value": 0.6, "play_style": "basic_save"},
        "expert": {"bot_profile_id": "goalie_pressure_bot_expert", "difficulty_value": 0.9, "play_style": "tight_save"},
    },
}


NON_BOT_DRILL_SUMMARIES: Dict[str, str] = {
    "solo_execution": "No defender. Focus on clean setup, first touch, and repeatability.",
    "recovery_timer": "Recover and regain control before the timer expires.",
    "target_contact_sequence": "Hit the intended contact sequence with control.",
    "boost_route_repetition": "Repeat a boost-efficient movement route through the drill.",
    "ghost_pressure": "Run the mechanic with implied pressure but without a live opponent.",
    "bot_duel": "Train against an active opponent profile that matches the selected mechanic.",
}


def focus_meta(focus_id: str) -> Dict[str, Any]:
    return dict(FOCUS_CATALOG.get(str(focus_id or "").strip(), {}))


def difficulty_profiles_for_focus(focus_id: str) -> List[Dict[str, Any]]:
    meta = focus_meta(focus_id)
    family = str(meta.get("bot_family", "") or "")
    profiles = BOT_PROFILES.get(family, {})
    out: List[Dict[str, Any]] = []
    for tier, tier_meta in DIFFICULTY_TIERS.items():
        profile = dict(profiles.get(tier, {}))
        out.append(
            {
                "tier": tier,
                "label": str(tier_meta.get("label", tier.title())),
                "difficulty_value": float(profile.get("difficulty_value", tier_meta.get("difficulty_value", 0.5))),
                "summary": str(tier_meta.get("summary", "")),
                "bot_profile_id": str(profile.get("bot_profile_id", f"{family}_{tier}" if family else "")),
                "play_style": str(profile.get("play_style", "")),
            }
        )
    return out


def build_training_option(focus_id: str) -> Dict[str, Any]:
    meta = focus_meta(focus_id)
    if not meta:
        return {}
    return {
        "focus_id": str(focus_id),
        "title": str(meta.get("title", focus_id)),
        "bot_required": bool(meta.get("bot_required", False)),
        "drill_mode_options": list(meta.get("drill_mode_options", [])),
        "scenario_ids": list(meta.get("scenario_ids", [])),
        "difficulty_profiles": difficulty_profiles_for_focus(focus_id),
        "bot_profile_ids": [x["bot_profile_id"] for x in difficulty_profiles_for_focus(focus_id)],
    }
