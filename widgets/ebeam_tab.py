"""Tab widget that exposes e-beam controls and live telemetry."""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
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
    _FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = EBeamController()
        self._vital_labels: Dict[str, QLabel] = {}
        self._setpoint_buttons: Dict[QDoubleSpinBox, QPushButton] = {}
        self._latest_filament_current: Optional[float] = None
        self._filament_ramp_queue: List[float] = []
        self._filament_step_size = 0.1
        self._filament_ramp_rate = 0.2

        self._timer = QTimer(self)
        self._timer.setInterval(self.VITAL_UPDATE_MS)
        self._timer.timeout.connect(self._refresh_vitals)

        self._filament_ramp_timer = QTimer(self)
        self._filament_ramp_timer.setInterval(self._calculate_ramp_interval_ms())
        self._filament_ramp_timer.timeout.connect(self._on_filament_ramp_timeout)

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

        self.filament_ramp_rate_input = self._create_spinbox(
            0.01,
            5.0,
            single_step=0.05,
            decimals=2,
        )
        self.filament_ramp_rate_input.setSuffix(" A/s")
        self.filament_ramp_rate_input.setValue(self._filament_ramp_rate)
        self._add_setpoint_row(
            param_layout,
            "Filament ramp rate",
            self.filament_ramp_rate_input,
            self._apply_filament_ramp_rate,
        )

        emission_control_row = QWidget()
        emission_layout = QHBoxLayout(emission_control_row)
        emission_layout.setContentsMargins(0, 0, 0, 0)
        self.emission_on_button = QPushButton("Emission On")
        self.emission_on_button.clicked.connect(lambda: self._set_emission_control(True))
        emission_layout.addWidget(self.emission_on_button)
        self.emission_off_button = QPushButton("Emission Off")
        self.emission_off_button.clicked.connect(lambda: self._set_emission_control(False))
        emission_layout.addWidget(self.emission_off_button)
        param_layout.addRow("Emission control", emission_control_row)

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
        self._apply_setpoint(
            self._controller.set_high_voltage,
            self.hv_input,
        )

    def _apply_emission_current(self) -> None:
        self._apply_setpoint(
            self._controller.set_emission_current,
            self.emission_input,
        )

    def _apply_filament_current(self) -> None:
        if not self._controller.is_connected:
            self.status_label.setText("Not connected")
            return
        self._filament_ramp_timer.stop()
        self._filament_ramp_queue.clear()
        target = self.filament_input.value()
        start = self._latest_filament_current
        if start is None:
            start = self._controller.get_filament_current()
        if start is None:
            start = target
        queue = self._build_filament_ramp(start, target)
        if not queue:
            try:
                self._controller.set_filament_current(target)
                self.status_label.setText("Command sent")
            except Exception as exc:  # pragma: no cover - depends on HW
                self.status_label.setText(f"Command failed: {exc}")
                return
        else:
            self._filament_ramp_queue = queue
            self._send_next_filament_step()
            if self._filament_ramp_queue:
                self._filament_ramp_timer.setInterval(
                    self._calculate_ramp_interval_ms()
                )
                self._filament_ramp_timer.start()
            else:
                self._filament_ramp_timer.stop()
        self._acknowledge_input(self.filament_input)

    def _apply_setpoint(self, setter, spinbox: QDoubleSpinBox) -> None:
        if not self._controller.is_connected:
            self.status_label.setText("Not connected")
            return
        try:
            setter(spinbox.value())
            self.status_label.setText("Command sent")
        except Exception as exc:  # pragma: no cover - depends on HW
            self.status_label.setText(f"Command failed: {exc}")
            return
        self._acknowledge_input(spinbox)

    def _apply_filament_ramp_rate(self) -> None:
        value = max(self.filament_ramp_rate_input.value(), 0.01)
        self._filament_ramp_rate = value
        self.filament_ramp_rate_input.setValue(value)
        self._filament_ramp_timer.setInterval(self._calculate_ramp_interval_ms())
        if self._filament_ramp_queue and not self._filament_ramp_timer.isActive():
            self._filament_ramp_timer.start()
        self.status_label.setText(f"Ramp rate set to {value:.2f} A/s")
        self._acknowledge_input(self.filament_ramp_rate_input)

    def _set_emission_control(self, enabled: bool) -> None:
        if not self._controller.is_connected:
            self.status_label.setText("Not connected")
            return
        try:
            self._controller.set_emission_control(enabled)
        except Exception as exc:  # pragma: no cover - depends on HW
            self.status_label.setText(f"Command failed: {exc}")
            return
        state = "on" if enabled else "off"
        self.status_label.setText(f"Emission control {state}")

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
            formatted = self._format_vital_value(key, vitals.get(key, "-"))
            label.setText(formatted)
        filament_value = vitals.get("Filament Current")
        self._latest_filament_current = self._parse_float(filament_value)

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

    @staticmethod
    def _restore_input_state(spinbox: QDoubleSpinBox, button: Optional[QPushButton]) -> None:
        spinbox.setEnabled(True)
        if button is not None:
            button.setEnabled(True)

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

    def _send_next_filament_step(self) -> None:
        if not self._filament_ramp_queue:
            return
        next_value = self._filament_ramp_queue.pop(0)
        try:
            self._controller.set_filament_current(next_value)
            self.status_label.setText("Command sent")
        except Exception as exc:  # pragma: no cover - depends on HW
            self.status_label.setText(f"Command failed: {exc}")
            self._filament_ramp_queue.clear()
            self._filament_ramp_timer.stop()

    def _format_vital_value(self, label: str, value: str) -> str:
        if label == "Emission Control":
            state = value.strip().lower()
            if state in {"1", "off", "true"}:
                return "on"
            if state in {"0", "on", "false"}:
                return "off"
            return value
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
