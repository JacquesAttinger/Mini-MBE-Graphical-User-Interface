# controllers/smcd14_controller.py
import asyncio
import logging
import struct
import time
from threading import Lock

import math

from pymodbus.client import ModbusTcpClient
from typing import Optional

# Quiet noisy auto-reconnect warnings from pymodbus
logging.getLogger("pymodbus").setLevel(logging.ERROR)

# ----------------------------------------------------------------------
# Register Addresses (SMCD14 manual references)
# ----------------------------------------------------------------------
MOVE_TYPE_ADDR       = 0
TARGET_POS_ADDR      = 2
TARGET_VEL_ADDR      = 8
START_REQ_ADDR       = 15
MOTOR_ON_ADDR        = 14
STATUS_ADDR          = 17
ACTUAL_POS_ADDR      = 18
ERROR_CODE_ADDR      = 20
STOP_REQ_ADDR        = 16
CLEAR_REQ_ADDR       = 22
BACKLASH_ADDR        = 72

# ----------------------------------------------------------------------
# Physical Velocity Constraints
# ----------------------------------------------------------------------
MIN_AXIS_VELOCITY = 1e-4  # mm/s
MAX_AXIS_VELOCITY = 1.0    # mm/s
VELOCITY_THRESHOLD = 5e-5  # Threshold for rounding to zero
EPSILON = 1e-4  # Positional tolerance in millimeters

# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------
def float_to_registers(value: float) -> list:
    """
    Convert a float into two 16-bit registers (lower word first).
    """
    packed = struct.pack('>f', value)  # Big-endian float
    reg_hi = struct.unpack('>H', packed[0:2])[0]
    reg_lo = struct.unpack('>H', packed[2:4])[0]
    return [reg_lo, reg_hi]

def registers_to_float(regs: list) -> float:
    """
    Convert two 16-bit registers into a float.
    Expects regs[0] = lower 16 bits, regs[1] = higher 16 bits.
    """
    if len(regs) != 2:
        raise ValueError("Expected exactly two registers for a 32-bit float.")
    packed = struct.pack('>HH', regs[1], regs[0])
    return struct.unpack('>f', packed)[0]

def validate_velocity(velocity):
        """Ensure the requested velocity is physically achievable."""
        if velocity < MIN_AXIS_VELOCITY:
            raise ValueError(f"Velocity too slow (min: {MIN_AXIS_VELOCITY} mm/s)")
        
        # Theoretical max: sqrt(3) * MAX_AXIS_VELOCITY when all 3 axes move at max speed
        theoretical_max = math.sqrt(3) * MAX_AXIS_VELOCITY
        if velocity > theoretical_max:
            raise ValueError(
                f"Requested velocity ({velocity} mm/s) exceeds maximum possible ({theoretical_max:.3f} mm/s) "
                f"for diagonal moves (all axes at {MAX_AXIS_VELOCITY} mm/s)"
            )
    
def adjust_axis_velocity(v):
    """Adjust individual axis velocity according to constraints"""
    if abs(v) < VELOCITY_THRESHOLD:
        return 0
    elif abs(v) < MIN_AXIS_VELOCITY:
        return math.copysign(MIN_AXIS_VELOCITY, v)
    elif abs(v) > MAX_AXIS_VELOCITY:
        return math.copysign(MAX_AXIS_VELOCITY, v)
    return v

def calculate_velocity_components(start_pos, end_pos, total_velocity):
    """
    Calculate velocity components for each axis with physical constraints
    """
    # Validate total velocity first
    validate_velocity(total_velocity)
    
    dx = end_pos[0] - start_pos[0]
    dy = end_pos[1] - start_pos[1]
    dz = end_pos[2] - start_pos[2]
    
    distance = math.sqrt(dx**2 + dy**2 + dz**2)
    if distance == 0:
        return (0, 0, 0)
        
    # Calculate direction unit vector
    ux = dx / distance
    uy = dy / distance
    uz = dz / distance
    
    # Scale by total velocity and apply constraints
    vx = adjust_axis_velocity(ux * total_velocity)
    vy = adjust_axis_velocity(uy * total_velocity)
    vz = adjust_axis_velocity(uz * total_velocity)
    
    # Re-normalize if any components were clamped
    actual_velocity = math.sqrt(vx**2 + vy**2 + vz**2)
    if actual_velocity > 0 and actual_velocity < total_velocity:
        scale = total_velocity / actual_velocity
        vx = adjust_axis_velocity(vx * scale)
        vy = adjust_axis_velocity(vy * scale)
        vz = adjust_axis_velocity(vz * scale)
    
    return (vx, vy, vz)

# ----------------------------------------------------------------------
# Main Controller Class
# ----------------------------------------------------------------------
class ManipulatorController:
    """Manages Modbus TCP communication with an SMCD14-based manipulator axis."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        timeout: int = 10,
        slave_id: int = 1,
        axis: str = "",
        logger=None,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.slave_id = slave_id
        self.axis = axis
        self.logger = logger

        self.client = None
        self.loop = None  # asyncio event loop for PyModbus
        self._lock = Lock()

    def _log(self, action: str, description: str, raw: str) -> None:
        if self.logger:
            self.logger(self.axis, action, description, raw)

    def connect(self) -> bool:
        """
        Establishes the Modbus TCP connection.
        """
        with self._lock:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            client = ModbusTcpClient(host=self.host, port=self.port, timeout=self.timeout)
            result = client.connect()
            if result:
                self.loop = loop
                self.client = client
            else:
                # Clean up resources so we don't leave a half-open client
                client.close()
                loop.run_until_complete(asyncio.sleep(0))
                loop.close()
        return result

    def disconnect(self) -> None:
        """
        Closes the Modbus TCP connection and cleans up the event loop.
        """
        with self._lock:
            if self.client:
                self.client.close()
            if self.loop:
                self.loop.run_until_complete(asyncio.sleep(0))
                self.loop.close()
            self.client = None
            self.loop = None

    def _check_connection(self):
        if not self.client:
            raise RuntimeError("Manipulator is not connected.")

    def motor_on(self) -> None:
        self._check_connection()
        with self._lock:
            res = self.client.write_register(address=MOTOR_ON_ADDR, value=1, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to turn motor on.")
            self._log(
                "motor_on",
                "Motor ON",
                f"{MOTOR_ON_ADDR}=1",
            )

    def motor_off(self) -> None:
        self._check_connection()
        with self._lock:
            res = self.client.write_register(address=MOTOR_ON_ADDR, value=0, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to turn motor off.")
            self._log(
                "motor_off",
                "Motor OFF",
                f"{MOTOR_ON_ADDR}=0",
            )

    def move_absolute(self, position: float, velocity: float) -> None:
        self._check_connection()
        with self._lock:
            res = self.client.write_register(address=MOVE_TYPE_ADDR, value=1, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to set move type to absolute.")
            pos_regs = float_to_registers(position)
            vel_regs = float_to_registers(velocity)
            res = self.client.write_registers(address=TARGET_POS_ADDR, values=pos_regs, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to write target position.")
            res = self.client.write_registers(address=TARGET_VEL_ADDR, values=vel_regs, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to write target velocity.")
            res = self.client.write_register(address=START_REQ_ADDR, value=1, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to send start request.")
            raw = (
                f"{MOVE_TYPE_ADDR}=1; {TARGET_POS_ADDR}={pos_regs};"
                f" {TARGET_VEL_ADDR}={vel_regs}; {START_REQ_ADDR}=1"
            )
            desc = f"Move to {position} mm @ {velocity} mm/s"
            self._log("move_absolute", desc, raw)

    def move_relative(self, distance: float, velocity: float) -> None:
        self._check_connection()
        with self._lock:
            res = self.client.write_register(address=MOVE_TYPE_ADDR, value=2, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to set move type to relative.")
            dist_regs = float_to_registers(distance)
            vel_regs  = float_to_registers(velocity)
            res = self.client.write_registers(address=TARGET_POS_ADDR, values=dist_regs, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to write relative distance.")
            res = self.client.write_registers(address=TARGET_VEL_ADDR, values=vel_regs, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to write target velocity.")
            res = self.client.write_register(address=START_REQ_ADDR, value=1, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to send start request.")
            raw = (
                f"{MOVE_TYPE_ADDR}=2; {TARGET_POS_ADDR}={dist_regs};"
                f" {TARGET_VEL_ADDR}={vel_regs}; {START_REQ_ADDR}=1"
            )
            desc = f"Move by {distance} mm @ {velocity} mm/s"
            self._log("move_relative", desc, raw)

    def emergency_stop(self) -> None:
        self._check_connection()
        with self._lock:
            res = self.client.write_register(address=STOP_REQ_ADDR, value=1, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Emergency stop failed.")
            self._log(
                "emergency_stop",
                "Emergency stop",
                f"{STOP_REQ_ADDR}=1",
            )

    def clear_error(self) -> None:
        self._check_connection()
        with self._lock:
            res = self.client.write_register(address=CLEAR_REQ_ADDR, value=1, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to clear error (step 1).")
            time.sleep(0.1)
            res = self.client.write_register(address=CLEAR_REQ_ADDR, value=0, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to clear error (step 2).")
            self._log(
                "clear_error",
                "Clear error",
                f"{CLEAR_REQ_ADDR}=1->0",
            )

    def wait_until_in_position(self, timeout: float = 15.0, target: Optional[float] = None) -> bool:
        self._check_connection()
        last_change = time.time()
        motion_started = False
        try:
            last_pos = self.read_position()
        except Exception:
            last_pos = None

        while True:
            status_val = self._read_status()
            try:
                curr_pos = self.read_position()
            except Exception:
                curr_pos = None

            if (
                target is not None
                and curr_pos is not None
                and abs(curr_pos - target) <= EPSILON
                and status_val & 16
            ):
                return True

            if not motion_started and not (status_val & 16):
                motion_started = True
                last_change = time.time()

            if (
                curr_pos is not None
                and (last_pos is None or abs(curr_pos - last_pos) > EPSILON)
            ):
                motion_started = True
                last_pos = curr_pos
                last_change = time.time()

            if motion_started and status_val & 16:
                if target is None or curr_pos is None or abs(curr_pos - target) <= EPSILON:
                    return True

            if (time.time() - last_change) >= timeout:
                if target is not None and curr_pos is not None and abs(curr_pos - target) <= EPSILON:
                    return True
                return False
            time.sleep(0.5)

    def read_position(self) -> float:
        self._check_connection()
        regs = self._read_registers(address=ACTUAL_POS_ADDR, count=2)
        pos = registers_to_float(regs)
        self._log(
            "read_position",
            f"Position {pos}",
            f"{ACTUAL_POS_ADDR}->{regs}",
        )
        return pos

    def get_position(self) -> float:
        """Compatibility wrapper for older callers."""
        return self.read_position()

    def read_error_code(self) -> int:
        self._check_connection()
        regs = self._read_registers(address=ERROR_CODE_ADDR, count=1)
        code = regs[0]
        self._log("read_error_code", f"Error {code}", f"{ERROR_CODE_ADDR}->{regs}")
        return code

    def set_backlash(self, value: float) -> None:
        self._check_connection()
        with self._lock:
            backlash_regs = float_to_registers(value)
            res = self.client.write_registers(address=BACKLASH_ADDR, values=backlash_regs, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to set backlash parameter.")
            self._log(
                "set_backlash",
                f"Backlash {value}",
                f"{BACKLASH_ADDR}={backlash_regs}",
            )

    def get_backlash(self) -> float:
        self._check_connection()
        regs = self._read_registers(address=BACKLASH_ADDR, count=2)
        val = registers_to_float(regs)
        self._log("get_backlash", f"Backlash {val}", f"{BACKLASH_ADDR}->{regs}")
        return val

    # Internal helper methods
    def _read_status(self) -> int:
        regs = self._read_registers(address=STATUS_ADDR, count=1)
        return regs[0]

    def _read_registers(self, address: int, count: int) -> list:
        self._check_connection()
        with self._lock:
            res = self.client.read_holding_registers(address=address, count=count, slave=self.slave_id)
            if res.isError():
                raise RuntimeError(f"Failed to read registers at address {address}.")
            return res.registers
