import struct

def float_to_registers(value: float) -> tuple:
    """Convert float to two 16-bit registers (big-endian)"""
    packed = struct.pack('>f', value)
    return (
        struct.unpack('>H', packed[2:4])[0],  # Lower word
        struct.unpack('>H', packed[0:2])[0]   # Higher word
    )

def registers_to_float(registers: tuple) -> float:
    """Convert two 16-bit registers to float (big-endian)"""
    if len(registers) != 2:
        raise ValueError("Need exactly 2 registers for 32-bit float")
    packed = struct.pack('>HH', registers[1], registers[0])
    return struct.unpack('>f', packed)[0]
