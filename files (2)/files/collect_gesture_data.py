"""
collect_gesture_data.py
=========================
Step 1 of 3. Captures labeled hand-landmark samples for training.

While the webcam window is focused, hold a gesture pose and press its
number key to save one sample. Move your hand slightly (angle, distance,
position in frame) between presses so the model learns to generalize -
don't just hold perfectly still and mash the key.

Key bindings (class id -> gesture):
    0 -> FIST
    1 -> ONE          (index finger only)
    2 -> TWO          (index + middle / peace-ish, fingers only, thumb tucked)
    3 -> THREE        (index + middle + ring)
    4 -> FOUR         (index + middle + ring + pinky, thumb tucked)
    5 -> OPEN_PALM    (all 5 fingers, including thumb, spread open)
    6 -> THUMBS_UP    (fist with thumb pointing up)
    7 -> THUMBS_DOWN  (fist with thumb pointing down)
    8 -> MODE_TOGGLE  (rock sign: index + pinky up, middle + ring down)

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

import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision as mp_vision

from gesture_utils import (
    CLASSES, CSV_PATH, ensure_hand_model, normalize_landmarks,
    build_hand_landmarker_options,
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

            if ord("0") <= key <= ord("8"):
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
