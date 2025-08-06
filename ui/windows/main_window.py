"""Main application window for the miniMBE GUI."""

import os
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
)

from widgets.axis_control import AxisControlWidget
from widgets.position_canvas import EnhancedPositionCanvas as PositionCanvas
from widgets.status_panel import StatusPanel


class MainWindow(QMainWindow):
    """Top-level window coordinating UI widgets with backend services."""

    def __init__(self, manager, dxf_service, initial_status, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.dxf_service = dxf_service
        self.controllers = manager.controllers
        self._setup_ui()
        self._update_initial_connection_status(initial_status)
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left panel - axis controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        for axis in ["x", "y", "z"]:
            axis_control = AxisControlWidget(axis.upper(), self.controllers[axis])
            axis_control.move_requested.connect(
                lambda pos, vel, a=axis: self.manager.move_axis(a, pos, vel)
            )
            axis_control.stop_requested.connect(
                lambda a=axis: self.manager.emergency_stop(a)
            )
            axis_control.home_btn.clicked.connect(
                lambda _, a=axis: self.manager.home_axis(a)
            )
            left_layout.addWidget(axis_control)

        # Right panel - visualization + status
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # Position canvas
        self.position_canvas = PositionCanvas()
        right_layout.addWidget(self.position_canvas, stretch=1)

        # DXF load button
        self.load_dxf_btn = QPushButton("Load DXF")
        right_layout.addWidget(self.load_dxf_btn)

        # Status panel
        self.status_panel = StatusPanel()
        right_layout.addWidget(self.status_panel)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, stretch=1)

        self.setWindowTitle("MBE Manipulator Control")
        self.resize(1200, 800)

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------
    def _connect_signals(self):
        self.manager.status_updated.connect(self.status_panel.log_message)
        self.manager.position_updated.connect(self._handle_position_update)
        self.manager.error_occurred.connect(self._handle_error)
        self.manager.connection_changed.connect(self._handle_connection_change)

        self.load_dxf_btn.clicked.connect(self._on_load_dxf)
        self.dxf_service.dxf_loaded.connect(self._handle_dxf_loaded)
        self.dxf_service.error_occurred.connect(
            lambda msg: self._handle_error("DXF", msg)
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _update_initial_connection_status(self, status):
        all_connected = all(status.values())
        self.status_panel.update_connection_status(all_connected)
        for axis, is_connected in status.items():
            state = "Connected" if is_connected else "Disconnected"
            self.status_panel.log_message(f"{axis.upper()} axis: {state}")

    def _handle_connection_change(self, axis, connected):
        all_connected = all(
            ctrl.client for ctrl in self.manager.controllers.values()
        )
        self.status_panel.update_connection_status(all_connected)
        state = "Connected" if connected else "Disconnected"
        self.status_panel.log_message(f"{axis.upper()} axis: {state}")

    def _handle_position_update(self, axis, position):
        self.position_canvas.update_position(
            self.controllers["x"].get_position() or 0,
            self.controllers["y"].get_position() or 0,
        )
        self.status_panel.log_message(
            f"{axis.upper()} position: {position:.3f} mm"
        )

    def _handle_error(self, axis, message):
        self.status_panel.log_message(f"{axis} ERROR: {message}")
        QMessageBox.critical(self, f"{axis} Error", message)

    def _on_load_dxf(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select DXF File", "", "DXF Files (*.dxf)"
        )
        if filename:
            self.dxf_service.load_dxf(filename, scale=1.0)

    def _handle_dxf_loaded(self, filename, geometry):
        self.position_canvas.update_dxf(geometry, scale_factor=1.0)
        self.status_panel.log_message(
            f"Loaded DXF: {os.path.basename(filename)}"
        )

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------
    def closeEvent(self, event):  # pragma: no cover - GUI callback
        self.manager.disconnect_all()
        super().closeEvent(event)

