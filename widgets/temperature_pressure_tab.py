"""Widget providing live temperature and pressure readouts."""

from __future__ import annotations

from collections import deque
import sys
sys.path.append("/Users/jacques/Documents/UChicago/UChicago Research/Yang Research/Mini-MBE GUI/miniMBE-GUI/services")
import time
from pathlib import Path
from typing import Deque, Optional

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
        self._logger = logger or DataLogger()
        self._logging = False
        self._last_temp = 0.0
        self._last_pressure = 0.0

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

        # Matplotlib plots
        self._fig = Figure(figsize=(5, 4))
        self._canvas = FigureCanvas(self._fig)
        self._temp_ax = self._fig.add_subplot(211)
        self._pressure_ax = self._fig.add_subplot(212)
        self._temp_ax.set_title("Temperature")
        self._pressure_ax.set_title("Pressure")
        (self._temp_line,) = self._temp_ax.plot([], [], "-o")
        (self._pressure_line,) = self._pressure_ax.plot([], [], "-o")
        layout.addWidget(self._canvas)

        # Connect buttons to handlers
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)

    # ------------------------------------------------------------------
    def add_reading(self, temperature: float, pressure: float) -> None:
        """Append a new temperature/pressure pair and update displays."""
        self._last_temp = temperature
        self._last_pressure = pressure
        self._temp_data.append(temperature)
        self._pressure_data.append(pressure)
        print(temperature)
        print(pressure)
        self.temp_label.setText(f"Temp: {temperature:.2f}")
        self.pressure_label.setText(f"Pressure: {pressure:.2f}")
        if self._logging:
            self._logger.append(time.time(), self._last_pressure, self._last_temp)
        self._update_plots()

    # ------------------------------------------------------------------
    def _update_plots(self) -> None:
        """Refresh line plots with current data."""
        x_temp = list(range(len(self._temp_data)))
        y_temp = list(self._temp_data)
        self._temp_line.set_data(x_temp, y_temp)
        self._temp_ax.relim()
        self._temp_ax.autoscale_view()

        x_pressure = list(range(len(self._pressure_data)))
        y_pressure = list(self._pressure_data)
        self._pressure_line.set_data(x_pressure, y_pressure)
        self._pressure_ax.relim()
        self._pressure_ax.autoscale_view()

        self._canvas.draw_idle()

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
        self.add_reading(self._last_temp, self._last_pressure)
        self._temp_data.append(value)
        self.temp_label.setText(f"Temp: {value:.2f}")
        if self._logging:
            self._logger.append(time.time(), self._last_pressure, self._last_temp)
            print('appended temp data')
        self._update_plots()

    # ------------------------------------------------------------------
    def _handle_pressure(self, value: float) -> None:
        """Handle a new pressure reading."""
        self._last_pressure = value
        self.add_reading(self._last_temp, self._last_pressure)
        self._pressure_data.append(value)
        self.pressure_label.setText(f"Pressure: {value:.2f}")
        if self._logging:
            self._logger.append(time.time(), self._last_pressure, self._last_temp)
            print('appended pressure data')
        self._update_plots()
