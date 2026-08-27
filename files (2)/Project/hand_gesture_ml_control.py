"""
hand_gesture_ml_control.py
=============================
Implements the gesture table:

    Gesture     | Normal Mode                    | TV Mode
    ------------|---------------------------------|------------------
    Open palm   | Bulb 1 toggle                  | Play
    Fist        | Bulb 2 toggle                  | Pause
    Thumbs up   | Fan ON / speed up              | Skip forward (next channel)
    Thumbs down | Fan OFF / speed down           | Skip back (prev channel)
    Peace (TWO) | Auto/occupancy mode toggle      | -- (inactive)
    OK sign     | Toggle TV Mode (enter)          | Toggle TV Mode (exit)

THREE MODES:
    NORMAL - manual bulb/fan control (default)
    TV     - Open palm/Fist/Thumbs up/down control a small animation
             "playing" on an OLED screen wired to the ESP32 (looks like
             a mini TV). Enter/exit via OK sign.
    AUTO   - entered via Peace sign from NORMAL. Forces Bulb1, Bulb2, and
             Fan OFF immediately and LOCKS manual gesture control (no PIR
             sensor - this is a pure "everything off" lockout mode).
             Exit back to NORMAL via Peace sign again.

SERIAL PROTOCOL (single byte, sent to ESP32):
    'A' -> Bulb 1 toggle
    'B' -> Bulb 2 toggle
    'C' -> Fan speed up (turns on / increases one step, caps at max)
    'D' -> Fan speed down (decreases one step / turns off at zero)
    'H' -> Auto mode ENTER  (ESP32 forces bulb1/bulb2/fan off, lights
                              its onboard "Auto" indicator LED)
    'I' -> Auto mode EXIT   (turns the indicator LED back off)
    'J' -> TV mode ENTER (turns OLED on, starts Channel 1 playing)
    'K' -> TV mode EXIT  (turns OLED off / blank screen)
    'P' -> TV Play  (resume animation)
    'Q' -> TV Pause (freeze current frame)
    'N' -> TV Skip forward (next channel)
    'M' -> TV Skip back (previous channel)

Requirements:
    pip install opencv-python mediapipe scikit-learn joblib pyserial

Run collect_gesture_data.py and train_gesture_model.py first (with the
NEW 6-class scheme) so that gesture_model.pkl exists.

Usage:
    python hand_gesture_ml_control.py --port COM5
    python hand_gesture_ml_control.py --no-serial   (test without ESP32)
"""

import argparse
import os
import time
import urllib.request
from collections import deque, Counter

import cv2
import joblib
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

try:
    import serial
except ImportError:
    serial = None

# ----------------------------------------------------------------------
# Shared config (previously in gesture_utils.py, now inlined here)
# ----------------------------------------------------------------------
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
    """
    landmarks_xy: list of 21 (x, y) tuples (normalized image coords, 0-1).
    Returns a flat list of 42 floats, relative to the wrist and scaled
    by the largest coordinate (distance/position invariant).
    """
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


class SerialLink:
    def __init__(self, port, baud=115200, enabled=True):
        self.enabled = enabled and serial is not None and port is not None
        self.conn = None
        if self.enabled:
            try:
                self.conn = serial.Serial(port, baud, timeout=1)
                time.sleep(2)
                print(f"[Serial] Connected to {port} @ {baud} baud")
            except Exception as e:
                print(f"[Serial] Could not open {port}: {e}")
                self.enabled = False

    def send(self, cmd_bytes):
        if self.enabled and self.conn:
            self.conn.write(cmd_bytes)
        print(f"[Serial] Sent: {cmd_bytes}")

    def close(self):
        if self.conn:
            self.conn.close()


class AppState:
    def __init__(self):
        self.mode = "NORMAL"  # NORMAL, TV, AUTO
        self.bulb1 = False
        self.bulb2 = False
        self.fan_level = 0  # 0..FAN_MAX_LEVEL


def handle_shape(shape, state: AppState, link: SerialLink):
    """
    Given a recognized shape and the current mode, performs the
    corresponding action (serial command / media key / mode switch) and
    returns a short label for logging, or None if the shape does nothing
    in the current mode.
    """
    mode = state.mode

    if mode == "NORMAL":
        if shape == "OPEN_PALM":
            state.bulb1 = not state.bulb1
            link.send(b"A")
            return "BULB1_TOGGLE"
        if shape == "FIST":
            state.bulb2 = not state.bulb2
            link.send(b"B")
            return "BULB2_TOGGLE"
        if shape == "THUMBS_UP":
            state.fan_level = min(state.fan_level + 1, FAN_MAX_LEVEL)
            link.send(b"C")
            return f"FAN_UP (level {state.fan_level})"
        if shape == "THUMBS_DOWN":
            state.fan_level = max(state.fan_level - 1, 0)
            link.send(b"D")
            return f"FAN_DOWN (level {state.fan_level})"
        if shape == "TWO":
            state.mode = "AUTO"
            state.bulb1 = False
            state.bulb2 = False
            state.fan_level = 0
            link.send(b"H")
            return "AUTO_MODE_ENTER"
        if shape == "OK_SIGN":
            state.mode = "TV"
            link.send(b"J")
            return "TV_MODE_ENTER"
        return None

    if mode == "TV":
        if shape == "OPEN_PALM":
            link.send(b"P")
            return "TV_PLAY"
        if shape == "FIST":
            link.send(b"Q")
            return "TV_PAUSE"
        if shape == "THUMBS_UP":
            link.send(b"N")
            return "TV_SKIP_FWD"
        if shape == "THUMBS_DOWN":
            link.send(b"M")
            return "TV_SKIP_BACK"
        if shape == "OK_SIGN":
            state.mode = "NORMAL"
            link.send(b"K")
            return "TV_MODE_EXIT"
        # TWO (peace sign) is inactive in TV mode per the gesture table
        return None

    if mode == "AUTO":
        if shape == "TWO":
            state.mode = "NORMAL"
            link.send(b"I")
            return "AUTO_MODE_EXIT"
        # Everything else is locked out while in Auto mode
        return None

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=None, help="ESP32 serial port, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--no-serial", action="store_true")
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()

    link = SerialLink(args.port, args.baud, enabled=not args.no_serial)

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
                result_label = handle_shape(stable_shape, state, link)
                if result_label:
                    print(f"[{state.mode}] {result_label}")
                    last_fired_shape = stable_shape
                    last_fire_time = now

            # --- On-screen display ---
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

            cv2.imshow("Gesture Control", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()
    link.close()


if __name__ == "__main__":
    main()