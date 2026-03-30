from __future__ import annotations

from rocketcoach.training.rldojo_catalog import (
    NON_BOT_DRILL_SUMMARIES,
    build_training_option,
    difficulty_profiles_for_focus,
    difficulty_tiers,
    focus_meta,
)


DIFFICULTY_TIERS = difficulty_tiers()


__all__ = [
    "DIFFICULTY_TIERS",
    "NON_BOT_DRILL_SUMMARIES",
    "build_training_option",
    "difficulty_profiles_for_focus",
    "focus_meta",
]
