import socket
import json
import struct
import sys

# --- SETTINGS ---
# If running on the same machine, use '127.0.0.1'.
# If running on a different laptop, put the Jetson's IP address here (e.g., '192.168.1.50')
HOST = '127.0.0.1'
PORT = 65432

def main():
    print(f"Attempting to connect to {HOST}:{PORT}...")
   
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((HOST, PORT))
            print("Connected! Waiting for data...")
            print("-" * 50)

            while True:
                # 1. Read the 4-byte Header (Payload Length)
                header_data = s.recv(4)
                if not header_data:
                    break # Connection closed
               
                # Unpack big-endian integer
                msg_len = struct.unpack('>I', header_data)[0]

                # 2. Read the Payload (exactly msg_len bytes)
                payload_data = b''
                while len(payload_data) < msg_len:
                    chunk = s.recv(msg_len - len(payload_data))
                    if not chunk:
                        break
                    payload_data += chunk

                # 3. Decode and Print
                try:
                    data = json.loads(payload_data.decode('utf-8'))
                   
                    if not data:
                        print("No target selected.")
                    else:
                        for target in data:
                            # Extract the specific variables requested
                            t_id = target.get('TrackID')
                            state = target.get('State') # This is the 0 or 1 toggle
                            cx = target.get('CenterX')
                            cy = target.get('CenterY')
                           
                            print(f"ID: {t_id} | State: {state} | Center: ({cx:.1f}, {cy:.1f})")

                except json.JSONDecodeError:
                    print("Error decoding JSON")

    except ConnectionRefusedError:
        print(f"Could not connect to {HOST}:{PORT}. Is the sender script running?")
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
