import serial
import time
import ast

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
target_HV = 2000 # Volts
target_filament_current = 1.5 # Amperes
# target_emission_current = 0.1 # milli_Amperes
flux_setpoint = 200e-9 # Amperes
get_hv_command = f"GET HV\r"
get_fil_command = f"GET Fil\r"

# Set HV (High voltage) to 2000
set_HV_command = f"SET HV {target_HV}\r"
ser.write(set_HV_command.encode()) # Write the command in bytes


time.sleep(6)

# Set filament current setpoint to 1.5A
def set_filament_current(current):
    # current = str(current)
    set_filament_current_command = f"SET Fil {current}\r"
    ser.write(set_filament_current_command.encode())

filament_current = 0.1
set_filament_current(filament_current)
time.sleep(3)
# Ramp up by 0.1 every second


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

# time.sleep(300) # Sit for five minutes

# Ramp up to two amps 

# Wait two minutes

# # Switch to emission control
# ser.write(b"SET Emiscon on\r")

# # Start deposition
# ser.write(b"SET Deposition on\r") # Start deposition

# # Set upspeed and downspeed for PID regulation (integer from 1 to 1000)
# ser.write(b"SET UpSpeed 5\r")
# ser.write(b"SET DownSpeed 5\r")

# # Maintain flux
# set_flux_setpoint_command = f"SET FL-SP {flux_setpoint}\r"
# ser.write(b"Set Fluxmode on\r") # Set this so you don't use the 0 to 10 volts automodus
# ser.write(set_flux_setpoint_command.encode()) # Set flux setpoint
# ser.write(b"SET Automodus on\r") # Activates flux regulation

# time.sleep(300) # Deposition time in seconds
# # Turn off emission control
# ser.write(b"SET Emiscon off\r")

# # End deposition
# ser.write(b"SET Deposition off\r") # End deposition



ser.close()