from __future__ import annotations

import json
import os
from pathlib import Path


PLAYER_ROLE_OFFENSE = 0
PLAYER_ROLE_DEFENSE = 1

OFFENSIVE_MODE = {
    "POSSESSION": 0,
    "BREAKOUT": 1,
    "PASS": 2,
    "BACKPASS": 3,
    "CARRY": 4,
    "CORNER": 5,
    "SIDEWALL": 6,
    "LOB_ON_GOAL": 7,
    "BACKWALL_BOUNCE": 8,
    "SIDEWALL_BREAKOUT": 9,
    "BACK_CORNER_BREAKOUT": 10,
    "BACKBOARD_PASS": 11,
    "SIDE_BACKBOARD_PASS": 12,
    "OVER_SHOULDER": 13,
}

DEFENSIVE_MODE = {
    "NEAR_SHADOW": 0,
    "FAR_SHADOW": 1,
    "NET": 2,
    "CORNER": 3,
    "RECOVERING": 4,
    "FRONT_INTERCEPT": 5,
}

DIFFICULTY_SETTINGS = {
    "beginner": {"label": "Beginner", "timeout": 7.5, "boost_range": [35, 75], "rule_zero": False},
    "intermediate": {"label": "Intermediate", "timeout": 8.0, "boost_range": [30, 75], "rule_zero": False},
    "advanced": {"label": "Advanced", "timeout": 8.5, "boost_range": [25, 80], "rule_zero": True},
    "expert": {"label": "Expert", "timeout": 9.0, "boost_range": [20, 85], "rule_zero": True},
}

PLAYLIST_DEFS = {
    "shadow_defense": {
        "title": "Shadow Defense",
        "description": "Teaches spacing, patience, and staying goal-side before challenging.",
        "difficulties": {
            "beginner": [
                ("POSSESSION", "NEAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("BREAKOUT", "NEAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("PASS", "NET", PLAYER_ROLE_DEFENSE),
            ],
            "intermediate": [
                ("POSSESSION", "NEAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("BREAKOUT", "FAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("CARRY", "NEAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("BACKPASS", "RECOVERING", PLAYER_ROLE_DEFENSE),
            ],
            "advanced": [
                ("BREAKOUT", "FAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("CARRY", "NEAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("OVER_SHOULDER", "NET", PLAYER_ROLE_DEFENSE),
                ("SIDEWALL_BREAKOUT", "FAR_SHADOW", PLAYER_ROLE_DEFENSE),
            ],
            "expert": [
                ("CARRY", "FAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("OVER_SHOULDER", "FAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("BACK_CORNER_BREAKOUT", "FAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("SIDEWALL_BREAKOUT", "NEAR_SHADOW", PLAYER_ROLE_DEFENSE),
                ("PASS", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
            ],
        },
    },
    "challenge": {
        "title": "Challenge Timing",
        "description": "Builds confidence taking controlled front-foot challenges without overcommitting.",
        "difficulties": {
            "beginner": [
                ("POSSESSION", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("PASS", "NET", PLAYER_ROLE_DEFENSE),
            ],
            "intermediate": [
                ("POSSESSION", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("SIDEWALL_BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
            ],
            "advanced": [
                ("BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("SIDEWALL", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("BACKPASS", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
            ],
            "expert": [
                ("SIDEWALL_BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("BACK_CORNER_BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("OVER_SHOULDER", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
                ("PASS", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
            ],
        },
    },
    "fifty_fifty_control": {
        "title": "50-50 Control",
        "description": "Focuses on entering contests balanced and forcing playable ball outcomes.",
        "difficulties": {
            "beginner": [
                ("POSSESSION", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("BACKPASS", "NET", PLAYER_ROLE_OFFENSE),
            ],
            "intermediate": [
                ("POSSESSION", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("BACKPASS", "RECOVERING", PLAYER_ROLE_OFFENSE),
            ],
            "advanced": [
                ("BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("SIDEWALL_BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("BACK_CORNER_BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
            ],
            "expert": [
                ("SIDEWALL", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("SIDEWALL_BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("BACK_CORNER_BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("OVER_SHOULDER", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
            ],
        },
    },
    "aerial_offense": {
        "title": "Aerial Offense",
        "description": "Targets reads and touches from wall, backboard, and lofted attacking balls.",
        "difficulties": {
            "beginner": [
                ("LOB_ON_GOAL", "NET", PLAYER_ROLE_OFFENSE),
                ("BACKWALL_BOUNCE", "NET", PLAYER_ROLE_OFFENSE),
                ("SIDEWALL", "NET", PLAYER_ROLE_OFFENSE),
            ],
            "intermediate": [
                ("LOB_ON_GOAL", "NET", PLAYER_ROLE_OFFENSE),
                ("BACKBOARD_PASS", "NET", PLAYER_ROLE_OFFENSE),
                ("SIDEWALL", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("SIDE_BACKBOARD_PASS", "NET", PLAYER_ROLE_OFFENSE),
            ],
            "advanced": [
                ("BACKBOARD_PASS", "NET", PLAYER_ROLE_OFFENSE),
                ("SIDE_BACKBOARD_PASS", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("SIDEWALL_BREAKOUT", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("OVER_SHOULDER", "NET", PLAYER_ROLE_OFFENSE),
            ],
            "expert": [
                ("SIDEWALL", "NET", PLAYER_ROLE_OFFENSE),
                ("SIDE_BACKBOARD_PASS", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("BACKBOARD_PASS", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("OVER_SHOULDER", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("BACKWALL_BOUNCE", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
            ],
        },
    },
    "aerial_defense": {
        "title": "Aerial Defense",
        "description": "Improves backboard reads, goal-line reactions, and airborne defensive touches.",
        "difficulties": {
            "beginner": [
                ("LOB_ON_GOAL", "NET", PLAYER_ROLE_DEFENSE),
                ("BACKWALL_BOUNCE", "NET", PLAYER_ROLE_DEFENSE),
                ("PASS", "NET", PLAYER_ROLE_DEFENSE),
            ],
            "intermediate": [
                ("BACKWALL_BOUNCE", "NET", PLAYER_ROLE_DEFENSE),
                ("SIDE_BACKBOARD_PASS", "NET", PLAYER_ROLE_DEFENSE),
                ("BACKBOARD_PASS", "NET", PLAYER_ROLE_DEFENSE),
                ("PASS", "CORNER", PLAYER_ROLE_DEFENSE),
            ],
            "advanced": [
                ("BACKWALL_BOUNCE", "NET", PLAYER_ROLE_DEFENSE),
                ("SIDE_BACKBOARD_PASS", "NET", PLAYER_ROLE_DEFENSE),
                ("OVER_SHOULDER", "NET", PLAYER_ROLE_DEFENSE),
                ("BACKBOARD_PASS", "CORNER", PLAYER_ROLE_DEFENSE),
            ],
            "expert": [
                ("SIDE_BACKBOARD_PASS", "NET", PLAYER_ROLE_DEFENSE),
                ("BACKBOARD_PASS", "NET", PLAYER_ROLE_DEFENSE),
                ("OVER_SHOULDER", "NET", PLAYER_ROLE_DEFENSE),
                ("BACKWALL_BOUNCE", "CORNER", PLAYER_ROLE_DEFENSE),
                ("PASS", "FRONT_INTERCEPT", PLAYER_ROLE_DEFENSE),
            ],
        },
    },
    "flicking": {
        "title": "Flicking",
        "description": "Builds controlled dribbles into simple, pressured flick opportunities.",
        "difficulties": {
            "beginner": [
                ("CARRY", "NET", PLAYER_ROLE_OFFENSE),
                ("POSSESSION", "NET", PLAYER_ROLE_OFFENSE),
                ("CARRY", "RECOVERING", PLAYER_ROLE_OFFENSE),
            ],
            "intermediate": [
                ("CARRY", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("POSSESSION", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("BREAKOUT", "NET", PLAYER_ROLE_OFFENSE),
                ("CARRY", "NET", PLAYER_ROLE_OFFENSE),
            ],
            "advanced": [
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("POSSESSION", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("BACKPASS", "NET", PLAYER_ROLE_OFFENSE),
            ],
            "expert": [
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("POSSESSION", "FAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("OVER_SHOULDER", "NET", PLAYER_ROLE_OFFENSE),
                ("BACKPASS", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
            ],
        },
    },
    "carrying_dribbling": {
        "title": "Carrying Dribbling",
        "description": "Repeats controlled first touches and grounded possession under realistic pressure.",
        "difficulties": {
            "beginner": [
                ("POSSESSION", "NET", PLAYER_ROLE_OFFENSE),
                ("CARRY", "RECOVERING", PLAYER_ROLE_OFFENSE),
                ("BREAKOUT", "NET", PLAYER_ROLE_OFFENSE),
            ],
            "intermediate": [
                ("POSSESSION", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("CARRY", "NET", PLAYER_ROLE_OFFENSE),
                ("BREAKOUT", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("BACKPASS", "RECOVERING", PLAYER_ROLE_OFFENSE),
            ],
            "advanced": [
                ("CARRY", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("POSSESSION", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("BREAKOUT", "FAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("BACK_CORNER_BREAKOUT", "NET", PLAYER_ROLE_OFFENSE),
            ],
            "expert": [
                ("CARRY", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("POSSESSION", "FAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
                ("SIDEWALL_BREAKOUT", "NEAR_SHADOW", PLAYER_ROLE_OFFENSE),
                ("BACK_CORNER_BREAKOUT", "FRONT_INTERCEPT", PLAYER_ROLE_OFFENSE),
            ],
        },
    },
}


def make_scenario(offense: str, defense: str, player_role: int) -> dict:
    return {
        "offensive_mode": OFFENSIVE_MODE[offense],
        "defensive_mode": DEFENSIVE_MODE[defense],
        "player_role": player_role,
        "weight": 1.0,
    }


def playlist_filename(mechanic_id: str, difficulty_id: str) -> str:
    return f"rc_{mechanic_id}_{difficulty_id}.json"


def playlist_title(mechanic_title: str, difficulty_label: str) -> str:
    return f"RC {mechanic_title} - {difficulty_label}"


def appdata_playlist_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set.")
    path = Path(appdata) / "RLBot" / "Dojo" / "Playlists"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_playlist_payload(mechanic_id: str, difficulty_id: str) -> dict:
    definition = PLAYLIST_DEFS[mechanic_id]
    settings = DIFFICULTY_SETTINGS[difficulty_id]
    scenarios = [
        make_scenario(offense, defense, role)
        for offense, defense, role in definition["difficulties"][difficulty_id]
    ]
    return {
        "name": playlist_title(definition["title"], settings["label"]),
        "description": f"{definition['description']} Rank target: {settings['label']}.",
        "scenarios": scenarios,
        "custom_scenarios": [],
        "settings": {
            "timeout": settings["timeout"],
            "shuffle": True,
            "loop": True,
            "boost_range": settings["boost_range"],
            "rule_zero": settings["rule_zero"],
        },
        "offensive_modes": [],
        "defensive_modes": [],
        "player_role": None,
    }


def main() -> int:
    playlist_dir = appdata_playlist_dir()
    written = []
    for mechanic_id in PLAYLIST_DEFS:
        for difficulty_id in DIFFICULTY_SETTINGS:
            payload = build_playlist_payload(mechanic_id, difficulty_id)
            target = playlist_dir / playlist_filename(mechanic_id, difficulty_id)
            target.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            written.append(target)

    print(f"Wrote {len(written)} RLDojo playlists to {playlist_dir}")
    print("Kickoff was intentionally skipped because RLDojo does not model true kickoff reps cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
