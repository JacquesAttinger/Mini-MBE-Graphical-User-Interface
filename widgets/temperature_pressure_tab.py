"""Widget providing live temperature and pressure readouts."""

from __future__ import annotations

from collections import deque
from typing import Deque

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class TemperaturePressureTab(QWidget):
    """Tab displaying temperature/pressure values and recent history plots."""

    # Signals to control acquisition
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # deques store last 10 readings
        self._temp_data: Deque[float] = deque(maxlen=10)
        self._pressure_data: Deque[float] = deque(maxlen=10)
        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Control row
        control = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.setStyleSheet("background-color: #5cb85c; color: white;")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("background-color: #d9534f; color: white;")
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

        # Connect buttons to signals
        self.start_btn.clicked.connect(self.start_requested.emit)
        self.stop_btn.clicked.connect(self.stop_requested.emit)

    # ------------------------------------------------------------------
    def add_reading(self, temperature: float, pressure: float) -> None:
        """Append a new temperature/pressure pair and update displays."""
        self._temp_data.append(temperature)
        self._pressure_data.append(pressure)
        self.temp_label.setText(f"Temp: {temperature:.2f}")
        self.pressure_label.setText(f"Pressure: {pressure:.2f}")
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
