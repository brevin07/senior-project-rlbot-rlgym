"""
Pull mechanic-feedback rows out of app.db.

Usage (from repo root):
    python scripts/export_mechanic_feedback.py                   # pretty-print JSON to stdout
    python scripts/export_mechanic_feedback.py --csv             # CSV to stdout
    python scripts/export_mechanic_feedback.py --csv -o out.csv  # CSV to file
    python scripts/export_mechanic_feedback.py --user 3          # filter by user id
    python scripts/export_mechanic_feedback.py --mechanic kickoff
    python scripts/export_mechanic_feedback.py --db /path/to/app.db
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from rocketcoach.common.persistence.db import AppDB, get_default_db_path


COLUMNS = [
    "id",
    "created_at",
    "user_id",
    "session_id",
    "replay_name",
    "mechanic_id",
    "event_time",
    "quality_label",
    "quality_score",
    "verdict",
    "reason",
    "note",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export mechanic_feedback rows from app.db")
    parser.add_argument("--db", type=Path, default=None, help="Path to app.db (defaults to RLBOT_APP_DB_PATH or platform default)")
    parser.add_argument("--user", type=int, default=None, help="Filter by user_id (users.id)")
    parser.add_argument("--mechanic", type=str, default=None, help="Filter by mechanic_id (e.g. kickoff, challenge)")
    parser.add_argument("--limit", type=int, default=10_000, help="Max rows (default 10000)")
    parser.add_argument("--csv", action="store_true", help="Emit CSV instead of JSON")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Write to this file instead of stdout")
    args = parser.parse_args()

    db_path = args.db or get_default_db_path()
    if not db_path.exists():
        print(f"[error] app.db not found at {db_path}", file=sys.stderr)
        return 2

    db = AppDB(db_path)
    rows = db.list_mechanic_feedback(
        user_id=args.user,
        mechanic_id=args.mechanic,
        limit=int(args.limit),
    )

    if args.csv:
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            fh = args.output.open("w", encoding="utf-8", newline="")
        else:
            fh = sys.stdout
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        if args.output:
            fh.close()
            print(f"[ok] wrote {len(rows)} rows to {args.output}", file=sys.stderr)
    else:
        payload = json.dumps(rows, indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
            print(f"[ok] wrote {len(rows)} rows to {args.output}", file=sys.stderr)
        else:
            print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
