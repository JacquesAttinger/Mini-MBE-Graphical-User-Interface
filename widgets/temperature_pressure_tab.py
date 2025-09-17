"""Widget providing live temperature and pressure readouts."""

from __future__ import annotations

from collections import deque
import sys
sys.path.append("/Users/jacques/Documents/UChicago/UChicago Research/Yang Research/Mini-MBE GUI/miniMBE-GUI/services")
import time
import smtplib
from pathlib import Path
from typing import Deque, Optional, Tuple, List
from datetime import datetime
import os, smtplib, threading, time
from email.mime.text import MIMEText

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QCheckBox,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QDoubleSpinBox,
    QMessageBox,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from email_credentials import ALERT_RECEIVER, GMAIL_APP_PASSWORD
from services.data_logger import DataLogger
from services.sensor_readers import PressureReader, TemperatureReader
from services.temperature_controller import TemperatureController




class TemperaturePressureTab(QWidget):
    """Tab displaying temperature/pressure values and recent history plots."""

    #: Maximum history (seconds) retained in memory regardless of the
    #: currently displayed window. This allows the view window to expand
    #: immediately without waiting for new data to accumulate.
    DEFAULT_MAX_HISTORY_SECONDS = 360.0

    # Signals to control acquisition
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        pressure_reader: Optional[PressureReader] = None,
        temperature_reader: Optional[TemperatureReader] = None,
        temperature_controller: Optional[TemperatureController] = None,
        logger: Optional[DataLogger] = None,
    ) -> None:
        super().__init__(parent)
        # deques store (timestamp, value) pairs for recent readings
        self._temp_data: Deque[Tuple[float, float]] = deque()
        self._pressure_data: Deque[Tuple[float, float]] = deque()

        # hardware interfaces / logger
        self._pressure_reader = pressure_reader
        self._temperature_reader = temperature_reader
        self._temperature_controller = temperature_controller
        self._logger = logger or DataLogger("/Users/jacques/Documents/UChicago/UChicago Research/Yang Research/Mini-MBE GUI/miniMBE-GUI/logs/Pressure and Temperature logs")
        self._logging = False
        self._acquisition_running = False
        self._last_temp = 0.0
        self._last_pressure = 0.0
        self._temp_pending = False
        self._pressure_pending = False
        self._service_mode = False
        self._max_history_seconds = self.DEFAULT_MAX_HISTORY_SECONDS
        self._log_retention_secs = 0.0

        # Automated email sending for interlock system
        self._alert_threshold = 5.0                  # mTorr (adjust)
        self._email_cooldown_secs = 60            # number of seconds between emails get sent
        self._email_next_allowed = 0.0               # monotonic timestamp
        self._email_inflight = False                 # prevent overlap
        self._alert_sender = "jacques.attinger@gmail.com"
        self._alert_receiver = ALERT_RECEIVER
        self._gmail_app_password = GMAIL_APP_PASSWORD

        # timer for plot updates
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_plots)

        # connect reader signals if provided
        if self._temperature_reader:
            self._temperature_reader.reading.connect(self._handle_temperature)
            print('connected to temperature handler')
        if self._pressure_reader:
            self._pressure_reader.reading.connect(self._handle_pressure)
            print('connected to pressure handler')

        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Control row
        control = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("log.csv")
        self.start_btn = QPushButton("Start")
        self.start_btn.setStyleSheet("background-color: #5cb85c; color: white;")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #d9534f; color: white;")
        control.addWidget(self.path_edit)
        control.addWidget(self.start_btn)
        control.addWidget(self.stop_btn)
        self.service_btn = QPushButton("Service mode: off")
        control.addWidget(self.service_btn)
        self.settings_btn = QPushButton("Settings…")
        control.addWidget(self.settings_btn)
        control.addStretch(1)
        layout.addLayout(control)

        # Current value labels
        values = QHBoxLayout()
        self.temp_label = QLabel("Temp: -")
        self.pressure_label = QLabel("Pressure: -")
        values.addWidget(self.temp_label)
        values.addStretch(1)
        values.addWidget(self.pressure_label)
        layout.addLayout(values)

        # Parameter toggle checkboxes
        toggles = QHBoxLayout()
        self.temp_box = QCheckBox("Temperature")
        self.temp_box.setChecked(True)
        self.pressure_box = QCheckBox("Pressure")
        self.pressure_box.setChecked(True)
        toggles.addWidget(self.temp_box)
        toggles.addWidget(self.pressure_box)
        toggles.addStretch(1)
        layout.addLayout(toggles)

        # Time window selector
        window_row = QHBoxLayout()
        window_row.addWidget(QLabel("Last seconds:"))
        self.window_edit = QLineEdit("10")
        self.window_edit.setFixedWidth(60)
        window_row.addWidget(self.window_edit)
        window_row.addStretch(1)
        layout.addLayout(window_row)

        # Temperature control inputs
        temp_ctrl = QHBoxLayout()
        self.setpoint_edit = QLineEdit()
        self.setpoint_edit.setPlaceholderText("Setpoint")
        self.setpoint_btn = QPushButton("Set T Setpoint")
        self.setpoint_btn.clicked.connect(self._on_set_setpoint)
        # self.ramp_rate_edit = QLineEdit()
        # self.ramp_rate_edit.setPlaceholderText("Ramp rate")
        # self.ramp_rate_btn = QPushButton("Set Ramp Rate")
        # self.ramp_rate_btn.clicked.connect(self._on_set_ramp_rate)
        temp_ctrl.addWidget(self.setpoint_edit)
        temp_ctrl.addWidget(self.setpoint_btn)
        # temp_ctrl.addWidget(self.ramp_rate_edit)
        # temp_ctrl.addWidget(self.ramp_rate_btn)
        temp_ctrl.addStretch(1)
        layout.addLayout(temp_ctrl)

        # Matplotlib plot with twin y-axes
        self._fig = Figure(figsize=(5, 4))
        self._canvas = FigureCanvas(self._fig)
        self._temp_ax = self._fig.add_subplot(111)
        self._pressure_ax = self._temp_ax.twinx()
        self._fig.tight_layout(pad=3.0)
        self._temp_ax.set_title("Temperature and Pressure")
        self._temp_ax.set_ylabel("Temperature (C)")
        self._pressure_ax.set_ylabel("Pressure")
        (self._temp_line,) = self._temp_ax.plot([], [], color="tab:red")
        (self._pressure_line,) = self._pressure_ax.plot([], [], color="tab:blue")
        layout.addWidget(self._canvas)

        # Connect buttons to handlers
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.service_btn.clicked.connect(self._toggle_service_mode)
        self.settings_btn.clicked.connect(self._on_settings_clicked)

        # Connect checkboxes to plot updates
        self.temp_box.toggled.connect(self._update_plots)
        self.pressure_box.toggled.connect(self._update_plots)
        
        

    def _get_window_seconds(self) -> float:
        """Return the user-specified history window in seconds."""
        try:
            return float(self.window_edit.text())
        except (AttributeError, ValueError):
            return 10.0

    def _trim_deque(self, data: Deque[Tuple[float, float]], window: float) -> None:
        """Remove entries older than the given window from *data*."""
        cutoff = time.time() - window
        while data and data[0][0] < cutoff:
            data.popleft()

    def _recent_data(
        self, data: Deque[Tuple[float, float]], window: float
    ) -> List[Tuple[float, float]]:
        """Return a list of data points within ``window`` seconds."""
        cutoff = time.time() - window
        return [(t, v) for t, v in data if t >= cutoff]

    def _update_temperature_plot(self) -> None:
        """Refresh the temperature line plot with current data."""
        window = self._get_window_seconds()
        points = self._recent_data(self._temp_data, window)
        if not self.temp_box.isChecked():
            self._temp_line.set_visible(False)
            self._temp_ax.get_yaxis().set_visible(False)
        else:
            if points:
                base = points[0][0]
                x_temp = [t - base for t, _ in points]
                y_temp = [v for _, v in points]
            else:
                x_temp, y_temp = [], []
            self._temp_line.set_data(x_temp, y_temp)
            self._temp_line.set_visible(True)
            self._temp_ax.get_yaxis().set_visible(True)
            self._temp_ax.relim()
            self._temp_ax.autoscale_view()
        self._canvas.draw_idle()

    def _update_pressure_plot(self) -> None:
        """Refresh the pressure line plot with current data."""
        window = self._get_window_seconds()
        points = self._recent_data(self._pressure_data, window)
        if not self.pressure_box.isChecked():
            self._pressure_line.set_visible(False)
            self._pressure_ax.get_yaxis().set_visible(False)
        else:
            if points:
                base = points[0][0]
                x_pressure = [t - base for t, _ in points]
                y_pressure = [v for _, v in points]
            else:
                x_pressure, y_pressure = [], []
            self._pressure_line.set_data(x_pressure, y_pressure)
            self._pressure_line.set_visible(True)
            self._pressure_ax.get_yaxis().set_visible(True)
            self._pressure_ax.relim()
            self._pressure_ax.autoscale_view()
        self._canvas.draw_idle()

    def _update_plots(self) -> None:
        """Refresh both plots. Used by the periodic timer."""
        self._update_temperature_plot()
        self._update_pressure_plot()

    # ------------------------------------------------------------------
    def _on_start(self) -> None:
        """Validate path, start readers/logger and timer."""
        if self._acquisition_running:
            return
        path = self.path_edit.text().strip()
        try:
            if not path:
                raise ValueError("Empty path")
            Path(path)  # validate
        except Exception:
            # highlight invalid path
            self.path_edit.setStyleSheet("background-color: pink;")
            return
        self.path_edit.setStyleSheet("")

        # start logger
        try:
            self._logger.start(path)
            print('started loggin')
            self._logging = True
            self._temp_pending = False
            self._pressure_pending = False
        except Exception:
            self._logging = False

        # start readers
        print(self._pressure_reader)
        if self._pressure_reader:
            print('attempting to start pressure reader')
            self._pressure_reader.start()
            print('started pressure reader')
        if self._temperature_reader:
            print('attempting to start temp reader')
            self._temperature_reader.start()
            print('started temp reader')

        self._timer.start()
        self._acquisition_running = True
        self.settings_btn.setEnabled(False)
        self.start_requested.emit()

    # ------------------------------------------------------------------
    def _on_stop(self) -> None:
        """Stop readers/logger and freeze plot updates."""
        if self._pressure_reader:
            self._pressure_reader.stop()
        if self._temperature_reader:
            self._temperature_reader.stop()
        if self._logging:
            self._logger.stop()
            self._logging = False
        self._temp_pending = False
        self._pressure_pending = False
        self._timer.stop()
        self._acquisition_running = False
        self.settings_btn.setEnabled(True)
        self.stop_requested.emit()

    def _on_set_setpoint(self) -> None:
        """Handle setpoint button click."""
        if not self._temperature_controller:
            return
        try:
            value = self.setpoint_edit.text()
            print(value)
        except ValueError:
            self.setpoint_edit.setStyleSheet("background-color: pink;")
            return
        self.setpoint_edit.setStyleSheet("")
        self._temperature_controller.set_setpoint(value)

    # def _on_set_ramp_rate(self) -> None:
    #     """Handle ramp rate button click."""
    #     if not self._temperature_controller:
    #         return
    #     try:
    #         value = float(self.ramp_rate_edit.text())
    #     except ValueError:
    #         self.ramp_rate_edit.setStyleSheet("background-color: pink;")
    #         return
    #     self.ramp_rate_edit.setStyleSheet("")
    #     self._temperature_controller.set_ramp_rate(value)

    # ------------------------------------------------------------------
    def _handle_temperature(self, value: float) -> None:
        """Handle a new temperature reading."""
        self._last_temp = value
        now = time.time()
        self._temp_data.append((now, value))
        self._trim_deque(self._temp_data, self._max_history_seconds)
        self.temp_label.setText(f"Temp: {value:.2f}")
        style = """
    font-size: 20pt;
    padding: 8px;
    border: 2px solid #333;
    border-radius: 6px;
    background-color: #f9f9f9;
"""
        self.temp_label.setStyleSheet(style)
        if self._logging:
            self._temp_pending = True
            self._log_latest_readings()
        # self._update_plots()
        self._update_temperature_plot()

    # if self._last_pressure < 5:
    #     sender = 'jacques.attinger@gmail.com'
    #     receiver = 'jacques.attinger@gmail.com'

    #     subject = 'Low Pressure Alert'
    #     message = f'The pressure in the chamber is quite low. It has a value of {self._last_pressure}'

    #     text = f"From: {sender}\nTo: {receiver}\nSubject: {subject}\n\n{message}"

    #     server = smtplib.SMTP("smtp.gmail.com", 587)
    #     server.starttls()

    #     server.login(sender, 'leximtegokofxrxa')

    #     server.sendmail(sender, receiver, text)

    #     print(f'email has been sent to {receiver}')

    def _maybe_alert_low_pressure(self, pressure_value: float) -> None:
        """If pressure is below threshold, queue an email (cooldown + nonblocking)."""
        if self._service_mode:
            return
        if pressure_value >= self._alert_threshold:
            return

        now = time.monotonic()
        if now < self._email_next_allowed:
            return  # still in cooldown window
        if self._email_inflight:
            return  # an email is already being sent

        # Guard future sends immediately to avoid races
        self._email_inflight = True
        self._email_next_allowed = now + self._email_cooldown_secs

        subject = "Mini-MBE: Low Pressure Alert"
        body = (
            f"Low pressure detected:\n"
            f"  Pressure: {pressure_value:.3e}\n"
            f"  Temperature (last): {self._last_temp:.2f}\n"
            f"  Time: {datetime.now().isoformat(timespec='seconds')}\n"
        )
        threading.Thread(
            target=self._send_email_async,
            args=(subject, body),
            daemon=True
        ).start()

    def _toggle_service_mode(self) -> None:
        self._service_mode = not self._service_mode
        state = "on" if self._service_mode else "off"
        self.service_btn.setText(f"Service mode: {state}")
    # ------------------------------------------------------------------
    def _handle_pressure(self, value: float) -> None:
        """Handle a new pressure reading."""
        self._last_pressure = value
        now = time.time()
        self._pressure_data.append((now, value))
        self._trim_deque(self._pressure_data, self._max_history_seconds)
        self.pressure_label.setText(f"Pressure: {value:.2e}")
        style = """
    font-size: 20pt;
    padding: 8px;
    border: 2px solid #333;
    border-radius: 6px;
    background-color: #f9f9f9;
"""
        self.pressure_label.setStyleSheet(style)
        if self._logging:
            self._pressure_pending = True
            self._log_latest_readings()
        # self._update_plots()
        self._maybe_alert_low_pressure(value)
        self._update_pressure_plot()

    def _log_latest_readings(self) -> None:
        """Write a single combined log row when both readings are updated."""
        if not (self._temp_pending and self._pressure_pending):
            return

        timestamp = datetime.now().isoformat(timespec="milliseconds")
        self._logger.append(timestamp, self._last_pressure, self._last_temp)
        if self._log_retention_secs > 0:
            self._logger.trim_older_than(self._log_retention_secs)
        self._temp_pending = False
        self._pressure_pending = False

    def _send_email_async(self, subject: str, body: str) -> None:
        """Runs in a background thread; never touch Qt widgets here."""
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self._alert_sender
            msg["To"] = self._alert_receiver

            with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
                server.starttls()
                server.login(self._alert_sender, self._gmail_app_password)
                server.sendmail(self._alert_sender, [self._alert_receiver], msg.as_string())
            print(f"[ALERT] Email sent to {self._alert_receiver}")
        except Exception as e:
            # Optional: back off sooner if send failed
            print(f"[ALERT] Email send failed: {e!r}")
        finally:
            # Release the inflight flag (safe enough for a boolean)
            self._email_inflight = False

    # ------------------------------------------------------------------
    def _on_settings_clicked(self) -> None:
        """Open the settings dialog when acquisition is idle."""
        if self._acquisition_running:
            QMessageBox.information(
                self,
                "Acquisition running",
                "Stop the acquisition before changing settings.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Temperature/Pressure Settings")
        form = QFormLayout(dialog)

        max_history_input = QDoubleSpinBox(dialog)
        max_history_input.setDecimals(1)
        max_history_input.setRange(1.0, 3600.0)
        max_history_input.setValue(self._max_history_seconds)
        max_history_input.setSuffix(" s")

        retention_input = QDoubleSpinBox(dialog)
        retention_input.setDecimals(1)
        retention_input.setRange(0.0, 3600.0)
        retention_input.setValue(self._log_retention_secs)
        retention_input.setSuffix(" s")
        retention_input.setSpecialValueText("Disabled")

        cooldown_input = QDoubleSpinBox(dialog)
        cooldown_input.setDecimals(1)
        cooldown_input.setRange(0.0, 3600.0)
        cooldown_input.setValue(self._email_cooldown_secs)
        cooldown_input.setSuffix(" s")

        pressure_input = QDoubleSpinBox(dialog)
        pressure_input.setDecimals(3)
        pressure_input.setRange(0.0, 1_000_000.0)
        pressure_input.setValue(self._alert_threshold)
        pressure_input.setSuffix(" mTorr")

        form.addRow("Max history", max_history_input)
        form.addRow("Log retention", retention_input)
        form.addRow("Alert cooldown", cooldown_input)
        form.addRow("Minimum pressure", pressure_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        self._max_history_seconds = max_history_input.value()
        self._log_retention_secs = retention_input.value()
        self._email_cooldown_secs = cooldown_input.value()
        self._alert_threshold = pressure_input.value()

        # Trim existing data to the new history length and refresh the plots
        self._trim_deque(self._temp_data, self._max_history_seconds)
        self._trim_deque(self._pressure_data, self._max_history_seconds)

        window_seconds = self._get_window_seconds()
        if window_seconds > self._max_history_seconds:
            self.window_edit.setText(f"{self._max_history_seconds:g}")

        self._update_plots()
