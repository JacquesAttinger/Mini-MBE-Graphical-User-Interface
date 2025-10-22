

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

def set_filament_current(current):
    # current = str(current)
    set_filament_current_command = f"SET Fil {current}\r"
    ser.write(set_filament_current_command.encode())

filament_current = 2.7
    
set_filament_current(filament_current)

ser.close()