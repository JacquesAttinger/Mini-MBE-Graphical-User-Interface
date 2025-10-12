# Increase emission current until a desired flux is achieved

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

target_flux = 4.0e-10
epsilon = 2e-11  # Acceptable error margin for flux

# PID parameters
min_step = 0.1
max_step = 0.8
length_of_stable_readings = 5

# correct_attempts_counter = 0
last_flux_values = []
while True:
    # if correct_attempts_counter >= 3:
    #     print("Flux stabilized within acceptable range. Exiting loop.")
    #     break
    time.sleep(3)
    if len(last_flux_values) >= length_of_stable_readings:
        mean_flux = sum(last_flux_values[-length_of_stable_readings:]) / length_of_stable_readings
        if abs(mean_flux - target_flux) < epsilon:
            print(f"Flux stabilized within acceptable range over last {length_of_stable_readings} readings. Exiting loop.")
            break


    ser.write(b"GET Flux\r")
    response = ser.readline().decode().strip()
    print(f"Current Flux: {response}")
    try:
        current_flux = float(response)
    except ValueError:
        print("Invalid flux value received. Retrying...")
        time.sleep(2)
        continue

    if abs(current_flux - target_flux) < epsilon:
        print("Target flux achieved.")
        # correct_attempts_counter += 1
        last_flux_values.append(current_flux)
        continue
    
    # Determine what sized step to take for Emission current adjustmentt
    flux_error = abs(current_flux - target_flux)
    normalized_error = min(flux_error / (10 * epsilon), 1.0)
    dynamic_step = round(min_step + (max_step - min_step) * normalized_error, 1)
    print(f'Dynamic step size for Emission current adjustment: {dynamic_step}')

    ser.write(b"GET Emis\r")
    response = ser.readline().decode().strip()
    print(f"Current Emission Current: {response}")
    try:
        current_emission = round(float(response), 1)
        print(f"Rounded Current Emission Current: {current_emission}")
    except ValueError:
        print("Invalid emission current value received. Retrying...")
        time.sleep(2)
        continue

    if current_flux < target_flux:
        new_emission = round(current_emission + dynamic_step, 1)
        set_emission_command = f"SET Emis {new_emission}\r"
        ser.write(set_emission_command.encode())
        print(f"Increasing emission current by setting new Emission Current to: {new_emission}")
        continue

    if current_flux > target_flux:
        new_emission = round(current_emission - dynamic_step, 1)
        set_emission_command = f"SET Emis {new_emission}\r"
        ser.write(set_emission_command.encode())
        print(f"Decreasing emission current by setting new Emission Current to: {new_emission}")
        continue




ser.close()