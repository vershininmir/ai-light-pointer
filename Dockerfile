# базовый образ — на Jetson нужно использовать совместимый образ
FROM python:3.10-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r jetson_app/requirements.txt || true
CMD ["bash"]
