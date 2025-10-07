"""High level manager for multiple manipulator axes."""

import logging
import math
import threading
import time
from typing import Dict, List, Set, Tuple

from PySide6.QtCore import QObject, Signal

from controllers.smcd14_controller import (
    ManipulatorController,
    MotionNeverStartedError,
)
from utils.speed import adjust_axis_speed

STOP_GO_SPEED_THRESHOLD = 1e-4  # mm/s
STOP_GO_HOP_SPEED = 1e-3        # mm/s
STOP_GO_STEP_FRACTION = 0.1     # move a fraction of the nozzle diameter each hop

# Default connection settings
HOST = "169.254.151.255"
PORT = 502
TIMEOUT = 10
AXIS_SLAVE_MAP = {"x": 1, "y": 2, "z": 3}

# Minimum positional delta that will trigger an actual move command.  Values
# smaller than this are treated as already "in position" to avoid waiting on
# axes that have no movement.
EPSILON = 4e-4


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
        self.nozzle_diameter_mm = 0.0
        self._abort_lock = threading.Lock()
        self._aborted_axes: Set[str] = set()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    def set_nozzle_diameter(self, diameter_mm: float) -> None:
        """Update the cached nozzle diameter used for stop-and-go motion."""

        self.nozzle_diameter_mm = max(0.0, float(diameter_mm))

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
            self._clear_axis_abort(axis)
            ctrl.move_absolute(position, axis_speed)
            try:
                ok = ctrl.wait_until_in_position(target=position)
            except MotionNeverStartedError as exc:
                # Immediately capture diagnostic registers so the log shows
                # the controller state at the moment the start request was
                # ignored.
                status = ctrl._read_status()
                err = ctrl.read_error_code()
                msg = str(exc)
                self._log_event(
                    axis,
                    "error",
                    msg,
                    f"err={err};status={status}",
                )
                raise
            if not ok:
                if self._consume_axis_abort(axis):
                    self._log_event(
                        axis,
                        "aborted",
                        f"target={position} speed={axis_speed}",
                        "",
                    )
                    return f"{axis.upper()} move stopped"
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
            if self._consume_axis_abort(axis):
                self._log_event(
                    axis,
                    "aborted",
                    f"target={position} speed={axis_speed}",
                    "",
                )
                return f"{axis.upper()} move stopped"
            return f"{axis.upper()} moved to {position:.3f} mm"

        self._run_async(axis, action, position, speed)

    def emergency_stop(self, axis: str):
        """Trigger emergency stop on a specific axis."""

        def action(ctrl):
            ctrl.emergency_stop()
            return f"{axis.upper()} emergency stop executed"

        self._mark_axis_aborted(axis)
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
        *,
        force_direct: bool = False,
    ) -> bool:
        """Issue move commands for axes that actually need to travel.

        Each active axis moves toward its target position at a speed scaled by
        its proportion of the total travel distance.  This keeps the overall
        velocity of the 3D move equal to ``speed`` regardless of how far each
        axis needs to move.

        Returns ``True`` if all commanded axes reported they reached their
        destination. If an axis fails the corresponding error signal is emitted
        and ``False`` is returned.
        """

        current_start = start
        while True:
            self._pause_event.wait()
            dx = target[0] - current_start[0]
            dy = target[1] - current_start[1]
            dz = target[2] - current_start[2]
            distance = (dx ** 2 + dy ** 2 + dz ** 2) ** 0.5
            micro_move = distance <= EPSILON and force_direct
            if (
                not force_direct
                and speed < STOP_GO_SPEED_THRESHOLD
                and self.nozzle_diameter_mm > 0.0
            ):
                return self._move_axes_stop_and_go(current_start, target, speed, distance)
            if distance <= EPSILON and not force_direct:
                self._log_event(
                    "ALL",
                    "info",
                    f"Zero-distance move ignored start={current_start} target={target}",
                    "",
                )
                return True
            if micro_move:
                self._log_event(
                    "ALL",
                    "micro_move",
                    f"distance={distance:.6f} start={current_start} target={target}",
                    "",
                )
                if self.motion_log_enabled:
                    self._motion_logger.info(
                        "t=%s axis=ALL micro_move distance=%.6f start=(%.6f,%.6f,%.6f) target=(%.6f,%.6f,%.6f)",
                        time.time(),
                        distance,
                        current_start[0],
                        current_start[1],
                        current_start[2],
                        target[0],
                        target[1],
                        target[2],
                    )

            deltas = [dx, dy, dz]
            active_axes = []
            for idx, axis in enumerate(("x", "y", "z")):
                delta = deltas[idx]
                if force_direct:
                    if math.isclose(delta, 0.0, abs_tol=1e-9):
                        continue
                elif abs(delta) <= EPSILON:
                    continue

                axis_speed = adjust_axis_speed(abs(speed * delta / distance))
                ctrl = self.controllers[axis]
                try:
                    ctrl.motor_on()
                except Exception:
                    pass
                self._clear_axis_abort(axis)
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
                travel = abs(delta)
                if axis_speed > 0 and math.isfinite(axis_speed):
                    expected_move_time = travel / axis_speed
                    wait_timeout = max(15.0, expected_move_time * 3.0)
                else:
                    wait_timeout = 15.0
                self._log_event(
                    axis,
                    "move",
                    f"target={target[idx]} speed={axis_speed}",
                    "",
                )
                active_axes.append((axis, target[idx], axis_speed, wait_timeout))

            paused = False
            aborted = False
            for axis, pos, axis_speed, wait_timeout in active_axes:
                ctrl = self.controllers[axis]
                try:
                    ok = ctrl.wait_until_in_position(
                        timeout=wait_timeout,
                        target=pos,
                        pause_event=self._pause_event,
                    )
                except MotionNeverStartedError as exc:
                    # Capture diagnostic registers right away to record the
                    # controller state responsible for ignoring the move command.
                    status = ctrl._read_status()
                    err = ctrl.read_error_code()
                    msg = str(exc)
                    self._log_event(
                        axis,
                        "error",
                        msg,
                        f"err={err};status={status}",
                    )
                    self.error_occurred.emit(axis, msg)
                    return False
                if ok is None:
                    paused = True
                    break
                if not ok:
                    if self._consume_axis_abort(axis):
                        self._log_event(
                            axis,
                            "aborted",
                            f"target={pos} speed={axis_speed}",
                            "",
                        )
                        self.status_updated.emit(f"{axis.upper()} move stopped")
                        aborted = True
                        break
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

            if paused:
                self._pause_event.wait()
                coords = []
                for idx, axis in enumerate(("x", "y", "z")):
                    ctrl = self.controllers.get(axis)
                    try:
                        coords.append(ctrl.read_position())
                    except Exception:
                        coords.append(current_start[idx])
                current_start = tuple(coords)
                continue

            if aborted:
                return False

            return True

    def _move_axes_stop_and_go(
        self,
        start: Tuple[float, float, float],
        target: Tuple[float, float, float],
        requested_speed: float,
        distance: float,
    ) -> bool:
        """Approximate very slow motion by hop-dwell cycles."""

        if requested_speed <= 0.0:
            raise ValueError("Requested speed must be positive for stop-and-go mode")

        step_length = max(self.nozzle_diameter_mm * STOP_GO_STEP_FRACTION, EPSILON)
        steps = max(1, math.ceil(distance / step_length))
        move_speed = max(STOP_GO_HOP_SPEED, requested_speed)

        dx = target[0] - start[0]
        dy = target[1] - start[1]
        dz = target[2] - start[2]

        prev_point = start
        travelled = 0.0
        for step in range(1, steps + 1):
            remaining = distance - travelled
            segment = min(step_length, remaining)
            travelled += segment
            frac = travelled / distance if distance else 1.0
            intermediate = (
                start[0] + dx * frac,
                start[1] + dy * frac,
                start[2] + dz * frac,
            )

            move_start = time.time()
            move_end = move_start
            try:
                move_success = self._move_axes(
                    prev_point, intermediate, move_speed, force_direct=True
                )
            finally:
                move_end = time.time()

            if not move_success:
                return False

            synthetic_move_time = segment / move_speed
            actual_move_time = move_end - move_start
            if actual_move_time <= 0:
                actual_move_time = synthetic_move_time

            total_time = segment / requested_speed
            dwell = max(0.0, total_time - actual_move_time)
            if dwell > 0:
                self._log_event(
                    "ALL",
                    "dwell",
                    f"segment={segment:.6f}mm dwell={dwell:.3f}s",
                    "",
                )
                remaining_dwell = dwell
                while remaining_dwell > 0:
                    self._pause_event.wait()
                    chunk = min(0.1, remaining_dwell)
                    start_sleep = time.time()
                    time.sleep(chunk)
                    elapsed = time.time() - start_sleep
                    remaining_dwell -= elapsed
            prev_point = intermediate

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
        self._stop_all_motion()
        self.status_updated.emit("Pattern paused")

    def resume_path(self):
        """Resume a paused path."""
        self._pause_event.set()
        self.status_updated.emit("Pattern resumed")

    def _stop_all_motion(self) -> None:
        """Issue an emergency stop to every connected axis."""

        for axis, ctrl in self.controllers.items():
            emergency_stop = getattr(ctrl, "emergency_stop", None)
            if emergency_stop is None:
                continue
            self._mark_axis_aborted(axis)
            try:
                emergency_stop()
            except Exception:
                # Best effort – stopping is more important than reporting here
                pass

    def _mark_axis_aborted(self, axis: str) -> None:
        with self._abort_lock:
            self._aborted_axes.add(axis)

    def _consume_axis_abort(self, axis: str) -> bool:
        with self._abort_lock:
            if axis in self._aborted_axes:
                self._aborted_axes.remove(axis)
                return True
            return False

    def _clear_axis_abort(self, axis: str) -> None:
        with self._abort_lock:
            self._aborted_axes.discard(axis)

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

    def execute_recipe(
        self,
        commands: List[dict],
        print_speed: float,
        travel_speed: float,
    ) -> None:
        """Execute a list of commands with different speeds for print and travel."""

        def worker():
            try:
                if not commands:
                    return
                self._pause_event.set()
                try:
                    current = (
                        self.controllers['x'].read_position(),
                        self.controllers['y'].read_position(),
                        self.controllers['z'].read_position(),
                    )
                except Exception:
                    current = (0.0, 0.0, 0.0)

                self._log_event(
                    "PATH",
                    "pattern_start",
                    f"start={current}",
                    "",
                )

                total = sum(max(len(cmd.get('vertices', [])) - 1, 0) for cmd in commands)
                progress_idx = 0

                for cmd in commands:
                    mode = cmd.get('mode', 'print')
                    verts = cmd.get('vertices', [])
                    speed = print_speed if mode == 'print' else travel_speed
                    for target in verts[1:]:
                        self._pause_event.wait()
                        if not self._move_axes(current, target, speed):
                            return
                        current = target
                        progress_idx += 1
                        pct = progress_idx / total if total else 1.0
                        self.pattern_progress.emit(progress_idx - 1, pct, 0.0)

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

