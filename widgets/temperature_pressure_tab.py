"""Widget providing live temperature and pressure readouts."""

from __future__ import annotations

from collections import deque
import sys
sys.path.append("/Users/jacques/Documents/UChicago/UChicago Research/Yang Research/Mini-MBE GUI/miniMBE-GUI/services")
import time
import smtplib
from pathlib import Path
from typing import Deque, Optional
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
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from services.data_logger import DataLogger
from services.sensor_readers import PressureReader, TemperatureReader




class TemperaturePressureTab(QWidget):
    """Tab displaying temperature/pressure values and recent history plots."""

    # Signals to control acquisition
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        pressure_reader: Optional[PressureReader] = None,
        temperature_reader: Optional[TemperatureReader] = None,
        logger: Optional[DataLogger] = None,
    ) -> None:
        super().__init__(parent)
        # deques store last 10 readings
        self._temp_data: Deque[float] = deque(maxlen=10)
        self._pressure_data: Deque[float] = deque(maxlen=10)

        # hardware interfaces / logger
        self._pressure_reader = pressure_reader
        self._temperature_reader = temperature_reader
        self._logger = logger or DataLogger("/Users/jacques/Documents/UChicago/UChicago Research/Yang Research/Mini-MBE GUI/miniMBE-GUI/logs/Pressure and Temperature logs")
        self._logging = False
        self._last_temp = 0.0
        self._last_pressure = 0.0
        self._service_mode = False

        # Automated email sending for interlock system
        self._alert_threshold = 5.0                  # mTorr (adjust)
        self._email_cooldown_secs = 5             # one email per minute max
        self._email_next_allowed = 0.0               # monotonic timestamp
        self._email_inflight = False                 # prevent overlap
        self._alert_sender = "jacques.attinger@gmail.com"
        self._alert_receiver = "jacques.attinger@gmail.com"
        self._gmail_app_password = "leximtegokofxrxa" 

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

        # Matplotlib plot with twin y-axes
        self._fig = Figure(figsize=(5, 4))
        self._canvas = FigureCanvas(self._fig)
        self._temp_ax = self._fig.add_subplot(111)
        self._pressure_ax = self._temp_ax.twinx()
        self._fig.tight_layout(pad=3.0)
        self._temp_ax.set_title("Temperature and Pressure")
        self._temp_ax.set_ylabel("Temperature")
        self._pressure_ax.set_ylabel("Pressure")
        (self._temp_line,) = self._temp_ax.plot([], [], "-o", color="tab:red")
        (self._pressure_line,) = self._pressure_ax.plot([], [], "-o", color="tab:blue")
        layout.addWidget(self._canvas)

        # Connect buttons to handlers
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.service_btn.clicked.connect(self._toggle_service_mode)

    

    
    
    def _update_temperature_plot(self) -> None:
        """Refresh the temperature line plot with current data."""
        x_temp = list(range(len(self._temp_data)))
        y_temp = list(self._temp_data)
        self._temp_line.set_data(x_temp, y_temp)
        self._temp_ax.relim()
        self._temp_ax.autoscale_view()
        self._canvas.draw_idle()

    def _update_pressure_plot(self) -> None:
        """Refresh the pressure line plot with current data."""
        x_pressure = list(range(len(self._pressure_data)))
        y_pressure = list(self._pressure_data)
        self._pressure_line.set_data(x_pressure, y_pressure)
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
        self._timer.stop()
        self.stop_requested.emit()

    # ------------------------------------------------------------------
    def _handle_temperature(self, value: float) -> None:
        """Handle a new temperature reading."""
        self._last_temp = value
        # self.add_reading(self._last_temp, self._last_pressure)
        self._temp_data.append(value)
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
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") #generates the current time
            self._logger.append(timestamp, self._last_pressure, self._last_temp)
            # print('appended temp data')
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
        # self.add_reading(self._last_temp, self._last_pressure)
        self._pressure_data.append(value)
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

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") #generates the current time
            self._logger.append(timestamp, self._last_pressure, self._last_temp)
            # print('appended pressure data')
        # self._update_plots()
        self._maybe_alert_low_pressure(value)
        self._update_pressure_plot()

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
