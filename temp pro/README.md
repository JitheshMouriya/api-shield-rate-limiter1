# API Shield

A lightweight **token-bucket rate limiter** with a FastAPI backend, SQLite persistence, and a Streamlit dashboard. Built for a company technical interview to demonstrate Python, REST API design, database persistence, data visualisation, and testing.

---

## Features

- Token-bucket algorithm with per-client independent buckets
- FastAPI backend with 11 endpoints
- SQLite persistence — request history and bucket state survive restarts
- Streamlit dashboard with real-time gauge, 4 Plotly charts, and burst testing
- Thread-safe concurrent request handling
- 60 automated tests across 4 test files

---

## Token-bucket algorithm

Each client has a bucket holding up to **capacity** tokens. Tokens refill at **refill\_rate** per second. Every allowed request consumes one token; if no token is available the request is denied and the client is told when to retry.

| Concept | Description |
|---|---|
| Capacity | Maximum tokens the bucket holds |
| Refill rate | Tokens added per second (0 = no refill) |
| New client | Starts with a full bucket |
| Allowed | Token ≥ 1 → consume, return `allowed: true` |
| Denied | Token < 1 → no consumption, return `allowed: false` + `retry_after` |

---

## Prerequisites

- Python 3.11+

---

## Installation

```bash
cd "temp pro"            # already in the project root
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Running the application

**Terminal 1 — FastAPI backend:**
```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Streamlit dashboard:**
```bash
source .venv/bin/activate
streamlit run frontend.py --server.port 8501
```

| Service | URL |
|---|---|
| Streamlit dashboard | http://localhost:8501 |
| FastAPI interactive docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/api/health |

---

## API endpoints

### Health
```
GET /api/health
```
```json
{ "status": "ok", "version": "2.0.0" }
```

### Configure a client bucket
```
POST /api/configure
{ "client_id": "user-42", "capacity": 10, "refill_rate": 2.0 }
```

### Check / consume a token
```
POST /api/check
{ "client_id": "user-42" }
```
```json
{ "client_id": "user-42", "allowed": true, "tokens_before": 10.0,
  "remaining": 9.0, "retry_after": null, "capacity": 10.0, "response_ms": 0.4 }
```

### Get bucket status
```
GET /api/status/{client_id}
```

### Reset bucket to full
```
POST /api/reset/{client_id}
```

### Request history (filterable)
```
GET /api/requests?client_id=user-42&decision=denied&minutes=60&limit=50
```

### Analytics
```
GET /api/analytics/summary?minutes=60
GET /api/analytics/activity?minutes=60
GET /api/analytics/outcomes?minutes=60
GET /api/analytics/clients?minutes=60
GET /api/analytics/tokens?client_id=user-42&minutes=60
```

---

## Running tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

Expected output: **60 passed**

Tests use temporary SQLite databases and a mocked monotonic clock — no real sleeps, no state left behind.

---

## SQLite persistence

- Database location: `data/api_shield.db` (created automatically)
- Tables: `clients` (bucket state), `request_history` (every decision)
- Bucket state is restored on restart using wall-clock timestamps to calculate elapsed refill time
- Request history is permanent across restarts; use `minutes` query parameter to filter by recency

---

## Project structure

```
app/
  main.py         FastAPI app entry point
  limiter.py      Token-bucket algorithm (pure Python, no DB)
  database.py     SQLite queries and schema
  models.py       Pydantic schemas
  routes/
    limiter.py    /api/configure, /api/check, /api/status, /api/reset, /api/requests
    analytics.py  /api/analytics/*
frontend.py       Streamlit dashboard
tests/
  test_limiter.py   Algorithm unit tests (20 tests)
  test_database.py  Database layer tests (11 tests)
  test_api.py       API integration tests (20 tests)
  test_analytics.py Analytics query tests (9 tests)
data/             SQLite database (created at runtime)
requirements.txt
.gitignore
README.md
```

---

## Known limitations

- **In-memory bucket state** — the `RateLimiter` singleton lives in the FastAPI process. State is lost if the process restarts, though request *history* and last-known bucket config survive via SQLite and are not automatically re-loaded into memory on startup.
- **Single process only** — running multiple Uvicorn workers with `--workers N` gives each worker its own independent `RateLimiter` instance. For multi-worker or multi-machine deployments, replace the in-memory store with Redis or a shared database.
- **No authentication** — any caller can use any `client_id`.
