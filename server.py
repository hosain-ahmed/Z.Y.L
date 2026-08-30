import serial
import struct
import time
import json
import os

COM_PORT = 'COM10'
BAUD_RATE = 115200
VIDEO_DIR = 'encoded_videos'
MANIFEST_PATH = os.path.join(VIDEO_DIR, 'manifest.json')

print(f"Connecting to ESP32 on {COM_PORT}...")
ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
time.sleep(2)

with open(MANIFEST_PATH, 'r') as f:
    manifest = json.load(f)

print(f"Syncing {len(manifest)} videos to ESP32...")
for entry in manifest:
    ser.write(bytes([0xAA, 0x11, 0x00, 0xBB]))
    ser.write(f"{entry['filename']}\n".encode())
    time.sleep(0.1)

print("Sync complete. Listening for fetch requests...")
print("-" * 40)

while True:
    if ser.in_waiting:
        line = ser.readline().decode(errors='ignore').strip()
        if not line:
            continue

        if line.startswith("FETCH:"):
            filename = line.split(":", 1)[1]
            filepath = os.path.join(VIDEO_DIR, filename)
            print(f"\n[REQUEST] {filename}")

            if not os.path.exists(filepath):
                print(f"[ERROR] {filepath} not found locally.")
                continue

            # Tell the ESP32 we're starting the transfer now
            ser.write(bytes([0xAA, 0x10, 0x00, 0xBB]))

            ser.write(f"{filename}\n".encode())
            time.sleep(0.05)

            file_size = os.path.getsize(filepath)
            ser.write(struct.pack('<I', file_size))

            with open(filepath, 'rb') as f:
                data = f.read()

            CHUNK_SIZE = 128
            sent = 0
            while sent < len(data):
                chunk = data[sent:sent + CHUNK_SIZE]
                ser.write(chunk)
                sent += len(chunk)

                while True:
                    resp = ser.readline().decode(errors='ignore').strip()
                    if not resp:
                        continue
                    if resp == "ACK":
                        break
                    if resp == "TIMEOUT_NO_DATA":
                        ser.write(chunk)  # resend this chunk
                    else:
                        print(f"[ESP32] {resp}")

                print(f"Progress: {sent}/{len(data)} bytes", end='\r')

            print(f"\n[SUCCESS] {filename} transfer complete.")

        else:
            print(f"[ESP32] {line}")
