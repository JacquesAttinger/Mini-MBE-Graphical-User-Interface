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
    QTabWidget,
    QDoubleSpinBox,
    QLabel,
)

from widgets.axis_control import AxisControlWidget
from widgets.position_canvas import EnhancedPositionCanvas as PositionCanvas
from widgets.status_panel import StatusPanel
from widgets.camera_tab import CameraTab


class MainWindow(QMainWindow):
    """Top-level window coordinating UI widgets with backend services."""

    def __init__(self, manager, dxf_service, initial_status, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.dxf_service = dxf_service
        self.controllers = manager.controllers
        self._positions = {"x": 0.0, "y": 0.0, "z": 0.0}
        self._vertices = []
        self._segments = []
        self._setup_ui()
        self._update_initial_connection_status(initial_status)
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _setup_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        # ------------------------------------------------------------------
        # Main control tab
        # ------------------------------------------------------------------
        main_tab = QWidget()
        tabs.addTab(main_tab, "Main")
        main_layout = QHBoxLayout(main_tab)

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

        # Pattern controls
        self.nozzle_input = QDoubleSpinBox()
        self.nozzle_input.setPrefix("Nozzle Ø ")
        self.nozzle_input.setSuffix(" µm")
        self.nozzle_input.setRange(1.0, 1000.0)
        self.nozzle_input.setValue(12.0)
        right_layout.addWidget(self.nozzle_input)

        self.speed_input = QDoubleSpinBox()
        self.speed_input.setPrefix("Speed ")
        self.speed_input.setSuffix(" mm/s")
        self.speed_input.setDecimals(4)
        self.speed_input.setRange(0.0001, 2.0)
        self.speed_input.setValue(0.1)
        right_layout.addWidget(self.speed_input)

        self.start_pattern_btn = QPushButton("Start Pattern")
        self.start_pattern_btn.setEnabled(False)
        right_layout.addWidget(self.start_pattern_btn)

        self.progress_label = QLabel("Pattern progress: 0%")
        right_layout.addWidget(self.progress_label)

        # Status panel
        self.status_panel = StatusPanel()
        right_layout.addWidget(self.status_panel)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, stretch=1)

        # ------------------------------------------------------------------
        # Camera tab
        # ------------------------------------------------------------------
        self.camera_tab = CameraTab()
        tabs.addTab(self.camera_tab, "Camera")

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
        self.start_pattern_btn.clicked.connect(self._on_start_pattern)
        self.manager.pattern_progress.connect(self._update_pattern_progress)
        self.manager.pattern_completed.connect(self._handle_pattern_completed)

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
        previous = self._positions.get(axis)
        self._positions[axis] = position
        self.position_canvas.update_position(
            self._positions["x"],
            self._positions["y"],
        )
        if previous is None or abs(position - previous) >= 0.01:
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
            try:
                z_pos = self.manager.controllers['z'].read_position()
            except Exception:
                z_pos = self._positions.get('z', 0.0)
            self.dxf_service.load_dxf(filename, scale=1.0, z_height=z_pos)

    def _handle_dxf_loaded(self, filename, geometry):
        self.position_canvas.update_dxf(geometry, scale_factor=1.0)
        self._vertices = geometry['movement']['vertices']
        self._segments = geometry['movement']['segments']
        self.start_pattern_btn.setEnabled(True)
        self.status_panel.log_message(
            f"Loaded DXF: {os.path.basename(filename)}"
        )

    def _on_start_pattern(self):
        if not self._vertices:
            return
        speed = self.speed_input.value()
        self.progress_label.setText("Pattern progress: 0%")
        self.manager.execute_path(self._vertices, speed)

    def _update_pattern_progress(self, index, pct, remaining):
        self.position_canvas.draw_path_progress(index, self._vertices, self._segments)
        self.progress_label.setText(
            f"Pattern progress: {pct*100:.1f}% | {remaining:.1f}s remaining"
        )

    def _handle_pattern_completed(self):
        self.progress_label.setText("Pattern progress: 100% | 0.0s remaining")
        self.status_panel.log_message("Pattern completed")

    # ------------------------------------------------------------------
    # Qt events
    # ------------------------------------------------------------------
    def closeEvent(self, event):  # pragma: no cover - GUI callback
        self.manager.disconnect_all()
        super().closeEvent(event)

