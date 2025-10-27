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
    # Get flux
    # Get emiscon
    # Get voltage
    # Get filament current
    # Get emission current
    
def interlock(ser):
    ser.write(b"GET Interlock\r")
    response = ser.readline().decode().strip()
    print(f"Interlock Status: {response}")

def update_displays(ser):
    ser.write(b"UPDATE DISPLAYS\r")