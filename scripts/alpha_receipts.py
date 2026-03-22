from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rocketcoach.replay_dashboard.replay_loader import load_replay_bytes

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class TestResult:
    kr: str
    name: str
    status: str
    summary: str
    details: Dict[str, Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_kr4_db_persistence(db_path: Path) -> TestResult:
    if not db_path.exists():
        return TestResult(
            kr="KR4",
            name="SQLite persistence evidence",
            status="FAIL",
            summary=f"Database file not found: {db_path}",
            details={"db_path": str(db_path)},
        )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    table_rows = cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    tables = [str(r["name"]) for r in table_rows]
    counts: Dict[str, int] = {}
    for t in ("users", "replay_sessions", "auth_users", "auth_sessions", "event_labels", "recommendation_snapshots"):
        try:
            counts[t] = int(cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
        except Exception:
            counts[t] = -1

    recent = []
    try:
        rows = cur.execute(
            """
            SELECT replay_name, created_at, duration_s, tracked_player_name,
                   replay_blob IS NOT NULL AS has_blob,
                   prepared_payload IS NOT NULL AS has_prepared
            FROM replay_sessions
            ORDER BY created_at DESC
            LIMIT 3
            """
        ).fetchall()
        for r in rows:
            recent.append(
                {
                    "replay_name": str(r["replay_name"]),
                    "created_at": str(r["created_at"]),
                    "duration_s": float(r["duration_s"] or 0.0),
                    "tracked_player_name": str(r["tracked_player_name"] or ""),
                    "has_blob": bool(r["has_blob"]),
                    "has_prepared": bool(r["has_prepared"]),
                }
            )
    finally:
        conn.close()

    ok = counts.get("replay_sessions", 0) > 0 and counts.get("users", 0) > 0
    return TestResult(
        kr="KR4",
        name="SQLite persistence evidence",
        status="PASS" if ok else "WARN",
        summary="Replay/session persistence rows are present in local SQLite artifacts."
        if ok
        else "Schema is present, but expected replay/user rows were not found.",
        details={
            "db_path": str(db_path),
            "table_count": len(tables),
            "tables": tables,
            "row_counts": counts,
            "recent_replay_sessions": recent,
        },
    )


def test_kr1_parser_and_dataframe(replay_path: Optional[Path]) -> TestResult:
    if replay_path is None:
        return TestResult(
            kr="KR1",
            name="Replay parsing to Pandas DataFrame",
            status="SKIP",
            summary="Replay path not provided. Pass --replay to run full parser test.",
            details={},
        )
    if not replay_path.exists():
        return TestResult(
            kr="KR1",
            name="Replay parsing to Pandas DataFrame",
            status="FAIL",
            summary=f"Replay file not found: {replay_path}",
            details={"replay_path": str(replay_path)},
        )

    try:
        data = replay_path.read_bytes()
        session = load_replay_bytes(file_name=replay_path.name, data=data)
        df = session.df
        required = ["time", "Ball_x", "Ball_y", "Ball_z"]
        missing = [c for c in required if c not in df.columns]
        ok = len(missing) == 0 and len(df) > 0
        return TestResult(
            kr="KR1",
            name="Replay parsing to Pandas DataFrame",
            status="PASS" if ok else "FAIL",
            summary="Replay parsed into DataFrame with required telemetry columns."
            if ok
            else "Replay parsed but required telemetry columns were missing.",
            details={
                "replay_path": str(replay_path),
                "session_id": str(session.session_id),
                "players": list(session.players),
                "duration_s": float(session.duration_s),
                "df_rows": int(len(df)),
                "df_cols": int(len(df.columns)),
                "missing_required_columns": missing,
            },
        )
    except Exception as exc:
        return TestResult(
            kr="KR1",
            name="Replay parsing to Pandas DataFrame",
            status="FAIL",
            summary=f"Replay parser execution failed: {exc}",
            details={"replay_path": str(replay_path)},
        )


def test_kr2_three_weaknesses(db_path: Path) -> TestResult:
    if not db_path.exists():
        return TestResult(
            kr="KR2",
            name="Top-3 weakness derivation",
            status="FAIL",
            summary=f"Database file not found: {db_path}",
            details={},
        )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    row = cur.execute(
        "SELECT replay_name, summary_json FROM replay_sessions ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not row:
        return TestResult(
            kr="KR2",
            name="Top-3 weakness derivation",
            status="WARN",
            summary="No replay_sessions rows found to derive weaknesses from.",
            details={},
        )

    summary = {}
    try:
        summary = json.loads(str(row["summary_json"] or "{}"))
    except Exception:
        summary = {}
    mech_scores = summary.get("mechanic_scores", {}) or {}
    parsed: List[tuple[str, float]] = []
    for k, v in mech_scores.items():
        try:
            parsed.append((str(k), float(v)))
        except Exception:
            continue
    parsed.sort(key=lambda x: x[1])
    weakest_three = parsed[:3]
    ok = len(weakest_three) == 3
    return TestResult(
        kr="KR2",
        name="Top-3 weakness derivation",
        status="PASS" if ok else "WARN",
        summary="Derived three weakest mechanics from stored threshold-based mechanic scores."
        if ok
        else "Could not derive three weaknesses from latest stored replay summary.",
        details={
            "replay_name": str(row["replay_name"]),
            "mechanic_score_count": len(parsed),
            "weakest_three": [{"mechanic_id": k, "score_0_100": v} for k, v in weakest_three],
        },
    )


def test_kr3_visualizer_readiness() -> TestResult:
    react_file = REPO_ROOT / "frontend" / "dashboard" / "src" / "components" / "replay" / "ReplayVisualizer.tsx"
    if not react_file.exists():
        return TestResult(
            kr="KR3",
            name="Visualizer pause/FPS instrumentation presence",
            status="FAIL",
            summary="Replay visualizer source file was not found.",
            details={},
        )

    react_src = react_file.read_text(encoding="utf-8", errors="replace")

    checks = {
        "react_auto_event_pause_callback": "onAutoEventPause?.(" in react_src,
        "react_pause_on_event_hit": "setPlaying(false);" in react_src and "if (hit)" in react_src,
        "react_debug_overlay_present": "debug-overlay" in react_src or "debugOverlay" in react_src,
    }
    ok = all(checks.values())
    manual_steps = [
        "Run replay dashboard: powershell -ExecutionPolicy Bypass -File scripts/replay_dashboard.ps1",
        "Load a replay and open the replay visualizer.",
        "Capture a screenshot showing event pause behavior and the active debug overlay.",
    ]
    return TestResult(
        kr="KR3",
        name="Visualizer pause/FPS instrumentation presence",
        status="PASS" if ok else "WARN",
        summary="Code paths for mistake-timestamp pause and FPS instrumentation are present."
        if ok
        else "One or more expected visualizer instrumentation hooks were not found.",
        details={"checks": checks, "manual_screenshot_steps": manual_steps},
    )


def render_markdown(results: List[TestResult], generated_at: str) -> str:
    lines = [
        "# Alpha Receipt Test Run",
        "",
        f"- Generated at (UTC): `{generated_at}`",
        "",
    ]
    for r in results:
        lines.append(f"## {r.kr} - {r.name}")
        lines.append(f"- Status: **{r.status}**")
        lines.append(f"- Summary: {r.summary}")
        lines.append("- Details:")
        lines.append("```json")
        lines.append(json.dumps(r.details, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Alpha milestone receipt tests and write screenshot-friendly artifacts.")
    parser.add_argument("--replay", default="", help="Optional path to a .replay file for KR1 parser test.")
    parser.add_argument("--rrrocket", default="", help="Optional path to rrrocket/rrrocket.exe for KR1 replay parsing.")
    parser.add_argument("--db-path", default=str(REPO_ROOT / "artifacts" / "data" / "app.db"), help="SQLite DB path.")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "alpha_receipts"), help="Output directory for report files.")
    args = parser.parse_args()

    replay_path = Path(args.replay).expanduser().resolve() if str(args.replay).strip() else None
    if str(args.rrrocket).strip():
        rrrocket_path = Path(args.rrrocket).expanduser().resolve()
        # replay_loader/extract_player_data consult RRROCKET_BIN
        import os

        os.environ["RRROCKET_BIN"] = str(rrrocket_path)
    db_path = Path(args.db_path).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    generated_at = _now_iso()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    results = [
        test_kr1_parser_and_dataframe(replay_path),
        test_kr2_three_weaknesses(db_path),
        test_kr3_visualizer_readiness(),
        test_kr4_db_persistence(db_path),
    ]

    json_path = output_dir / f"alpha_receipts_{stamp}.json"
    md_path = output_dir / f"alpha_receipts_{stamp}.md"
    payload = {
        "generated_at_utc": generated_at,
        "results": [asdict(r) for r in results],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(results, generated_at), encoding="utf-8")

    print(f"[alpha_receipts] wrote JSON: {json_path}")
    print(f"[alpha_receipts] wrote Markdown: {md_path}")
    print("[alpha_receipts] status summary:")
    for r in results:
        print(f"  - {r.kr}: {r.status} - {r.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
