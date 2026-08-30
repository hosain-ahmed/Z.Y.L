import serial
import struct
import sys
import time
import os

if len(sys.argv) < 3:
    print("Usage: python send_test_file.py <COM_PORT> <path_to_bin_file>")
    sys.exit(1)

port = sys.argv[1]
filepath = sys.argv[2]

if not os.path.exists(filepath):
    print(f"File not found: {filepath}")
    sys.exit(1)

file_size = os.path.getsize(filepath)
print(f"Sending {filepath} ({file_size} bytes) to {port}...")

ser = serial.Serial(port, 115200, timeout=2)
time.sleep(2)  # let the ESP32 reboot on connect

# Print anything the ESP32 says until it signals it's ready
while True:
    line = ser.readline().decode(errors='ignore').strip()
    if line:
        print(f"[ESP32] {line}")
    if line == "READY_FOR_FILE":
        break

# Send 4-byte little-endian size
ser.write(struct.pack('<I', file_size))

# Send the file in 128-byte chunks, waiting for an ACK after each one
CHUNK_SIZE = 128
with open(filepath, 'rb') as f:
    data = f.read()

sent = 0
while sent < len(data):
    chunk = data[sent:sent + CHUNK_SIZE]
    ser.write(chunk)
    sent += len(chunk)

    # Wait for this chunk's response before sending the next one
    while True:
        line = ser.readline().decode(errors='ignore').strip()
        if not line:
            print("No response from ESP32 for 2s — connection may have stalled.")
            continue
        print(f"[ESP32] {line}")
        if line == "ACK":
            break
        if line == "TIMEOUT_NO_DATA":
            # ESP32 didn't get the bytes it expected — resend this chunk
            ser.write(chunk)

print(f"Sent {sent}/{len(data)} bytes with per-chunk ACKs.")

# Print remaining ESP32 output (write-complete confirmation, read-back size)
start = time.time()
while time.time() - start < 10:
    line = ser.readline().decode(errors='ignore').strip()
    if line:
        print(f"[ESP32] {line}")

print("Done. Check the OLED — it should now be looping the test video.")
