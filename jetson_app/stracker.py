import jetson.inference
import jetson.utils
import socket
import json
import sys
import threading
import math
import termios
import tty
import os

# --- SETTINGS ---
HOST = '0.0.0.0'
PORT = 65432

# --- Global Shared State ---
target_track_id = -1   # -1 means "track no one"
tracking_state = 0     # 0 or 1 (toggled by Spacebar)
input_command = None   # Communicates key presses to main thread ('NEXT', 'PREV', 'TOGGLE', 'QUIT')
state_lock = threading.Lock()

# --- Custom Tracking State ---
active_person_tracks = {}
next_available_id = 1
TRACKING_THRESHOLD_PX = 150

def get_key():
    """
    Reads a single keypress from stdin without requiring Enter.
    Works on Linux (Jetson).
    """
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        if ch == '\x1b': # Arrow keys start with Escape sequence
            ch += sys.stdin.read(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def keyboard_listener_thread():
    """
    Background thread to listen for Arrow Keys and Spacebar.
    """
    global input_command
   
    print("\n--- CONTROLS ---")
    print(" [ <- / -> ] : Cycle through people")
    print(" [ SPACE ]   : Toggle State (0=Green / 1=Red)")
    print(" [ Q ]       : Quit")
    print("----------------\n")
   
    while True:
        key = get_key()
       
        with state_lock:
            if key == '\x03' or key.lower() == 'q': # Ctrl+C or q
                input_command = 'QUIT'
                break
           
            # Arrow Keys (ANSI escape sequences)
            elif key == '\x1b[C': # Right Arrow
                input_command = 'NEXT'
            elif key == '\x1b[D': # Left Arrow
                input_command = 'PREV'
           
            # Spacebar
            elif key == ' ':
                input_command = 'TOGGLE'

def calculate_distance_sq(center1, center2):
    return (center1[0] - center2[0])**2 + (center1[1] - center2[1])**2

def main():
    global next_available_id, active_person_tracks, target_track_id, tracking_state, input_command

    # 1. Load Model
    net = jetson.inference.detectNet("ssd-mobilenet-v2", threshold=0.5)

    # 2. Find Person Class ID
    # This ensures we know exactly which ID corresponds to 'person' in the loaded model
    person_class_id = -1
    for i in range(net.GetNumClasses()):
        if net.GetClassDesc(i).lower() == 'person':
            person_class_id = i
            break
           
    if person_class_id < 0:
        print("Error: 'person' class not found in the loaded model.")
        sys.exit(1)
    else:
        print(f"Tracking Class 'person' (ID: {person_class_id})")
   
    # 3. Init Camera
    try:
        camera = jetson.utils.videoSource("/dev/video0")
    except Exception as e:
        print(f"Error opening camera: {e}")
        sys.exit(1)

    # 4. Init Display and Font
    display = jetson.utils.videoOutput()
    font = jetson.utils.cudaFont()

    # 5. Start Input Thread
    input_thread = threading.Thread(target=keyboard_listener_thread, daemon=True)
    input_thread.start()

    print(f"Server listening on {HOST}:{PORT}...")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen()
           
            conn, addr = s.accept()
            with conn:
                print(f"Connected: {addr}")
               
                while display.IsStreaming():
                    # Check for quit command
                    if input_command == 'QUIT':
                        break

                    img = camera.Capture()
                   
                    # IMPORTANT: overlay='none' ensures the network doesn't draw generic boxes
                    # for things like 'chair' or 'dog'. We will draw manually later.
                    detections = net.Detect(img, overlay='none')
                   
                    # --- TRACKING LOGIC ---
                   
                    # STRICT FILTER: Discard any detection that is NOT a person
                    current_person_detections = [d for d in detections if d.ClassID == person_class_id]
                   
                    new_active_tracks = {}
                    unmatched_current = list(current_person_detections)
                    threshold_sq = TRACKING_THRESHOLD_PX ** 2
                   
                    # Match existing
                    for track_id, last_det in active_person_tracks.items():
                        min_dist = float('inf')
                        best_det = None
                        best_idx = -1
                       
                        for i, curr in enumerate(unmatched_current):
                            dist = calculate_distance_sq(last_det.Center, curr.Center)
                            if dist < min_dist and dist < threshold_sq:
                                min_dist = dist
                                best_det = curr
                                best_idx = i
                       
                        if best_det:
                            best_det.TrackID = track_id
                            new_active_tracks[track_id] = best_det
                            unmatched_current.pop(best_idx)

                    # Add new
                    for new_det in unmatched_current:
                        new_det.TrackID = next_available_id
                        new_active_tracks[next_available_id] = new_det
                        next_available_id += 1
                       
                    active_person_tracks = new_active_tracks

                    # --- PROCESS INPUT COMMANDS (Selection Logic) ---
                    current_ids = sorted(list(active_person_tracks.keys()))
                   
                    with state_lock:
                        if input_command == 'TOGGLE':
                            # Flip 0 (Green/Off) to 1 (Red/On), or 1 to 0
                            tracking_state = 1 - tracking_state
                            input_command = None # Reset command
                       
                        elif input_command in ('NEXT', 'PREV'):
                            if len(current_ids) > 0:
                                if target_track_id not in current_ids:
                                    # If currently tracking nothing (or lost track), pick the first one
                                    target_track_id = current_ids[0]
                                else:
                                    # Find current index and cycle
                                    curr_idx = current_ids.index(target_track_id)
                                    if input_command == 'NEXT':
                                        new_idx = (curr_idx + 1) % len(current_ids)
                                    else:
                                        new_idx = (curr_idx - 1) % len(current_ids)
                                    target_track_id = current_ids[new_idx]
                            else:
                                target_track_id = -1 # No one to track
                           
                            input_command = None # Reset command

                    # --- RENDERING & DATA ---
                    detections_to_send = []
                   
                    for track_id, track in active_person_tracks.items():
                       
                        # Default: Blue for non-targets (Transparent: 40)
                        color = (0, 100, 255, 40)
                        label_text = f"ID {track_id}"
                       
                        # Target Logic
                        if track_id == target_track_id:
                            # Determine color based on State Variable (Transparent: 75)
                            if tracking_state == 0:
                                color = (0, 255, 0, 75) # GREEN (State 0)
                            else:
                                color = (255, 0, 0, 75) # RED (State 1)
                               
                            # Updated Label to show State and Center
                            cx, cy = int(track.Center[0]), int(track.Center[1])
                            label_text = f"TARGET {track_id} | State: {tracking_state} | Center: ({cx}, {cy})"
                           
                            # Pack JSON - Including State and Center
                            det_data = {
                                "TrackID": track_id,
                                "State": tracking_state, # The 0 or 1 variable
                                "Light": "off" if tracking_state == 0 else "on",
                                "Confidence": track.Confidence,
                                "Left": track.Left,
                                "Top": track.Top,
                                "Right": track.Right,
                                "Bottom": track.Bottom,
                                "CenterX": track.Center[0],
                                "CenterY": track.Center[1]
                            }
                            detections_to_send.append(det_data)
                       
                        # Draw overlay
                        box = (track.Left, track.Top, track.Right, track.Bottom)
                        jetson.utils.cudaDrawRect(img, box, color)
                        font.OverlayText(img, text=label_text, x=int(track.Left), y=int(track.Top)-25, color=(255,255,255), background=color)

                    # --- SEND OVER SOCKET ---
                    try:
                        payload = json.dumps(detections_to_send).encode('utf-8')
                        # Send 4-byte length header followed by payload
                        header = len(payload).to_bytes(4, 'big')
                        conn.sendall(header + payload)
                    except:
                        print("Client disconnected, waiting for new connection...")
                        conn, addr = s.accept() # Simple reconnect logic
                        print(f"Reconnected: {addr}")

                    display.Render(img)
                    display.SetStatus(f"FPS: {net.GetNetworkFPS():.1f} | Target: {target_track_id} | State: {tracking_state}")

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)
    finally:
        print("Exiting...")

if __name__ == '__main__':
    main()

