"""High level manager for multiple manipulator axes."""

import logging
import threading
import time
from typing import Dict, List, Tuple

from PySide6.QtCore import QObject, Signal

from controllers.smcd14_controller import (
    ManipulatorController,
    MotionNeverStartedError,
)
from utils.speed import adjust_axis_speed

# Default connection settings
HOST = "169.254.151.255"
PORT = 502
TIMEOUT = 10
AXIS_SLAVE_MAP = {"x": 1, "y": 2, "z": 3}

# Minimum positional delta that will trigger an actual move command.  Values
# smaller than this are treated as already "in position" to avoid waiting on
# axes that have no movement.
EPSILON = 1e-4


class ManipulatorManager(QObject):
    """Coordinate multiple :class:`ManipulatorController` instances.

    This class encapsulates controller creation, connection management and
    background monitoring.  It exposes Qt signals so GUI components can react
    to controller events without embedding control logic in the widgets.
    """

    status_updated = Signal(str)
    position_updated = Signal(str, float)
    error_occurred = Signal(str, str)
    connection_changed = Signal(str, bool)
    pattern_progress = Signal(int, float, float)  # index, percentage, remaining seconds
    pattern_completed = Signal()
    point_reached = Signal(tuple)  # emitted when move_to_point completes
    # axis, action, human readable description, raw register string
    modbus_event = Signal(str, str, str, str)

    def __init__(self,
                 host: str = HOST,
                 port: int = PORT,
                 timeout: int = TIMEOUT,
                 axis_slave_map: Dict[str, int] = AXIS_SLAVE_MAP,
                 motion_logging: bool = False):
        super().__init__()
        self._modbus_log = []
        self.controllers = {}
        self._motion_logger = logging.getLogger(__name__)
        self.motion_log_enabled = motion_logging
        for axis, slave in axis_slave_map.items():
            ctrl = ManipulatorController(
                host, port, timeout, slave, axis=axis, logger=self._log_event
            )
            self.controllers[axis] = ctrl
        self._monitoring = False
        self._monitor_thread = None
        self._pause_event = threading.Event()
        self._pause_event.set()

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------
    def connect_all(self) -> Dict[str, bool]:
        """Attempt connection to all configured axes.

        Returns a dictionary mapping axis names to a boolean connection status.
        """
        status = {}
        any_connected = False
        for axis, ctrl in self.controllers.items():
            try:
                connected = ctrl.connect()
                status[axis] = connected
                self.connection_changed.emit(axis, connected)
                if connected:
                    any_connected = True
                    self.status_updated.emit(f"{axis.upper()} axis connected")
                    try:
                        ctrl.set_backlash(0.0)
                    except Exception:
                        # Best effort: backlash configuration is optional
                        pass
            except Exception as exc:  # pragma: no cover - hardware dependent
                status[axis] = False
                self.error_occurred.emit(axis, str(exc))
        if any_connected:
            self._start_monitor()
        return status

    def disconnect_all(self):
        """Disconnect all axes and stop monitoring."""
        self._monitoring = False
        for ctrl in self.controllers.values():
            try:
                ctrl.disconnect()
            except Exception:  # pragma: no cover - best effort
                pass

    def _log_event(self, axis: str, action: str, description: str, raw: str) -> None:
        """Internal callback used by controllers to report Modbus traffic."""
        entry = {
            "time": time.time(),
            "axis": axis,
            "action": action,
            "description": description,
            "raw": raw,
        }
        self._modbus_log.append(entry)
        self.modbus_event.emit(axis, action, description, raw)

    def get_modbus_log(self) -> List[Dict[str, str]]:
        """Return a copy of all recorded Modbus events."""
        return list(self._modbus_log)

    def _run_async(self, axis: str, action, *args):
        """Execute controller actions in a background thread.

        Parameters
        ----------
        axis:
            Axis identifier used for routing errors.
        action:
            Callable receiving the controller instance and ``*args``.
            It may optionally return a status string which will be emitted
            via :attr:`status_updated`.
        *args:
            Additional arguments passed to ``action``.
        """

        def worker():
            ctrl = self.controllers[axis]
            try:
                message = action(ctrl, *args)
                if message:
                    self.status_updated.emit(message)
            except Exception as exc:  # pragma: no cover - hardware dependent
                self.error_occurred.emit(axis, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Movement commands
    # ------------------------------------------------------------------
    def move_axis(self, axis: str, position: float, speed: float):
        """Move an individual axis in a worker thread."""

        def action(ctrl, position, speed):
            try:
                current = ctrl.read_position()
            except Exception:
                current = None
            if current is not None and abs(current - position) <= EPSILON:
                return f"{axis.upper()} already at {position:.3f} mm"
            try:
                ctrl.motor_on()
            except Exception:
                pass
            axis_speed = adjust_axis_speed(abs(speed))
            ctrl.move_absolute(position, axis_speed)
            try:
                ok = ctrl.wait_until_in_position(target=position)
            except MotionNeverStartedError as exc:
                status = ctrl._read_status()
                msg = str(exc)
                self._log_event(
                    axis,
                    "error",
                    msg,
                    f"status={status}",
                )
                raise
            if not ok:
                err = ctrl.read_error_code()
                status = ctrl._read_status()
                msg = (
                    f"Failed to reach position (err={err}, status={status})"
                )
                self._log_event(
                    axis,
                    "error",
                    msg,
                    f"err={err};status={status}",
                )
                raise RuntimeError(msg)
            return f"{axis.upper()} moved to {position:.3f} mm"

        self._run_async(axis, action, position, speed)

    def emergency_stop(self, axis: str):
        """Trigger emergency stop on a specific axis."""

        def action(ctrl):
            ctrl.emergency_stop()
            return f"{axis.upper()} emergency stop executed"

        self._run_async(axis, action)

    def home_axis(self, axis: str):
        """Placeholder homing operation."""

        def action(ctrl):
            ctrl.motor_on()
            # Actual homing logic would be implemented here
            return f"{axis.upper()} homing procedure started"

        self._run_async(axis, action)
    # ------------------------------------------------------------------
    # High level composite moves
    # ------------------------------------------------------------------
    def _move_axes(
        self,
        start: Tuple[float, float, float],
        target: Tuple[float, float, float],
        speed: float,
    ) -> bool:
        """Issue move commands for axes that actually need to travel.

        Each active axis moves at the requested ``speed`` toward its target
        position.  The previous behavior scaled per-axis velocities based on the
        relative displacement of each axis which could result in extremely slow
        speeds when one axis had only a small travel component.  By using the
        same speed for all axes, no axis is artificially slowed and short moves
        no longer exceed controller timeouts.

        Returns ``True`` if all commanded axes reported they reached their
        destination. If an axis fails the corresponding error signal is emitted
        and ``False`` is returned.
        """

        deltas = [target[i] - start[i] for i in range(3)]
        distance = (deltas[0] ** 2 + deltas[1] ** 2 + deltas[2] ** 2) ** 0.5
        if distance <= EPSILON:
            self._log_event(
                "ALL",
                "info",
                f"Zero-distance move ignored start={start} target={target}",
                "",
            )
            return True

        active_axes = []
        for idx, axis in enumerate(("x", "y", "z")):
            delta = deltas[idx]
            if abs(delta) > EPSILON:
                axis_speed = adjust_axis_speed(abs(speed))
                ctrl = self.controllers[axis]
                try:
                    ctrl.motor_on()
                except Exception:
                    pass
                if self.motion_log_enabled:
                    self._motion_logger.info(
                        "t=%s axis=%s target=%.3f speed=%.3f",
                        time.time(),
                        axis,
                        target[idx],
                        axis_speed,
                    )
                ctrl.move_absolute(target[idx], axis_speed)
                if hasattr(ctrl, "_last_speed"):
                    assert (
                        abs(ctrl._last_speed - axis_speed) <= EPSILON
                    ), f"{axis} speed mismatch"
                self._log_event(
                    axis,
                    "move",
                    f"target={target[idx]} speed={axis_speed}",
                    "",
                )
                active_axes.append((axis, target[idx], axis_speed))

        for axis, pos, axis_speed in active_axes:
            ctrl = self.controllers[axis]
            try:
                ok = ctrl.wait_until_in_position(target=pos)
            except MotionNeverStartedError as exc:
                status = ctrl._read_status()
                msg = str(exc)
                self._log_event(
                    axis,
                    "error",
                    msg,
                    f"status={status}",
                )
                self.error_occurred.emit(axis, msg)
                return False
            if not ok:
                err = ctrl.read_error_code()
                status = ctrl._read_status()
                msg = (
                    f"Failed to reach position (err={err}, status={status})"
                )
                self._log_event(
                    axis,
                    "error",
                    msg,
                    f"err={err};status={status}",
                )
                self.error_occurred.emit(axis, msg)
                return False
            self._log_event(
                axis,
                "in_position",
                f"target={pos} speed={axis_speed}",
                "",
            )
        return True

    def move_to_point(self, target: Tuple[float, float, float], speed: float) -> None:
        """Move to a single 3D coordinate at the given speed."""

        def worker():
            try:
                start = (
                    self.controllers['x'].read_position(),
                    self.controllers['y'].read_position(),
                    self.controllers['z'].read_position(),
                )
            except Exception:
                start = (0.0, 0.0, 0.0)

            try:
                if self._move_axes(start, target, speed):
                    self.status_updated.emit(
                        f"Moved to ({target[0]:.3f}, {target[1]:.3f}, {target[2]:.3f})"
                    )
                    self.point_reached.emit(target)
            except Exception as exc:  # pragma: no cover - hardware dependent
                self.error_occurred.emit("PATH", str(exc))

        threading.Thread(target=worker, daemon=True).start()
        
    def pause_path(self):
        """Pause the currently executing path."""
        self._pause_event.clear()
        self.status_updated.emit("Pattern paused")

    def resume_path(self):
        """Resume a paused path."""
        self._pause_event.set()
        self.status_updated.emit("Pattern resumed")

    def execute_path(self, vertices: List[Tuple[float, float, float]], speed: float):
        """Execute a series of 3D vertices sequentially at a constant speed."""

        def worker():
            try:
                if not vertices:
                    return
                self._pause_event.set()
                total = len(vertices)
                try:
                    current = (
                        self.controllers['x'].read_position(),
                        self.controllers['y'].read_position(),
                        self.controllers['z'].read_position(),
                    )
                except Exception:
                    current = (0.0, 0.0, 0.0)

                # Record starting coordinate and timestamp
                self._log_event(
                    "PATH",
                    "pattern_start",
                    f"start={current}",
                    "",
                )

                for idx, target in enumerate(vertices):
                    self._pause_event.wait()
                    if not self._move_axes(current, target, speed):
                        return
                    current = target
                    pct = (idx + 1) / total if total else 1.0
                    self.pattern_progress.emit(idx, pct, 0.0)

                # Record completion coordinate and timestamp
                self._log_event(
                    "PATH",
                    "pattern_completed",
                    f"end={current}",
                    "",
                )
                self.pattern_completed.emit()
            except Exception as exc:  # pragma: no cover - hardware dependent
                self.error_occurred.emit("PATH", str(exc))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Background monitoring
    # ------------------------------------------------------------------
    def _start_monitor(self):
        if self._monitoring:
            return
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()

    def _monitor_loop(self):
        while self._monitoring:
            for axis, ctrl in self.controllers.items():
                client = ctrl.client
                if not client:
                    continue
                connected_attr = getattr(client, "connected", None)
                is_connected = (
                    connected_attr()
                    if callable(connected_attr)
                    else bool(connected_attr)
                )
                if not is_connected:
                    continue
                try:
                    pos = ctrl.read_position()
                    self.position_updated.emit(axis, pos)
                except Exception as exc:  # pragma: no cover - hardware dependent
                    self.error_occurred.emit(axis, f"Monitor error: {exc}")
                    ctrl.disconnect()
                    self.connection_changed.emit(axis, False)
            time.sleep(0.3)

