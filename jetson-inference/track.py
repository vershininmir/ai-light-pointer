import jetson.inference
import jetson.utils
import numpy as np
import math
import time

# --- Configuration ---
# You must set your desired ID here. It's best to run the script once, 
# observe the IDs, and then set this to the ID of the person you want to track.
TARGET_TRACK_ID = 1 
TARGET_CLASS_ID = 1 # COCO dataset class ID for 'person'

# Set the detection network model to use
MODEL_NAME = "ssd-mobilenet-v2" 
THRESHOLD = 0.5

# Input/Output setup
VIDEO_INPUT = "csi://0" # Use "csi://0" for CSI camera, or "/dev/video0" for V4L2 USB camera, or a video file path
VIDEO_OUTPUT = "display://0"

# --- Centroid Tracker Class (Simple MOT) ---
class CentroidTracker:
    def __init__(self, max_disappeared=50):
        # Stores the next unique object ID counter
        self.next_object_id = 0
        # Stores a dictionary of object IDs to their centroids (x, y)
        self.objects = {}
        # Stores a dictionary of object IDs to the number of consecutive frames they were not detected
        self.disappeared = {}
        # Maximum number of frames an object can be marked as 'disappeared' before being deregistered
        self.max_disappeared = max_disappeared

    def register(self, centroid):
        # Register a new object using the next available ID
        self.objects[self.next_object_id] = centroid
        self.disappeared[self.next_object_id] = 0
        self.next_object_id += 1
        return self.next_object_id - 1 # Return the newly assigned ID

    def deregister(self, object_id):
        # Deregister an object
        del self.objects[object_id]
        del self.disappeared[object_id]

    def update(self, rect_centroids):
        # If no detections, increment 'disappeared' count for all existing objects
        if len(rect_centroids) == 0:
            for object_id in list(self.disappeared.keys()):
                self.disappeared[object_id] += 1
                if self.disappeared[object_id] > self.max_disappeared:
                    self.deregister(object_id)
            return self.objects

        # Initialize list to store new assignments
        input_centroids = np.array(rect_centroids)
        output_objects = list(self.objects.keys())
        output_centroids = np.array(list(self.objects.values()))

        # If no objects are currently being tracked, register all new detections
        if len(self.objects) == 0:
            current_ids = {}
            for i in range(len(input_centroids)):
                new_id = self.register(input_centroids[i])
                current_ids[new_id] = input_centroids[i]
            self.objects = current_ids
            return self.objects

        # Compute the Euclidean distance between all existing centroids and new centroids
        D = np.zeros((len(output_centroids), len(input_centroids)))
        for i in range(len(output_centroids)):
            for j in range(len(input_centroids)):
                D[i, j] = math.hypot(output_centroids[i][0] - input_centroids[j][0],
                                     output_centroids[i][1] - input_centroids[j][1])
        
        # Simple assignment: find the minimum distance
        rows = D.min(axis=1).argsort()
        cols = D.argmin(axis=1)[rows]

        # Use to track which detections are already matched
        used_rows = set()
        used_cols = set()
        current_ids = {}

        # Loop over the sorted distances
        for (row, col) in zip(rows, cols):
            if row in used_rows or col in used_cols:
                continue

            object_id = output_objects[row]
            self.objects[object_id] = input_centroids[col]
            self.disappeared[object_id] = 0
            current_ids[object_id] = input_centroids[col]

            used_rows.add(row)
            used_cols.add(col)

        # Handle 'disappeared' objects
        unused_rows = set(range(len(output_centroids))).difference(used_rows)
        for row in unused_rows:
            object_id = output_objects[row]
            self.disappeared[object_id] += 1
            if self.disappeared[object_id] > self.max_disappeared:
                self.deregister(object_id)
            else:
                current_ids[object_id] = self.objects[object_id]

        # Handle new 'registered' objects
        unused_cols = set(range(len(input_centroids))).difference(used_cols)
        for col in unused_cols:
            new_id = self.register(input_centroids[col])
            current_ids[new_id] = input_centroids[col]

        self.objects = current_ids
        return self.objects

# --- Main Logic ---
def run_jetson_tracking():
    # Load detection network
    net = jetson.inference.detectNet(MODEL_NAME, threshold=THRESHOLD)
    
    # Create video sources and sinks
    input = jetson.utils.videoSource(VIDEO_INPUT)
    output = jetson.utils.videoOutput(VIDEO_OUTPUT)
    
    # Initialize the tracker
    tracker = CentroidTracker()

    print(f"\nTracking person (Class ID {TARGET_CLASS_ID}) with pre-defined Track ID {TARGET_TRACK_ID}...\n")
    
    while output.IsStreaming():
        # Capture the image
        img = input.Capture()

        # Perform detection
        detections = net.Detect(img, overlay="box,labels,conf")
        
        # Process detections for the tracker
        current_centroids = []
        detection_map = {} # Map centroid to its full Detection object for drawing

        for detection in detections:
            if detection.ClassID == TARGET_CLASS_ID:
                # The 'Center' attribute is already a tuple (x, y)
                center_x, center_y = detection.Center[0], detection.Center[1]
                centroid = (center_x, center_y)
                current_centroids.append(centroid)
                
                # Store the detection object to be used later for drawing
                detection_map[centroid] = detection

        # Update the tracker and get persistent IDs for the current centroids
        tracked_objects = tracker.update(current_centroids)

        # --- Visualize and Output Data ---
        for track_id, centroid in tracked_objects.items():
            # Get the original detection object associated with this centroid (if it exists in this frame)
            # Note: CentroidTracker returns the last known position for 'disappeared' objects too.
            if tuple(centroid) in detection_map:
                detection = detection_map[tuple(centroid)]
                
                # --- 1. Output Center Coordinates for the TARGET ID ---
                if track_id == TARGET_TRACK_ID:
                    print(f"ID {track_id} Center: ({int(centroid[0])}, {int(centroid[1])})")

                    # --- 2. Visualization (Drawing) ---
                    # To draw on the image buffer, we must use OpenCV/Numpy operations after mapping it.
                    # Map the CUDA image buffer to a numpy array for OpenCV operations
                    # This step is resource-intensive but necessary for custom drawing logic
                    numpy_img = jetson.utils.cudaToNumpy(img)
                    
                    # Define color for the target (e.g., bright red)
                    color = (0, 0, 255) # BGR format
                    
                    # Draw a highlighted circle at the center
                    cv2.circle(numpy_img, (int(centroid[0]), int(centroid[1])), 8, color, -1)
                    
                    # Add custom text for the ID and Center
                    text_id = f"ID: {track_id}"
                    text_center = f"({int(centroid[0])}, {int(centroid[1])})"

                    # Convert back to CUDA buffer and render (this is handled by the Jetson Utils pipeline)
                    # We render the NumPy image with the custom drawings
                    img = jetson.utils.numpyToCUDA(numpy_img)

        # Render the final image with Jetson Utils' overlay and our custom drawings
        output.Render(img)

        # Update the status text with FPS
        output.SetStatus(f"Object Tracking | Network {net.GetNetworkFPS():.1f} FPS")

    # The tracker is simple and handles its own cleanup when the script exits
    print("\nTracking stopped.")

if __name__ == "__main__":
    import cv2 # Import here to ensure it's available only if the script runs
    run_jetson_tracking()

