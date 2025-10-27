"""Tab widget that exposes e-beam controls and live telemetry."""

from __future__ import annotations

from typing import Dict

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.ebeam_controller import EBeamController


class EBeamControlTab(QWidget):
    """Provides controls and live vitals for the e-beam evaporator."""

    VITAL_UPDATE_MS = 500

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = EBeamController()
        self._vital_labels: Dict[str, QLabel] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(self.VITAL_UPDATE_MS)
        self._timer.timeout.connect(self._refresh_vitals)

        self._build_ui()
        self._update_connection_state(False)
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

        self.status_label = QLabel("Disconnected")
        conn_layout.addWidget(self.status_label, 1, 0, 1, 3)

        layout.addWidget(conn_group)

        # Parameter controls
        param_group = QGroupBox("Setpoints")
        param_layout = QFormLayout(param_group)

        self.hv_input = self._create_spinbox(0.0, 10000.0)
        self.hv_input.setSuffix(" V")
        self.hv_input.editingFinished.connect(self._apply_high_voltage)
        param_layout.addRow("High voltage", self.hv_input)

        self.emission_input = self._create_spinbox(0.0, 500.0)
        self.emission_input.setSuffix(" mA")
        self.emission_input.editingFinished.connect(self._apply_emission_current)
        param_layout.addRow("Emission current", self.emission_input)

        self.filament_input = self._create_spinbox(0.0, 10.0)
        self.filament_input.setSuffix(" A")
        self.filament_input.editingFinished.connect(self._apply_filament_current)
        param_layout.addRow("Filament current", self.filament_input)

        layout.addWidget(param_group)

        # Vitals display
        vitals_group = QGroupBox("Vitals")
        vitals_layout = QFormLayout(vitals_group)
        for label in EBeamController.vital_labels():
            value_label = QLabel("-")
            value_label.setObjectName(label.replace(" ", "_").lower())
            vitals_layout.addRow(label + ":", value_label)
            self._vital_labels[label] = value_label
        layout.addWidget(vitals_group)

        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _toggle_connection(self) -> None:
        if self._controller.is_connected:
            self._controller.disconnect()
            self._timer.stop()
            self._update_connection_state(False)
            return

        port_text = self.port_edit.text().strip()
        if port_text:
            self._controller.configure_port(port_text)
        try:
            self._controller.connect()
        except Exception as exc:  # pragma: no cover - serial failures depend on HW
            self.status_label.setText(f"Connection failed: {exc}")
            self._update_connection_state(False)
            return

        self._update_connection_state(True)
        self._refresh_vitals()
        self._timer.start()

    def _apply_high_voltage(self) -> None:
        self._apply_setpoint(self._controller.set_high_voltage, self.hv_input.value())

    def _apply_emission_current(self) -> None:
        self._apply_setpoint(self._controller.set_emission_current, self.emission_input.value())

    def _apply_filament_current(self) -> None:
        self._apply_setpoint(self._controller.set_filament_current, self.filament_input.value())

    def _apply_setpoint(self, setter, value: float) -> None:
        if not self._controller.is_connected:
            self.status_label.setText("Not connected")
            return
        try:
            setter(value)
            self.status_label.setText("Command sent")
        except Exception as exc:  # pragma: no cover - depends on HW
            self.status_label.setText(f"Command failed: {exc}")

    def _refresh_vitals(self) -> None:
        if not self._controller.is_connected:
            for label in self._vital_labels.values():
                label.setText("-")
            return
        try:
            vitals = self._controller.get_vitals()
        except Exception as exc:  # pragma: no cover - depends on HW
            self.status_label.setText(f"Vitals error: {exc}")
            self._timer.stop()
            return
        for key, label in self._vital_labels.items():
            label.setText(vitals.get(key, "-"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _update_connection_state(self, connected: bool) -> None:
        if connected:
            self.status_label.setText("Connected")
            self.connect_btn.setText("Disconnect")
        else:
            self.status_label.setText("Disconnected")
            self.connect_btn.setText("Connect")

    @staticmethod
    def _create_spinbox(min_value: float, max_value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(min_value, max_value)
        spin.setDecimals(3)
        spin.setSingleStep(0.1)
        spin.setKeyboardTracking(False)
        return spin


__all__ = ["EBeamControlTab"]
