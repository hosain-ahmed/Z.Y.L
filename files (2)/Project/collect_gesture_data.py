"""
collect_gesture_data.py
=========================
Step 1 of 3. Captures labeled hand-landmark samples for training.

While the webcam window is focused, hold a gesture pose and press its
number key to save one sample. Move your hand slightly (angle, distance,
position in frame) between presses so the model learns to generalize -
don't just hold perfectly still and mash the key.

Key bindings (class id -> gesture):
    0 -> FIST         (all fingers curled, thumb tucked)
    1 -> OPEN_PALM    (all 5 fingers, including thumb, spread open)
    2 -> THUMBS_UP    (fist with thumb pointing up)
    3 -> THUMBS_DOWN  (fist with thumb pointing down)
    4 -> TWO          (peace sign: index + middle up, thumb tucked)
    5 -> OK_SIGN      (thumb tip touching index tip, other 3 fingers up)

NOTE: If you previously collected data for the old 9-class scheme
(ONE/THREE/FOUR/MODE_TOGGLE), that gesture_data.csv is now INCOMPATIBLE
- the label ids mean different gestures now. Delete or rename the old
gesture_data.csv before collecting fresh data for this new scheme.

Press 'q' to quit and save.

Aim for at least 50-100 samples per class for a reasonably robust model.
Samples append to gesture_data.csv - you can run this script multiple
times (e.g. different sessions/lighting) and it will keep adding to it.

Requirements:
    pip install opencv-python mediapipe
"""

import csv
import os
import time
import urllib.request

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# ----------------------------------------------------------------------
# Shared config (previously in gesture_utils.py, now inlined here)
# ----------------------------------------------------------------------
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HAND_MODEL_PATH = os.path.join(SCRIPT_DIR, "hand_landmarker.task")
CSV_PATH = os.path.join(SCRIPT_DIR, "gesture_data.csv")

CLASSES = [
    "FIST",         # 0
    "OPEN_PALM",    # 1
    "THUMBS_UP",    # 2
    "THUMBS_DOWN",  # 3
    "TWO",          # 4  (peace sign)
    "OK_SIGN",      # 5  (thumb tip touching index tip, other 3 fingers up)
]


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


def main():
    ensure_hand_model()

    options = build_hand_landmarker_options(num_hands=1)
    HandLandmarker = mp_vision.HandLandmarker

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: could not open webcam.")
        return

    file_exists = os.path.exists(CSV_PATH)
    csv_file = open(CSV_PATH, "a", newline="")
    writer = csv.writer(csv_file)

    sample_counts = {name: 0 for name in CLASSES}
    if file_exists:
        with open(CSV_PATH, "r", newline="") as f:
            for row in csv.reader(f):
                if row:
                    label_id = int(row[0])
                    sample_counts[CLASSES[label_id]] += 1

    start_time = time.time()

    print("Ready. Key bindings:")
    for i, name in enumerate(CLASSES):
        print(f"  {i} -> {name}")
    print("Press 'q' to quit.\n")

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

            current_landmarks = None
            if result.hand_landmarks:
                landmarks_raw = result.hand_landmarks[0]
                current_landmarks = [(lm.x, lm.y) for lm in landmarks_raw]

                h, w, _ = frame.shape
                for lm in landmarks_raw:
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cv2.circle(frame, (cx, cy), 4, (0, 255, 0), -1)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break

            if ord("0") <= key <= ord("5"):
                label_id = key - ord("0")
                if current_landmarks:
                    features = normalize_landmarks(current_landmarks)
                    writer.writerow([label_id] + features)
                    csv_file.flush()
                    sample_counts[CLASSES[label_id]] += 1
                    print(f"Saved sample for {CLASSES[label_id]} "
                          f"(total: {sample_counts[CLASSES[label_id]]})")
                else:
                    print("No hand detected - sample not saved.")

            # --- On-screen display ---
            y = 30
            cv2.putText(frame, "Hold pose, press 0-8 to label. 'q' to quit.",
                        (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            for i, name in enumerate(CLASSES):
                y += 22
                text = f"{i}: {name} ({sample_counts[name]})"
                cv2.putText(frame, text, (10, y + 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow("Collect Gesture Data", frame)

    cap.release()
    cv2.destroyAllWindows()
    csv_file.close()

    print("\nFinal sample counts:")
    for name, count in sample_counts.items():
        print(f"  {name}: {count}")
    print(f"\nSaved to {CSV_PATH}")


if __name__ == "__main__":
    main()
