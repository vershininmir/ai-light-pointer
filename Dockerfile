FROM python:3.10-slim

# Устанавливаем зависимости Python
WORKDIR /app
COPY requirements.txt .
# Установка pySerial и других системных зависимостей, если необходимо
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY dmx_controller.py .

# Устанавливаем переменные окружения для Python
ENV PYTHONUNBUFFERED 1

# Запуск будет осуществляться через docker-compose
# ENTRYPOINT ["python3", "dmx_controller.py"]

