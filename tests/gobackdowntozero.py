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


# Parameters
target_HV = 0 # Volts
target_filament_current = 0.1 # Amperes
# target_emission_current = 0.1 # milli_Amperes
flux_setpoint = 200e-9 # Amperes

# Set HV (High voltage) to 2000
set_HV_command = f"SET HV {target_HV}\r"
ser.write(set_HV_command.encode()) # Write the command in bytes

time.sleep(3)

# Set filament current setpoint to 1.5A
set_filament_current_command = f"SET Fil {target_filament_current}\r"
ser.write(set_filament_current_command.encode())

time.sleep(3)



ser.close()