"""
train_gesture_model.py
========================
Step 2 of 3. Trains a small neural network classifier on the landmark
samples collected by collect_gesture_data.py, and saves it for use in
hand_gesture_ml_control.py.

Requirements:
    pip install scikit-learn joblib
"""

import csv
import os

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, accuracy_score
import joblib

# ----------------------------------------------------------------------
# Shared config (previously in gesture_utils.py, now inlined here)
# ----------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "gesture_data.csv")
CLASSIFIER_PATH = os.path.join(SCRIPT_DIR, "gesture_model.pkl")

CLASSES = [
    "FIST",         # 0
    "OPEN_PALM",    # 1
    "THUMBS_UP",    # 2
    "THUMBS_DOWN",  # 3
    "TWO",          # 4  (peace sign)
    "OK_SIGN",      # 5  (thumb tip touching index tip, other 3 fingers up)
]


def load_data():
    X, y = [], []
    with open(CSV_PATH, "r", newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            y.append(int(row[0]))
            X.append([float(v) for v in row[1:]])
    return np.array(X), np.array(y)


def main():
    print(f"Loading data from {CSV_PATH} ...")
    X, y = load_data()
    print(f"Loaded {len(X)} samples across {len(set(y))} classes.")

    counts = {CLASSES[i]: int((y == i).sum()) for i in sorted(set(y))}
    for name, count in counts.items():
        flag = "  <-- consider collecting more" if count < 30 else ""
        print(f"  {name}: {count}{flag}")

    if len(X) < 50:
        print("\nWarning: very little data. Collect more samples for a "
              "reliable model (aim for 50-100+ per class).")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    clf = MLPClassifier(
        hidden_layer_sizes=(64, 32),
        activation="relu",
        max_iter=2000,
        random_state=42,
        early_stopping=True,
    )
    clf.fit(X_train_scaled, y_train)

    y_pred = clf.predict(X_test_scaled)
    acc = accuracy_score(y_test, y_pred)
    print(f"\nTest accuracy: {acc:.3f}\n")
    print(classification_report(
        y_test, y_pred,
        labels=sorted(set(y)),
        target_names=[CLASSES[i] for i in sorted(set(y))],
        zero_division=0,
    ))

    joblib.dump({"scaler": scaler, "classifier": clf, "classes": CLASSES}, CLASSIFIER_PATH)
    print(f"Model saved to {CLASSIFIER_PATH}")


if __name__ == "__main__":
    main()
