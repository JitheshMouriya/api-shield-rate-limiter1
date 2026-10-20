"""
Analytics query accuracy tests (tests/test_analytics.py).
Uses a temporary database; patches DB_PATH so the real DB is never touched.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

import app.database as db_module


@pytest.fixture()
def tdb(tmp_path):
    db_file = tmp_path / "analytics_test.db"
    with patch.object(db_module, "DB_PATH", db_file):
        db_module.init_db()
        yield db_module


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")


def _past_str(minutes: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


# ---------------------------------------------------------------------------
# Summary accuracy
# ---------------------------------------------------------------------------

def test_summary_allow_pct(tdb):
    for _ in range(7):
        tdb.insert_request("x", True, 9.0, 8.0, None, 1.0)
    for _ in range(3):
        tdb.insert_request("x", False, 0.1, 0.1, 0.9, 1.0)
    s = tdb.summary_stats()
    assert s["total"] == 10
    assert s["allow_pct"] == 70.0


def test_summary_since_filter(tdb, tmp_path):
    """Old records should be excluded when `since` is set."""
    old_ts = _past_str(120)
    cutoff  = _past_str(10)

    # Insert an old record directly via SQL with a specific timestamp
    db_file = tmp_path / "analytics_test.db"
    with patch.object(db_module, "DB_PATH", db_file):
        import sqlite3
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            """INSERT INTO request_history
               (client_id, allowed, tokens_before, tokens_after, retry_after, response_ms, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("y", 1, 9.0, 8.0, None, 1.0, old_ts),
        )
        conn.commit()
        conn.close()

    tdb.insert_request("y", True, 8.0, 7.0, None, 1.0)  # recent

    s = tdb.summary_stats(since=cutoff)
    assert s["total"] == 1  # only the recent one


# ---------------------------------------------------------------------------
# Client activity ordering
# ---------------------------------------------------------------------------

def test_client_activity_ordered_by_total(tdb):
    for _ in range(5):
        tdb.insert_request("busy", True, 9.0, 8.0, None, 1.0)
    for _ in range(2):
        tdb.insert_request("lazy", True, 9.0, 8.0, None, 1.0)

    result = tdb.client_activity()
    assert result[0]["client_id"] == "busy"
    assert result[0]["total"] == 5


# ---------------------------------------------------------------------------
# Token history ordering
# ---------------------------------------------------------------------------

def test_token_history_ascending(tdb):
    tdb.insert_request("t1", True, 10.0, 9.0, None, 1.0)
    tdb.insert_request("t1", True,  9.0, 8.0, None, 1.0)
    hist = tdb.token_history("t1")
    assert len(hist) == 2
    assert hist[0]["tokens_before"] == 10.0
    assert hist[1]["tokens_before"] == 9.0


# ---------------------------------------------------------------------------
# Empty database edge cases
# ---------------------------------------------------------------------------

def test_activity_empty_db(tdb):
    assert tdb.activity_over_time() == []


def test_client_activity_empty_db(tdb):
    assert tdb.client_activity() == []


def test_token_history_unknown_client(tdb):
    assert tdb.token_history("nobody") == []


def test_summary_empty_db(tdb):
    s = tdb.summary_stats()
    assert s["total"] == 0
    assert s["allowed"] == 0
    assert s["denied"] == 0
    assert s["allow_pct"] == 0.0
