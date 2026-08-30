import serial
import struct
import sys
import time
import os

if len(sys.argv) < 3:
    # Use a raw string (r"") so the backslashes in your Windows path don't break the text
    print(r"Usage: python send_test_file.py COM10 Q:\GestureControlledSystem\encoded_videos\video1.bin")
    sys.exit(1)

port = sys.argv[1]
filepath = sys.argv[2]

if not os.path.exists(filepath):
    print(f"File not found: {filepath}")
    sys.exit(1)

file_size = os.path.getsize(filepath)
print(f"Sending {filepath} ({file_size} bytes) to {port}...")

try:
    ser = serial.Serial(port, 115200, timeout=2)
except serial.SerialException as e:
    print(f"Failed to open port {port}: {e}")
    sys.exit(1)

time.sleep(2)  # let the ESP32 reboot on connect

print("Waiting for ESP32 to say it is ready...")
# Print anything the ESP32 says until it signals it's ready
timeout_start = time.time()
while True:
    line = ser.readline().decode(errors='ignore').strip()
    if line:
        print(f"[ESP32] {line}")
    if line == "READY_FOR_FILE":
        break
    
    # Add a timeout so the script doesn't hang forever if the ESP32 isn't ready
    if time.time() - timeout_start > 10:
        print("Error: Timed out waiting for READY_FOR_FILE from ESP32.")
        ser.close()
        sys.exit(1)

# Send 4-byte little-endian size, then the raw file bytes
print("Sending file size...")
ser.write(struct.pack('<I', file_size))

print("Sending file data...")
# Sending in chunks is much safer for the ESP32's limited serial buffer
with open(filepath, 'rb') as f:
    while True:
        chunk = f.read(1024) # Send 1KB at a time
        if not chunk:
            break
        ser.write(chunk)

# Print remaining ESP32 output (progress + confirmation)
print("Data sent! Waiting for ESP32 confirmation...")
start = time.time()
while time.time() - start < 15:
    line = ser.readline().decode(errors='ignore').strip()
    if line:
        print(f"[ESP32] {line}")

print("Done. Check the OLED — it should now be looping the test video.")
ser.close()