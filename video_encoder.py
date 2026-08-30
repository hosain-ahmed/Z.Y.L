import cv2
import numpy as np
from PIL import Image
import json
import os

# --- CONFIGURATION ---
MAX_FRAMES_ALLOWED = 500          # hardware/flash cap per video
PROCESS_MODE = 'dither'           # 'dither', 'edge', or 'threshold'
OUTPUT_DIR = r'Q:\GestureControlledSystem\encoded_videos'
MANIFEST_PATH = os.path.join(OUTPUT_DIR, 'manifest.json')


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, 'r') as f:
            return json.load(f)
    return []


def save_manifest(manifest):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(MANIFEST_PATH, 'w') as f:
        json.dump(manifest, f, indent=2)


def next_output_filename(manifest):
    # video1.bin, video2.bin, ... based on how many entries already exist
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


def encode_video(source_path, start_sec, display_name):
    cap = cv2.VideoCapture(source_path)
    if not cap.isOpened():
        print(f"Error: could not open '{source_path}'.")
        return None

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30.0  # fallback if the container doesn't report FPS reliably

    max_seconds = MAX_FRAMES_ALLOWED / fps
    print(f"Video FPS: {fps:.2f}. Max clip length at {MAX_FRAMES_ALLOWED} frames: {max_seconds:.1f}s.")
    print(f"Extracting up to {MAX_FRAMES_ALLOWED} frames starting at {start_sec}s...")

    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000)

    manifest = load_manifest()
    output_filename = next_output_filename(manifest)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

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
            print(f"Processed frame {frames_extracted}/{MAX_FRAMES_ALLOWED}", end='\r')

    cap.release()

    if frames_extracted == 0:
        print("\nNo frames were extracted — check the start time against the video length.")
        os.remove(output_path)
        return None

    print(f"\nSaved {frames_extracted} frames to {output_path}.")

    manifest.append({
        "name": display_name,
        "filename": output_filename,
        "frame_count": frames_extracted,
        "fps_source": round(fps, 2)
    })
    save_manifest(manifest)
    print(f"Added to manifest as '{display_name}' ({output_filename}).")
    return output_path


def main():
    print("=== ESP32 Mini-TV Video Encoder ===")
    source_path = input("Path to source video file: ").strip().strip('"')

    if not os.path.exists(source_path):
        print(f"File not found: {source_path}")
        return

    display_name = input("Name to show in the ESP32 menu (e.g. 'Big Buck Bunny'): ").strip()
    if not display_name:
        display_name = os.path.splitext(os.path.basename(source_path))[0]

    while True:
        raw = input("Start encoding at which second? [0]: ").strip()
        if raw == "":
            start_sec = 0
            break
        try:
            start_sec = float(raw)
            break
        except ValueError:
            print("Enter a number, e.g. 12 or 12.5")

    encode_video(source_path, start_sec, display_name)


if __name__ == "__main__":
    main()