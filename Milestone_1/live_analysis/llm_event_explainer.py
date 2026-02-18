from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict


def llm_enabled() -> bool:
    return str(os.environ.get("RLBOT_ENABLE_LLM_EXPLAIN", "0")).strip() in {"1", "true", "True"}


def maybe_rewrite_explanation(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optional LLM explanation rewrite.
    Disabled unless:
      - RLBOT_ENABLE_LLM_EXPLAIN=1
      - OPENAI_API_KEY is present
    """
    api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
    if not llm_enabled() or not api_key:
        return {"enabled": False, "used": False, "style": "plain_language_coach", "text": "", "error": ""}

    prompt = {
        "mechanic": payload.get("title", payload.get("mechanic_id", "")),
        "quality_label": payload.get("quality_label", ""),
        "quality_score_0_100": payload.get("quality_score_0_100", 0),
        "reason": payload.get("reason", ""),
        "thresholds": payload.get("thresholds", []),
        "observed": payload.get("observed", {}),
        "breakdown": payload.get("breakdown", []),
        "coaching_context": payload.get("coaching_context", {}),
        "actionable_hints": payload.get("actionable_hints", []),
        "confidence_note": payload.get("confidence_note", ""),
        "deterministic_summary": payload.get("deterministic_summary", ""),
    }

    req_body = {
        "model": "gpt-4o-mini",
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a Rocket League coach explaining one moment to a non-technical player. "
                    "Use only the provided facts. "
                    "Write in plain everyday language with no coding/data jargon. "
                    "Output 2-3 short sentences. "
                    "Mention one concrete observed value naturally (for example speed, distance, or time). "
                    "Keep it practical: what happened, what to do next time, and one thing to avoid."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt, ensure_ascii=True),
            },
        ],
        "temperature": 0.2,
        "max_output_tokens": 220,
    }

    try:
        req = urllib.request.Request(
            url="https://api.openai.com/v1/responses",
            method="POST",
            data=json.dumps(req_body, ensure_ascii=True).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        text = str(data.get("output_text", "") or "").strip()
        if not text:
            # fallback parse
            out = data.get("output", []) or []
            if out and isinstance(out, list):
                for item in out:
                    for c in (item.get("content", []) if isinstance(item, dict) else []):
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            text = str(c.get("text", "")).strip()
                            if text:
                                break
                    if text:
                        break
        return {"enabled": True, "used": bool(text), "style": "plain_language_coach", "text": text, "error": ""}
    except Exception as exc:
        return {"enabled": True, "used": False, "style": "plain_language_coach", "text": "", "error": str(exc)}
