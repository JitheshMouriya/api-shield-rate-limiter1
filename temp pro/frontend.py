"""
API Shield — Streamlit Dashboard
Token Bucket Rate Limiting Monitor

Run with:
    streamlit run frontend.py
"""

import time
from datetime import datetime, timezone, timedelta

import plotly.graph_objects as go
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "http://localhost:8000"
REFRESH_INTERVAL = 3   # seconds between auto-refresh when burst is idle

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="API Shield",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — dark, restrained, professional
# ---------------------------------------------------------------------------

st.markdown("""
<style>
  /* Dark base */
  [data-testid="stAppViewContainer"] { background: #0f1117; }
  [data-testid="stSidebar"]          { background: #1a1d27; border-right: 1px solid #2a2d3a; }
  [data-testid="stHeader"]           { background: #0f1117; }

  /* Typography */
  html, body, [class*="css"] { font-family: 'Inter', system-ui, sans-serif; color: #e2e4ed; }

  /* Metric cards */
  [data-testid="metric-container"] {
    background: #1a1d27;
    border: 1px solid #2a2d3a;
    border-radius: 6px;
    padding: 14px 18px;
  }
  [data-testid="stMetricLabel"]  { color: #7b8099 !important; font-size: 12px !important; text-transform: uppercase; letter-spacing: .06em; }
  [data-testid="stMetricValue"]  { color: #e2e4ed !important; font-size: 26px !important; font-weight: 700; }

  /* Buttons */
  .stButton > button {
    background: #1e40af; color: #fff; border: none;
    border-radius: 5px; font-weight: 600; padding: 6px 18px;
    transition: opacity .15s;
  }
  .stButton > button:hover { opacity: .85; }

  /* Dividers */
  hr { border-color: #2a2d3a; }

  /* Result banner helpers */
  .banner-allowed { background:#0f2e1a; border:1px solid #166534; border-radius:6px; padding:10px 16px; color:#22c55e; font-weight:600; }
  .banner-denied  { background:#2d1a05; border:1px solid #92400e; border-radius:6px; padding:10px 16px; color:#f59e0b; font-weight:600; }
  .badge-ok   { display:inline-block; background:#166534; color:#22c55e; border-radius:99px; font-size:11px; font-weight:700; padding:2px 8px; text-transform:uppercase; }
  .badge-deny { display:inline-block; background:#78350f; color:#f59e0b; border-radius:99px; font-size:11px; font-weight:700; padding:2px 8px; text-transform:uppercase; }
  .muted { color:#7b8099; font-size:12px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api(method: str, path: str, **kwargs):
    """Call FastAPI; return (ok, data)."""
    try:
        r = requests.request(method, f"{API_BASE}{path}", timeout=5, **kwargs)
        return r.ok, r.json()
    except Exception as exc:
        return False, {"detail": str(exc)}


@st.cache_data(ttl=5)
def fetch_health():
    ok, data = api("GET", "/api/health")
    return ok and data.get("status") == "ok"


def fetch_status(client_id: str):
    ok, data = api("GET", f"/api/status/{client_id}")
    return data if ok else None


def fetch_summary(minutes: int = 60):
    _, data = api("GET", f"/api/analytics/summary?minutes={minutes}")
    return data


def fetch_activity(minutes: int = 60):
    _, data = api("GET", f"/api/analytics/activity?minutes={minutes}")
    return data if isinstance(data, list) else []


def fetch_clients(minutes: int = 60):
    _, data = api("GET", f"/api/analytics/clients?minutes={minutes}")
    return data if isinstance(data, list) else []


def fetch_tokens(client_id: str, minutes: int = 60):
    _, data = api("GET", f"/api/analytics/tokens?client_id={client_id}&minutes={minutes}")
    return data if isinstance(data, list) else []


def fetch_requests(client_id: str = "", decision: str = "", minutes: int = 60, limit: int = 50):
    params = f"minutes={minutes}&limit={limit}"
    if client_id:
        params += f"&client_id={client_id}"
    if decision:
        params += f"&decision={decision}"
    _, data = api("GET", f"/api/requests?{params}")
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

for _k, _v in {
    "last_result": None,
    "burst_running": False,
    "burst_results": [],
    "token_snapshot": None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Sidebar — configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🛡️ API Shield")
    st.caption("Token Bucket Rate Limiting Monitor")
    st.divider()

    # --- Client selector ---
    st.markdown("**Client ID**")
    client_id = st.text_input(
        "client_id_input",
        value="client-1",
        max_chars=64,
        label_visibility="collapsed",
        placeholder="e.g. user-42",
    ).strip()
    if not client_id:
        client_id = "client-1"

    st.divider()

    # --- Bucket configuration ---
    st.markdown("**Bucket Configuration**")
    capacity = st.slider("Capacity (tokens)", 1, 100, 10)
    refill_rate = st.slider("Refill rate (tokens/sec)", 0.0, 20.0, 1.0, step=0.1)

    col_a, col_b = st.columns(2)
    with col_a:
        apply_cfg = st.button("Apply", use_container_width=True)
    with col_b:
        reset_btn = st.button("Reset", use_container_width=True)

    if apply_cfg and client_id:
        ok, data = api("POST", "/api/configure", json={
            "client_id": client_id,
            "capacity": capacity,
            "refill_rate": refill_rate,
        })
        if ok:
            st.success(f"Configured: cap={capacity}, rate={refill_rate}/s")
            st.cache_data.clear()
            st.session_state.last_result = None
        else:
            st.error(data.get("detail", "Error"))

    if reset_btn and client_id:
        ok, data = api("POST", f"/api/reset/{client_id}")
        if ok:
            st.success("Bucket reset to full.")
            st.cache_data.clear()
            st.session_state.last_result = None
        elif "404" in str(data.get("detail", "")):
            st.warning("No bucket yet — send a request first.")
        else:
            st.error(data.get("detail", "Error"))

    st.divider()

    # Active settings display
    snap = fetch_status(client_id)
    if snap:
        st.markdown("**Active settings**")
        st.markdown(
            f"<span class='muted'>Client:</span> `{client_id}`  \n"
            f"<span class='muted'>Capacity:</span> `{snap['capacity']}`  \n"
            f"<span class='muted'>Rate:</span> `{snap['refill_rate']} tok/s`  \n"
            f"<span class='muted'>Tokens now:</span> `{snap['tokens']:.2f}`",
            unsafe_allow_html=True,
        )
    else:
        st.caption("No active bucket — apply config or send a request.")

    st.divider()

    # Time-range filter for charts
    time_range = st.selectbox(
        "Chart time range",
        ["Last 15 min", "Last hour", "Last 24 hours"],
        index=1,
    )
    TIME_MAP = {"Last 15 min": 15, "Last hour": 60, "Last 24 hours": 1440}
    minutes = TIME_MAP[time_range]

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

healthy = fetch_health()
dot     = "🟢" if healthy else "🔴"
status_txt = "Backend online" if healthy else "Backend unreachable"

c1, c2 = st.columns([6, 2])
with c1:
    st.markdown("## 🛡️ API Shield")
    st.caption("Token Bucket Rate Limiting Monitor")
with c2:
    st.markdown(f"<div style='text-align:right;margin-top:16px'>{dot} {status_txt}</div>",
                unsafe_allow_html=True)

st.divider()

if not healthy:
    st.error("⚠️ Cannot reach FastAPI backend at localhost:8000. Start it with: `uvicorn app.main:app --reload`")
    st.stop()

# ---------------------------------------------------------------------------
# Summary metric cards
# ---------------------------------------------------------------------------

summary = fetch_summary(minutes)
total   = summary.get("total", 0)
allowed = summary.get("allowed", 0)
denied  = summary.get("denied", 0)
pct     = summary.get("allow_pct", 0.0)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Requests",    total)
m2.metric("Allowed",           allowed)
m3.metric("Denied",            denied)
m4.metric("Allow Rate",        f"{pct}%")

st.divider()

# ---------------------------------------------------------------------------
# Main layout — visualizer (left) | controls (right)
# ---------------------------------------------------------------------------

viz_col, ctrl_col = st.columns([3, 2], gap="large")

# ── Token-bucket visualizer ──────────────────────────────────────────────────
with viz_col:
    st.markdown("### Token Bucket")

    # Determine display values
    res = st.session_state.last_result
    if res:
        tokens_now = res.get("remaining", 0.0)
        cap_now    = res.get("capacity", 10.0)
        state      = "Allowed ✓" if res.get("allowed") else "Rate Limited ✗"
        state_color = "#22c55e" if res.get("allowed") else "#f59e0b"
    else:
        snap = fetch_status(client_id)
        if snap:
            tokens_now  = snap["tokens"]
            cap_now     = snap["capacity"]
        else:
            tokens_now = capacity
            cap_now    = capacity
        state       = "Ready"
        state_color = "#3b82f6"

    pct_full = min(100.0, tokens_now / cap_now * 100) if cap_now > 0 else 0.0

    # Plotly gauge
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=tokens_now,
        number={"suffix": f" / {cap_now:.0f}", "font": {"size": 28, "color": "#e2e4ed"}},
        gauge={
            "axis": {"range": [0, cap_now], "tickcolor": "#7b8099"},
            "bar": {"color": state_color},
            "bgcolor": "#1a1d27",
            "bordercolor": "#2a2d3a",
            "steps": [{"range": [0, cap_now], "color": "#252836"}],
            "threshold": {
                "line": {"color": "#ef4444", "width": 2},
                "thickness": 0.75,
                "value": 1,
            },
        },
        title={"text": f"<span style='color:#7b8099;font-size:13px'>{client_id}</span>",
               "font": {"size": 14}},
    ))
    fig_gauge.update_layout(
        paper_bgcolor="#0f1117",
        font_color="#e2e4ed",
        height=260,
        margin=dict(t=50, b=10, l=30, r=30),
    )
    st.plotly_chart(fig_gauge, use_container_width=True, key="gauge")

    # State + detail row
    g1, g2, g3 = st.columns(3)
    g1.metric("State",    state)
    g2.metric("Filled",   f"{pct_full:.1f}%")
    g3.metric("Rate",     f"{refill_rate} tok/s")

    # Last-result banner
    if res:
        if res.get("allowed"):
            st.markdown(
                f"<div class='banner-allowed'>✓ ALLOWED &nbsp;·&nbsp; "
                f"{res['remaining']:.2f} tokens remaining &nbsp;·&nbsp; "
                f"{res.get('response_ms', 0):.1f} ms</div>",
                unsafe_allow_html=True,
            )
        else:
            retry = res.get("retry_after")
            retry_txt = f" &nbsp;·&nbsp; Retry after {retry}s" if retry else ""
            st.markdown(
                f"<div class='banner-denied'>✗ RATE LIMITED &nbsp;·&nbsp; "
                f"{res['remaining']:.2f} tokens left{retry_txt}</div>",
                unsafe_allow_html=True,
            )

# ── Request controls ─────────────────────────────────────────────────────────
with ctrl_col:
    st.markdown("### Send Requests")

    # Single request
    if st.button("▶ Send Request", use_container_width=True):
        ok, data = api("POST", "/api/check", json={"client_id": client_id})
        if ok:
            st.session_state.last_result = data
            st.cache_data.clear()
        else:
            st.error(data.get("detail", "Request failed"))
        st.rerun()

    st.markdown("")

    # Burst controls
    burst_size  = st.number_input("Burst size", 1, 50, 5, step=1)
    burst_delay = st.number_input("Delay between requests (s)", 0.0, 2.0, 0.0, step=0.1)

    burst_btn  = st.button("⚡ Burst Requests", use_container_width=True,
                            disabled=st.session_state.burst_running)
    stop_btn   = st.button("⏹ Stop Burst", use_container_width=True,
                            disabled=not st.session_state.burst_running)

    if stop_btn:
        st.session_state.burst_running = False

    burst_progress = st.empty()
    burst_status   = st.empty()

    if burst_btn and not st.session_state.burst_running:
        st.session_state.burst_running = True
        st.session_state.burst_results = []
        ok_count = deny_count = 0

        for i in range(int(burst_size)):
            if not st.session_state.burst_running:
                break
            ok, data = api("POST", "/api/check", json={"client_id": client_id})
            if ok:
                st.session_state.last_result = data
                st.cache_data.clear()
                if data.get("allowed"):
                    ok_count += 1
                else:
                    deny_count += 1
                st.session_state.burst_results.append(data)
            burst_progress.progress((i + 1) / burst_size,
                                    text=f"Request {i+1}/{burst_size}")
            if burst_delay > 0 and i < burst_size - 1:
                time.sleep(burst_delay)

        st.session_state.burst_running = False
        burst_progress.empty()
        burst_status.markdown(
            f"<span class='banner-allowed'>✓ {ok_count} allowed</span> &nbsp;"
            f"<span class='banner-denied'>✗ {deny_count} denied</span>",
            unsafe_allow_html=True,
        )
        st.rerun()

    # Burst result mini-table
    if st.session_state.burst_results:
        st.markdown("**Burst summary**")
        rows = st.session_state.burst_results[-10:]
        table_md = "| # | Decision | Remaining |\n|---|---|---|\n"
        for idx, r in enumerate(rows, 1):
            dec = "✓ OK" if r.get("allowed") else "✗ DENY"
            table_md += f"| {idx} | {dec} | {r.get('remaining', 0):.2f} |\n"
        st.markdown(table_md)

st.divider()

# ---------------------------------------------------------------------------
# Analytics charts
# ---------------------------------------------------------------------------

st.markdown("### Analytics")

ac1, ac2 = st.columns(2)

# ── Token level over time ────────────────────────────────────────────────────
with ac1:
    st.markdown("**Token Level Over Time**")
    token_hist = fetch_tokens(client_id, minutes)
    if token_hist:
        ts     = [r["created_at"] for r in token_hist]
        after  = [r["tokens_after"] for r in token_hist]
        cap_v  = [capacity] * len(ts)  # configured capacity line

        # Use the snap capacity if available
        snap2 = fetch_status(client_id)
        if snap2:
            cap_v = [snap2["capacity"]] * len(ts)

        fig_tok = go.Figure()
        fig_tok.add_trace(go.Scatter(
            x=ts, y=after, mode="lines+markers", name="Tokens",
            line=dict(color="#3b82f6", width=2),
            marker=dict(size=4),
        ))
        fig_tok.add_trace(go.Scatter(
            x=ts, y=cap_v, mode="lines", name="Capacity",
            line=dict(color="#4b5563", width=1, dash="dash"),
        ))
        fig_tok.update_layout(
            paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
            font_color="#7b8099", height=260,
            margin=dict(t=10, b=40, l=40, r=10),
            legend=dict(font_color="#7b8099"),
            xaxis=dict(gridcolor="#1e2130"),
            yaxis=dict(gridcolor="#1e2130", title="Tokens"),
        )
        st.plotly_chart(fig_tok, use_container_width=True, key="tok_hist")
    else:
        st.caption("No token history yet for this client.")

# ── Request outcomes doughnut ────────────────────────────────────────────────
with ac2:
    st.markdown("**Request Outcomes**")
    out = fetch_summary(minutes)
    a_val = out.get("allowed", 0)
    d_val = out.get("denied", 0)
    if a_val + d_val > 0:
        fig_pie = go.Figure(go.Pie(
            labels=["Allowed", "Denied"],
            values=[a_val, d_val],
            marker_colors=["#22c55e", "#f59e0b"],
            hole=0.6,
            textinfo="label+percent",
            textfont_color="#e2e4ed",
        ))
        fig_pie.update_layout(
            paper_bgcolor="#0f1117",
            font_color="#7b8099",
            height=260,
            margin=dict(t=10, b=10, l=10, r=10),
            showlegend=False,
        )
        st.plotly_chart(fig_pie, use_container_width=True, key="pie")
    else:
        st.caption("No request data yet.")

ac3, ac4 = st.columns(2)

# ── Request activity over time ───────────────────────────────────────────────
with ac3:
    st.markdown("**Request Activity Over Time**")
    act = fetch_activity(minutes)
    if act:
        buckets   = [r["bucket"] for r in act]
        allowed_v = [r["allowed"] for r in act]
        denied_v  = [r["denied"]  for r in act]
        fig_act = go.Figure()
        fig_act.add_trace(go.Bar(x=buckets, y=allowed_v, name="Allowed",
                                  marker_color="#22c55e"))
        fig_act.add_trace(go.Bar(x=buckets, y=denied_v, name="Denied",
                                  marker_color="#f59e0b"))
        fig_act.update_layout(
            barmode="stack",
            paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
            font_color="#7b8099", height=260,
            margin=dict(t=10, b=40, l=40, r=10),
            legend=dict(font_color="#7b8099"),
            xaxis=dict(gridcolor="#1e2130"),
            yaxis=dict(gridcolor="#1e2130", title="Requests"),
        )
        st.plotly_chart(fig_act, use_container_width=True, key="activity")
    else:
        st.caption("No activity data yet.")

# ── Client activity bar chart ────────────────────────────────────────────────
with ac4:
    st.markdown("**Client Activity**")
    cli_data = fetch_clients(minutes)
    if cli_data:
        names  = [r["client_id"] for r in cli_data]
        totals = [r["total"] for r in cli_data]
        fig_cli = go.Figure(go.Bar(
            x=totals, y=names, orientation="h",
            marker_color="#3b82f6",
            text=totals, textposition="outside",
            textfont_color="#e2e4ed",
        ))
        fig_cli.update_layout(
            paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
            font_color="#7b8099", height=260,
            margin=dict(t=10, b=10, l=10, r=40),
            xaxis=dict(gridcolor="#1e2130", title="Requests"),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_cli, use_container_width=True, key="clients")
    else:
        st.caption("No client data yet.")

st.divider()

# ---------------------------------------------------------------------------
# Recent request history
# ---------------------------------------------------------------------------

st.markdown("### Recent Requests")

hist_col1, hist_col2, hist_col3 = st.columns([2, 2, 1])
with hist_col1:
    filter_client = st.text_input("Filter client", value="", placeholder="All clients",
                                   label_visibility="collapsed")
with hist_col2:
    filter_dec = st.selectbox("Filter decision", ["All", "Allowed", "Denied"],
                               label_visibility="collapsed")
with hist_col3:
    hist_limit = st.number_input("Rows", 10, 200, 50, step=10,
                                  label_visibility="collapsed")

dec_param = "" if filter_dec == "All" else filter_dec.lower()
rows = fetch_requests(
    client_id=filter_client.strip(),
    decision=dec_param,
    minutes=minutes,
    limit=int(hist_limit),
)

if rows:
    import pandas as pd

    df = pd.DataFrame(rows)
    df["Decision"] = df["allowed"].apply(lambda v: "✓ OK" if v else "✗ DENY")
    df["Retry (s)"] = df["retry_after"].apply(
        lambda v: f"{v:.2f}" if v is not None else "—"
    )
    df["RT (ms)"] = df["response_ms"].apply(
        lambda v: f"{v:.1f}" if v is not None else "—"
    )
    df["Time"] = df["created_at"].str[:19].str.replace("T", " ")

    display_cols = ["Time", "client_id", "Decision",
                    "tokens_before", "tokens_after", "RT (ms)", "Retry (s)"]
    rename_map = {
        "client_id": "Client",
        "tokens_before": "Before",
        "tokens_after": "After",
    }
    st.dataframe(
        df[display_cols].rename(columns=rename_map),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.caption("No requests in the selected time range.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.caption("API Shield v2.0 · FastAPI + SQLite + Streamlit · "
           f"Data window: {time_range} · Backend: {API_BASE}")
