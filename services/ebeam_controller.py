"""High-level interface for controlling the e-beam evaporator."""

from __future__ import annotations

from typing import Dict, Optional

import serial
import re


class EBeamController:
    """Wraps the serial protocol used by the e-beam evaporator."""

    #: Commands that return diagnostic information.
    _VITAL_COMMANDS = {
        "Flux": "GET Flux",
        "High Voltage": "GET HV",
        "Filament Current": "GET Fil",
        "Emission Current": "GET Emis",
        "Suppressor": "GET Supr",
    }

    _FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

    def __init__(
        self,
        *,
        port: str = "COM5",
        baudrate: int = 57600,
        timeout: float = 1.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None

    @classmethod
    def vital_labels(cls) -> tuple[str, ...]:
        """Return the ordered labels reported by :meth:`get_vitals`."""
        return tuple(cls._VITAL_COMMANDS.keys())

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open the serial connection if it is not already active."""
        if self._serial and self._serial.is_open:
            return
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=True,
            timeout=self.timeout,
        )

    def disconnect(self) -> None:
        """Close the serial connection if open."""
        if self._serial:
            self._serial.close()
            self._serial = None

    @property
    def is_connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def configure_port(self, port: str) -> None:
        """Update the port. Connection must be reopened to take effect."""
        self.port = port
        if self._serial and self._serial.is_open:
            # Re-open so the new port takes effect immediately.
            self.disconnect()
            self.connect()

    # ------------------------------------------------------------------
    # Setters
    # ------------------------------------------------------------------
    def set_high_voltage(self, voltage: float) -> None:
        self._send_set_command("HV", voltage)

    def set_emission_current(self, current: float) -> None:
        self._send_set_command("Emis", current)

    def set_filament_current(self, current: float) -> None:
        self._send_set_command("Fil", current)

    def set_suppressor_state(self, enabled: bool) -> None:
        """Enable or disable the suppressor."""
        state = "on" if enabled else "off"
        self._send_set_command("Supr", state)

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------
    def get_vitals(self) -> Dict[str, str]:
        """Return a dictionary of vitals reported by the evaporator."""
        self._ensure_connection()
        vitals: Dict[str, str] = {}
        for label, command in self._VITAL_COMMANDS.items():
            response = self._query(command)
            vitals[label] = response
        return vitals

    def get_filament_current(self) -> Optional[float]:
        """Return the current filament reading, if it can be parsed."""
        try:
            response = self._query("GET Fil")
        except Exception:  # pragma: no cover - depends on HW
            return None
        match = self._FLOAT_RE.search(response)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    def get_suppressor_state(self) -> Optional[bool]:
        """Return ``True`` if the suppressor is on, ``False`` if off."""
        try:
            response = self._query("GET Supr")
        except Exception:  # pragma: no cover - depends on HW
            return None
        normalized = response.strip().lower()
        if "on" in normalized:
            return True
        if "off" in normalized:
            return False
        try:
            value = int(normalized)
        except ValueError:
            match = self._FLOAT_RE.search(response)
            if match:
                try:
                    value = int(float(match.group(0)))
                except ValueError:
                    return None
            else:
                return None
        if value == 1:
            return True
        if value == 0:
            return False
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _ensure_connection(self) -> None:
        if not self.is_connected:
            raise RuntimeError("E-beam controller is not connected")

    def _send_set_command(self, parameter: str, value: float | str) -> None:
        self._ensure_connection()
        if isinstance(value, str):
            formatted = value.strip()
        else:
            formatted = self._format_value(value)
        command = f"SET {parameter} {formatted}"
        self._write_line(command)

    def _query(self, command: str) -> str:
        self._ensure_connection()
        response = self._write_line(command)
        return response

    def _write_line(self, command: str) -> str:
        assert self._serial is not None
        self._serial.reset_input_buffer()
        payload = command.strip() + "\r"
        self._serial.write(payload.encode())
        reply = self._serial.readline().decode(errors="replace").strip()
        return reply

    @staticmethod
    def _format_value(value: float) -> str:
        # Strip trailing zeros to keep commands compact.
        return (f"{value:.4f}".rstrip("0").rstrip(".") or "0")


__all__ = ["EBeamController"]
