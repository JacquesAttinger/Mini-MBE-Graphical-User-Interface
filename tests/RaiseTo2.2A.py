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

target_filament_current = 2.7 # Amperes

filament_current = 1.5

# Keep ramping up current until it reaches target value
while True:
    
    # Check filament current
    # ser.write(get_fil_command.encode())
    time.sleep(1)
    # response = ser.readline().decode().strip()
    
    # If filament current > 1.5, break the while loop
    if filament_current >= target_filament_current:
        set_filament_current(target_filament_current)
        break
    else:
        filament_current = filament_current + 0.1
        set_filament_current(filament_current)

ser.close()
    