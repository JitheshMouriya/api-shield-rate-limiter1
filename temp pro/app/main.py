"""
API Shield — FastAPI application entry point.

Endpoints:
  GET  /api/health
  POST /api/configure
  POST /api/check
  GET  /api/status/{client_id}
  POST /api/reset/{client_id}
  GET  /api/requests
  GET  /api/analytics/summary
  GET  /api/analytics/activity
  GET  /api/analytics/outcomes
  GET  /api/analytics/clients
  GET  /api/analytics/tokens
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import database as db
from app.models import HealthResponse
from app.routes import analytics as analytics_router
from app.routes import limiter as limiter_router

VERSION = "2.0.0"

app = FastAPI(
    title="API Shield",
    description="Token-bucket rate limiter with SQLite persistence and a Streamlit dashboard.",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Streamlit runs on a different port
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database tables on startup
@app.on_event("startup")
def startup() -> None:
    db.init_db()


# Mount routers
app.include_router(limiter_router.router)
app.include_router(analytics_router.router)


@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=VERSION)
