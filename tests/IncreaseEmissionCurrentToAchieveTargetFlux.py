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

target_flux = 9.5e-10
epsilon = 2e-11  # Acceptable error margin for flux

# PID parameters
min_step = 0.1
max_step = 0.8
length_of_stable_readings = 10

# correct_attempts_counter = 0
last_flux_values = []
while True:
    # if correct_attempts_counter >= 3:
    #     print("Flux stabilized within acceptable range. Exiting loop.")
    #     break
    time.sleep(0.5)
    ser.write(b"GET Flux\r")
    response = ser.readline().decode().strip()
    print(f"Current Flux: {response}")
    try:
        current_flux = float(response)
    except ValueError:
        print("Invalid flux value received. Retrying...")
        time.sleep(2)
        continue

    if len(last_flux_values) < length_of_stable_readings:
        print("Appending flux value for stability check.")
        last_flux_values.append(current_flux)
        continue 

    last_flux_values.append(current_flux)

    if len(last_flux_values) % length_of_stable_readings == 0:
        mean_flux = sum(last_flux_values[-length_of_stable_readings:]) / length_of_stable_readings
        print(f"Mean Flux over last {length_of_stable_readings} readings: {mean_flux}")
        if abs(mean_flux - target_flux) < epsilon:
            print(f"Flux stabilized within acceptable range over last {length_of_stable_readings} readings. Exiting loop.")
            break


    
    
        # Determine what sized step to take for Emission current adjustmentt
        flux_error = abs(mean_flux - target_flux)
        normalized_error = min(flux_error / (40 * epsilon), 1.0)
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

        if mean_flux < target_flux:
            new_emission = round(current_emission + dynamic_step, 1)
            set_emission_command = f"SET Emis {new_emission}\r"
            ser.write(set_emission_command.encode())
            print(f"Increasing emission current by setting new Emission Current to: {new_emission}")
            sleep_time = 10  # Scale sleep time with step size
            time.sleep(sleep_time)
            continue

        if current_flux > target_flux:
            new_emission = round(current_emission - dynamic_step, 1)
            set_emission_command = f"SET Emis {new_emission}\r"
            ser.write(set_emission_command.encode())
            print(f"Decreasing emission current by setting new Emission Current to: {new_emission}")
            sleep_time = 10  # Scale sleep time with step size
            time.sleep(sleep_time)
            continue




ser.close()