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

# ser.write(b"GET Supr\r")
# response = ser.readline().decode().strip()
# print(f"Suppressor Response: {response}")
# ser.close()

# ser.write(b"SET Supr off\r")
# ser.close()