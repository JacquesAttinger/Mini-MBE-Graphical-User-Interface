"""Tab widget that exposes e-beam controls and live telemetry."""

from __future__ import annotations

from collections import deque
from datetime import datetime
import math
import re
import time
from typing import Callable, Deque, Dict, List, Optional, Tuple

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from services.ebeam_controller import EBeamController
from services.flux_logger import FluxLogger


class EBeamControlTab(QWidget):
    """Provides controls and live vitals for the e-beam evaporator."""

    VITAL_UPDATE_MS = 500
    SHUTDOWN_EMISSION_TARGET = 0.1
    SHUTDOWN_FILAMENT_TARGET = 0.1
    SHUTDOWN_TOLERANCE = 0.01
    EMISSION_MODE_THRESHOLD = 1.0  # mA
    FILAMENT_MODE_THRESHOLD = 0.6  # mA
    DEFAULT_FLUX_WINDOW_SECONDS = 60.0
    MAX_FLUX_HISTORY_SECONDS = 21600.0  # 6 hours of history retained in memory
    _FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = EBeamController()
        self._vital_labels: Dict[str, QLabel] = {}
        self._setpoint_buttons: Dict[QDoubleSpinBox, QPushButton] = {}
        self._latest_filament_current: Optional[float] = None
        self._latest_emission_current: Optional[float] = None
        self._latest_flux_nanoamps: Optional[float] = None
        self._control_mode: str = "Filament Control"
        self._control_mode_detected = False
        self._suppressor_state: Optional[bool] = None
        self._suppressor_button_cooldown = False
        self._filament_ramp_queue: List[float] = []
        self._filament_step_size = 0.1
        self._filament_ramp_rate = 0.4
        self._filament_ramp_complete_callback: Optional[Callable[[], None]] = None
        self._shutdown_state: Optional[str] = None
        self._flux_data: Deque[Tuple[float, float]] = deque()
        self._flux_logger = FluxLogger()
        self._flux_logging = False
        self._flux_window_seconds = self.DEFAULT_FLUX_WINDOW_SECONDS
        self._max_flux_history_seconds = self.MAX_FLUX_HISTORY_SECONDS

        self._timer = QTimer(self)
        self._timer.setInterval(self.VITAL_UPDATE_MS)
        self._timer.timeout.connect(self._refresh_vitals)

        self._filament_ramp_timer = QTimer(self)
        self._filament_ramp_timer.setInterval(self._calculate_ramp_interval_ms())
        self._filament_ramp_timer.timeout.connect(self._on_filament_ramp_timeout)

        self._build_ui()
        self._update_connection_state(False)
        self._update_control_mode_ui()
        self._update_suppressor_ui()
        self._update_flux_plot()
        self._update_flux_logging_ui()
        self.destroyed.connect(lambda _: self._controller.disconnect())

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Connection controls
        conn_group = QGroupBox("Connection")
        conn_layout = QGridLayout(conn_group)
        conn_layout.addWidget(QLabel("Port:"), 0, 0)
        self.port_edit = QLineEdit(self._controller.port)
        self.port_edit.setPlaceholderText("COM port (e.g., COM5)")
        conn_layout.addWidget(self.port_edit, 0, 1)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        conn_layout.addWidget(self.connect_btn, 0, 2)

        self.connection_label = QLabel("Disconnected")
        self.connection_label.setAlignment(Qt.AlignCenter)
        conn_layout.addWidget(self.connection_label, 1, 0)

        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        conn_layout.addWidget(self.message_label, 1, 1, 1, 2)
        conn_layout.setColumnStretch(1, 1)
        conn_layout.setColumnStretch(2, 1)

        layout.addWidget(conn_group)

        # Parameter controls
        param_group = QGroupBox("Setpoints")
        param_layout = QFormLayout(param_group)

        self.hv_input = self._create_spinbox(0.0, 10000.0, single_step=1.0, decimals=0)
        self.hv_input.setSuffix(" V")
        self._add_setpoint_row(
            param_layout,
            "High voltage",
            self.hv_input,
            self._apply_high_voltage,
        )

        self.emission_input = self._create_spinbox(0.0, 500.0)
        self.emission_input.setSuffix(" mA")
        self._add_setpoint_row(
            param_layout,
            "Emission current",
            self.emission_input,
            self._apply_emission_current,
        )

        self.filament_input = self._create_spinbox(0.0, 10.0)
        self.filament_input.setSuffix(" A")
        self._add_setpoint_row(
            param_layout,
            "Filament current",
            self.filament_input,
            self._apply_filament_current,
        )

        self.suppressor_button = QPushButton("Toggle Suppressor")
        self.suppressor_button.clicked.connect(self._toggle_suppressor)
        param_layout.addRow("Suppressor", self.suppressor_button)

        self.shutdown_button = QPushButton("Shutdown")
        self.shutdown_button.clicked.connect(self._start_shutdown)
        param_layout.addRow(self.shutdown_button)

        layout.addWidget(param_group)

        # Flux monitor
        flux_group = QGroupBox("Flux Monitor")
        flux_layout = QVBoxLayout(flux_group)

        flux_controls = QHBoxLayout()
        self.flux_path_edit = QLineEdit()
        self.flux_path_edit.setPlaceholderText("flux_log.csv")
        flux_controls.addWidget(self.flux_path_edit)
        self.flux_start_btn = QPushButton("Start Log")
        self.flux_start_btn.clicked.connect(self._start_flux_log)
        flux_controls.addWidget(self.flux_start_btn)
        self.flux_stop_btn = QPushButton("Stop Log")
        self.flux_stop_btn.clicked.connect(self._stop_flux_log)
        flux_controls.addWidget(self.flux_stop_btn)
        flux_controls.addStretch(1)
        flux_layout.addLayout(flux_controls)

        flux_window_row = QHBoxLayout()
        flux_window_row.addWidget(QLabel("Display last:"))
        self.flux_window_spin = QDoubleSpinBox()
        self.flux_window_spin.setRange(1.0, self._max_flux_history_seconds)
        self.flux_window_spin.setValue(self._flux_window_seconds)
        self.flux_window_spin.setSuffix(" s")
        self.flux_window_spin.valueChanged.connect(self._on_flux_window_changed)
        flux_window_row.addWidget(self.flux_window_spin)
        flux_window_row.addStretch(1)
        flux_layout.addLayout(flux_window_row)

        self._flux_figure = Figure(figsize=(5, 2.5))
        self._flux_canvas = FigureCanvas(self._flux_figure)
        self._flux_ax = self._flux_figure.add_subplot(111)
        self._flux_ax.set_title("Flux")
        self._flux_ax.set_xlabel("Time (s)")
        self._flux_ax.set_ylabel("Flux (nA)")
        (self._flux_line,) = self._flux_ax.plot([], [], color="tab:green")
        self._flux_figure.tight_layout(pad=2.0)
        flux_layout.addWidget(self._flux_canvas)

        layout.addWidget(flux_group)

        # Vitals display
        vitals_group = QGroupBox("Vitals")
        vitals_layout = QFormLayout(vitals_group)
        for label in (*EBeamController.vital_labels(), "Control Mode"):
            value_label = QLabel("-")
            value_label.setObjectName(label.replace(" ", "_").lower())
            vitals_layout.addRow(label + ":", value_label)
            self._vital_labels[label] = value_label
        layout.addWidget(vitals_group)

        self._set_shutdown_state(None)
        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _toggle_connection(self) -> None:
        if self._controller.is_connected:
            self._controller.disconnect()
            self._timer.stop()
            self._filament_ramp_timer.stop()
            self._filament_ramp_queue.clear()
            self._filament_ramp_complete_callback = None
            self._set_shutdown_state(None)
            self._update_connection_state(False)
            return

        port_text = self.port_edit.text().strip()
        if port_text:
            self._controller.configure_port(port_text)
        try:
            self._controller.connect()
        except Exception as exc:  # pragma: no cover - serial failures depend on HW
            self._set_status_message(f"Connection failed: {exc}")
            self._update_connection_state(False)
            return

        self._update_connection_state(True)
        self._refresh_vitals()
        self._timer.start()

    def _apply_high_voltage(self) -> None:
        self._apply_setpoint(
            self._controller.set_high_voltage,
            self.hv_input,
        )

    def _apply_emission_current(self) -> None:
        value = self.emission_input.value()
        if value < 0.1:
            self._set_status_message("Emission current must be at least 0.1 mA")
            if self._latest_emission_current is not None and self._latest_emission_current >= 0.1:
                self.emission_input.setValue(self._latest_emission_current)
            else:
                self.emission_input.setValue(0.1)
            return
        if value < self.FILAMENT_MODE_THRESHOLD:
            response = QMessageBox.warning(
                self,
                "Confirm emission current",
                (
                    "Warning! Setting emission current below 0.6 mA will "
                    "ramp down the emission current to 0 and switch to "
                    "filament control mode. Are you sure you would like to "
                    "proceed?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if response != QMessageBox.Yes:
                if self._latest_emission_current is not None:
                    self.emission_input.setValue(self._latest_emission_current)
                self._set_status_message("Emission current command cancelled")
                return
        self._apply_setpoint(
            self._controller.set_emission_current,
            self.emission_input,
        )

    def _apply_filament_current(self) -> None:
        target = self.filament_input.value()
        if self._start_filament_ramp(target):
            self._acknowledge_input(self.filament_input)

    def _start_filament_ramp(
        self,
        target: float,
        *,
        callback: Optional[Callable[[], None]] = None,
    ) -> bool:
        if not self._controller.is_connected:
            self._set_status_message("Not connected")
            return False
        self._filament_ramp_timer.stop()
        self._filament_ramp_queue.clear()
        self._filament_ramp_complete_callback = callback

        start = self._latest_filament_current
        if start is None:
            start = self._controller.get_filament_current()
        if start is None:
            start = target

        queue = self._build_filament_ramp(start, target)
        if not queue:
            try:
                self._controller.set_filament_current(target)
                self._set_status_message("Command sent")
            except Exception as exc:  # pragma: no cover - depends on HW
                self._set_status_message(f"Command failed: {exc}")
                self._filament_ramp_complete_callback = None
                return False
            self._on_filament_ramp_complete()
            return True

        self._filament_ramp_queue = queue
        self._send_next_filament_step()
        if self._filament_ramp_queue:
            self._filament_ramp_timer.setInterval(self._calculate_ramp_interval_ms())
            self._filament_ramp_timer.start()
        else:
            self._filament_ramp_timer.stop()
            self._on_filament_ramp_complete()
        return True

    def _apply_setpoint(self, setter, spinbox: QDoubleSpinBox) -> None:
        if not self._controller.is_connected:
            self._set_status_message("Not connected")
            return
        try:
            setter(spinbox.value())
            self._set_status_message("Command sent")
        except Exception as exc:  # pragma: no cover - depends on HW
            self._set_status_message(f"Command failed: {exc}")
            return
        self._acknowledge_input(spinbox)

    def initiate_shutdown(self, *, reason: Optional[str] = None) -> None:
        """Public helper used by interlock systems to start shutdown."""
        if reason:
            self._set_status_message(reason)
        if self._shutdown_state is not None:
            return
        self._start_shutdown()

    def _start_shutdown(self) -> None:
        if not self._controller.is_connected:
            self._set_status_message("Not connected")
            return
        if self._shutdown_state is not None:
            self._set_status_message("Shutdown already in progress")
            return
        try:
            self._controller.set_emission_current(self.SHUTDOWN_EMISSION_TARGET)
        except Exception as exc:  # pragma: no cover - depends on HW
            self._set_status_message(f"Shutdown failed: {exc}")
            return
        self.emission_input.setValue(self.SHUTDOWN_EMISSION_TARGET)
        self._set_shutdown_state("waiting_emission")
        self._set_status_message("Shutdown: waiting for emission")
        self._maybe_advance_shutdown()

    def _refresh_vitals(self) -> None:
        if not self._controller.is_connected:
            for label in self._vital_labels.values():
                label.setText("-")
            self._latest_filament_current = None
            self._latest_emission_current = None
            self._latest_flux_nanoamps = None
            self._flux_data.clear()
            self._control_mode_detected = False
            self._suppressor_state = None
            self._update_control_mode_ui()
            self._update_suppressor_ui()
            self._update_flux_plot()
            if self._shutdown_state is not None:
                self._finish_shutdown("Shutdown aborted: disconnected")
            return
        try:
            vitals = self._controller.get_vitals()
        except Exception as exc:  # pragma: no cover - depends on HW
            self._set_status_message(f"Vitals error: {exc}")
            self._timer.stop()
            return
        suppressor_state = self._parse_suppressor_state(vitals.get("Suppressor"))
        self._suppressor_state = suppressor_state
        if suppressor_state is not None:
            vitals["Suppressor"] = "On" if suppressor_state else "Off"

        flux_value = vitals.get("Flux")
        flux_nanoamps = self._parse_flux_nanoamps(flux_value)
        self._latest_flux_nanoamps = flux_nanoamps
        if flux_nanoamps is not None:
            self._record_flux_sample(flux_nanoamps)

        filament_value = vitals.get("Filament Current")
        self._latest_filament_current = self._parse_float(filament_value)
        emission_value = vitals.get("Emission Current")
        self._latest_emission_current = self._parse_float(emission_value)
        previous_mode_snapshot = self._control_mode
        previous_detected = self._control_mode_detected
        control_mode_detected = previous_detected
        if self._latest_emission_current is not None:
            if previous_mode_snapshot == "Emission Control":
                if self._latest_emission_current < self.FILAMENT_MODE_THRESHOLD:
                    self._control_mode = "Filament Control"
            else:
                if self._latest_emission_current > self.EMISSION_MODE_THRESHOLD:
                    self._control_mode = "Emission Control"
                else:
                    self._control_mode = "Filament Control"
            control_mode_detected = True
        else:
            control_mode_detected = False

        self._control_mode_detected = control_mode_detected
        vitals["Control Mode"] = (
            self._control_mode if control_mode_detected else "-"
        )

        for key, label in self._vital_labels.items():
            formatted = self._format_vital_value(key, vitals.get(key, "-"))
            label.setText(formatted)

        mode_changed = (
            control_mode_detected != previous_detected
            or (
                control_mode_detected
                and self._control_mode != previous_mode_snapshot
            )
            or (not control_mode_detected and previous_detected)
        )
        if mode_changed:
            self._update_control_mode_ui()
        self._update_suppressor_ui()
        self._update_flux_plot()
        self._maybe_advance_shutdown()

    def _maybe_advance_shutdown(self) -> None:
        if self._shutdown_state == "waiting_emission":
            current = self._latest_emission_current
            if current is None:
                return
            if current <= self.SHUTDOWN_EMISSION_TARGET + self.SHUTDOWN_TOLERANCE:
                self.filament_input.setValue(self.SHUTDOWN_FILAMENT_TARGET)
                self._set_shutdown_state("ramping_filament")
                if not self._start_filament_ramp(
                    self.SHUTDOWN_FILAMENT_TARGET,
                    callback=self._on_shutdown_filament_complete,
                ):
                    message = self.message_label.text() if hasattr(self, "message_label") else ""
                    message = message or "Shutdown aborted"
                    self._finish_shutdown(message)
                elif self._shutdown_state == "ramping_filament":
                    self._set_status_message("Shutdown: ramping filament")

    def _on_shutdown_filament_complete(self) -> None:
        if self._shutdown_state != "ramping_filament":
            return
        try:
            self._controller.set_high_voltage(0.0)
        except Exception as exc:  # pragma: no cover - depends on HW
            self._finish_shutdown(f"Shutdown failed: {exc}")
            return
        self.hv_input.setValue(0.0)
        self._finish_shutdown("Shutdown complete")

    def _finish_shutdown(self, message: Optional[str] = None) -> None:
        self._set_shutdown_state(None)
        self._filament_ramp_complete_callback = None
        if message:
            self._set_status_message(message)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _update_connection_state(self, connected: bool) -> None:
        if connected:
            self.connection_label.setText("Connected")
            self.connection_label.setStyleSheet(
                "background-color: #5cb85c; color: white; padding: 4px 8px; border-radius: 4px;"
            )
            self.connect_btn.setText("Disconnect")
            self._suppressor_button_cooldown = False
            if hasattr(self, "suppressor_button"):
                self.suppressor_button.setEnabled(True)
            self._set_status_message("Connected")
            self._update_control_mode_ui()
        else:
            self.connection_label.setText("Disconnected")
            self.connection_label.setStyleSheet(
                "background-color: #d9534f; color: white; padding: 4px 8px; border-radius: 4px;"
            )
            self.connect_btn.setText("Connect")
            self._set_shutdown_state(None)
            self._set_status_message("")
            self._suppressor_button_cooldown = False
            if hasattr(self, "suppressor_button"):
                self.suppressor_button.setEnabled(False)
            self._control_mode_detected = False
            self._update_control_mode_ui()
            self._suppressor_state = None
        self._update_suppressor_ui()

    def _set_shutdown_state(self, state: Optional[str]) -> None:
        self._shutdown_state = state
        if hasattr(self, "shutdown_button"):
            self.shutdown_button.setEnabled(state is None)

    def _set_status_message(self, text: str) -> None:
        if hasattr(self, "message_label"):
            self.message_label.setText(text)

    def _set_spinbox_row_enabled(
        self, spinbox: QDoubleSpinBox, enabled: bool
    ) -> None:
        spinbox.setEnabled(enabled)
        button = self._setpoint_buttons.get(spinbox)
        if button is not None:
            button.setEnabled(enabled)

    def _update_control_mode_ui(self) -> None:
        label = self._vital_labels.get("Control Mode")
        if label is not None:
            label.setText(self._control_mode if self._control_mode_detected else "-")
        if not hasattr(self, "emission_input") or not hasattr(self, "filament_input"):
            return
        if not self._controller.is_connected or not self._control_mode_detected:
            emission_enabled = True
            filament_enabled = True
        elif self._control_mode == "Emission Control":
            emission_enabled = True
            filament_enabled = False
        else:
            emission_enabled = False
            filament_enabled = True
        self._set_spinbox_row_enabled(self.emission_input, emission_enabled)
        self._set_spinbox_row_enabled(self.filament_input, filament_enabled)

    def _toggle_suppressor(self) -> None:
        if not self._controller.is_connected:
            self._set_status_message("Not connected")
            return
        self._start_suppressor_button_cooldown()
        target_state = not self._suppressor_state if self._suppressor_state is not None else True
        try:
            self._controller.set_suppressor_state(target_state)
            reported = self._controller.get_suppressor_state()
            if reported is not None:
                self._suppressor_state = reported
            else:
                self._suppressor_state = target_state
            state_text = "on" if self._suppressor_state else "off"
            self._set_status_message(f"Suppressor turned {state_text}")
        except Exception as exc:  # pragma: no cover - depends on HW
            self._set_status_message(f"Suppressor command failed: {exc}")
            return
        self._update_suppressor_ui()

    def _update_suppressor_ui(self) -> None:
        suppressor_label = self._vital_labels.get("Suppressor")
        if suppressor_label is not None:
            if not self._controller.is_connected:
                self._suppressor_button_cooldown = False
                suppressor_label.setText("-")
            elif self._suppressor_state is True:
                suppressor_label.setText("On")
            elif self._suppressor_state is False:
                suppressor_label.setText("Off")
            else:
                suppressor_label.setText("-")
        if not hasattr(self, "suppressor_button"):
            return
        if not self._controller.is_connected:
            self.suppressor_button.setEnabled(False)
            self.suppressor_button.setText("Toggle Suppressor")
            return
        self.suppressor_button.setEnabled(not self._suppressor_button_cooldown)
        if self._suppressor_state is True:
            self.suppressor_button.setText("Turn Suppressor Off")
        elif self._suppressor_state is False:
            self.suppressor_button.setText("Turn Suppressor On")
        else:
            self.suppressor_button.setText("Toggle Suppressor")

    def _start_suppressor_button_cooldown(self) -> None:
        if self._suppressor_button_cooldown:
            return
        self._suppressor_button_cooldown = True
        if hasattr(self, "suppressor_button"):
            self.suppressor_button.setEnabled(False)
        QTimer.singleShot(1000, self._end_suppressor_button_cooldown)

    def _end_suppressor_button_cooldown(self) -> None:
        self._suppressor_button_cooldown = False
        self._update_suppressor_ui()

    @staticmethod
    def _parse_suppressor_state(raw: Optional[str]) -> Optional[bool]:
        if raw is None:
            return None
        text = str(raw).strip().lower()
        if "on" in text:
            return True
        if "off" in text:
            return False
        match = EBeamControlTab._FLOAT_RE.search(text)
        if not match:
            return None
        try:
            numeric = float(match.group(0))
        except ValueError:
            return None
        if numeric == 1:
            return True
        if numeric == 0:
            return False
        return None

    def _start_flux_log(self) -> None:
        if self._flux_logging:
            return
        path = self.flux_path_edit.text().strip() or "flux_log.csv"
        try:
            self._flux_logger.start(path)
        except Exception as exc:  # pragma: no cover - depends on HW
            self._set_status_message(f"Failed to start flux log: {exc}")
            return
        self._flux_logging = True
        self._set_status_message("Flux logging started")
        self._update_flux_logging_ui()

    def _stop_flux_log(self) -> None:
        if not self._flux_logging:
            return
        try:
            self._flux_logger.stop()
        except Exception as exc:  # pragma: no cover - depends on HW
            self._set_status_message(f"Failed to stop flux log: {exc}")
            self._flux_logging = False
            self._update_flux_logging_ui()
            return
        self._flux_logging = False
        self._set_status_message("Flux logging stopped")
        self._update_flux_logging_ui()

    def _update_flux_logging_ui(self) -> None:
        if not hasattr(self, "flux_start_btn"):
            return
        self.flux_start_btn.setEnabled(not self._flux_logging)
        self.flux_stop_btn.setEnabled(self._flux_logging)

    def _on_flux_window_changed(self, value: float) -> None:
        self._flux_window_seconds = max(1.0, min(float(value), self._max_flux_history_seconds))
        self._update_flux_plot()

    def _record_flux_sample(self, flux_nanoamps: float) -> None:
        timestamp = time.time()
        self._flux_data.append((timestamp, flux_nanoamps))
        self._trim_flux_history(timestamp)
        if self._flux_logging:
            try:
                self._flux_logger.append(datetime.now(), flux_nanoamps)
            except Exception as exc:  # pragma: no cover - depends on HW
                self._set_status_message(f"Flux log write failed: {exc}")
                try:
                    self._flux_logger.stop()
                except Exception:  # pragma: no cover - depends on HW
                    pass
                self._flux_logging = False
                self._update_flux_logging_ui()

    def _trim_flux_history(self, current_time: Optional[float] = None) -> None:
        if current_time is None:
            current_time = time.time()
        cutoff = current_time - self._max_flux_history_seconds
        while self._flux_data and self._flux_data[0][0] < cutoff:
            self._flux_data.popleft()

    def _update_flux_plot(self) -> None:
        if not hasattr(self, "_flux_line"):
            return
        if not self._flux_data:
            self._flux_line.set_data([], [])
            self._flux_ax.relim()
            self._flux_ax.autoscale_view()
            self._flux_canvas.draw_idle()
            return
        points = list(self._flux_data)
        latest_time = points[-1][0]
        window = min(self._flux_window_seconds, self._max_flux_history_seconds)
        cutoff = latest_time - window
        display_points = [p for p in points if p[0] >= cutoff]
        if not display_points:
            display_points = [points[-1]]
        base = display_points[0][0]
        x_values = [t - base for t, _ in display_points]
        y_values = [v for _, v in display_points]
        self._flux_line.set_data(x_values, y_values)
        self._flux_ax.relim()
        self._flux_ax.autoscale_view()
        self._flux_canvas.draw_idle()

    def _parse_flux_nanoamps(self, raw: Optional[str]) -> Optional[float]:
        numeric, units = self._extract_numeric_and_units(raw)
        if numeric is None:
            return None
        multiplier = self._flux_units_to_amps_multiplier(units)
        if multiplier is None:
            return None
        return numeric * multiplier * 1e9

    @staticmethod
    def _create_spinbox(
        min_value: float,
        max_value: float,
        *,
        single_step: float = 0.1,
        decimals: int = 3,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(min_value, max_value)
        spin.setDecimals(decimals)
        spin.setSingleStep(single_step)
        spin.setKeyboardTracking(False)
        return spin

    def _add_setpoint_row(
        self,
        layout: QFormLayout,
        label: str,
        spinbox: QDoubleSpinBox,
        handler,
    ) -> None:
        container = QWidget()
        row_layout = QHBoxLayout(container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(spinbox)
        button = QPushButton("Enter")
        row_layout.addWidget(button)
        layout.addRow(label, container)

        button.clicked.connect(
            lambda *, func=handler: self._on_setpoint_button(func)
        )
        spinbox.lineEdit().returnPressed.connect(
            lambda func=handler: self._on_spinbox_return_pressed(func)
        )
        self._setpoint_buttons[spinbox] = button

    def _on_setpoint_button(self, handler) -> None:
        handler()

    def _on_spinbox_return_pressed(
        self,
        handler,
    ) -> None:
        handler()

    def _acknowledge_input(self, spinbox: QDoubleSpinBox) -> None:
        button = self._setpoint_buttons.get(spinbox)
        spinbox.setEnabled(False)
        if button is not None:
            button.setEnabled(False)
        QTimer.singleShot(
            1000,
            lambda sb=spinbox, btn=button: self._restore_input_state(sb, btn),
        )

    def _restore_input_state(
        self, spinbox: QDoubleSpinBox, button: Optional[QPushButton]
    ) -> None:
        spinbox.setEnabled(True)
        if button is not None:
            button.setEnabled(True)
        self._update_control_mode_ui()

    def _build_filament_ramp(self, start: float, target: float) -> List[float]:
        if math.isclose(start, target, abs_tol=1e-6):
            return []
        step = self._filament_step_size if target > start else -self._filament_step_size
        values: List[float] = []
        current = start
        while True:
            if (step > 0 and current >= target) or (step < 0 and current <= target):
                break
            current = current + step
            if step > 0 and current > target:
                current = target
            elif step < 0 and current < target:
                current = target
            values.append(round(current, 3))
            if math.isclose(current, target, abs_tol=1e-6):
                break
        return values

    def _on_filament_ramp_timeout(self) -> None:
        self._send_next_filament_step()
        if not self._filament_ramp_queue:
            self._filament_ramp_timer.stop()
            self._on_filament_ramp_complete()

    def _send_next_filament_step(self) -> None:
        if not self._filament_ramp_queue:
            return
        next_value = self._filament_ramp_queue.pop(0)
        try:
            self._controller.set_filament_current(next_value)
            self._set_status_message("Command sent")
        except Exception as exc:  # pragma: no cover - depends on HW
            self._set_status_message(f"Command failed: {exc}")
            self._filament_ramp_queue.clear()
            self._filament_ramp_timer.stop()
            self._filament_ramp_complete_callback = None
            if self._shutdown_state is not None:
                self._finish_shutdown(f"Shutdown failed: {exc}")

    def _on_filament_ramp_complete(self) -> None:
        callback = self._filament_ramp_complete_callback
        self._filament_ramp_complete_callback = None
        if callback is not None:
            callback()

    def _format_vital_value(self, label: str, value: str) -> str:
        if label == "High Voltage":
            numeric = self._parse_float(value)
            if numeric is None:
                return value
            return f"{numeric:.0f} V"
        if label == "Filament Current":
            numeric = self._parse_float(value)
            if numeric is None:
                return value
            return f"{numeric:.2f} A"
        if label == "Emission Current":
            numeric = self._parse_float(value)
            if numeric is None:
                return value
            return f"{numeric:.2f} mA"
        if label == "Flux":
            return self._format_flux(value)
        return value

    def _format_flux(self, raw: str) -> str:
        numeric, units = self._extract_numeric_and_units(raw)
        if numeric is None:
            return raw
        multiplier = self._flux_units_to_amps_multiplier(units)
        if multiplier is None:
            return raw
        amps = numeric * multiplier
        nanoamps = amps * 1e9
        return f"{nanoamps:.2f} nA"

    @staticmethod
    def _parse_float(raw: Optional[str]) -> Optional[float]:
        if not raw:
            return None
        try:
            text = raw.strip()
        except AttributeError:
            return None
        match = EBeamControlTab._FLOAT_RE.search(text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    @staticmethod
    def _extract_numeric_and_units(raw: Optional[str]) -> tuple[Optional[float], str]:
        if not raw:
            return None, ""
        try:
            text = raw.strip()
        except AttributeError:
            return None, ""
        match = EBeamControlTab._FLOAT_RE.search(text)
        if not match:
            return None, text
        number_text = match.group(0)
        try:
            numeric = float(number_text)
        except ValueError:
            numeric = None
        units = (text[: match.start()] + text[match.end():]).strip()
        return numeric, units

    def _calculate_ramp_interval_ms(self) -> int:
        rate = max(self._filament_ramp_rate, 0.01)
        interval = abs(self._filament_step_size / rate) * 1000.0
        return max(50, int(round(interval)))

    @staticmethod
    def _flux_units_to_amps_multiplier(units: str) -> Optional[float]:
        if units is None:
            return 1.0
        normalized = units.strip()
        if not normalized:
            return 1.0
        normalized = normalized.replace("µ", "u")
        normalized = normalized.replace("amperes", "a")
        normalized = normalized.replace("amper", "a")
        normalized = normalized.replace("amps", "a")
        normalized = normalized.replace("amp", "a")
        normalized = normalized.replace(" ", "")
        normalized = normalized.lower()
        if normalized in {"a"}:
            return 1.0
        if normalized in {"ma"}:
            return 1e-3
        if normalized in {"ua"}:
            return 1e-6
        if normalized in {"na"}:
            return 1e-9
        if normalized in {"pa"}:
            return 1e-12
        return None


__all__ = ["EBeamControlTab"]
