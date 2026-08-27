import re

# Read your header file
with open('VideoFrame.h', 'r') as f:
    data = f.read()

# Extract all the hex values (e.g., 0xFF, 0x00)
hex_values = re.findall(r'0x[0-9A-Fa-f]{2}', data)

# Convert to raw bytes and save as video.bin
with open('video.bin', 'wb') as f:
    for hex_val in hex_values:
        f.write(bytes([int(hex_val, 16)]))

print(f"Saved {len(hex_values)} bytes to video.bin")