"""
SQLite persistence layer for API Shield.

Tables
------
clients          — bucket configuration and current token count
request_history  — every request decision with timing

All timestamps stored as ISO-8601 UTC strings for easy filtering.
Monotonic time is NOT stored; we use wall-clock (datetime.utcnow) for
persistence and calculate elapsed refill time from that on restart.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

DB_PATH = Path(__file__).parent.parent / "data" / "api_shield.db"

# One lock for writes; SQLite WAL mode allows concurrent readers.
_write_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables and indexes if they do not already exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                client_id    TEXT PRIMARY KEY,
                capacity     REAL NOT NULL,
                refill_rate  REAL NOT NULL,
                tokens       REAL NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS request_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id     TEXT NOT NULL,
                allowed       INTEGER NOT NULL,   -- 1 or 0
                tokens_before REAL NOT NULL,
                tokens_after  REAL NOT NULL,
                retry_after   REAL,
                response_ms   REAL,
                created_at    TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_rh_client    ON request_history(client_id);
            CREATE INDEX IF NOT EXISTS idx_rh_created   ON request_history(created_at);
            CREATE INDEX IF NOT EXISTS idx_rh_allowed   ON request_history(allowed);
        """)


# ---------------------------------------------------------------------------
# Client / bucket persistence
# ---------------------------------------------------------------------------

def upsert_client(
    client_id: str,
    capacity: float,
    refill_rate: float,
    tokens: float,
) -> None:
    """Insert or update the persisted bucket state for a client."""
    now = _now()
    with _write_lock, get_conn() as conn:
        conn.execute(
            """
            INSERT INTO clients (client_id, capacity, refill_rate, tokens, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                capacity    = excluded.capacity,
                refill_rate = excluded.refill_rate,
                tokens      = excluded.tokens,
                updated_at  = excluded.updated_at
            """,
            (client_id, capacity, refill_rate, tokens, now),
        )


def get_client(client_id: str) -> Optional[dict]:
    """Return persisted bucket state or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM clients WHERE client_id = ?", (client_id,)
        ).fetchone()
    return dict(row) if row else None


def get_all_clients() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT client_id, capacity, refill_rate, tokens FROM clients ORDER BY client_id"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Request history
# ---------------------------------------------------------------------------

def insert_request(
    client_id: str,
    allowed: bool,
    tokens_before: float,
    tokens_after: float,
    retry_after: Optional[float],
    response_ms: Optional[float],
) -> None:
    now = _now()
    with _write_lock, get_conn() as conn:
        conn.execute(
            """
            INSERT INTO request_history
                (client_id, allowed, tokens_before, tokens_after,
                 retry_after, response_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_id,
                1 if allowed else 0,
                tokens_before,
                tokens_after,
                retry_after,
                response_ms,
                now,
            ),
        )


def get_requests(
    client_id: Optional[str] = None,
    decision: Optional[str] = None,   # "allowed" | "denied" | None
    since: Optional[str] = None,       # ISO timestamp
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    filters = []
    params: list = []
    if client_id:
        filters.append("client_id = ?")
        params.append(client_id)
    if decision == "allowed":
        filters.append("allowed = 1")
    elif decision == "denied":
        filters.append("allowed = 0")
    if since:
        filters.append("created_at >= ?")
        params.append(since)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params += [limit, offset]

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, client_id, allowed, tokens_before, tokens_after,
                   retry_after, response_ms, created_at
            FROM request_history
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Analytics queries
# ---------------------------------------------------------------------------

def summary_stats(since: Optional[str] = None) -> dict:
    where = "WHERE created_at >= ?" if since else ""
    params = [since] if since else []
    with get_conn() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*)                    AS total,
                SUM(allowed)                AS allowed,
                COUNT(*) - SUM(allowed)     AS denied
            FROM request_history {where}
            """,
            params,
        ).fetchone()
    total   = row["total"] or 0
    allowed = row["allowed"] or 0
    denied  = row["denied"] or 0
    pct     = round(allowed / total * 100, 1) if total > 0 else 0.0
    return {"total": total, "allowed": allowed, "denied": denied, "allow_pct": pct}


def activity_over_time(since: Optional[str] = None, bucket_minutes: int = 1) -> list[dict]:
    """Return allowed/denied counts grouped by time bucket."""
    where = "WHERE created_at >= ?" if since else ""
    params = [since] if since else []
    # SQLite strftime can group by minute
    fmt = "%Y-%m-%dT%H:%M" if bucket_minutes <= 1 else "%Y-%m-%dT%H"
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT
                strftime('{fmt}', created_at) AS bucket,
                SUM(allowed)                  AS allowed,
                COUNT(*) - SUM(allowed)       AS denied
            FROM request_history {where}
            GROUP BY bucket
            ORDER BY bucket
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def outcomes(since: Optional[str] = None) -> dict:
    return summary_stats(since)  # reuse


def client_activity(since: Optional[str] = None, top_n: int = 10) -> list[dict]:
    where = "WHERE created_at >= ?" if since else ""
    params = [since] if since else []
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT
                client_id,
                COUNT(*)        AS total,
                SUM(allowed)    AS allowed,
                COUNT(*) - SUM(allowed) AS denied
            FROM request_history {where}
            GROUP BY client_id
            ORDER BY total DESC
            LIMIT {top_n}
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def token_history(client_id: str, since: Optional[str] = None) -> list[dict]:
    where = "WHERE client_id = ?"
    params: list = [client_id]
    if since:
        where += " AND created_at >= ?"
        params.append(since)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT created_at, tokens_before, tokens_after, allowed
            FROM request_history {where}
            ORDER BY created_at ASC
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
