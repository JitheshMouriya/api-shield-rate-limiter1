/**
 * API Shield — app.js
 * Calls the real FastAPI endpoints; no simulated results.
 */

const API = {
  health:    () => fetch('/api/health').then(r => r.json()),
  configure: (body) => fetch('/api/configure', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) }).then(r => r.json().then(d => ({ok: r.ok, data: d}))),
  check:     (client_id) => fetch('/api/check', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({client_id}) }).then(r => r.json().then(d => ({ok: r.ok, data: d}))),
  status:    (client_id) => fetch(`/api/status/${encodeURIComponent(client_id)}`).then(r => r.json().then(d => ({ok: r.ok, data: d}))),
};

// ---- DOM refs ----
const elStatusDot    = document.getElementById('status-dot');
const elStatusText   = document.getElementById('status-text');
const elCapacity     = document.getElementById('capacity');
const elRefillRate   = document.getElementById('refill-rate');
const elCapacityErr  = document.getElementById('capacity-err');
const elRateErr      = document.getElementById('rate-err');
const elBtnConfigure = document.getElementById('btn-configure');
const elClientId     = document.getElementById('client-id');
const elClientErr    = document.getElementById('client-err');
const elBtnSend      = document.getElementById('btn-send');
const elResultBanner = document.getElementById('result-banner');
const elResultIcon   = document.getElementById('result-icon');
const elResultTitle  = document.getElementById('result-title');
const elResultMeta   = document.getElementById('result-meta');
const elBarFill      = document.getElementById('token-bar-fill');
const elTokenLabel   = document.getElementById('token-label');
const elHistoryBody  = document.getElementById('history-body');
const elToast        = document.getElementById('toast');

const MAX_HISTORY = 10;
let history = [];

// ---- Health poll ----
async function checkHealth() {
  try {
    const data = await API.health();
    if (data.status === 'ok') {
      elStatusDot.className  = 'status-dot ok';
      elStatusText.textContent = 'Service online';
    } else { throw new Error(); }
  } catch {
    elStatusDot.className  = 'status-dot err';
    elStatusText.textContent = 'Service unreachable';
  }
}

// ---- Toast ----
let toastTimer;
function showToast(msg) {
  elToast.textContent = msg;
  elToast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => elToast.classList.remove('show'), 3000);
}

// ---- Configure ----
elBtnConfigure.addEventListener('click', async () => {
  let valid = true;

  const cap = parseFloat(elCapacity.value);
  const rate = parseFloat(elRefillRate.value);

  elCapacityErr.textContent = '';
  elRateErr.textContent = '';
  elCapacity.classList.remove('error');
  elRefillRate.classList.remove('error');

  if (!elCapacity.value || isNaN(cap) || cap <= 0) {
    elCapacityErr.textContent = 'Enter a positive number.';
    elCapacity.classList.add('error');
    valid = false;
  }
  if (!elRefillRate.value || isNaN(rate) || rate <= 0) {
    elRateErr.textContent = 'Enter a positive number.';
    elRefillRate.classList.add('error');
    valid = false;
  }
  if (!valid) return;

  elBtnConfigure.disabled = true;
  elBtnConfigure.textContent = 'Saving…';

  const { ok, data } = await API.configure({ capacity: cap, refill_rate: rate });
  elBtnConfigure.disabled = false;
  elBtnConfigure.textContent = 'Apply';

  if (ok) {
    showToast(`Config saved — capacity ${cap}, rate ${rate}/s`);
  } else {
    showToast(`Error: ${data.detail || 'Unknown error'}`);
  }
});

// ---- Send request ----
elBtnSend.addEventListener('click', sendRequest);
elClientId.addEventListener('keydown', e => { if (e.key === 'Enter') sendRequest(); });

async function sendRequest() {
  elClientErr.textContent = '';
  elClientId.classList.remove('error');

  const cid = elClientId.value.trim();
  if (!cid) {
    elClientErr.textContent = 'Client ID is required.';
    elClientId.classList.add('error');
    return;
  }

  elBtnSend.disabled = true;
  elBtnSend.innerHTML = '<span class="spinner"></span> Sending…';

  const { ok, data } = await API.check(cid);
  elBtnSend.disabled = false;
  elBtnSend.textContent = 'Send Request';

  if (!ok) {
    showToast(`Error: ${data.detail || 'Request failed'}`);
    return;
  }

  renderResult(data);
  updateTokenDisplay(data.remaining, data.remaining); // will be refined by status call
  addHistory(data);

  // Fetch accurate bucket status for the token bar capacity
  const st = await API.status(cid);
  if (st.ok) {
    updateTokenDisplay(st.data.tokens, st.data.capacity);
  }
}

function renderResult(data) {
  elResultBanner.className = 'card ' + (data.allowed ? 'allowed' : 'denied');
  elResultIcon.textContent  = data.allowed ? '✓' : '✗';
  elResultTitle.textContent = data.allowed ? 'Allowed' : 'Rate Limited';

  if (data.allowed) {
    elResultMeta.textContent = `${data.remaining.toFixed(2)} token(s) remaining`;
  } else {
    const ra = data.retry_after !== null ? `Retry after ${data.retry_after}s` : '';
    elResultMeta.textContent = `Bucket empty. ${ra}`;
  }
}

function updateTokenDisplay(tokens, capacity) {
  const pct = capacity > 0 ? Math.min(100, (tokens / capacity) * 100) : 0;
  elBarFill.style.width = pct.toFixed(1) + '%';
  elTokenLabel.textContent = `${tokens.toFixed(2)} / ${capacity}`;
}

function addHistory(data) {
  history.unshift(data);
  if (history.length > MAX_HISTORY) history.pop();
  renderHistory();
}

function renderHistory() {
  if (history.length === 0) {
    elHistoryBody.innerHTML = '<div class="empty-msg">No requests yet.</div>';
    return;
  }
  elHistoryBody.innerHTML = history.map(d => `
    <div class="history-row">
      <span class="history-client" title="${escHtml(d.client_id)}">${escHtml(d.client_id)}</span>
      <span><span class="badge ${d.allowed ? 'allowed' : 'denied'}">${d.allowed ? 'OK' : 'DENY'}</span></span>
      <span class="history-tokens">${d.remaining.toFixed(2)}</span>
    </div>
  `).join('');
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ---- Init ----
checkHealth();
renderHistory();
