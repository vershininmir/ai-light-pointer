import cv2
import time

cap = cv2.VideoCapture(0)  # or /dev/video0
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

if not cap.isOpened():
    raise SystemExit("Camera not opened")

start = time.time()
frames = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break
    frames += 1
    cv2.imshow('camera', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
    if frames >= 100:
        break

end = time.time()
fps = frames / (end - start)
print(f"Captured {frames} frames, approx FPS: {fps:.2f}")
cap.release()
cv2.destroyAllWindows()
