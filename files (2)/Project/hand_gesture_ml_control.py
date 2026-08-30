"""
hand_gesture_ml_control.py
=============================
Implements the gesture table and background video downloads via threading.
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
import joblib
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

try:
    import serial
except ImportError:
    serial = None

VIDEO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "encoded_videos")
MANIFEST_PATH = os.path.join(VIDEO_DIR, "manifest.json")

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HAND_MODEL_PATH = os.path.join(SCRIPT_DIR, "hand_landmarker.task")
CLASSIFIER_PATH = os.path.join(SCRIPT_DIR, "gesture_model.pkl")


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


def build_packet(cmd_id: int, payload: int = 0) -> bytes:
    return bytes([START_BYTE, cmd_id, payload & 0xFF, END_BYTE])


def sync_video_manifest(link):
    if not link.enabled or not link.conn:
        return
    if not os.path.exists(MANIFEST_PATH):
        print(f"[Library] No manifest found at {MANIFEST_PATH} — skipping sync.")
        return
    with open(MANIFEST_PATH, 'r') as f:
        manifest = json.load(f)
    print(f"[Library] Syncing {len(manifest)} videos to ESP32...")
    for entry in manifest:
        link.conn.write(bytes([START_BYTE, 0x11, 0x00, END_BYTE]))
        link.conn.write(f"{entry['filename']}\n".encode())
        time.sleep(0.1)
    print("[Library] Sync complete.")


def serve_fetch_request_threaded(link, filename, state):
    """Runs in a background thread to prevent webcam freezing.
    state.is_downloading is set by the CALLER before this thread starts —
    do not set it here, that would leave a race window open."""
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

        while True:
            resp = conn.readline().decode(errors='ignore').strip()
            if not resp:
                continue
            if resp == "ACK":
                break
            if resp == "TIMEOUT_NO_DATA":
                conn.write(chunk)
            else:
                print(f"[ESP32] {resp}")

        state.download_progress = (sent / len(data)) * 100

    print(f"\n[SUCCESS] {filename} transfer complete.")
    state.is_downloading = False


def check_for_fetch_requests(link, state):
    """Non-blocking check. Spawns a thread if a file is requested."""
    if not link.enabled or not link.conn:
        return

    if state.is_downloading:
        return

    if link.conn.in_waiting:
        line = link.conn.readline().decode(errors='ignore').strip()
        if not line:
            return
        if line.startswith("FETCH:"):
            filename = line.split(":", 1)[1]
            # Set the flag HERE, synchronously in the main thread, before the
            # background thread even starts — closes the race window entirely.
            state.is_downloading = True
            threading.Thread(
                target=serve_fetch_request_threaded,
                args=(link, filename, state),
                daemon=True
            ).start()
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
        """Wait for the ESP32 to actually finish setup() (LittleFS mount/format
        included) instead of guessing a fixed delay — first-time LittleFS format
        can take longer than a couple seconds and swallow early sync packets."""
        start = time.time()
        while time.time() - start < timeout:
            line = self.conn.readline().decode(errors='ignore').strip()
            if line:
                print(f"[ESP32 boot] {line}")
            if line == "BOOT_READY":
                print("[Serial] ESP32 confirmed ready.")
                return
        print("[Serial] Warning: never saw BOOT_READY — proceeding anyway, sync may fail.")

    def send(self, cmd_bytes):
        if self.enabled and self.conn:
            self.conn.write(cmd_bytes)
        print(f"[Serial] Sent: {cmd_bytes}")

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
            pwm_val = int((state.fan_level / FAN_MAX_LEVEL) * 255)
            link.send(build_packet(CMD_FAN_SPEED, pwm_val))
            return f"FAN_UP (level {state.fan_level})"
        if shape == "THUMBS_DOWN":
            state.fan_level = max(state.fan_level - 1, 0)
            pwm_val = int((state.fan_level / FAN_MAX_LEVEL) * 255)
            link.send(build_packet(CMD_FAN_SPEED, pwm_val))
            return f"FAN_DOWN (level {state.fan_level})"
        if shape == "TWO":
            state.mode = "AUTO"
            state.bulb1 = False
            state.bulb2 = False
            state.fan_level = 0
            link.send(build_packet(CMD_AUTO_ON))
            return "AUTO_MODE_ENTER"
        if shape == "OK_SIGN":
            state.mode = "TV"
            link.send(build_packet(CMD_TV_ON))
            return "TV_MODE_ENTER"
        return None

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
        return None

    if mode == "AUTO":
        if shape == "TWO":
            state.mode = "NORMAL"
            link.send(build_packet(CMD_AUTO_OFF))
            return "AUTO_MODE_EXIT"
        return None

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=None, help="ESP32 serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--no-serial", action="store_true")
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()

    link = SerialLink(args.port, args.baud, enabled=not args.no_serial)
    sync_video_manifest(link)

    ensure_hand_model()

    try:
        saved = joblib.load(CLASSIFIER_PATH)
    except FileNotFoundError:
        print(f"Error: {CLASSIFIER_PATH} not found.")
        print("Run collect_gesture_data.py then train_gesture_model.py first.")
        return

    scaler = saved["scaler"]
    clf = saved["classifier"]
    classes = saved["classes"]

    options = build_hand_landmarker_options(num_hands=1)
    HandLandmarker = mp_vision.HandLandmarker

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print("Error: could not open webcam.")
        return

    shape_history = deque(maxlen=WINDOW_SIZE)
    state = AppState()

    last_fired_shape = None
    last_fire_time = 0.0
    last_stable_shape_seen = None

    start_time = time.time()

    with HandLandmarker.create_from_options(options) as landmarker:
        while True:
            check_for_fetch_requests(link, state)

            ok, frame = cap.read()
            if not ok:
                print("Error: failed to read frame from webcam.")
                break

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int((time.time() - start_time) * 1000)

            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            raw_shape = None
            display_text = "NO_HAND"

            if result.hand_landmarks:
                landmarks_raw = result.hand_landmarks[0]
                landmarks = [(lm.x, lm.y) for lm in landmarks_raw]
                features = normalize_landmarks(landmarks)

                features_scaled = scaler.transform([features])
                probs = clf.predict_proba(features_scaled)[0]
                best_idx = probs.argmax()
                confidence = probs[best_idx]

                if confidence >= MIN_CONFIDENCE:
                    raw_shape = classes[best_idx]
                    display_text = f"{raw_shape} ({confidence:.2f})"
                else:
                    display_text = f"UNSURE ({confidence:.2f})"

                h, w, _ = frame.shape
                for lm in landmarks_raw:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 4, (0, 255, 0), -1)

            shape_history.append(raw_shape)

            stable_shape = None
            if len(shape_history) == WINDOW_SIZE:
                counts = Counter(s for s in shape_history if s is not None)
                if counts:
                    top_shape, top_count = counts.most_common(1)[0]
                    if top_count >= MIN_VOTES:
                        stable_shape = top_shape

            if stable_shape != last_stable_shape_seen:
                last_fired_shape = None
                last_stable_shape_seen = stable_shape

            now = time.time()

            if (stable_shape and stable_shape != last_fired_shape
                    and (now - last_fire_time) > MIN_COOLDOWN_SEC):
                if not state.is_downloading:
                    result_label = handle_shape(stable_shape, state, link)
                    if result_label:
                        print(f"[{state.mode}] {result_label}")
                        last_fired_shape = stable_shape
                        last_fire_time = now

            cv2.putText(frame, f"Mode: {state.mode}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 200, 0), 2)
            if state.mode == "NORMAL":
                status = (f"Bulb1: {'ON' if state.bulb1 else 'OFF'}  "
                          f"Bulb2: {'ON' if state.bulb2 else 'OFF'}  "
                          f"Fan: {state.fan_level}/{FAN_MAX_LEVEL}")
                cv2.putText(frame, status, (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)
            cv2.putText(frame, f"Predicted: {display_text}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            if stable_shape:
                cv2.putText(frame, f"Stable: {stable_shape}", (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

            if state.is_downloading:
                cv2.putText(frame, f"DOWNLOADING TO TV: {state.download_progress:.1f}%", (10, 150),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow("Gesture Control", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()
    link.close()


if __name__ == "__main__":
    main()