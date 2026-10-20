"""
Rate-limiter routes: configure, check, status, reset.
"""

import time
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException

from app import database as db
from app.limiter import limiter
from app.models import (
    CheckRequest,
    CheckResponse,
    ConfigureRequest,
    ConfigureResponse,
    ResetResponse,
    StatusResponse,
)

router = APIRouter(prefix="/api", tags=["rate-limit"])


def _since(minutes: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")


@router.post("/configure", response_model=ConfigureResponse)
def configure(body: ConfigureRequest) -> ConfigureResponse:
    """Configure or reconfigure a client's bucket."""
    try:
        limiter.configure(
            client_id=body.client_id,
            capacity=body.capacity,
            refill_rate=body.refill_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Persist current state
    snap = limiter.status(body.client_id)
    if snap:
        db.upsert_client(
            body.client_id, snap["capacity"], snap["refill_rate"], snap["tokens"]
        )

    return ConfigureResponse(
        message="Configuration applied.",
        client_id=body.client_id,
        capacity=body.capacity,
        refill_rate=body.refill_rate,
    )


@router.post("/check", response_model=CheckResponse)
def check(body: CheckRequest) -> CheckResponse:
    """Consume one token for a client."""
    t0 = time.perf_counter()
    result = limiter.check(body.client_id)
    response_ms = round((time.perf_counter() - t0) * 1000, 3)

    # Persist request + updated bucket state
    db.insert_request(
        client_id=body.client_id,
        allowed=result["allowed"],
        tokens_before=result["tokens_before"],
        tokens_after=result["remaining"],
        retry_after=result["retry_after"],
        response_ms=response_ms,
    )
    snap = limiter.status(body.client_id)
    if snap:
        db.upsert_client(
            body.client_id, snap["capacity"], snap["refill_rate"], snap["tokens"]
        )

    return CheckResponse(
        client_id=result["client_id"],
        allowed=result["allowed"],
        tokens_before=result["tokens_before"],
        remaining=result["remaining"],
        retry_after=result["retry_after"],
        capacity=result["capacity"],
        response_ms=response_ms,
    )


@router.get("/status/{client_id}", response_model=StatusResponse)
def status(client_id: str) -> StatusResponse:
    """Return current bucket snapshot for an existing client."""
    client_id = client_id.strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id must not be blank.")
    snap = limiter.status(client_id)
    if snap is None:
        raise HTTPException(
            status_code=404,
            detail=f"No bucket found for '{client_id}'. Send a request first.",
        )
    return StatusResponse(**snap)


@router.post("/reset/{client_id}", response_model=ResetResponse)
def reset(client_id: str) -> ResetResponse:
    """Reset client bucket to full capacity."""
    client_id = client_id.strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id must not be blank.")
    ok = limiter.reset(client_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"No bucket found for '{client_id}'.",
        )
    snap = limiter.status(client_id)
    if snap:
        db.upsert_client(
            client_id, snap["capacity"], snap["refill_rate"], snap["tokens"]
        )
    return ResetResponse(message="Bucket reset to full.", client_id=client_id)


@router.get("/requests")
def get_requests(
    client_id: str = "",
    decision: str = "",
    minutes: int = 60,
    limit: int = 100,
    offset: int = 0,
) -> list:
    since = _since(minutes)
    rows = db.get_requests(
        client_id=client_id or None,
        decision=decision or None,
        since=since,
        limit=min(limit, 500),
        offset=offset,
    )
    return rows
