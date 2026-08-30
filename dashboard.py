"""
Smart Home & Media Dashboard
=============================
Unified GUI for ML Gesture Control, Smart Home State, and Video Encoding.
"""

import argparse
import os
import time
import struct
import json
import threading
from collections import deque, Counter
import urllib.request

import cv2
import numpy as np
import joblib
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

import tkinter as tk
from tkinter import filedialog, ttk
from PIL import Image, ImageTk

try:
    import serial
except ImportError:
    serial = None

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(SCRIPT_DIR, "encoded_videos")
MANIFEST_PATH = os.path.join(VIDEO_DIR, "manifest.json")

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
HAND_MODEL_PATH = os.path.join(SCRIPT_DIR, "hand_landmarker.task")
CLASSIFIER_PATH = os.path.join(SCRIPT_DIR, "gesture_model.pkl")

MAX_FRAMES_ALLOWED = 500
PROCESS_MODE = 'dither'
WINDOW_SIZE = 10
MIN_VOTES = 8
MIN_COOLDOWN_SEC = 1.2
MIN_CONFIDENCE = 0.6
FAN_MAX_LEVEL = 3

START_BYTE = 0xAA
END_BYTE = 0xBB

CMD_BULB1_TOGGLE = 0x01
CMD_BULB2_TOGGLE = 0x02
CMD_AUTO_ON      = 0x03
CMD_AUTO_OFF     = 0x04
CMD_TV_ON        = 0x05
CMD_TV_OFF       = 0x06
CMD_TV_PLAY      = 0x07
CMD_TV_PAUSE     = 0x08
CMD_TV_NEXT      = 0x09
CMD_TV_PREV      = 0x0A
CMD_FAN_SPEED    = 0x0B

# --- UTILITY FUNCTIONS ---
def ensure_hand_model():
    if not os.path.exists(HAND_MODEL_PATH):
        print("Downloading hand landmark model (one-time, ~10MB)...")
        urllib.request.urlretrieve(MODEL_URL, HAND_MODEL_PATH)
        print("Model downloaded.")

def normalize_landmarks(landmarks_xy):
    wrist_x, wrist_y = landmarks_xy[0]
    relative = [(x - wrist_x, y - wrist_y) for (x, y) in landmarks_xy]
    flat = []
    for x, y in relative:
        flat.append(x)
        flat.append(y)
    max_val = max(abs(v) for v in flat) or 1.0
    return [v / max_val for v in flat]

def build_hand_landmarker_options(num_hands=1):
    return mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=HAND_MODEL_PATH),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=num_hands,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.5,
    )

def build_packet(cmd_id: int, payload: int = 0) -> bytes:
    return bytes([START_BYTE, cmd_id, payload & 0xFF, END_BYTE])

def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, 'r') as f:
            return json.load(f)
    return []

def save_manifest(manifest):
    os.makedirs(VIDEO_DIR, exist_ok=True)
    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, indent=2)

def next_output_filename(manifest):
    existing_numbers = []
    for entry in manifest:
        name = entry['filename']
        if name.startswith('video') and name.endswith('.bin'):
            try:
                existing_numbers.append(int(name[5:-4]))
            except ValueError:
                pass
    next_num = (max(existing_numbers) + 1) if existing_numbers else 1
    return f"video{next_num}.bin"

def sync_video_manifest(link):
    if not link.enabled or not link.conn:
        return
    if not os.path.exists(MANIFEST_PATH):
        return
    with open(MANIFEST_PATH, 'r') as f:
        manifest = json.load(f)
    print(f"[Library] Syncing {len(manifest)} videos to ESP32...")
    for entry in manifest:
        link.conn.write(bytes([START_BYTE, 0x11, 0x00, END_BYTE]))
        link.conn.write(f"{entry['filename']}\n".encode())
        time.sleep(0.1)
    print("[Library] Sync complete.")

# --- ENCODING LOGIC (Background Safe) ---
def encode_video_process(source_path, start_sec, display_name, progress_callback):
    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        return False, "Could not open video file."

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)

    manifest = load_manifest()
    output_filename = next_output_filename(manifest)
    output_path = os.path.join(VIDEO_DIR, output_filename)
    os.makedirs(VIDEO_DIR, exist_ok=True)

    frames_extracted = 0
    with open(output_path, 'wb') as f:
        while cap.isOpened() and frames_extracted < MAX_FRAMES_ALLOWED:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.resize(frame, (128, 64))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if PROCESS_MODE == 'edge':
                processed = cv2.Canny(gray, 50, 150)
            elif PROCESS_MODE == 'dither':
                pil_img = Image.fromarray(gray)
                processed = np.array(pil_img.convert('1'), dtype=np.uint8) * 255
            else:
                _, processed = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

            byte_array = bytearray()
            for row in range(64):
                for col_byte in range(16):
                    byte = 0
                    for bit in range(8):
                        if processed[row, col_byte * 8 + bit] > 0:
                            byte |= (1 << bit)
                    byte_array.append(byte)

            f.write(byte_array)
            frames_extracted += 1
            if frames_extracted % 10 == 0:
                progress_callback(frames_extracted, MAX_FRAMES_ALLOWED)

    cap.release()
    if frames_extracted == 0:
        if os.path.exists(output_path): os.remove(output_path)
        return False, "No frames extracted."

    manifest.append({
        "name": display_name,
        "filename": output_filename,
        "frame_count": frames_extracted,
        "fps_source": round(fps, 2)
    })
    save_manifest(manifest)
    return True, f"Encoded {frames_extracted} frames."


def serve_fetch_request_threaded(link, filename, state):
    state.download_progress = 0.0
    filepath = os.path.join(VIDEO_DIR, filename)
    print(f"\n[REQUEST] ESP32 wants: {filename}")

    if not os.path.exists(filepath):
        print(f"[ERROR] {filepath} not found locally.")
        state.is_downloading = False
        return

    conn = link.conn
    conn.write(bytes([START_BYTE, 0x10, 0x00, END_BYTE]))
    conn.write(f"{filename}\n".encode())
    time.sleep(0.05)

    file_size = os.path.getsize(filepath)
    conn.write(struct.pack('<I', file_size))

    with open(filepath, 'rb') as f:
        data = f.read()

    CHUNK_SIZE = 128
    sent = 0
    
    while sent < len(data):
        chunk = data[sent:sent + CHUNK_SIZE]
        conn.write(chunk)
        sent += len(chunk)

        timeout_fails = 0
        while True:
            resp = conn.readline().decode(errors='ignore').strip()
            
            if not resp:
                timeout_fails += 1
                if timeout_fails > 5:  # 5 seconds of total silence
                    print(f"\n[ERROR] ESP32 stopped responding. Aborting.")
                    state.is_downloading = False
                    return
                continue
            
            if resp == "ACK":
                break
                
            if resp in ["TIMEOUT_NO_DATA", "OPEN_WRITE_FAIL"]:
                print(f"\n[ERROR] ESP32 aborted transfer: {resp}")
                state.is_downloading = False
                return
                
            # If the ESP32 sends a normal serial print, log it but keep waiting for ACK
            print(f"[ESP32] {resp}")

        state.download_progress = (sent / len(data)) * 100

    print(f"\n[SUCCESS] {filename} transfer complete.")
    state.is_downloading = False

def check_for_fetch_requests(link, state):
    if not link.enabled or not link.conn or state.is_downloading:
        return
    if link.conn.in_waiting:
        line = link.conn.readline().decode(errors='ignore').strip()
        if not line:
            return
        if line.startswith("FETCH:"):
            filename = line.split(":", 1)[1]
            state.is_downloading = True
            threading.Thread(target=serve_fetch_request_threaded, args=(link, filename, state), daemon=True).start()
        elif line:
            print(f"[ESP32] {line}")

class SerialLink:
    def __init__(self, port, baud=115200, enabled=True):
        self.enabled = enabled and serial is not None and port is not None
        self.conn = None
        if self.enabled:
            try:
                self.conn = serial.Serial(port, baud, timeout=1)
                print(f"[Serial] Connected to {port} @ {baud} baud, waiting for ESP32 boot...")
                self._wait_for_boot_ready()
            except Exception as e:
                print(f"[Serial] Could not open {port}: {e}")
                self.enabled = False

    def _wait_for_boot_ready(self, timeout=15):
        start = time.time()
        while time.time() - start < timeout:
            line = self.conn.readline().decode(errors='ignore').strip()
            if line == "BOOT_READY":
                print("[Serial] ESP32 confirmed ready.")
                return
        print("[Serial] Warning: never saw BOOT_READY — proceeding anyway.")

    def send(self, cmd_bytes):
        if self.enabled and self.conn:
            self.conn.write(cmd_bytes)

    def close(self):
        if self.conn:
            self.conn.close()

class AppState:
    def __init__(self):
        self.mode = "NORMAL"
        self.bulb1 = False
        self.bulb2 = False
        self.fan_level = 0
        self.is_downloading = False
        self.download_progress = 0.0

def handle_shape(shape, state: AppState, link: SerialLink):
    mode = state.mode
    if mode == "NORMAL":
        if shape == "OPEN_PALM":
            state.bulb1 = not state.bulb1
            link.send(build_packet(CMD_BULB1_TOGGLE))
            return "BULB1_TOGGLE"
        if shape == "FIST":
            state.bulb2 = not state.bulb2
            link.send(build_packet(CMD_BULB2_TOGGLE))
            return "BULB2_TOGGLE"
        if shape == "THUMBS_UP":
            state.fan_level = min(state.fan_level + 1, FAN_MAX_LEVEL)
            link.send(build_packet(CMD_FAN_SPEED, int((state.fan_level / FAN_MAX_LEVEL) * 255)))
            return f"FAN_UP"
        if shape == "THUMBS_DOWN":
            state.fan_level = max(state.fan_level - 1, 0)
            link.send(build_packet(CMD_FAN_SPEED, int((state.fan_level / FAN_MAX_LEVEL) * 255)))
            return f"FAN_DOWN"
        if shape == "TWO":
            state.mode = "AUTO"
            state.bulb1 = False; state.bulb2 = False; state.fan_level = 0
            link.send(build_packet(CMD_AUTO_ON))
            return "AUTO_MODE_ENTER"
        if shape == "OK_SIGN":
            state.mode = "TV"
            link.send(build_packet(CMD_TV_ON))
            return "TV_MODE_ENTER"
    if mode == "TV":
        if shape == "OPEN_PALM":
            link.send(build_packet(CMD_TV_PLAY))
            return "TV_PLAY"
        if shape == "FIST":
            link.send(build_packet(CMD_TV_PAUSE))
            return "TV_PAUSE"
        if shape == "THUMBS_UP":
            link.send(build_packet(CMD_TV_NEXT))
            return "TV_SKIP_FWD"
        if shape == "THUMBS_DOWN":
            link.send(build_packet(CMD_TV_PREV))
            return "TV_SKIP_BACK"
        if shape == "OK_SIGN":
            state.mode = "NORMAL"
            link.send(build_packet(CMD_TV_OFF))
            return "TV_MODE_EXIT"
    if mode == "AUTO":
        if shape == "TWO":
            state.mode = "NORMAL"
            link.send(build_packet(CMD_AUTO_OFF))
            return "AUTO_MODE_EXIT"
    return None

# --- TKINTER GUI APP ---
class DashboardApp:
    def __init__(self, root, args):
        self.root = root
        self.root.title("Smart Home & Media Dashboard")
        self.root.geometry("1000x550")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.link = SerialLink(args.port, args.baud, enabled=not args.no_serial)
        sync_video_manifest(self.link)
        
        ensure_hand_model()
        saved = joblib.load(CLASSIFIER_PATH)
        self.scaler, self.clf, self.classes = saved["scaler"], saved["classifier"], saved["classes"]
        
        self.cap = cv2.VideoCapture(args.camera)
        self.landmarker = mp_vision.HandLandmarker.create_from_options(build_hand_landmarker_options())
        
        self.state = AppState()
        self.shape_history = deque(maxlen=WINDOW_SIZE)
        self.last_fired_shape = None
        self.last_fire_time = 0.0
        self.last_stable_shape_seen = None
        self.start_time = time.time()
        
        self.build_ui()
        self.refresh_listbox()
        self.update_webcam_loop()

    def build_ui(self):
        # Layout Grids
        left_frame = tk.Frame(self.root, width=640, height=480)
        left_frame.grid(row=0, column=0, rowspan=2, padx=10, pady=10)
        
        right_top = tk.LabelFrame(self.root, text="Smart Home Status", font=('Helvetica', 12, 'bold'))
        right_top.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        right_bot = tk.LabelFrame(self.root, text="Video Encoding Studio", font=('Helvetica', 12, 'bold'))
        right_bot.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)

        # Left: Webcam
        self.video_label = tk.Label(left_frame)
        self.video_label.pack()

        # Right-Top: Status
        self.lbl_mode = tk.Label(right_top, text="Mode: NORMAL", font=('Helvetica', 14))
        self.lbl_mode.pack(pady=5)
        self.lbl_b1 = tk.Label(right_top, text="Bulb 1: OFF", font=('Helvetica', 12))
        self.lbl_b1.pack()
        self.lbl_b2 = tk.Label(right_top, text="Bulb 2: OFF", font=('Helvetica', 12))
        self.lbl_b2.pack()
        self.lbl_fan = tk.Label(right_top, text="Fan: 0/3", font=('Helvetica', 12))
        self.lbl_fan.pack()

        # Right-Bottom: Encoder
        tk.Label(right_bot, text="Manifest Files:").grid(row=0, column=0, columnspan=2, sticky="w")
        self.listbox = tk.Listbox(right_bot, height=5)
        self.listbox.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        
        tk.Label(right_bot, text="File:").grid(row=2, column=0, sticky="e")
        self.path_var = tk.StringVar()
        tk.Entry(right_bot, textvariable=self.path_var, width=20).grid(row=2, column=1, padx=5, pady=2)
        tk.Button(right_bot, text="Browse", command=self.browse_file).grid(row=2, column=2, padx=5)

        tk.Label(right_bot, text="Display Name:").grid(row=3, column=0, sticky="e")
        self.name_var = tk.StringVar()
        tk.Entry(right_bot, textvariable=self.name_var, width=20).grid(row=3, column=1, padx=5, pady=2)

        tk.Label(right_bot, text="Start Sec:").grid(row=4, column=0, sticky="e")
        self.time_var = tk.StringVar(value="0")
        tk.Entry(right_bot, textvariable=self.time_var, width=5).grid(row=4, column=1, sticky="w", padx=5, pady=2)

        self.btn_encode = tk.Button(right_bot, text="Encode & Auto-Sync", command=self.start_encode_thread, bg="lightblue")
        self.btn_encode.grid(row=5, column=0, columnspan=3, pady=10, sticky="ew")

        self.lbl_enc_status = tk.Label(right_bot, text="Ready", fg="gray")
        self.lbl_enc_status.grid(row=6, column=0, columnspan=3)

    def browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.gif *.avi")])
        if path:
            self.path_var.set(path)
            if not self.name_var.get():
                self.name_var.set(os.path.splitext(os.path.basename(path))[0])

    def refresh_listbox(self):
        self.listbox.delete(0, tk.END)
        for item in load_manifest():
            self.listbox.insert(tk.END, f"{item['name']} ({item['filename']})")

    def start_encode_thread(self):
        source = self.path_var.get()
        name = self.name_var.get()
        try:
            start_sec = float(self.time_var.get())
        except ValueError:
            start_sec = 0.0

        if not os.path.exists(source):
            self.lbl_enc_status.config(text="Error: File not found", fg="red")
            return

        self.btn_encode.config(state="disabled")
        self.lbl_enc_status.config(text="Extracting & Encoding...", fg="blue")
        threading.Thread(target=self._encode_worker, args=(source, start_sec, name), daemon=True).start()

    def _encode_worker(self, source, start_sec, name):
        def update_progress(current, total):
            self.root.after(0, lambda: self.lbl_enc_status.config(text=f"Processing {current}/{total} frames..."))
            
        success, msg = encode_video_process(source, start_sec, name, update_progress)
        
        # We removed the full sync_video_manifest() call from here
        # so it doesn't duplicate the ESP32's list.
        
        self.root.after(0, self._encode_finished, success, msg)

    def _encode_finished(self, success, msg):
        self.btn_encode.config(state="normal")
        self.lbl_enc_status.config(text=msg, fg="green" if success else "red")
        self.refresh_listbox()
        
        # Send ONLY the newly encoded video to the ESP32 menu
        if success and self.link.enabled and self.link.conn:
            manifest = load_manifest()
            if manifest:
                new_video = manifest[-1]['filename']
                self.link.conn.write(bytes([START_BYTE, 0x11, 0x00, END_BYTE]))
                self.link.conn.write(f"{new_video}\n".encode())
                print(f"[Library] Appended new video to ESP32 menu: {new_video}")   

    def update_webcam_loop(self):
        check_for_fetch_requests(self.link, self.state)

        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts = int((time.time() - self.start_time) * 1000)

            result = self.landmarker.detect_for_video(mp_image, ts)
            
            raw_shape = None
            display_text = "NO_HAND"

            if result.hand_landmarks:
                landmarks_raw = result.hand_landmarks[0]
                landmarks = [(lm.x, lm.y) for lm in landmarks_raw]
                features = normalize_landmarks(landmarks)
                
                features_scaled = self.scaler.transform([features])
                probs = self.clf.predict_proba(features_scaled)[0]
                best_idx = probs.argmax()
                confidence = probs[best_idx]

                if confidence >= MIN_CONFIDENCE:
                    raw_shape = self.classes[best_idx]
                    display_text = f"{raw_shape} ({confidence:.2f})"

                h, w, _ = frame.shape
                for lm in landmarks_raw:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 4, (0, 255, 0), -1)

            self.shape_history.append(raw_shape)

            stable_shape = None
            if len(self.shape_history) == WINDOW_SIZE:
                counts = Counter(s for s in self.shape_history if s is not None)
                if counts:
                    top_shape, top_count = counts.most_common(1)[0]
                    if top_count >= MIN_VOTES:
                        stable_shape = top_shape

            if stable_shape != self.last_stable_shape_seen:
                self.last_fired_shape = None
                self.last_stable_shape_seen = stable_shape

            now = time.time()
            if (stable_shape and stable_shape != self.last_fired_shape 
                and (now - self.last_fire_time) > MIN_COOLDOWN_SEC):
                if not self.state.is_downloading:
                    action = handle_shape(stable_shape, self.state, self.link)
                    if action:
                        self.last_fired_shape = stable_shape
                        self.last_fire_time = now

            # OpenCV Overlays
            cv2.putText(frame, f"Predicted: {display_text}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            if self.state.is_downloading:
                cv2.putText(frame, f"DOWNLOADING TO TV: {self.state.download_progress:.1f}%", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # Update Tkinter Labels
            self.lbl_mode.config(text=f"Mode: {self.state.mode}")
            self.lbl_b1.config(text=f"Bulb 1: {'ON' if self.state.bulb1 else 'OFF'}")
            self.lbl_b2.config(text=f"Bulb 2: {'ON' if self.state.bulb2 else 'OFF'}")
            self.lbl_fan.config(text=f"Fan: {self.state.fan_level}/{FAN_MAX_LEVEL}")

            # Push image to UI
            pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            imgtk = ImageTk.PhotoImage(image=pil_img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)

        self.root.after(15, self.update_webcam_loop)

    def on_close(self):
        self.cap.release()
        self.link.close()
        self.root.destroy()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=None)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--no-serial", action="store_true")
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()

    root = tk.Tk()
    app = DashboardApp(root, args)
    root.mainloop()