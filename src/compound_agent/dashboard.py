"""Minimal web dashboard for Compound Agent monitoring."""
import hmac
import logging
import os
import threading
from datetime import datetime, timezone, timedelta

from flask import Flask, jsonify, render_template_string, request, abort

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def create_app(config=None, memory=None, event_log=None, agent_state=None):
    """Create Flask app with injected dependencies."""
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    def check_auth():
        """Check basic auth if password is set."""
        pw = os.environ.get("DASHBOARD_PASSWORD", "")
        if not pw:
            return  # No auth required
        auth = request.authorization
        if not auth or not hmac.compare_digest(auth.password, pw):
            abort(401)

    @app.before_request
    def require_auth():
        if request.path == "/health":
            return
        check_auth()

    @app.route("/")
    def index():
        return render_template_string(DASHBOARD_HTML)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "timestamp": datetime.now(KST).isoformat()})

    @app.route("/api/status")
    def api_status():
        status = {
            "agent_mode": config.agent_mode if config else "unknown",
            "state": (
                agent_state.current_state
                if agent_state and hasattr(agent_state, "current_state")
                else "unknown"
            ),
            "timestamp": datetime.now(KST).isoformat(),
        }
        return jsonify(status)

    @app.route("/api/events")
    def api_events():
        if not event_log:
            return jsonify({"events": []})
        limit = min(request.args.get("limit", 50, type=int), 500)
        try:
            events = event_log.get_events(limit=limit)
        except Exception:
            events = []
        # Reverse so most recent is first
        events = list(reversed(events))
        return jsonify({"events": events, "count": len(events)})

    @app.route("/api/memory")
    def api_memory():
        if not memory:
            return jsonify({})
        try:
            engagement = memory.get_engagement_stats(days=7)
            categories = memory.get_preferred_categories(top_n=10)
            sources = memory.get_source_rankings(min_shown=1)
            return jsonify({
                "engagement_7d": engagement,
                "preferred_categories": [
                    {"category": c, "score": round(s, 2)} for c, s in categories
                ],
                "source_rankings": [
                    {"source": s, "quality": round(q, 2)} for s, q in sources
                ],
            })
        except Exception as e:
            return jsonify({"error": str(e)})

    return app


def run_dashboard(app, port=8080):
    """Run dashboard in a daemon thread."""
    thread = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0", port=port, debug=False, use_reloader=False
        ),
        daemon=True,
    )
    thread.start()
    logger.info("Dashboard running on port %d", port)
    return thread


# ---------------------------------------------------------------------------
# Dashboard HTML (single-page, dark theme, no external deps)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Compound Agent Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --muted: #8b949e;
    --green: #3fb950;
    --red: #f85149;
    --blue: #58a6ff;
    --yellow: #d29922;
  }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 13px;
    padding: 16px;
    min-height: 100vh;
  }
  h1 { font-size: 18px; color: var(--blue); margin-bottom: 4px; }
  .subtitle { color: var(--muted); font-size: 11px; margin-bottom: 20px; }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 14px;
  }
  .card-title {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-bottom: 10px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 6px;
  }
  .status-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  .dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  }
  .dot-green { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .dot-red   { background: var(--red);   box-shadow: 0 0 6px var(--red); }
  .dot-yellow{ background: var(--yellow);}
  .label { color: var(--muted); width: 90px; flex-shrink: 0; }
  .value { color: var(--text); }
  .stat-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 3px 0;
    border-bottom: 1px solid var(--border);
  }
  .stat-row:last-child { border-bottom: none; }
  .stat-num { color: var(--blue); font-weight: bold; }
  /* Bar chart */
  .bar-item { margin-bottom: 8px; }
  .bar-label {
    display: flex; justify-content: space-between;
    color: var(--muted); font-size: 11px; margin-bottom: 3px;
  }
  .bar-track {
    background: var(--border); border-radius: 2px; height: 6px; overflow: hidden;
  }
  .bar-fill {
    height: 100%; background: var(--blue); border-radius: 2px;
    transition: width 0.4s ease;
  }
  /* Event log */
  .event-table-wrap {
    overflow-x: auto; overflow-y: auto; max-height: 420px;
  }
  table {
    width: 100%; border-collapse: collapse; font-size: 11px;
  }
  thead th {
    background: var(--bg);
    color: var(--muted);
    text-align: left;
    padding: 5px 8px;
    position: sticky; top: 0;
    border-bottom: 1px solid var(--border);
    font-weight: normal;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  tbody tr:hover { background: #1c2128; }
  td {
    padding: 4px 8px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
    max-width: 280px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text);
  }
  td.ts { color: var(--muted); white-space: nowrap; width: 155px; }
  td.agent { color: var(--yellow); width: 80px; }
  td.etype { color: var(--green); width: 120px; }
  .footer {
    margin-top: 16px; color: var(--muted); font-size: 10px;
    display: flex; justify-content: space-between;
  }
  @media (max-width: 600px) {
    .grid { grid-template-columns: 1fr; }
    td.ts { width: auto; }
  }
</style>
</head>
<body>
<h1>Compound Agent</h1>
<p class="subtitle" id="last-refresh">Loading...</p>

<div class="grid">
  <div class="card" id="card-status">
    <div class="card-title">Agent Status</div>
    <div class="status-row">
      <div class="dot dot-yellow" id="status-dot"></div>
      <span class="label">Mode</span>
      <span class="value" id="status-mode">—</span>
    </div>
    <div class="status-row">
      <div style="width:8px;flex-shrink:0;"></div>
      <span class="label">State</span>
      <span class="value" id="status-state">—</span>
    </div>
    <div class="status-row">
      <div style="width:8px;flex-shrink:0;"></div>
      <span class="label">Updated</span>
      <span class="value" id="status-ts">—</span>
    </div>
  </div>

  <div class="card" id="card-engagement">
    <div class="card-title">Engagement (7d)</div>
    <div class="stat-row"><span>Total</span><span class="stat-num" id="eng-total">—</span></div>
    <div class="stat-row"><span>Positive</span><span class="stat-num" id="eng-pos">—</span></div>
    <div class="stat-row"><span>Negative</span><span class="stat-num" id="eng-neg">—</span></div>
    <div class="stat-row"><span>Bookmark</span><span class="stat-num" id="eng-bkm">—</span></div>
    <div class="stat-row"><span>Rate</span><span class="stat-num" id="eng-rate">—</span></div>
  </div>

  <div class="card">
    <div class="card-title">Top Categories</div>
    <div id="cat-bars">
      <span style="color:var(--muted);font-size:11px;">No data</span>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Source Rankings</div>
    <div id="src-bars">
      <span style="color:var(--muted);font-size:11px;">No data</span>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-title">Event Log (last 50)</div>
  <div class="event-table-wrap">
    <table>
      <thead>
        <tr>
          <th>Timestamp</th>
          <th>Type</th>
          <th>Agent</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody id="event-tbody">
        <tr><td colspan="4" style="color:var(--muted);text-align:center;padding:16px;">Loading...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="footer">
  <span>Auto-refresh every 30s</span>
  <span id="footer-time"></span>
</div>

<script>
function fmt(ts) {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    return d.toLocaleString('ko-KR', {timeZone: 'Asia/Seoul', hour12: false});
  } catch { return ts; }
}

function pct(n) { return (n * 100).toFixed(1) + '%'; }

function esc(s) { const d=document.createElement('div'); d.textContent=String(s); return d.innerHTML; }

function barHtml(items, labelKey, valKey) {
  if (!items || items.length === 0) return '<span style="color:var(--muted);font-size:11px;">No data</span>';
  const max = Math.max(...items.map(x => x[valKey]));
  return items.map(x => {
    const w = max > 0 ? (x[valKey] / max * 100).toFixed(1) : 0;
    return `<div class="bar-item">
      <div class="bar-label"><span>${esc(x[labelKey])}</span><span>${esc(x[valKey])}</span></div>
      <div class="bar-track"><div class="bar-fill" style="width:${w}%"></div></div>
    </div>`;
  }).join('');
}

async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    document.getElementById('status-mode').textContent = d.agent_mode || '—';
    document.getElementById('status-state').textContent = d.state || '—';
    document.getElementById('status-ts').textContent = fmt(d.timestamp);
    const dot = document.getElementById('status-dot');
    dot.className = 'dot ' + (d.agent_mode && d.agent_mode !== 'unknown' ? 'dot-green' : 'dot-red');
  } catch (e) {
    document.getElementById('status-mode').textContent = 'error';
    document.getElementById('status-dot').className = 'dot dot-red';
  }
}

async function loadMemory() {
  try {
    const r = await fetch('/api/memory');
    const d = await r.json();
    if (d.error) return;

    const e = d.engagement_7d || {};
    document.getElementById('eng-total').textContent = e.total ?? '—';
    document.getElementById('eng-pos').textContent = e.positive ?? '—';
    document.getElementById('eng-neg').textContent = e.negative ?? '—';
    document.getElementById('eng-bkm').textContent = e.bookmark ?? '—';
    document.getElementById('eng-rate').textContent =
      e.engagement_rate != null ? pct(e.engagement_rate) : '—';

    document.getElementById('cat-bars').innerHTML =
      barHtml(d.preferred_categories || [], 'category', 'score');
    document.getElementById('src-bars').innerHTML =
      barHtml(d.source_rankings || [], 'source', 'quality');
  } catch {}
}

async function loadEvents() {
  try {
    const r = await fetch('/api/events?limit=50');
    const d = await r.json();
    const events = d.events || [];
    const tbody = document.getElementById('event-tbody');
    if (events.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:16px;">No events</td></tr>';
      return;
    }
    tbody.innerHTML = events.map(ev => {
      const details = JSON.stringify(ev.result || {});
      return `<tr>
        <td class="ts">${fmt(ev.timestamp)}</td>
        <td class="etype">${esc(ev.event_type || '—')}</td>
        <td class="agent">${esc(ev.agent || '—')}</td>
        <td title="${esc(details)}">${esc(details.slice(0, 120))}${details.length > 120 ? '…' : ''}</td>
      </tr>`;
    }).join('');
  } catch {}
}

function refresh() {
  const now = new Date().toLocaleString('ko-KR', {timeZone: 'Asia/Seoul', hour12: false});
  document.getElementById('last-refresh').textContent = 'Last refresh: ' + now;
  document.getElementById('footer-time').textContent = now;
  loadStatus();
  loadMemory();
  loadEvents();
}

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>"""
