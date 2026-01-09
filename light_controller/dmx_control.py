#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import serial
import sys
import time
import threading

# ======================
# НАСТРОЙКИ
# ======================

DMX_DEVICE = "/dev/ttyUSB0"
DMX_BAUDRATE = 250000
DMX_CHANNELS = 512

FIXTURE_ADDRESS = 1
FIXTURE_CHANNELS = 11

DMX_FPS = 30

# ======================
# ИНИЦИАЛИЗАЦИЯ DMX
# ======================

try:
    ser = serial.Serial(
        port=DMX_DEVICE,
        baudrate=DMX_BAUDRATE,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_TWO,
        timeout=1
    )
except serial.SerialException as e:
    print("Ошибка открытия DMX:", e)
    sys.exit(1)

dmx_data = [0] * DMX_CHANNELS
running = True
lock = threading.Lock()

# ======================
# ОТПРАВКА DMX
# ======================

def send_dmx_frame(data):
    # Break
    ser.break_condition = True
    time.sleep(0.0001)
    ser.break_condition = False

    # Mark After Break
    time.sleep(0.000012)

    # Start code + data
    ser.write(bytes([0] + data))

def dmx_sender():
    interval = 1.0 / DMX_FPS
    while running:
        with lock:
            send_dmx_frame(dmx_data)
        time.sleep(interval)

# ======================
# ЗАПУСК DMX ПОТОКА
# ======================

thread = threading.Thread(target=dmx_sender)
thread.daemon = True
thread.start()

# ======================
# КОНСОЛЬ
# ======================

print("DMX 11CH Moving Head Controller")
print("Адрес прибора:", FIXTURE_ADDRESS)
print("Каналы: 1–11")
print("CH1/2 = PAN coarse/fine")
print("CH3/4 = TILT coarse/fine")
print("q — выход\n")

while True:
    try:
        ch = input("Канал (1-11) или q: ").strip()
        if ch.lower() == "q":
            break

        channel = int(ch)
        if not 1 <= channel <= FIXTURE_CHANNELS:
            print("Канал должен быть 1–11")
            continue

        val = input("Значение (0–255): ").strip()
        if val.lower() == "q":
            break

        value = int(val)
        if not 0 <= value <= 255:
            print("Значение должно быть 0–255")
            continue

        dmx_index = (FIXTURE_ADDRESS - 1) + (channel - 1)

        with lock:
            dmx_data[dmx_index] = value

        print("Установлено: CH{} = {}".format(channel, value))

    except ValueError:
        print("Ошибка ввода")
    except KeyboardInterrupt:
        break

# ======================
# ЗАВЕРШЕНИЕ
# ======================

running = False
thread.join()
ser.close()
print("Выход")

