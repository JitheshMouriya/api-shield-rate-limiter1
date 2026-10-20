"""
Analytics routes — all data comes from the SQLite database.
"""

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter

from app import database as db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _since(minutes: int) -> str | None:
    if minutes <= 0:
        return None
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


@router.get("/summary")
def summary(minutes: int = 60) -> dict:
    return db.summary_stats(since=_since(minutes))


@router.get("/activity")
def activity(minutes: int = 60) -> list:
    bucket_minutes = 1 if minutes <= 60 else 60
    return db.activity_over_time(since=_since(minutes), bucket_minutes=bucket_minutes)


@router.get("/outcomes")
def outcomes(minutes: int = 60) -> dict:
    return db.outcomes(since=_since(minutes))


@router.get("/clients")
def clients(minutes: int = 60, top_n: int = 10) -> list:
    return db.client_activity(since=_since(minutes), top_n=top_n)


@router.get("/tokens")
def tokens(client_id: str, minutes: int = 60) -> list:
    return db.token_history(client_id=client_id, since=_since(minutes))
