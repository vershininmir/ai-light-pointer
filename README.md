# ai-light-pointer

Smart Light Tracker — NVIDIA Jetson (jetson-inference) detects people in FullHD stream and sends coordinates to DMX light controller.

Structure:
- `jetson_app/` — detection app (Python, runs in Docker on Jetson).
- `light_controller/` — DMX controller (Python).
- `docs/` — architecture and protocol.

See `/docs` for setup and protocol.
