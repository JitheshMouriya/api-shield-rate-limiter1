# API Shield — Token-Bucket Rate Limiter

A lightweight API rate-limiting system built with **FastAPI, Python, SQLite, and Streamlit**. API Shield implements the Token Bucket algorithm to control request traffic, prevent excessive API usage, and visualize rate-limiting behavior through an interactive dashboard.

## Overview

APIs often need protection against excessive requests from individual clients. Without rate limiting, a client can consume disproportionate resources, degrade service performance, or overwhelm an application with repeated requests.

API Shield addresses this problem using the **Token Bucket algorithm**. Each client has a bucket with a configurable token capacity. Requests consume tokens, and tokens replenish over time at a configurable rate. When a bucket has insufficient tokens, the request is denied until enough tokens become available.

The project combines a REST API with an interactive dashboard to make rate-limiting behavior easy to test, monitor, and understand.

## Key Features

- **Token Bucket Algorithm:** Controls request frequency using token consumption and time-based replenishment.
- **Configurable Rate Limits:** Adjust bucket capacity and token refill rate.
- **Client-Level Isolation:** Maintain independent token buckets for different clients.
- **Request Evaluation:** Allow or deny requests based on token availability.
- **Retry Timing:** Estimate when a denied client can make another request.
- **Persistent Storage:** Store request history, configuration, and analytics in SQLite.
- **Interactive Dashboard:** Monitor token availability and simulate individual requests or bursts of traffic.
- **Visual Analytics:** Explore allowed and denied requests, token usage, and client activity through charts.
- **Automated Testing:** Validate rate-limiting logic and API behavior with pytest.

## Tech Stack

| Technology | Purpose |
|---|---|
| Python | Core application logic |
| FastAPI | REST API and request handling |
| SQLite | Persistent storage for configurations and request history |
| Streamlit | Interactive monitoring dashboard |
| Plotly | Interactive charts and visualizations |
| Pytest | Automated testing |

## How It Works

API Shield follows four basic steps:

1. **Initialize:** A new client receives a bucket containing the configured number of tokens.
2. **Refill:** Tokens are replenished according to the elapsed time and configured refill rate, without exceeding bucket capacity.
3. **Evaluate:** An incoming request is allowed if at least one token is available. An allowed request consumes one token; a denied request consumes none.
4. **Monitor:** Request outcomes and relevant activity are recorded for analysis in the dashboard.

### Example

Suppose a client has a bucket capacity of 5 tokens and a refill rate of 1 token per second.

- The first five requests can be accepted when the bucket is full.
- A sixth immediate request is denied because no tokens remain.
- After one second, approximately one token becomes available.
- The client can make another request, subject to the current bucket state.

This behavior provides a simple mechanism for controlling request bursts while allowing traffic to resume as tokens replenish.

## Architecture

```text
                 ┌──────────────────────┐
                 │   Streamlit Dashboard│
                 │ Controls, Charts, UI │
                 └──────────┬───────────┘
                            │ HTTP Requests
                            ▼
                 ┌──────────────────────┐
                 │     FastAPI Backend  │
                 │   REST API Endpoints │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │   Token Bucket Logic │
                 │ Refill and Evaluation│
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │    SQLite Database   │
                 │ History and Analytics│
                 └──────────────────────┘
```

The backend handles request evaluation, the token-bucket module implements the rate-limiting rules, SQLite stores persistent records, and Streamlit provides the monitoring interface.

## Dashboard and Analytics

The dashboard is designed to make the algorithm observable rather than treating rate limiting as a black box.

Depending on the implemented features, it can provide:

- Current token availability and bucket capacity.
- Controls for changing capacity and refill rate.
- Individual request and burst-traffic simulations.
- Total, allowed, and denied request counts.
- Request allowance percentage.
- Token-usage history over time.
- Allowed-versus-denied request distribution.
- Client activity comparisons.
- A request history table for examining individual outcomes.

Charts should be populated from the application's recorded data rather than simulated placeholder values.

## Getting Started

### Prerequisites

- Python 3.10 or a compatible version supported by your dependencies.
- pip
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/api-shield-rate-limiter.git
cd api-shield-rate-limiter
```

Replace `YOUR_USERNAME` with your GitHub username.

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

### 3. Install Dependencies

If the project includes a `requirements.txt` file:

```bash
pip install -r requirements.txt
```

If dependencies are managed through another file or tool, follow the repository's actual setup instructions.

### 4. Start the Backend

For a project using `app.main:app` as its FastAPI entry point:

```bash
uvicorn app.main:app --reload
```

The API will typically be available at:

`http://127.0.0.1:8000`

FastAPI's interactive API documentation is available at:

`http://127.0.0.1:8000/docs`

### 5. Start the Dashboard

Open a second terminal, activate the same virtual environment, and run the Streamlit entry point. For example, if the file is named `frontend.py`:

```bash
streamlit run frontend.py
```

Streamlit will display the local dashboard URL in the terminal.

**Note:** Adjust the entry-point commands above if your repository uses different filenames or module paths.

## API Endpoints

The following table describes the intended API surface. Keep only the endpoints that are implemented in the repository and update their paths or methods where necessary.

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Check service health |
| `POST /api/configure` | Configure rate-limiting parameters |
| `POST /api/check` | Evaluate an incoming request |
| `GET /api/status/{client_id}` | Retrieve a client's bucket status |
| `POST /api/reset/{client_id}` | Reset a client's bucket |
| `GET /api/requests` | Retrieve request history |
| Analytics endpoints | Retrieve aggregated request and token-usage metrics |

## Running Tests

Run the automated test suite from the project root:

```bash
pytest -v
```

Tests should cover core behavior such as token consumption, token replenishment, bucket-capacity enforcement, request denial, independent client buckets, and relevant API responses.

## Project Structure

An example structure for this project is:

```text
api-shield-rate-limiter/
├── app/
│   ├── main.py
│   ├── limiter.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   └── routes/
├── tests/
├── data/
├── frontend.py
├── requirements.txt
├── .gitignore
└── README.md
```

The actual directory structure may differ depending on the implementation.

## Design Considerations

- **Separation of concerns:** Keep rate-limiting logic independent of the API and dashboard.
- **Persistence:** Store request history and configuration in a local SQLite database.
- **Correctness:** Refill tokens based on elapsed time while enforcing bucket capacity.
- **Client isolation:** Track each client's bucket independently.
- **Testability:** Make time-dependent logic testable without relying on real delays.
- **Observability:** Use recorded request outcomes to derive analytics.

This implementation is intended as a learning and demonstration project. Production deployments would require additional consideration of distributed rate limiting, authentication, deployment security, and coordination across multiple application workers.

## Future Improvements

- Add configurable per-client rate-limit policies.
- Support rate-limit response headers such as `Retry-After`.
- Add API-key-based client identification.
- Explore Redis-backed shared state for multi-worker deployments.
- Add load testing and performance benchmarks.
- Introduce configurable alert thresholds for unusual denial rates.

## Learning Outcomes

This project demonstrates practical experience with:

- REST API development using FastAPI.
- Rate-limiting algorithms and time-dependent state.
- Database persistence and SQL-based analytics.
- Interactive dashboards and data visualization.
- Automated testing and modular application design.
- Backend/frontend integration and API observability.

## License

Add a license file if you intend to distribute the project publicly. For example, an MIT License can be used if it suits your intended use and you include the appropriate license text.

---

**API Shield** — making API request control observable, testable, and easy to understand.
