import cv2
import numpy as np
from PIL import Image

# --- CONFIGURATION ---
VIDEO_FILE = 'colour_video.mp4'
OUTPUT_BIN = 'video3.bin'
PROCESS_MODE = 'dither'  # 'dither', 'edge', or 'threshold'
MAX_FRAMES_ALLOWED = 900

# Snippet Selection
START_TIME_SEC = 0  # Start extracting at 15 seconds into the video

cap = cv2.VideoCapture(VIDEO_FILE)
fps = cap.get(cv2.CAP_PROP_FPS)
max_seconds = MAX_FRAMES_ALLOWED / fps

print(f"Video FPS: {fps:.2f}. Max hardware capacity is {max_seconds:.1f} seconds.")
print(f"Extracting up to 900 frames starting from {START_TIME_SEC}s...")

# Seek to the start time
cap.set(cv2.CAP_PROP_POS_MSEC, START_TIME_SEC * 1000)

frames_extracted = 0

# Open directly as a binary write file ('wb')
with open(OUTPUT_BIN, 'wb') as f:
    while cap.isOpened() and frames_extracted < MAX_FRAMES_ALLOWED:
        ret, frame = cap.read()
        if not ret: break
        
        frame = cv2.resize(frame, (128, 64))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        if PROCESS_MODE == 'edge':
            processed = cv2.Canny(gray, 50, 150)
        elif PROCESS_MODE == 'dither':
            pil_img = Image.fromarray(gray)
            processed = np.array(pil_img.convert('1'), dtype=np.uint8) * 255
        else: # hard threshold fallback
            _, processed = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
            
        byte_array = bytearray()
        for row in range(64):
            for col_byte in range(16):
                byte = 0
                for bit in range(8):
                    if processed[row, col_byte * 8 + bit] > 0:
                        byte |= (1 << bit)
                byte_array.append(byte)
        
        # Write flat bytes directly to the file
        f.write(byte_array)
        frames_extracted += 1
        print(f"Processed frame {frames_extracted}/{MAX_FRAMES_ALLOWED}", end='\r')

cap.release()
print(f"\nSuccessfully saved {frames_extracted} frames directly to {OUTPUT_BIN}.")