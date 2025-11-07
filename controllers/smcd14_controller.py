# controllers/smcd14_controller.py
import asyncio
import logging
import struct
import time
from threading import Event, Lock
from contextlib import nullcontext

from pymodbus.client import ModbusTcpClient
from typing import Optional
from utils.speed import adjust_axis_speed

# Quiet noisy auto-reconnect warnings from pymodbus
logging.getLogger("pymodbus").setLevel(logging.ERROR)

# ----------------------------------------------------------------------
# Register Addresses (SMCD14 manual references)
# ----------------------------------------------------------------------
MOVE_TYPE_ADDR       = 0
TARGET_POS_ADDR      = 2
TARGET_SPEED_ADDR    = 8
START_REQ_ADDR       = 15
MOTOR_ON_ADDR        = 14
STATUS_ADDR          = 17
ACTUAL_POS_ADDR      = 18
ERROR_CODE_ADDR      = 20
STOP_REQ_ADDR        = 16
CLEAR_REQ_ADDR       = 22
BACKLASH_ADDR        = 72

# ----------------------------------------------------------------------
# Motion constraints
# ----------------------------------------------------------------------
EPSILON = 2e-3  # Positional tolerance in millimeters (+/- 2 microns)
RUNNING_BIT_TIMEOUT = 2.0  # seconds to wait for running bit to assert

# ----------------------------------------------------------------------
# Custom Exceptions
# ----------------------------------------------------------------------


class MotionNeverStartedError(RuntimeError):
    """Raised when a move command fails to trigger motion."""

    pass

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
        # Serialize pulses to the START_REQ register so concurrent
        # move commands do not overlap the 0→1→0 cycle.
        self._start_lock = Lock()
        self._last_speed = None

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

    def move_absolute(self, position: float, speed: float) -> None:
        self._check_connection()
        with self._lock:
            res = self.client.write_register(address=MOVE_TYPE_ADDR, value=1, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to set move type to absolute.")
            pos_regs = float_to_registers(position)
            axis_speed = adjust_axis_speed(abs(speed))
            speed_regs = float_to_registers(axis_speed)
            res = self.client.write_registers(address=TARGET_POS_ADDR, values=pos_regs, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to write target position.")
            res = self.client.write_registers(address=TARGET_SPEED_ADDR, values=speed_regs, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to write target speed.")
            self._pulse_start_req()
            raw = (
                f"{MOVE_TYPE_ADDR}=1; {TARGET_POS_ADDR}={pos_regs};"
                f" {TARGET_SPEED_ADDR}={speed_regs}; {START_REQ_ADDR}=1->0"
            )
            self._last_speed = axis_speed
            desc = f"Move to {position} mm @ {axis_speed} mm/s"
            self._log("move_absolute", desc, raw)

    def move_relative(self, distance: float, speed: float) -> None:
        self._check_connection()
        with self._lock:
            res = self.client.write_register(address=MOVE_TYPE_ADDR, value=2, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to set move type to relative.")
            dist_regs = float_to_registers(distance)
            axis_speed = adjust_axis_speed(abs(speed))
            speed_regs  = float_to_registers(axis_speed)
            res = self.client.write_registers(address=TARGET_POS_ADDR, values=dist_regs, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to write relative distance.")
            res = self.client.write_registers(address=TARGET_SPEED_ADDR, values=speed_regs, slave=self.slave_id)
            if res.isError():
                raise RuntimeError("Failed to write target speed.")
            self._pulse_start_req()
            raw = (
                f"{MOVE_TYPE_ADDR}=2; {TARGET_POS_ADDR}={dist_regs};"
                f" {TARGET_SPEED_ADDR}={speed_regs}; {START_REQ_ADDR}=1->0"
            )
            desc = f"Move by {distance} mm @ {axis_speed} mm/s"
            self._log("move_relative", desc, raw)

    def emergency_stop(self) -> None:
        self._check_connection()
        with self._lock:
            self._pulse_register(STOP_REQ_ADDR)
            self._log(
                "emergency_stop",
                "Emergency stop",
                f"{STOP_REQ_ADDR}=1->0",
            )

    def clear_error(self) -> None:
        self._check_connection()
        with self._lock:
            self._pulse_register(CLEAR_REQ_ADDR)
            self._log(
                "clear_error",
                "Clear error",
                f"{CLEAR_REQ_ADDR}=1->0",
            )

    def wait_until_in_position(
        self,
        timeout: float = 15.0,
        target: Optional[float] = None,
        pause_event: Optional[Event] = None,
    ) -> Optional[bool]:
        self._check_connection()
        last_change = time.time()
        motion_started = False
        running_deadline = time.time() + RUNNING_BIT_TIMEOUT
        try:
            last_pos = self.read_position()
        except Exception:
            last_pos = None
        paused = False

        while True:
            status_val = self._read_status()
            running = bool(status_val & 1)
            in_pos = bool(status_val & 16)
            try:
                curr_pos = self.read_position()
            except Exception:
                curr_pos = None

            if (
                target is not None
                and curr_pos is not None
                and abs(curr_pos - target) <= EPSILON
                and in_pos
            ):
                return True

            if pause_event is not None and not pause_event.is_set():
                if not paused:
                    try:
                        self.emergency_stop()
                    except Exception:
                        pass
                    paused = True
                if not running:
                    return None
                time.sleep(0.05)
                continue

            if running:
                motion_started = True
                last_change = time.time()

            if (
                not motion_started
                and not running
                and in_pos
                and time.time() > running_deadline
            ):
                # Record diagnostic information before raising so calling
                # code can see the controller state that caused the failure.
                err = self.read_error_code()
                self._log(
                    "error",
                    f"Motion never started (err={err}, status={status_val})",
                    f"{STATUS_ADDR}->{status_val}; {ERROR_CODE_ADDR}->{err}",
                )
                raise MotionNeverStartedError(
                    f"Motion never started (err={err}, status={status_val})"
                )

            if (
                curr_pos is not None
                and (last_pos is None or abs(curr_pos - last_pos) > EPSILON)
            ):
                motion_started = True
                last_pos = curr_pos
                last_change = time.time()

            if motion_started and in_pos:
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
    def _pulse_register(self, address: int, lock: Optional[Lock] = None) -> None:
        """Pulse a register (0→1→0) and wait until it clears."""
        self._check_connection()
        ctx = lock if lock is not None else nullcontext()
        with ctx:
            res = self.client.write_register(address=address, value=1, slave=self.slave_id)
            if res.isError():
                raise RuntimeError(f"Failed to set register {address}.")
            # Allow time for the controller to latch the request
            time.sleep(0.05)
            res = self.client.write_register(address=address, value=0, slave=self.slave_id)
            if res.isError():
                raise RuntimeError(f"Failed to reset register {address}.")
            deadline = time.time() + 1.0
            while True:
                res = self.client.read_holding_registers(address=address, count=1, slave=self.slave_id)
                if res.isError():
                    raise RuntimeError(f"Failed to read register {address}.")
                if res.registers[0] == 0:
                    break
                if time.time() > deadline:
                    raise RuntimeError(f"Register {address} did not clear.")
                time.sleep(0.01)

    def _pulse_start_req(self) -> None:
        """Issue a start request pulse using the dedicated lock."""
        self._pulse_register(START_REQ_ADDR, lock=self._start_lock)

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
