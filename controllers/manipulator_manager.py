"""High level manager for multiple manipulator axes."""

import threading
import time
from typing import Dict

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

