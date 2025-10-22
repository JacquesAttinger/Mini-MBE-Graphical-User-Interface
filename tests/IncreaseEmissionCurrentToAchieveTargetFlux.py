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

# PID-like parameters
min_step = 0.1
max_step = 0.8
buffer_size = 10  # Number of readings to average
required_stable_cycles = 5  # How many good averages before stopping

flux_buffer = []
stable_cycle_count = 0

def get_average_flux(buffer):
    return sum(buffer) / len(buffer) if buffer else 0

while True:
    time.sleep(3)

    # Get new flux reading
    ser.write(b"GET Flux\r")
    response = ser.readline().decode().strip()
    print(f"Raw Flux Reading: {response}")

    try:
        current_flux = float(response)
    except ValueError:
        print("Invalid flux value received. Retrying...")
        time.sleep(2)
        continue

    # Add to buffer and keep only the latest N readings
    flux_buffer.append(current_flux)
    if len(flux_buffer) > buffer_size:
        flux_buffer.pop(0)

    # Wait until buffer is full to make meaningful decisions
    if len(flux_buffer) < buffer_size:
        continue

    avg_flux = get_average_flux(flux_buffer)
    print(f"Averaged Flux over last {buffer_size} readings: {avg_flux:.2e}")

    if abs(avg_flux - target_flux) < epsilon:
        stable_cycle_count += 1
        print(f"Stable cycle count: {stable_cycle_count}/{required_stable_cycles}")
        if stable_cycle_count >= required_stable_cycles:
            print("Flux stabilized within acceptable range. Exiting loop.")
            break
        else:
            continue
    else:
        stable_cycle_count = 0  # Reset if out of range

    # Determine step size for emission current adjustment
    flux_error = abs(avg_flux - target_flux)
    normalized_error = min(flux_error / (10 * epsilon), 1.0)
    dynamic_step = round(min_step + (max_step - min_step) * normalized_error, 1)
    print(f'Dynamic step size for Emission current adjustment: {dynamic_step}')

    # Read current emission current
    ser.write(b"GET Emis\r")
    response = ser.readline().decode().strip()
    print(f"Current Emission Current: {response}")

    try:
        current_emission = round(float(response), 1)
    except ValueError:
        print("Invalid emission current value received. Retrying...")
        time.sleep(2)
        continue

    # Adjust emission based on average flux
    if avg_flux < target_flux:
        new_emission = round(current_emission + dynamic_step, 1)
        print(f"Increasing emission current to: {new_emission}")
    else:
        new_emission = round(current_emission - dynamic_step, 1)
        print(f"Decreasing emission current to: {new_emission}")

    set_emission_command = f"SET Emis {new_emission}\r"
    ser.write(set_emission_command.encode())

ser.close()
