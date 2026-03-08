from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List


def llm_enabled() -> bool:
    return str(os.environ.get("RLBOT_ENABLE_LLM_EXPLAIN", "0")).strip() in {"1", "true", "True"}


def _extract_output_text(data: Dict[str, Any]) -> str:
    text = str(data.get("output_text", "") or "").strip()
    if text:
        return text
    out = data.get("output", []) or []
    if out and isinstance(out, list):
        for item in out:
            for c in (item.get("content", []) if isinstance(item, dict) else []):
                if isinstance(c, dict) and c.get("type") == "output_text":
                    text = str(c.get("text", "")).strip()
                    if text:
                        return text
    return ""


def _strip_code_fence(s: str) -> str:
    t = str(s or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if len(lines) >= 2:
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
    return t


def _request_responses_api(api_key: str, req_body: Dict[str, Any], timeout_s: int = 7) -> Dict[str, Any]:
    attempts = 4
    for attempt in range(attempts):
        try:
            t0 = time.time()
            req = urllib.request.Request(
                url="https://api.openai.com/v1/responses",
                method="POST",
                data=json.dumps(req_body, ensure_ascii=True).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            dt = max(0.0, time.time() - t0)
            print(f"[replay_perf] llm_request_ok model={req_body.get('model','')} dt={dt:.3f}s")
            return {"ok": True, "data": json.loads(raw), "error": ""}
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < attempts - 1:
                delay = (0.6 * (2 ** attempt)) + random.uniform(0.0, 0.35)
                time.sleep(delay)
                continue
            print(f"[replay_perf] llm_request_http_error code={exc.code} model={req_body.get('model','')}")
            return {"ok": False, "data": {}, "error": f"HTTP {exc.code}: {exc.reason}"}
        except Exception as exc:
            print(f"[replay_perf] llm_request_error model={req_body.get('model','')} err={exc}")
            return {"ok": False, "data": {}, "error": str(exc)}
    return {"ok": False, "data": {}, "error": "Rate limited (429) after retries"}


def maybe_rewrite_explanation(payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
    model = str(os.environ.get("RLBOT_LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini")
    max_tokens = int(os.environ.get("RLBOT_LLM_MAX_TOKENS", "80") or "80")
    timeout_s = int(os.environ.get("RLBOT_LLM_TIMEOUT_S", "6") or "6")
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
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a Rocket League coach explaining one moment to a non-technical player. "
                    "Use only the provided facts. "
                    "Write in plain everyday language with no coding/data jargon. "
                    "Output exactly 2-3 short sentences."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "style_seed": hashlib.sha1(
                            json.dumps(
                                {
                                    "mid": prompt.get("mechanic", ""),
                                    "label": prompt.get("quality_label", ""),
                                    "observed": prompt.get("observed", {}),
                                },
                                ensure_ascii=True,
                                sort_keys=True,
                            ).encode("utf-8")
                        ).hexdigest()[:12],
                        "payload": prompt,
                    },
                    ensure_ascii=True,
                ),
            },
        ],
        "temperature": 0.35,
        "max_output_tokens": max(32, max_tokens),
    }

    resp = _request_responses_api(api_key, req_body, timeout_s=max(3, timeout_s))
    if not resp.get("ok"):
        return {"enabled": True, "used": False, "style": "plain_language_coach", "text": "", "error": str(resp.get("error", ""))}
    text = _extract_output_text(dict(resp.get("data") or {}))
    return {"enabled": True, "used": bool(text), "style": "plain_language_coach", "text": text, "error": ""}


def maybe_rewrite_explanations_batch(events: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Rewrite many event explanations in chunks to reduce total latency and API load.
    Input items must include:
      - key
      - mechanic
      - time_s
      - quality_label
      - score
      - reason
    Returns map: key -> short explanation text.
    """
    api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
    model = str(os.environ.get("RLBOT_LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini")
    max_tokens = int(os.environ.get("RLBOT_LLM_BATCH_MAX_TOKENS", "900") or "900")
    chunk_size = int(os.environ.get("RLBOT_LLM_BATCH_CHUNK_SIZE", "30") or "30")
    timeout_s = int(os.environ.get("RLBOT_LLM_BATCH_TIMEOUT_S", "8") or "8")
    if not llm_enabled() or not api_key or not events:
        return {}

    out: Dict[str, str] = {}
    for start in range(0, len(events), chunk_size):
        chunk = events[start:start + chunk_size]
        req_body = {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are a Rocket League coach. "
                        "For each input event, write exactly 2-3 short sentences in plain language. "
                        "Do not invent facts. "
                        "Return STRICT JSON object mapping each event key to its text."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"events": chunk}, ensure_ascii=True),
                },
            ],
            "temperature": 0.3,
            "max_output_tokens": max(256, max_tokens),
        }
        resp = _request_responses_api(api_key, req_body, timeout_s=max(4, timeout_s))
        if not resp.get("ok"):
            continue
        text = _strip_code_fence(_extract_output_text(dict(resp.get("data") or {})))
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    ks = str(k or "").strip()
                    vs = str(v or "").strip()
                    if ks and vs:
                        out[ks] = vs
        except Exception:
            continue
    return out
