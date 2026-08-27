import cv2
import numpy as np

# Load your video
cap = cv2.VideoCapture('bad_apple.mp4')
frames_extracted = 0

with open('videoframe.h', 'w') as f:
    f.write('const int TOTAL_FRAMES = 900;\n')
    f.write('const int FRAME_SIZE = 1024;\n')
    f.write('const unsigned char video_frames[][FRAME_SIZE] PROGMEM = {\n')

    while cap.isOpened() and frames_extracted < 900:
        ret, frame = cap.read()
        if not ret: break
        
        # Resize to OLED dimensions
        frame = cv2.resize(frame, (128, 64))
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Apply a hard threshold (no dithering)
        _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        
        # Convert pixels to XBM format bytes (LSB first)
        byte_array = []
        for row in range(64):
            for col_byte in range(16):
                byte = 0
                for bit in range(8):
                    pixel_val = thresh[row, col_byte * 8 + bit]
                    if pixel_val > 0:
                        byte |= (1 << bit) # Set bit for white pixels
                byte_array.append(byte)
        
        # Write to header file
        hex_strings = [f"0x{b:02X}" for b in byte_array]
        f.write('  { ' + ', '.join(hex_strings) + ' },\n')
        
        frames_extracted += 1

    f.write('};\n')
cap.release()
print(f"Successfully processed {frames_extracted} frames.")