"""
hand_gesture_ml_control.py
=============================
Device Mode / Music Mode gesture control using your trained MLPClassifier
(gesture_model.pkl). Device Mode actions are now sent over serial to an
ESP32, which switches 4 relays/LEDs accordingly. Music Mode still just
prints (no hardware attached to it yet).

GESTURE VOCABULARY:
  Rock sign (MODE_TOGGLE) -> switch DEVICE <-> MUSIC mode

  DEVICE MODE:
    ONE/TWO/THREE/FOUR -> select Device 1-4
    THUMBS_UP          -> turn selected device ON   -> sent to ESP32
    THUMBS_DOWN        -> turn selected device OFF  -> sent to ESP32

  MUSIC MODE:
    OPEN_PALM   -> Play/Pause     (printed only)
    FIST        -> Stop           (printed only)
    TWO         -> Next track     (printed only)
    THREE       -> Previous track (printed only)
    THUMBS_UP   -> Volume up      (printed only)
    THUMBS_DOWN -> Volume down    (printed only)

SERIAL PROTOCOL (single byte per command, sent to ESP32):
    b'1' -> Device 1 ON      b'2' -> Device 1 OFF
    b'3' -> Device 2 ON      b'4' -> Device 2 OFF
    b'5' -> Device 3 ON      b'6' -> Device 3 OFF
    b'7' -> Device 4 ON      b'8' -> Device 4 OFF

Requirements:
    pip install opencv-python mediapipe scikit-learn joblib pyserial

Run collect_gesture_data.py and train_gesture_model.py first so that
gesture_model.pkl exists.

Usage:
    python hand_gesture_ml_control.py --port COM5          (Windows)
    python hand_gesture_ml_control.py --port /dev/ttyUSB0  (Linux)
    python hand_gesture_ml_control.py --no-serial           (test without ESP32)
"""

import argparse
import time
from collections import deque, Counter

import cv2
import joblib
import mediapipe as mp
from mediapipe.tasks.python import vision as mp_vision

try:
    import serial
except ImportError:
    serial = None

from gesture_utils import (
    CLASSIFIER_PATH, ensure_hand_model, normalize_landmarks,
    build_hand_landmarker_options,
)

WINDOW_SIZE = 10
MIN_VOTES = 8
MIN_COOLDOWN_SEC = 1.5
MIN_CONFIDENCE = 0.6

DEVICE_SELECT_SHAPES = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4}

ACTION_TO_BYTE = {
    "DEVICE1_ON": b"1", "DEVICE1_OFF": b"2",
    "DEVICE2_ON": b"3", "DEVICE2_OFF": b"4",
    "DEVICE3_ON": b"5", "DEVICE3_OFF": b"6",
    "DEVICE4_ON": b"7", "DEVICE4_OFF": b"8",
}


class SerialLink:
    """Thin wrapper so the rest of the code doesn't care if serial is absent."""

    def __init__(self, port, baud=115200, enabled=True):
        self.enabled = enabled and serial is not None and port is not None
        self.conn = None
        if self.enabled:
            try:
                self.conn = serial.Serial(port, baud, timeout=1)
                time.sleep(2)  # allow ESP32 to reset after the port opens
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


def interpret_action(shape, mode, selected_device):
    if shape is None:
        return None, selected_device

    if mode == "DEVICE":
        if shape in DEVICE_SELECT_SHAPES:
            selected_device = DEVICE_SELECT_SHAPES[shape]
            return f"SELECT_DEVICE_{selected_device}", selected_device
        if shape == "THUMBS_UP" and selected_device:
            return f"DEVICE{selected_device}_ON", selected_device
        if shape == "THUMBS_DOWN" and selected_device:
            return f"DEVICE{selected_device}_OFF", selected_device
        return None, selected_device

    if mode == "MUSIC":
        mapping = {
            "OPEN_PALM": "PLAY_PAUSE",
            "FIST": "STOP",
            "TWO": "NEXT_TRACK",
            "THREE": "PREV_TRACK",
            "THUMBS_UP": "VOLUME_UP",
            "THUMBS_DOWN": "VOLUME_DOWN",
        }
        return mapping.get(shape), selected_device

    return None, selected_device


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=None, help="ESP32 serial port, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--no-serial", action="store_true", help="Run without sending to ESP32")
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

    mode = "DEVICE"
    selected_device = None
    last_fired_action = None
    last_fire_time = 0.0
    last_stable_shape_seen = None

    device_states = {1: False, 2: False, 3: False, 4: False}  # for on-screen display only

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
                last_fired_action = None
                last_stable_shape_seen = stable_shape

            now = time.time()

            if stable_shape == "MODE_TOGGLE" and last_fired_action != "MODE_TOGGLE":
                mode = "MUSIC" if mode == "DEVICE" else "DEVICE"
                print(f"Mode switched -> {mode}")
                last_fired_action = "MODE_TOGGLE"
                last_fire_time = now

            elif stable_shape:
                action, selected_device = interpret_action(stable_shape, mode, selected_device)
                if action and action != last_fired_action and (now - last_fire_time) > MIN_COOLDOWN_SEC:
                    print(f"[{mode}] Action: {action}")
                    last_fired_action = action
                    last_fire_time = now

                    if action in ACTION_TO_BYTE:
                        link.send(ACTION_TO_BYTE[action])
                        dev_num = int(action[6])  # "DEVICEn_ON"/"DEVICEn_OFF" -> n
                        device_states[dev_num] = action.endswith("_ON")

            # --- On-screen display ---
            cv2.putText(frame, f"Mode: {mode}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 200, 0), 2)
            if mode == "DEVICE":
                cv2.putText(frame, f"Selected device: {selected_device or '-'}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 0), 2)
                states_text = "  ".join(
                    f"D{n}:{'ON' if s else 'OFF'}" for n, s in device_states.items()
                )
                cv2.putText(frame, states_text, (10, 150),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
            cv2.putText(frame, f"Predicted: {display_text}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            if stable_shape:
                cv2.putText(frame, f"Stable: {stable_shape}", (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)

            cv2.imshow("ML Gesture Control", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()
    link.close()


if __name__ == "__main__":
    main()