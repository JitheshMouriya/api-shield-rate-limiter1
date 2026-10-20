"""
Tests for the database layer (app/database.py).
Uses a temporary SQLite file so the real data/api_shield.db is never touched.
"""

import os
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

import app.database as real_db


# ---------------------------------------------------------------------------
# Fixture — temporary database
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Patch DB_PATH to a temp file and initialise the schema."""
    db_file = tmp_path / "test.db"
    with patch.object(real_db, "DB_PATH", db_file):
        real_db.init_db()
        yield real_db


# ---------------------------------------------------------------------------
# 1. Schema initialises correctly
# ---------------------------------------------------------------------------

def test_init_creates_tables(tmp_db):
    with tmp_db.get_conn() as conn:
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "clients" in tables
    assert "request_history" in tables


# ---------------------------------------------------------------------------
# 2. Upsert and retrieve client
# ---------------------------------------------------------------------------

def test_upsert_and_get_client(tmp_db):
    tmp_db.upsert_client("c1", capacity=10.0, refill_rate=1.0, tokens=8.5)
    row = tmp_db.get_client("c1")
    assert row is not None
    assert row["capacity"] == 10.0
    assert row["tokens"] == 8.5


def test_upsert_updates_existing(tmp_db):
    tmp_db.upsert_client("c2", 10.0, 1.0, 10.0)
    tmp_db.upsert_client("c2", 20.0, 2.0, 15.0)  # update
    row = tmp_db.get_client("c2")
    assert row["capacity"] == 20.0
    assert row["tokens"] == 15.0


def test_get_unknown_client_returns_none(tmp_db):
    assert tmp_db.get_client("ghost") is None


# ---------------------------------------------------------------------------
# 3. Request history insert and query
# ---------------------------------------------------------------------------

def test_insert_and_retrieve_request(tmp_db):
    tmp_db.insert_request("u1", allowed=True, tokens_before=9.0,
                           tokens_after=8.0, retry_after=None, response_ms=1.2)
    rows = tmp_db.get_requests(client_id="u1")
    assert len(rows) == 1
    assert rows[0]["allowed"] == 1
    assert rows[0]["tokens_before"] == 9.0


def test_filter_by_decision(tmp_db):
    tmp_db.insert_request("u2", True,  9.0, 8.0, None, 1.0)
    tmp_db.insert_request("u2", False, 0.1, 0.1, 0.9, 1.0)
    allowed_rows = tmp_db.get_requests(client_id="u2", decision="allowed")
    denied_rows  = tmp_db.get_requests(client_id="u2", decision="denied")
    assert len(allowed_rows) == 1
    assert len(denied_rows)  == 1


def test_filter_by_since(tmp_db):
    past   = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.%f")
    recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.%f")
    # Manually insert an old row (patch _now)
    with patch.object(real_db, "_now", return_value=past):
        tmp_db.insert_request("u3", True, 9.0, 8.0, None, 1.0)
    tmp_db.insert_request("u3", True, 8.0, 7.0, None, 1.0)  # recent

    rows = tmp_db.get_requests(client_id="u3", since=recent)
    assert len(rows) == 1  # only the recent one


# ---------------------------------------------------------------------------
# 4. Analytics — summary stats
# ---------------------------------------------------------------------------

def test_summary_empty(tmp_db):
    s = tmp_db.summary_stats()
    assert s["total"] == 0
    assert s["allow_pct"] == 0.0


def test_summary_counts(tmp_db):
    for _ in range(3):
        tmp_db.insert_request("s1", True,  9.0, 8.0, None, 1.0)
    for _ in range(2):
        tmp_db.insert_request("s1", False, 0.1, 0.1, 0.9, 1.0)

    s = tmp_db.summary_stats()
    assert s["total"]   == 5
    assert s["allowed"] == 3
    assert s["denied"]  == 2
    assert s["allow_pct"] == 60.0


# ---------------------------------------------------------------------------
# 5. Analytics — activity over time
# ---------------------------------------------------------------------------

def test_activity_returns_list(tmp_db):
    tmp_db.insert_request("a1", True, 9.0, 8.0, None, 1.0)
    result = tmp_db.activity_over_time()
    assert isinstance(result, list)
    assert len(result) >= 1


# ---------------------------------------------------------------------------
# 6. Analytics — client activity
# ---------------------------------------------------------------------------

def test_client_activity(tmp_db):
    tmp_db.insert_request("alpha", True, 9.0, 8.0, None, 1.0)
    tmp_db.insert_request("alpha", True, 8.0, 7.0, None, 1.0)
    tmp_db.insert_request("beta",  True, 9.0, 8.0, None, 1.0)
    result = tmp_db.client_activity()
    clients = [r["client_id"] for r in result]
    assert "alpha" in clients
    assert "beta"  in clients
    # alpha should be first (most requests)
    assert clients[0] == "alpha"


# ---------------------------------------------------------------------------
# 7. Token history
# ---------------------------------------------------------------------------

def test_token_history(tmp_db):
    tmp_db.insert_request("tok1", True,  10.0, 9.0, None, 1.0)
    tmp_db.insert_request("tok1", False,  0.5, 0.5, 0.5, 1.0)
    hist = tmp_db.token_history("tok1")
    assert len(hist) == 2
    assert hist[0]["tokens_before"] == 10.0
    assert hist[1]["tokens_after"]  == 0.5
