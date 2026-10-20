"""
Tests for the token-bucket algorithm (app/limiter.py).
Uses mocked monotonic clock — no real sleeping required.
"""

import threading
import time
from unittest.mock import patch

import pytest

from app.limiter import Bucket, RateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bucket(capacity: float = 10.0, refill_rate: float = 1.0) -> Bucket:
    b = Bucket(capacity=capacity, refill_rate=refill_rate, tokens=capacity)
    b.last_refill = time.monotonic()
    return b


def make_limiter(capacity: float = 10.0, refill_rate: float = 1.0) -> RateLimiter:
    return RateLimiter(default_capacity=capacity, default_refill_rate=refill_rate)


# ---------------------------------------------------------------------------
# 1. New client starts with a full bucket
# ---------------------------------------------------------------------------

def test_new_client_starts_full():
    rl = make_limiter(capacity=5.0, refill_rate=1.0)
    assert rl.status("alice") is None

    result = rl.check("alice")
    assert result["allowed"] is True
    assert pytest.approx(result["remaining"], abs=0.05) == 4.0


# ---------------------------------------------------------------------------
# 2. Token consumption per request
# ---------------------------------------------------------------------------

def test_tokens_consumed_per_request():
    rl = make_limiter(capacity=5.0, refill_rate=0.0)
    for expected in [4.0, 3.0, 2.0, 1.0, 0.0]:
        r = rl.check("bob")
        assert r["allowed"] is True
        assert pytest.approx(r["remaining"], abs=0.01) == expected


# ---------------------------------------------------------------------------
# 3. Request denied when empty; denied request consumes no token
# ---------------------------------------------------------------------------

def test_request_denied_when_empty():
    rl = make_limiter(capacity=2.0, refill_rate=0.0)
    rl.check("carol")
    rl.check("carol")
    r = rl.check("carol")
    assert r["allowed"] is False
    assert r["remaining"] < 1.0
    # tokens_before and tokens_after should be the same (no consumption)
    assert r["tokens_before"] == r["remaining"]


# ---------------------------------------------------------------------------
# 4. Fractional refill (mocked clock)
# ---------------------------------------------------------------------------

def test_fractional_refill():
    bucket = make_bucket(capacity=10.0, refill_rate=2.0)
    for _ in range(10):
        bucket.consume()

    # 1.5s × 2.0 tok/s = 3 tokens earned; consume 1 → 2 remaining
    future = bucket.last_refill + 1.5
    with patch("app.limiter.time.monotonic", return_value=future):
        allowed, _, tokens_after, _ = bucket.consume()

    assert allowed is True
    assert pytest.approx(tokens_after, abs=0.05) == 2.0


# ---------------------------------------------------------------------------
# 5. Tokens never exceed capacity
# ---------------------------------------------------------------------------

def test_tokens_never_exceed_capacity():
    bucket = make_bucket(capacity=5.0, refill_rate=100.0)
    future = bucket.last_refill + 1000.0
    with patch("app.limiter.time.monotonic", return_value=future):
        snap = bucket.status()
    assert snap["tokens"] == 5.0


# ---------------------------------------------------------------------------
# 6. Independent state per client
# ---------------------------------------------------------------------------

def test_independent_client_state():
    rl = make_limiter(capacity=3.0, refill_rate=0.0)
    for _ in range(3):
        rl.check("x")
    assert rl.check("x")["allowed"] is False

    ry = rl.check("y")
    assert ry["allowed"] is True
    assert pytest.approx(ry["remaining"], abs=0.01) == 2.0


# ---------------------------------------------------------------------------
# 7. Configuration change — reconfigure existing bucket
# ---------------------------------------------------------------------------

def test_reconfigure_preserves_tokens():
    rl = make_limiter(capacity=10.0, refill_rate=0.0)
    rl.check("dave")                             # 9 tokens left
    rl.configure("dave", capacity=20.0, refill_rate=2.0)
    snap = rl.status("dave")
    # Should be ~9 (not reset to 20)
    assert snap["tokens"] <= 10.0
    assert snap["tokens"] >= 8.5


def test_reconfigure_clamps_to_new_capacity():
    rl = make_limiter(capacity=10.0, refill_rate=0.0)
    rl.configure("eve", capacity=10.0, refill_rate=0.0)   # bucket = 10 tokens
    rl.configure("eve", capacity=3.0, refill_rate=0.0)    # shrink
    snap = rl.status("eve")
    assert snap["tokens"] <= 3.0
    assert snap["capacity"] == 3.0


# ---------------------------------------------------------------------------
# 8. Reset
# ---------------------------------------------------------------------------

def test_reset_refills_to_capacity():
    rl = make_limiter(capacity=5.0, refill_rate=0.0)
    for _ in range(5):
        rl.check("frank")
    rl.reset("frank")
    snap = rl.status("frank")
    assert pytest.approx(snap["tokens"], abs=0.01) == 5.0


def test_reset_unknown_client_returns_false():
    rl = make_limiter()
    assert rl.reset("nobody") is False


# ---------------------------------------------------------------------------
# 9. Zero refill rate — no division-by-zero
# ---------------------------------------------------------------------------

def test_zero_refill_rate_allows_until_empty():
    rl = make_limiter(capacity=2.0, refill_rate=0.0)
    assert rl.check("zr")["allowed"] is True
    assert rl.check("zr")["allowed"] is True
    r = rl.check("zr")
    assert r["allowed"] is False
    assert r["retry_after"] is None   # never refills


def test_zero_refill_rate_tokens_do_not_grow():
    bucket = make_bucket(capacity=5.0, refill_rate=0.0)
    future = bucket.last_refill + 1000.0
    with patch("app.limiter.time.monotonic", return_value=future):
        snap = bucket.status()
    assert snap["tokens"] == 5.0   # unchanged


# ---------------------------------------------------------------------------
# 10. Retry-after
# ---------------------------------------------------------------------------

def test_retry_after_positive_when_denied():
    rl = make_limiter(capacity=1.0, refill_rate=2.0)
    rl.check("g")
    r = rl.check("g")
    assert r["allowed"] is False
    assert r["retry_after"] is not None
    assert 0 < r["retry_after"] <= 0.6


def test_retry_after_none_when_allowed():
    rl = make_limiter(capacity=5.0, refill_rate=1.0)
    assert rl.check("h")["retry_after"] is None


def test_retry_after_none_when_zero_refill():
    rl = make_limiter(capacity=1.0, refill_rate=0.0)
    rl.check("i")
    r = rl.check("i")
    assert r["allowed"] is False
    assert r["retry_after"] is None


# ---------------------------------------------------------------------------
# 11. Concurrent safety
# ---------------------------------------------------------------------------

def test_concurrent_requests_safe():
    N  = 20
    rl = make_limiter(capacity=N // 2, refill_rate=0.0)
    results = []
    lock = threading.Lock()

    def worker():
        r = rl.check("concurrent")
        with lock:
            results.append(r["allowed"])

    threads = [threading.Thread(target=worker) for _ in range(N)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert sum(results) == N // 2
    assert len(results) == N


# ---------------------------------------------------------------------------
# 12. Status
# ---------------------------------------------------------------------------

def test_status_unknown_client():
    assert make_limiter().status("nobody") is None


def test_status_known_client():
    rl = make_limiter(capacity=7.0, refill_rate=1.0)
    rl.check("known")
    snap = rl.status("known")
    assert snap is not None
    assert snap["capacity"] == 7.0
    assert snap["tokens"] <= 7.0


# ---------------------------------------------------------------------------
# 13. set_defaults does not affect existing clients
# ---------------------------------------------------------------------------

def test_set_defaults_only_affects_new_clients():
    rl = make_limiter(capacity=10.0, refill_rate=1.0)
    rl.check("existing")                      # creates bucket with cap 10
    rl.set_defaults(capacity=3.0, refill_rate=0.5)
    rl.check("newclient")                      # should get cap 3

    assert rl.status("existing")["capacity"] == 10.0
    assert rl.status("newclient")["capacity"] == 3.0


# ---------------------------------------------------------------------------
# 14. Invalid configuration
# ---------------------------------------------------------------------------

def test_configure_rejects_zero_capacity():
    rl = make_limiter()
    with pytest.raises(ValueError, match="capacity"):
        rl.configure("bad", capacity=0, refill_rate=1.0)


def test_configure_rejects_negative_capacity():
    rl = make_limiter()
    with pytest.raises(ValueError, match="capacity"):
        rl.configure("bad", capacity=-5, refill_rate=1.0)


def test_configure_rejects_negative_rate():
    rl = make_limiter()
    with pytest.raises(ValueError, match="refill_rate"):
        rl.configure("bad", capacity=10.0, refill_rate=-1.0)
