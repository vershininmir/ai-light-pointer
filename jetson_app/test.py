#!/usr/bin/env python3
import serial
import time

def test_enttec():
    print("🧪 Тест Enttec Open DMX")
    
    try:
        # Пробуем разные порты
        ports = ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0']
        
        for port in ports:
            print(f"\nПопытка подключения к {port}...")
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=250000,
                    bytesize=8,
                    parity='N',
                    stopbits=2,
                    timeout=1
                )
                
                print(f"✅ Порт {port} открыт!")
                
                # Тестовая последовательность
                for i in [0, 128, 255, 0]:
                    print(f"Отправка значения: {i}")
                    
                    # BREAK
                    ser.send_break(duration=0.0001)
                    time.sleep(0.00001)
                    
                    # Данные: стартовый код + 512 байт
                    data = bytes([0] + [i]*512)
                    ser.write(data)
                    ser.flush()
                    
                    time.sleep(1)
                
                ser.close()
                return True
                
            except Exception as e:
                print(f"❌ {port}: {e}")
        
        return False
        
    except Exception as e:
        print(f"❌ Общая ошибка: {e}")
        return False

if __name__ == "__main__":
    if test_enttec():
        print("\n✅ Тест пройден успешно!")
    else:
        print("\n❌ Тест не пройден")
