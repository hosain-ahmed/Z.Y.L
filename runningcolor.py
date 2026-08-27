import cv2
import numpy as np
from PIL import Image

# --- CONFIGURATION ---
VIDEO_FILE = 'colour_video.mp4'  # Replace with your video file name
OUTPUT_FILE = 'videoframe2.h'   # Outputs as the second video file

# CHANGE THIS to 'dither' or 'edge' to test the different styles!
PROCESS_MODE = 'dither'  

# Memory limit: 30 seconds at 30fps = 900 frames max
MAX_FRAMES = 900  

cap = cv2.VideoCapture(VIDEO_FILE)
frames_extracted = 0

with open(OUTPUT_FILE, 'w') as f:
    # Write the C++ header formatting
    f.write(f'const int TOTAL_FRAMES_2 = {MAX_FRAMES};\n')
    f.write('const unsigned char video_frames2[][1024] PROGMEM = {\n')

    while cap.isOpened() and frames_extracted < MAX_FRAMES:
        ret, frame = cap.read()
        if not ret:
            break
        
        # 1. Resize to OLED dimensions (128x64)
        frame = cv2.resize(frame, (128, 64))
        
        # 2. Convert to Grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 3. Apply the chosen processing style
        if PROCESS_MODE == 'edge':
            # Canny Edge Detection (finds outlines)
            # You can adjust 50 and 150 if the lines are too thick or too thin
            processed = cv2.Canny(gray, 50, 150)
            
        elif PROCESS_MODE == 'dither':
            # Floyd-Steinberg Dithering (simulates shading)
            pil_img = Image.fromarray(gray)
            dithered = pil_img.convert('1') # '1' triggers 1-bit dithering
            processed = np.array(dithered, dtype=np.uint8) * 255
            
        else:
            print("Invalid PROCESS_MODE. Use 'dither' or 'edge'.")
            break
            
        # 4. Convert pixels to XBM format bytes (Least Significant Bit first)
        byte_array = []
        for row in range(64):
            for col_byte in range(16):
                byte = 0
                for bit in range(8):
                    pixel_val = processed[row, col_byte * 8 + bit]
                    if pixel_val > 0:
                        byte |= (1 << bit) # Set bit for white pixels
                byte_array.append(byte)
        
        # 5. Write raw hex bytes to the file
        hex_strings = [f"0x{b:02X}" for b in byte_array]
        f.write('  { ' + ', '.join(hex_strings) + ' },\n')
        
        frames_extracted += 1
        # Print progress in the terminal
        print(f"Processed frame {frames_extracted}/{MAX_FRAMES}", end='\r')

    f.write('};\n')

cap.release()
print(f"\nSuccessfully saved {frames_extracted} frames to {OUTPUT_FILE}.")