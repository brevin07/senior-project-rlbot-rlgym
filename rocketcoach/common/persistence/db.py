from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os
import sqlite3
import hashlib
import hmac
import secrets


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _email_norm(email: str) -> str:
    return str(email or "").strip().lower()


def _norm_username(username: str) -> str:
    return "".join(ch.lower() for ch in str(username or "").strip() if ch.isalnum() or ch in ("_", "-"))


VALID_PLATFORMS = {"epic", "steam"}

# Stored as lowercase enum-like slugs.
VALID_RANKS = {
    "bronze_1",
    "bronze_2",
    "bronze_3",
    "silver_1",
    "silver_2",
    "silver_3",
    "gold_1",
    "gold_2",
    "gold_3",
    "platinum_1",
    "platinum_2",
    "platinum_3",
    "diamond_1",
    "diamond_2",
    "diamond_3",
    "champion_1",
    "champion_2",
    "champion_3",
    "grand_champion_1",
    "grand_champion_2",
    "grand_champion_3",
    "ssl",
}


def normalize_rank(rank: str) -> str:
    v = str(rank or "").strip().lower().replace(" ", "_")
    if v in VALID_RANKS:
        return v
    return "bronze_1"


def get_default_db_path() -> Path:
    env = os.environ.get("RLBOT_APP_DB_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        return Path(appdata) / "RLGymBotTraining" / "data" / "app.db"
    return Path.home() / ".rlgym_bot_training" / "app.db"


class AppDB:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or get_default_db_path())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    email_norm TEXT NOT NULL UNIQUE,
                    cognito_sub TEXT UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES auth_users(id)
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    username_norm TEXT NOT NULL UNIQUE,
                    rank_tier TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS replay_sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    replay_name TEXT NOT NULL,
                    map_name TEXT NOT NULL,
                    duration_s REAL NOT NULL,
                    tracked_player_name TEXT NOT NULL,
                    tracked_player_index INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    artifact_manifest_json TEXT NOT NULL,
                    replay_blob BLOB,
                    prepared_payload BLOB,
                    summary_json TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE INDEX IF NOT EXISTS idx_replay_sessions_user_created
                ON replay_sessions(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS event_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    note TEXT NOT NULL,
                    author TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, event_id),
                    FOREIGN KEY(session_id) REFERENCES replay_sessions(id)
                );

                CREATE TABLE IF NOT EXISTS recommendation_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    window_size INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS drill_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    focus_id TEXT NOT NULL,
                    bot_profile_id TEXT NOT NULL,
                    scenario_ids_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    outcome_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS llm_event_explanations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    replay_fingerprint TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    mechanic_id TEXT NOT NULL,
                    event_time_s REAL NOT NULL,
                    event_hash TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, replay_fingerprint, event_key, model_id, prompt_version, event_hash),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE INDEX IF NOT EXISTS idx_llm_event_explanations_lookup
                ON llm_event_explanations(user_id, replay_fingerprint, model_id, prompt_version, updated_at DESC);
                """
            )
            cols = conn.execute("PRAGMA table_info(replay_sessions)").fetchall()
            col_names = {str(r["name"]) for r in cols}
            if "replay_blob" not in col_names:
                conn.execute("ALTER TABLE replay_sessions ADD COLUMN replay_blob BLOB")
            if "prepared_payload" not in col_names:
                conn.execute("ALTER TABLE replay_sessions ADD COLUMN prepared_payload BLOB")
            user_cols = conn.execute("PRAGMA table_info(users)").fetchall()
            user_col_names = {str(r["name"]) for r in user_cols}
            if "auth_user_id" not in user_col_names:
                conn.execute("ALTER TABLE users ADD COLUMN auth_user_id INTEGER")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_users_auth_user ON users(auth_user_id)")
            auth_cols = conn.execute("PRAGMA table_info(auth_users)").fetchall()
            auth_col_names = {str(r["name"]) for r in auth_cols}
            if "cognito_sub" not in auth_col_names:
                conn.execute("ALTER TABLE auth_users ADD COLUMN cognito_sub TEXT")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_users_cognito_sub ON auth_users(cognito_sub)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_llm_event_explanations_lookup "
                "ON llm_event_explanations(user_id, replay_fingerprint, model_id, prompt_version, updated_at DESC)"
            )

    @staticmethod
    def _row_to_user(row: sqlite3.Row | None) -> Dict[str, Any] | None:
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "username": str(row["username"]),
            "rank_tier": str(row["rank_tier"]),
            "platform": str(row["platform"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "auth_user_id": int(row["auth_user_id"]) if row["auth_user_id"] is not None else None,
        }

    @staticmethod
    def _hash_password(password: str) -> str:
        pw = str(password or "")
        if not pw:
            raise RuntimeError("password is required")
        salt = secrets.token_bytes(16)
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 120000)
        return f"pbkdf2_sha256${salt.hex()}${dk.hex()}"

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        try:
            algo, salt_hex, hash_hex = str(stored).split("$", 2)
        except Exception:
            return False
        if algo != "pbkdf2_sha256":
            return False
        try:
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
        except Exception:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt, 120000)
        return hmac.compare_digest(dk, expected)

    def create_auth_user(self, *, email: str, password: str) -> Dict[str, Any]:
        email = str(email or "").strip()
        if not email:
            raise RuntimeError("email is required")
        email_norm = _email_norm(email)
        now = _utc_now_iso()
        pwh = self._hash_password(password)
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM auth_users WHERE email_norm = ?", (email_norm,)).fetchone()
            if row:
                raise RuntimeError("Email already registered.")
            conn.execute(
                "INSERT INTO auth_users (email, email_norm, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (email, email_norm, pwh, now, now),
            )
            out = conn.execute("SELECT * FROM auth_users WHERE email_norm = ?", (email_norm,)).fetchone()
        return {
            "id": int(out["id"]),
            "email": str(out["email"]),
            "created_at": str(out["created_at"]),
            "updated_at": str(out["updated_at"]),
        }

    def authenticate(self, *, email: str, password: str) -> Dict[str, Any]:
        email_norm = _email_norm(email)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE email_norm = ?", (email_norm,)).fetchone()
            if not row:
                raise RuntimeError("Invalid email or password.")
            if not self._verify_password(password, str(row["password_hash"])):
                raise RuntimeError("Invalid email or password.")
            return {
                "id": int(row["id"]),
                "email": str(row["email"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }

    def upsert_auth_user_from_cognito(self, *, cognito_sub: str, email: str) -> Dict[str, Any]:
        sub = str(cognito_sub or "").strip()
        if not sub:
            raise RuntimeError("cognito_sub is required")
        clean_email = str(email or "").strip()
        email_norm = _email_norm(clean_email)
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE cognito_sub = ?", (sub,)).fetchone()
            if row:
                if clean_email:
                    conn.execute(
                        "UPDATE auth_users SET email = ?, email_norm = ?, updated_at = ? WHERE id = ?",
                        (clean_email, email_norm, now, int(row["id"])),
                    )
                out = conn.execute("SELECT * FROM auth_users WHERE id = ?", (int(row["id"]),)).fetchone()
                return {
                    "id": int(out["id"]),
                    "email": str(out["email"]),
                    "created_at": str(out["created_at"]),
                    "updated_at": str(out["updated_at"]),
                }

            if clean_email:
                row = conn.execute("SELECT * FROM auth_users WHERE email_norm = ?", (email_norm,)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE auth_users SET cognito_sub = ?, email = ?, updated_at = ? WHERE id = ?",
                        (sub, clean_email, now, int(row["id"])),
                    )
                    out = conn.execute("SELECT * FROM auth_users WHERE id = ?", (int(row["id"]),)).fetchone()
                    return {
                        "id": int(out["id"]),
                        "email": str(out["email"]),
                        "created_at": str(out["created_at"]),
                        "updated_at": str(out["updated_at"]),
                    }
            if not clean_email:
                clean_email = f"{sub}@cognito.local"
                email_norm = _email_norm(clean_email)
            pw = self._hash_password(secrets.token_urlsafe(32))
            conn.execute(
                "INSERT INTO auth_users (email, email_norm, cognito_sub, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (clean_email, email_norm, sub, pw, now, now),
            )
            out = conn.execute("SELECT * FROM auth_users WHERE cognito_sub = ?", (sub,)).fetchone()
            return {
                "id": int(out["id"]),
                "email": str(out["email"]),
                "created_at": str(out["created_at"]),
                "updated_at": str(out["updated_at"]),
            }

    def create_session(self, *, user_id: int, hours: int = 24 * 7) -> str:
        sid = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        exp = now + timedelta(hours=int(hours))
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO auth_sessions (session_id, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (sid, int(user_id), now.isoformat(), exp.isoformat()),
            )
        return sid

    def delete_session(self, *, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (str(session_id),))

    def get_auth_user_by_session(self, *, session_id: str) -> Dict[str, Any] | None:
        sid = str(session_id or "").strip()
        if not sid:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT au.* , s.expires_at
                FROM auth_sessions s
                JOIN auth_users au ON au.id = s.user_id
                WHERE s.session_id = ?
                """,
                (sid,),
            ).fetchone()
            if not row:
                return None
            try:
                exp = datetime.fromisoformat(str(row["expires_at"]))
                if exp < datetime.now(timezone.utc):
                    conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (sid,))
                    return None
            except Exception:
                pass
            return {
                "id": int(row["id"]),
                "email": str(row["email"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }

    def get_auth_user_by_email(self, *, email: str) -> Dict[str, Any] | None:
        email_norm = _email_norm(email)
        if not email_norm:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE email_norm = ?", (email_norm,)).fetchone()
            if not row:
                return None
            return {
                "id": int(row["id"]),
                "email": str(row["email"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "cognito_sub": str(row["cognito_sub"] or ""),
            }

    def list_auth_users(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, email, cognito_sub, created_at, updated_at FROM auth_users ORDER BY email_norm ASC"
            ).fetchall()
            return [
                {
                    "id": int(row["id"]),
                    "email": str(row["email"]),
                    "cognito_sub": str(row["cognito_sub"] or ""),
                    "created_at": str(row["created_at"]),
                    "updated_at": str(row["updated_at"]),
                }
                for row in rows
            ]

    def get_profile_by_auth_user(self, *, auth_user_id: int) -> Dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE auth_user_id = ?", (int(auth_user_id),)).fetchone()
            user = self._row_to_user(row)
            if not user:
                return None
            user["aliases"] = self._read_aliases(conn, int(user["id"]))
            return user

    def _aliases_key(self, user_id: int) -> str:
        return f"user_aliases_{int(user_id)}"

    def _read_aliases(self, conn: sqlite3.Connection, user_id: int) -> List[str]:
        row = conn.execute("SELECT value FROM app_state WHERE key = ?", (self._aliases_key(user_id),)).fetchone()
        if not row:
            return []
        try:
            payload = json.loads(str(row["value"] or "[]"))
        except Exception:
            payload = []
        out: List[str] = []
        seen = set()
        for x in (payload if isinstance(payload, list) else []):
            s = str(x or "").strip()
            n = _norm_username(s)
            if not s or not n or n in seen:
                continue
            seen.add(n)
            out.append(s)
        return out

    def _write_aliases(self, conn: sqlite3.Connection, user_id: int, aliases: List[str]) -> None:
        conn.execute(
            "INSERT INTO app_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self._aliases_key(user_id), json.dumps(list(aliases or []), ensure_ascii=True)),
        )

    def upsert_user(
        self,
        *,
        username: str,
        rank_tier: str,
        platform: str,
        aliases: Optional[List[str]] = None,
        auth_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        username = str(username or "").strip()
        if not username:
            raise RuntimeError("username is required")
        username_norm = _norm_username(username)
        if not username_norm:
            raise RuntimeError("username is invalid")
        platform = str(platform or "").strip().lower()
        if platform not in VALID_PLATFORMS:
            raise RuntimeError("platform must be epic or steam")
        rank_tier = normalize_rank(rank_tier)
        now = _utc_now_iso()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username_norm = ?", (username_norm,)).fetchone()
            if row:
                if auth_user_id is not None and row["auth_user_id"] not in (None, int(auth_user_id)):
                    raise RuntimeError("username is already in use")
                conn.execute(
                    "UPDATE users SET username = ?, rank_tier = ?, platform = ?, updated_at = ?, auth_user_id = COALESCE(auth_user_id, ?) WHERE id = ?",
                    (username, rank_tier, platform, now, auth_user_id, int(row["id"])),
                )
                out = conn.execute("SELECT * FROM users WHERE id = ?", (int(row["id"]),)).fetchone()
            else:
                conn.execute(
                    "INSERT INTO users (username, username_norm, rank_tier, platform, created_at, updated_at, auth_user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (username, username_norm, rank_tier, platform, now, now, auth_user_id),
                )
                out = conn.execute("SELECT * FROM users WHERE username_norm = ?", (username_norm,)).fetchone()
            conn.execute(
                "INSERT INTO app_state (key, value) VALUES ('active_user_id', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(int(out["id"])),),
            )
            user = self._row_to_user(out) or {}
            if aliases is not None:
                clean: List[str] = []
                seen = set()
                for a in aliases:
                    s = str(a or "").strip()
                    n = _norm_username(s)
                    if not s or not n or n == username_norm or n in seen:
                        continue
                    seen.add(n)
                    clean.append(s)
                self._write_aliases(conn, int(out["id"]), clean)
            user["aliases"] = self._read_aliases(conn, int(out["id"]))
            return user

    def current_user(self) -> Dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key = 'active_user_id'").fetchone()
            if not row:
                return None
            try:
                user_id = int(str(row["value"]))
            except Exception:
                return None
            u = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            user = self._row_to_user(u)
            if not user:
                return None
            user["aliases"] = self._read_aliases(conn, user_id)
            return user

    def current_user_for_session(self, *, session_id: str) -> Dict[str, Any] | None:
        auth = self.get_auth_user_by_session(session_id=session_id)
        if not auth:
            return None
        return self.get_profile_by_auth_user(auth_user_id=int(auth["id"]))

    def set_active_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO app_state (key, value) VALUES ('active_user_id', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(int(user_id)),),
            )

    def clear_active_user(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM app_state WHERE key = 'active_user_id'")

    def save_replay_session(
        self,
        *,
        session_id: str,
        user_id: int,
        source_type: str,
        replay_name: str,
        map_name: str,
        duration_s: float,
        tracked_player_name: str,
        tracked_player_index: int,
        artifact_manifest: Dict[str, Any],
        replay_blob: bytes | None = None,
        prepared_payload: bytes | None = None,
        summary: Dict[str, Any],
        created_at: str | None = None,
    ) -> None:
        sid = str(session_id or "").strip()
        if not sid:
            raise RuntimeError("session_id is required")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO replay_sessions (
                    id, user_id, source_type, replay_name, map_name, duration_s,
                    tracked_player_name, tracked_player_index, created_at,
                    artifact_manifest_json, replay_blob, prepared_payload, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    user_id=excluded.user_id,
                    source_type=excluded.source_type,
                    replay_name=excluded.replay_name,
                    map_name=excluded.map_name,
                    duration_s=excluded.duration_s,
                    tracked_player_name=excluded.tracked_player_name,
                    tracked_player_index=excluded.tracked_player_index,
                    artifact_manifest_json=excluded.artifact_manifest_json,
                    replay_blob=COALESCE(excluded.replay_blob, replay_sessions.replay_blob),
                    prepared_payload=COALESCE(excluded.prepared_payload, replay_sessions.prepared_payload),
                    summary_json=excluded.summary_json
                """,
                (
                    sid,
                    int(user_id),
                    str(source_type or "replay_upload"),
                    str(replay_name or sid),
                    str(map_name or "soccar"),
                    float(duration_s or 0.0),
                    str(tracked_player_name or ""),
                    int(tracked_player_index or 0),
                    str(created_at or _utc_now_iso()),
                    json.dumps(artifact_manifest or {}, ensure_ascii=True),
                    replay_blob,
                    prepared_payload,
                    json.dumps(summary or {}, ensure_ascii=True),
                ),
            )
            # Keep library replay names unique per user (case-insensitive), retaining newest row.
            self.prune_duplicate_replay_names(user_id=int(user_id), conn=conn)

    def prune_duplicate_replay_names(self, *, user_id: int, conn: sqlite3.Connection | None = None) -> int:
        """
        Remove duplicate replay names for a user, keeping the newest created_at row in each
        case-insensitive replay_name group. Returns number of deleted rows.
        """
        own_conn = conn is None
        c = conn or self._connect()
        deleted = 0
        try:
            rows = c.execute(
                """
                SELECT id, replay_name, created_at
                FROM replay_sessions
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (int(user_id),),
            ).fetchall()
            seen: set[str] = set()
            to_delete: List[str] = []
            for r in rows:
                key = str(r["replay_name"] or "").strip().lower()
                if not key:
                    key = str(r["id"] or "")
                if key in seen:
                    to_delete.append(str(r["id"]))
                else:
                    seen.add(key)
            if to_delete:
                q = ",".join(["?"] * len(to_delete))
                c.execute(f"DELETE FROM replay_sessions WHERE id IN ({q})", tuple(to_delete))
                deleted = len(to_delete)
        finally:
            if own_conn:
                try:
                    c.commit()
                except Exception:
                    pass
                c.close()
        return deleted

    def list_replay_sessions(self, *, user_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, source_type, replay_name, map_name, duration_s, tracked_player_name,
                       tracked_player_index, created_at, summary_json, replay_blob, prepared_payload
                FROM replay_sessions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (int(user_id), max(1, int(limit))),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    summary = json.loads(str(r["summary_json"] or "{}"))
                except Exception:
                    summary = {}
                out.append(
                    {
                        "session_id": str(r["id"]),
                        "source_type": str(r["source_type"]),
                        "replay_name": str(r["replay_name"]),
                        "map_name": str(r["map_name"]),
                        "duration_s": float(r["duration_s"] or 0.0),
                        "tracked_player_name": str(r["tracked_player_name"] or ""),
                        "tracked_player_index": int(r["tracked_player_index"] or 0),
                        "created_at": str(r["created_at"]),
                        "has_replay_blob": bool(r["replay_blob"]),
                        "has_prepared_payload": bool(r["prepared_payload"]),
                        "summary": summary,
                    }
                )
            return out

    def list_replay_sessions_detailed(self, *, user_id: int, limit: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM replay_sessions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (int(user_id), max(1, int(limit))),
            ).fetchall()
            out: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    artifact_manifest = json.loads(str(r["artifact_manifest_json"] or "{}"))
                except Exception:
                    artifact_manifest = {}
                try:
                    summary = json.loads(str(r["summary_json"] or "{}"))
                except Exception:
                    summary = {}
                out.append(
                    {
                        "session_id": str(r["id"]),
                        "user_id": int(r["user_id"]),
                        "source_type": str(r["source_type"]),
                        "replay_name": str(r["replay_name"]),
                        "map_name": str(r["map_name"]),
                        "duration_s": float(r["duration_s"] or 0.0),
                        "tracked_player_name": str(r["tracked_player_name"] or ""),
                        "tracked_player_index": int(r["tracked_player_index"] or 0),
                        "created_at": str(r["created_at"]),
                        "has_replay_blob": bool(r["replay_blob"]),
                        "has_prepared_payload": bool(r["prepared_payload"]),
                        "artifact_manifest": artifact_manifest,
                        "summary": summary,
                    }
                )
            return out

    def get_replay_session(self, *, session_id: str, user_id: int) -> Dict[str, Any] | None:
        with self._connect() as conn:
            r = conn.execute(
                """
                SELECT * FROM replay_sessions
                WHERE id = ? AND user_id = ?
                """,
                (str(session_id), int(user_id)),
            ).fetchone()
            if not r:
                return None
            try:
                artifact_manifest = json.loads(str(r["artifact_manifest_json"] or "{}"))
            except Exception:
                artifact_manifest = {}
            try:
                summary = json.loads(str(r["summary_json"] or "{}"))
            except Exception:
                summary = {}
            return {
                "session_id": str(r["id"]),
                "user_id": int(r["user_id"]),
                "source_type": str(r["source_type"]),
                "replay_name": str(r["replay_name"]),
                "map_name": str(r["map_name"]),
                "duration_s": float(r["duration_s"] or 0.0),
                "tracked_player_name": str(r["tracked_player_name"] or ""),
                "tracked_player_index": int(r["tracked_player_index"] or 0),
                "created_at": str(r["created_at"]),
                "has_replay_blob": bool(r["replay_blob"]),
                "has_prepared_payload": bool(r["prepared_payload"]),
                "replay_blob": bytes(r["replay_blob"]) if r["replay_blob"] is not None else None,
                "prepared_payload": bytes(r["prepared_payload"]) if r["prepared_payload"] is not None else None,
                "artifact_manifest": artifact_manifest,
                "summary": summary,
            }

    def delete_replay_session(self, *, session_id: str, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM replay_sessions WHERE id = ? AND user_id = ?",
                (str(session_id), int(user_id)),
            )

    def delete_replay_sessions_without_blob(self, *, user_id: int) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM replay_sessions WHERE user_id = ? AND replay_blob IS NULL",
                (int(user_id),),
            )
            try:
                return int(cur.rowcount or 0)
            except Exception:
                return 0

    def upsert_event_label(
        self, *, session_id: str, event_id: str, label: str, note: str = "", author: str = "user"
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO event_labels (session_id, event_id, label, note, author, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, event_id) DO UPDATE SET
                  label=excluded.label,
                  note=excluded.note,
                  author=excluded.author,
                  updated_at=excluded.updated_at
                """,
                (str(session_id), str(event_id), str(label), str(note or ""), str(author or "user"), _utc_now_iso()),
            )

    def list_event_labels(self, *, session_id: str) -> Dict[str, Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_id, label, note, author FROM event_labels WHERE session_id = ?",
                (str(session_id),),
            ).fetchall()
            out: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                out[str(r["event_id"])] = {
                    "label": str(r["label"]),
                    "note": str(r["note"] or ""),
                    "author": str(r["author"] or "user"),
                }
            return out

    def list_llm_event_explanations(
        self,
        *,
        user_id: int,
        replay_fingerprint: str,
        model_id: str,
        prompt_version: str,
    ) -> Dict[str, Dict[str, Any]]:
        fp = str(replay_fingerprint or "").strip()
        if not fp:
            return {}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_key, event_hash, title, body, updated_at
                FROM llm_event_explanations
                WHERE user_id = ? AND replay_fingerprint = ? AND model_id = ? AND prompt_version = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (int(user_id), fp, str(model_id or ""), str(prompt_version or "")),
            ).fetchall()
            out: Dict[str, Dict[str, Any]] = {}
            for r in rows:
                k = str(r["event_key"] or "").strip()
                if not k or k in out:
                    continue
                out[k] = {
                    "event_hash": str(r["event_hash"] or ""),
                    "title": str(r["title"] or ""),
                    "body": str(r["body"] or ""),
                    "updated_at": str(r["updated_at"] or ""),
                }
            return out

    def upsert_llm_event_explanations(
        self,
        *,
        user_id: int,
        replay_fingerprint: str,
        model_id: str,
        prompt_version: str,
        rows: List[Dict[str, Any]],
    ) -> None:
        fp = str(replay_fingerprint or "").strip()
        if not fp or not rows:
            return
        now = _utc_now_iso()
        with self._connect() as conn:
            for row in rows:
                event_key = str(row.get("event_key", "") or "").strip()
                if not event_key:
                    continue
                conn.execute(
                    """
                    INSERT INTO llm_event_explanations (
                        user_id, replay_fingerprint, event_key, mechanic_id, event_time_s,
                        event_hash, model_id, prompt_version, title, body, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, replay_fingerprint, event_key, model_id, prompt_version, event_hash) DO UPDATE SET
                        title=excluded.title,
                        body=excluded.body,
                        updated_at=excluded.updated_at
                    """,
                    (
                        int(user_id),
                        fp,
                        event_key,
                        str(row.get("mechanic_id", "") or ""),
                        float(row.get("event_time_s", 0.0) or 0.0),
                        str(row.get("event_hash", "") or ""),
                        str(model_id or ""),
                        str(prompt_version or ""),
                        str(row.get("title", "") or ""),
                        str(row.get("body", "") or ""),
                        now,
                    ),
                )

    def delete_account(self, *, auth_user_id: int) -> None:
        auth_user_id = int(auth_user_id)
        with self._connect() as conn:
            user_row = conn.execute("SELECT id FROM users WHERE auth_user_id = ?", (auth_user_id,)).fetchone()
            user_id = int(user_row["id"]) if user_row else None

            if user_id is not None:
                replay_ids = [
                    str(row["id"])
                    for row in conn.execute("SELECT id FROM replay_sessions WHERE user_id = ?", (user_id,)).fetchall()
                ]
                if replay_ids:
                    q = ",".join(["?"] * len(replay_ids))
                    conn.execute(f"DELETE FROM event_labels WHERE session_id IN ({q})", tuple(replay_ids))
                conn.execute("DELETE FROM replay_sessions WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM recommendation_snapshots WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM drill_runs WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM llm_event_explanations WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM app_state WHERE key = ?", (self._aliases_key(user_id),))
                conn.execute(
                    "DELETE FROM app_state WHERE key = 'active_user_id' AND value = ?",
                    (str(user_id),),
                )
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

            conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (auth_user_id,))
            conn.execute("DELETE FROM auth_users WHERE id = ?", (auth_user_id,))
