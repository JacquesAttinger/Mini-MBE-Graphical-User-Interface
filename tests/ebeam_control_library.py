# E-beam control library
import serial
import time

def open_serial_connection(port="COM5", baudrate=57600, timeout=1):
    ser = serial.Serial(
        port=port,       
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        xonxoff=True,   
        timeout=timeout
    )
    return ser

def set_emission_current(ser, current):
    command = f"SET Emis {current} \r"
    ser.write(command.encode())

def set_filament_current(ser, current):
    command = f"SET Fil {current}\r"
    ser.write(command.encode())

def set_high_voltage(ser, voltage):
    command = f"SET HV {voltage}\r"
    ser.write(command.encode())

def get_vitals(ser):
    ser.write(b"GET Emiscon\r")
    emiscon_response = ser.readline().decode().strip()
    print(f"Emiscon Response: {emiscon_response}")

    ser.write(b"GET Fluxmode\r")
    fluxmode_response = ser.readline().decode().strip()
    print(f"Fluxmode Response: {fluxmode_response}")

    ser.write(b"GET Automodus\r")
    automodus_response = ser.readline().decode().strip()
    print(f"Automodus Response: {automodus_response}")

    ser.write(b"GET Deposition\r")
    deposition_response = ser.readline().decode().strip()
    print(f"Desposition Response: {deposition_response}")

    ser.write(b"GET UpSpeed\r")
    upspeed_response = ser.readline().decode().strip()
    print(f"Upspeed Response: {upspeed_response}")

    ser.write(b"GET Flux\r")
    flux_response = ser.readline().decode().strip()
    print(f"Flux Response: {flux_response}")

    ser.write(b"GET Emiscon\r")
    emiscon2_response = ser.readline().decode().strip()
    print(f"Emiscon Response: {emiscon2_response}")

    ser.write(b"GET HV\r")
    hv_response = ser.readline().decode().strip()
    print(f"High Voltage Response: {hv_response}")

    ser.write(b"GET Fil\r")
    fil_response = ser.readline().decode().strip()
    print(f"Filament Current Response: {fil_response}")

    ser.write(b"GET Emis\r")
    emis_response = ser.readline().decode().strip()
    print(f"Emission Current Response: {emis_response}")

    return {
        "emiscon_response": emiscon_response,
        "fluxmode_response": fluxmode_response,
        "automodus_response": automodus_response,
        "deposition_response": deposition_response,
        "upspeed_response": upspeed_response,
        "flux_response": flux_response,
        "emiscon2_response": emiscon2_response,
        "hv_response": hv_response,
        "fil_response": fil_response,
        "emis_response": emis_response,
    }

    
def interlock(ser):
    ser.write(b"GET Interlock\r")
    response = ser.readline().decode().strip()
    print(f"Interlock Status: {response}")

def update_displays(ser):
    ser.write(b"UPDATE DISPLAYS\r")

ser = open_serial_connection()
set_high_voltage(ser, 0)