"""High level manager for multiple manipulator axes."""

import threading
import time
import math
from typing import Dict, List, Tuple, Optional

from PySide6.QtCore import QObject, Signal

from controllers.smcd14_controller import ManipulatorController

# Default connection settings
HOST = "169.254.151.255"
PORT = 502
TIMEOUT = 10
AXIS_SLAVE_MAP = {"x": 1, "y": 2, "z": 3}


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

    def __init__(self,
                 host: str = HOST,
                 port: int = PORT,
                 timeout: int = TIMEOUT,
                 axis_slave_map: Dict[str, int] = AXIS_SLAVE_MAP):
        super().__init__()
        self.controllers = {
            axis: ManipulatorController(host, port, timeout, slave)
            for axis, slave in axis_slave_map.items()
        }
        self._monitoring = False
        self._monitor_thread = None
        # Software offset applied to every vertex in execute_path.
        # This is derived from the manipulator's position when a path starts
        # executing so that any previously set hardware origin is ignored.
        self._origin_offset: Optional[Tuple[float, float, float]] = None

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

    def reset_path_state(self) -> None:
        """Clear any remembered path offset.

        The manipulator's internal coordinate system can be re-zeroed by other
        software.  When this happens we derive a software offset in
        :meth:`execute_path` so DXF coordinates remain relative to the current
        physical position.  Calling this method before starting a new pattern
        discards the previous offset, preventing stale coordinates from
        influencing subsequent paths.
        """
        self._origin_offset = None

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
    def move_axis(self, axis: str, position: float, velocity: float):
        """Move an individual axis in a worker thread."""

        def action(ctrl, position, velocity):
            ctrl.move_absolute(position, velocity)
            return f"{axis.upper()} moved to {position:.3f} mm"

        self._run_async(axis, action, position, velocity)

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
    def _move_to(self, start: Tuple[float, float, float], target: Tuple[float, float, float], speed: float) -> Tuple[bool, float]:
        """Synchronously move all axes from ``start`` to ``target``.

        This simplified implementation issues a single absolute move command to
        each axis using the provided ``speed`` value.  After commanding the move
        it waits for all axes to report they are in position.  No per-axis
        velocity calculations are performed which ensures straightforward,
        sequential motion for each coordinate in a path.

        Returns a tuple ``(ok, distance_mm)`` where ``ok`` indicates whether all
        axes reported they reached the commanded position and ``distance_mm`` is
        the travelled distance.
        """

        disable_z = abs(target[2] - start[2]) < 1e-6

        # Command each axis to the target position.  All axes use the same speed
        # value to keep behaviour predictable.
        self.controllers['x'].move_absolute(target[0], speed)
        self.controllers['y'].move_absolute(target[1], speed)
        if not disable_z:
            self.controllers['z'].move_absolute(target[2], speed)

        # Wait for the axes to finish the move before proceeding.  If any axis
        # fails, surface the error and abort the current operation.
        wait_results = {
            'x': self.controllers['x'].wait_until_in_position(),
            'y': self.controllers['y'].wait_until_in_position(),
        }
        if not disable_z:
            wait_results['z'] = self.controllers['z'].wait_until_in_position()

        for axis, ok in wait_results.items():
            if not ok:
                self.error_occurred.emit(axis, "Failed to reach position")
                return False, 0.0

        dist = math.sqrt(
            (target[0] - start[0]) ** 2 +
            (target[1] - start[1]) ** 2 +
            (target[2] - start[2]) ** 2
        )
        return True, dist

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

            ok, _ = self._move_to(start, target, speed)
            if ok:
                self.status_updated.emit(
                    f"Moved to ({target[0]:.3f}, {target[1]:.3f}, {target[2]:.3f})"
                )

        threading.Thread(target=worker, daemon=True).start()

    def execute_path(self, vertices: List[Tuple[float, float, float]], speed: float):
        """Execute a series of 3D vertices at constant speed."""

        def worker():
            try:
                if not vertices:
                    return
                try:
                    current_pos = (
                        self.controllers['x'].read_position(),
                        self.controllers['y'].read_position(),
                        self.controllers['z'].read_position(),
                    )
                except Exception:
                    current_pos = (0.0, 0.0, 0.0)

                # Establish software offset if not already set
                if self._origin_offset is None:
                    first = vertices[0]
                    self._origin_offset = (
                        current_pos[0] - first[0],
                        current_pos[1] - first[1],
                        current_pos[2] - first[2],
                    )

                total_dist = 0.0
                for i in range(1, len(vertices)):
                    sx, sy, sz = vertices[i-1]
                    ex, ey, ez = vertices[i]
                    total_dist += math.sqrt((ex-sx)**2 + (ey-sy)**2 + (ez-sz)**2)

                if speed > 0:
                    self.pattern_progress.emit(0, 0.0, total_dist / speed)

                elapsed = 0.0
                for idx, target in enumerate(vertices):
                    adjusted_target = (
                        target[0] + self._origin_offset[0],
                        target[1] + self._origin_offset[1],
                        target[2] + self._origin_offset[2],
                    )
                    ok, dist = self._move_to(current_pos, adjusted_target, speed)
                    if not ok:
                        return
                    elapsed += dist
                    remaining = max(0.0, total_dist - elapsed)
                    pct = elapsed / total_dist if total_dist else 1.0
                    if speed > 0:
                        self.pattern_progress.emit(idx, pct, remaining / speed)
                    else:
                        self.pattern_progress.emit(idx, pct, 0.0)
                    current_pos = adjusted_target

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

