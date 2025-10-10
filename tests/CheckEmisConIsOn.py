import serial
import time

# Open serial connection (make sure port is correct)
ser = serial.Serial(
    port="COM5",       
    baudrate=57600,
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    xonxoff=True,   
    timeout=1
)

ser.write(b"GET Emiscon\r")
response = ser.readline().decode().strip()
print(f"Emiscon Response: {response}")
time.sleep(1)
ser.write(b"GET Fluxmode\r")
response = ser.readline().decode().strip()
print(f"Fluxmode Response: {response}")
time.sleep(1)
ser.write(b"GET Automodus\r")
response = ser.readline().decode().strip()
print(f"Automodus Response: {response}")
time.sleep(1)
ser.write(b"GET Deposition\r")
response = ser.readline().decode().strip()
print(f"Desposition Response: {response}")
time.sleep(1)
ser.write(b"GET UpSpeed\r")
response = ser.readline().decode().strip()
print(f"Upspeed Response: {response}")

ser.close()