"""
gesture_utils.py
=================
Shared helpers for the 3-script ML gesture pipeline:
    collect_gesture_data.py -> train_gesture_model.py -> hand_gesture_ml_control.py

Keeps landmark normalization IDENTICAL across data collection, training,
and live inference - this consistency matters a lot for accuracy.
"""

import os
import urllib.request

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HAND_MODEL_PATH = os.path.join(SCRIPT_DIR, "hand_landmarker.task")

CSV_PATH = os.path.join(SCRIPT_DIR, "gesture_data.csv")
CLASSIFIER_PATH = os.path.join(SCRIPT_DIR, "gesture_model.pkl")

# Fixed class list and key bindings used during data collection.
# Index in this list = the label id saved to the CSV.
CLASSES = [
    "FIST",         # 0
    "ONE",          # 1
    "TWO",          # 2
    "THREE",        # 3
    "FOUR",         # 4
    "OPEN_PALM",    # 5
    "THUMBS_UP",    # 6
    "THUMBS_DOWN",  # 7
    "MODE_TOGGLE",  # 8  (rock sign: index + pinky up)
]


def ensure_hand_model():
    if not os.path.exists(HAND_MODEL_PATH):
        print("Downloading hand landmark model (one-time, ~10MB)...")
        urllib.request.urlretrieve(MODEL_URL, HAND_MODEL_PATH)
        print("Model downloaded.")


def normalize_landmarks(landmarks_xy):
    """
    landmarks_xy: list of 21 (x, y) tuples (normalized image coords, 0-1).

    Returns a flat list of 42 floats:
        1. Make coordinates relative to the wrist (landmark 0)
           -> removes dependency on WHERE the hand is in frame.
        2. Scale by the largest absolute coordinate
           -> removes dependency on hand distance from camera.
    This matches the preprocessing style used by the reference repo's
    keypoint classifier, so the same trick that made that project work
    applies here too.
    """
    wrist_x, wrist_y = landmarks_xy[0]
    relative = [(x - wrist_x, y - wrist_y) for (x, y) in landmarks_xy]

    flat = []
    for x, y in relative:
        flat.append(x)
        flat.append(y)

    max_val = max(abs(v) for v in flat) or 1.0  # avoid divide-by-zero
    normalized = [v / max_val for v in flat]
    return normalized


def build_hand_landmarker_options(num_hands=1):
    """Returns configured HandLandmarkerOptions ready for create_from_options()."""
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision

    return mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=HAND_MODEL_PATH),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=num_hands,
        min_hand_detection_confidence=0.6,
        min_hand_presence_confidence=0.6,
        min_tracking_confidence=0.5,
    )
