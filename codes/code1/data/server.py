import serial
import os
import struct
import time

# --- CONFIGURATION ---
COM_PORT = 'COM10'  # Change to your ESP32's COM port
BAUD_RATE = 115200

print(f"Connecting to ESP32 on {COM_PORT}...")
try:
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Give the ESP32 time to reboot upon connection
except Exception as e:
    print(f"Failed to connect: {e}")
    exit()

# 1. Scan the directory for cached video files
videos = [f for f in os.listdir('Q:\GestureControlledSystem\codes\code1\data') if f.endswith('.bin')]
if not videos:
    print("No .bin files found in this directory. Create some first!")
    exit()

# 2. Sync the video list to the ESP32 OLED
print(f"Found {len(videos)} videos. Syncing to ESP32...")
for video_name in videos:
    # Send the 0x11 command packet to trigger the list addition
    ser.write(bytes([0xAA, 0x11, 0x00, 0xBB]))
    # Immediately send the string name
    ser.write(f"{video_name}\n".encode())
    time.sleep(0.1)  # Brief pause so the ESP32 queue doesn't choke

print("Sync complete. Media Server is running and listening...")
print("-" * 40)

# 3. The Listening Loop (Wait for Potentiometer/Button fetches)
while True:
    if ser.in_waiting:
        # Read incoming serial data
        line = ser.readline().decode(errors='ignore').strip()
        
        # Check if the ESP32 is asking for a file
        if line.startswith("FETCH:"):
            filename = line.split(":", 1)[1]
            print(f"\n[REQUEST] ESP32 requested: {filename}")
            
            if os.path.exists(filename):
                # Send the 0x10 command packet to trigger downloadRoutine()
                ser.write(bytes([0xAA, 0x10, 0x00, 0xBB]))
                
                # Wait for the ESP32 to open LittleFS and reply "READY"
                while True:
                    resp = ser.readline().decode(errors='ignore').strip()
                    if resp == "READY":
                        break
                
                print("ESP32 Ready. Streaming data...")
                
                # --- NEW FIX: Send the video name so ESP32 knows what it is ---
                ser.write(f"{filename}\n".encode())
                time.sleep(0.05) # Tiny pause to let ESP32 read the string
                # --------------------------------------------------------------
                
                # Send the total file size as a 4-byte little-endian integer
                file_size = os.path.getsize(filename)
                ser.write(struct.pack('<I', file_size))
                
               # Stream the file in safer 128-byte chunks
                with open(filename, 'rb') as f:
                    bytes_sent = 0
                    while bytes_sent < file_size:
                        chunk = f.read(128) # --- CHANGED TO 128 ---
                        ser.write(chunk)
                        bytes_sent += len(chunk)
                        
                        # Wait for the ESP32 to write the chunk and reply "ACK"
                        while True:
                            ack = ser.readline().decode(errors='ignore').strip()
                            if ack == "ACK":
                                break
                            elif ack: 
                                # --- NEW: If ESP32 sends an error, print it! ---
                                print(f"[ESP32 message]: {ack}")
                                
                        print(f"Progress: {bytes_sent}/{file_size} bytes", end='\r')
                        
                print(f"\n[SUCCESS] {filename} transfer complete!")
            else:
                print(f"[ERROR] {filename} not found on PC.")
        
        elif line:
            # Print standard ESP32 debug messages (e.g., "TV OFF")
            print(f"[ESP32] {line}")