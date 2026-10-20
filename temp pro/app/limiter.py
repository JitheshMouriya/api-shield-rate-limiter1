"""
Token-bucket rate limiting algorithm.

Each client gets an independent bucket holding at most `capacity` tokens.
Tokens refill at `refill_rate` tokens per second. A new client's bucket
starts full. Every allowed request consumes exactly one token; requests
arriving when fewer than one token is available are denied.

Designed to be used by the FastAPI backend. The database layer is kept
separate — this module is pure in-memory algorithm logic.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Bucket:
    """Mutable state for a single client's token bucket."""
    capacity: float
    refill_rate: float
    tokens: float
    last_refill: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock, compare=False, repr=False)

    def _refill(self) -> None:
        """Add tokens earned since last refill. Must be called while holding self.lock."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        if self.refill_rate > 0:
            earned = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + earned)
        self.last_refill = now

    def consume(self) -> tuple[bool, float, float, Optional[float]]:
        """
        Attempt to consume one token.

        Returns
        -------
        allowed : bool
        tokens_before : float  — snapshot before this operation
        tokens_after  : float  — snapshot after this operation
        retry_after   : float | None
        """
        with self.lock:
            self._refill()
            tokens_before = round(self.tokens, 4)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                tokens_after = round(self.tokens, 4)
                return True, tokens_before, tokens_after, None
            # Not enough tokens — calculate wait time
            if self.refill_rate > 0:
                deficit = 1.0 - self.tokens
                retry_after = round(deficit / self.refill_rate, 3)
            else:
                retry_after = None  # never refills
            tokens_after = round(self.tokens, 4)
            return False, tokens_before, tokens_after, retry_after

    def status(self) -> dict:
        """Return a current snapshot (refills first)."""
        with self.lock:
            self._refill()
            return {
                "tokens": round(self.tokens, 4),
                "capacity": self.capacity,
                "refill_rate": self.refill_rate,
            }

    def reconfigure(self, capacity: float, refill_rate: float) -> None:
        """
        Update capacity and refill rate for this existing bucket.
        Refills under old settings first, then clamps tokens to new capacity.
        """
        with self.lock:
            self._refill()                          # earn under old rate first
            self.capacity = capacity
            self.refill_rate = refill_rate
            self.tokens = min(self.tokens, capacity) # clamp, don't reset

    def reset(self) -> None:
        """Refill to capacity immediately."""
        with self.lock:
            self.tokens = self.capacity
            self.last_refill = time.monotonic()


class RateLimiter:
    """
    Manages independent token buckets for multiple clients.

    Thread-safe: a registry lock protects the _buckets dict; individual
    bucket operations use per-bucket locks so different clients never
    block each other.
    """

    DEFAULT_CAPACITY = 10.0
    DEFAULT_REFILL_RATE = 1.0

    def __init__(
        self,
        default_capacity: float = DEFAULT_CAPACITY,
        default_refill_rate: float = DEFAULT_REFILL_RATE,
    ):
        self._validate(default_capacity, default_refill_rate)
        self._default_capacity = default_capacity
        self._default_refill_rate = default_refill_rate
        self._buckets: dict[str, Bucket] = {}
        self._registry_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate(capacity: float, refill_rate: float) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if refill_rate < 0:
            raise ValueError("refill_rate must be >= 0")

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(
        self,
        client_id: str,
        capacity: float,
        refill_rate: float,
    ) -> None:
        """
        Configure (or reconfigure) the bucket for a specific client.
        If no bucket exists yet, create one full.
        """
        self._validate(capacity, refill_rate)
        with self._registry_lock:
            if client_id in self._buckets:
                self._buckets[client_id].reconfigure(capacity, refill_rate)
            else:
                self._buckets[client_id] = Bucket(
                    capacity=capacity,
                    refill_rate=refill_rate,
                    tokens=capacity,
                )

    def set_defaults(self, capacity: float, refill_rate: float) -> None:
        """Update defaults used when new clients are first seen."""
        self._validate(capacity, refill_rate)
        self._default_capacity = capacity
        self._default_refill_rate = refill_rate

    # ------------------------------------------------------------------
    # Bucket access
    # ------------------------------------------------------------------

    def _get_or_create(self, client_id: str) -> Bucket:
        with self._registry_lock:
            if client_id not in self._buckets:
                self._buckets[client_id] = Bucket(
                    capacity=self._default_capacity,
                    refill_rate=self._default_refill_rate,
                    tokens=self._default_capacity,
                )
            return self._buckets[client_id]

    def _get(self, client_id: str) -> Optional[Bucket]:
        with self._registry_lock:
            return self._buckets.get(client_id)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, client_id: str) -> dict:
        """Evaluate and consume one token for client_id."""
        bucket = self._get_or_create(client_id)
        allowed, tokens_before, tokens_after, retry_after = bucket.consume()
        return {
            "client_id": client_id,
            "allowed": allowed,
            "tokens_before": tokens_before,
            "remaining": tokens_after,
            "retry_after": retry_after,
            "capacity": bucket.capacity,
        }

    def status(self, client_id: str) -> Optional[dict]:
        """Return current bucket snapshot or None if client is unknown."""
        bucket = self._get(client_id)
        if bucket is None:
            return None
        snap = bucket.status()
        snap["client_id"] = client_id
        return snap

    def reset(self, client_id: str) -> bool:
        """Reset client bucket to full. Returns False if client is unknown."""
        bucket = self._get(client_id)
        if bucket is None:
            return False
        bucket.reset()
        return True

    def get_defaults(self) -> dict:
        return {
            "capacity": self._default_capacity,
            "refill_rate": self._default_refill_rate,
        }


# Module-level singleton used by the FastAPI application.
limiter = RateLimiter()
