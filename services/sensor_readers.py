"""Background readers for pressure and temperature sensors."""

from __future__ import annotations

import threading
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal

try:  # pragma: no cover - optional dependency
    from serial import Serial  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    Serial = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from pfieffer_vacuum_protocol import PfiefferVacuumProtocol  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    try:  # pragma: no cover - alternative import name
        from PfiefferVacuumProtocol import PfiefferVacuumProtocol  # type: ignore
    except Exception:  # pragma: no cover - handled at runtime
        PfiefferVacuumProtocol = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from pymodbus.client import ModbusTcpClient  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    ModbusTcpClient = None  # type: ignore


class PressureReader(QObject):
    """Continuously poll a Pfeiffer gauge for pressure readings."""

    reading = Signal(float)

    def __init__(self, port: str, baudrate: int = 9600) -> None:
        super().__init__()
        self._port = port
        self._baudrate = baudrate
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start polling in the background."""
        if self._thread:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    # ------------------------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - hardware interaction
        if Serial is None or PfiefferVacuumProtocol is None:
            return
        proto = PfiefferVacuumProtocol()
        while self._running:
            try:
                with Serial(self._port, self._baudrate, timeout=1) as ser:
                    while self._running:
                        try:
                            value = proto.read_pressure(ser)
                            self.reading.emit(float(value))
                            time.sleep(1)
                        except Exception:
                            break
            except Exception:
                time.sleep(0.5)
            time.sleep(0.5)


class TemperatureReader(QObject):
    """Poll a Modbus TCP temperature controller for readings."""

    reading = Signal(float)

    def __init__(self, host: str, port: int = 502, unit: int = 1, address: int = 0) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._unit = unit
        self._address = address
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start polling in the background."""
        if self._thread:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    # ------------------------------------------------------------------
    def _run(self) -> None:  # pragma: no cover - hardware interaction
        if ModbusTcpClient is None:
            return
        while self._running:
            client = ModbusTcpClient(self._host, port=self._port)
            try:
                if not client.connect():
                    raise ConnectionError("Failed to connect")
                while self._running:
                    try:
                        resp = client.read_input_registers(self._address, count=1, unit=self._unit)
                        if resp and not getattr(resp, "isError", lambda: False)():
                            self.reading.emit(float(resp.registers[0]))
                        else:
                            raise ConnectionError("Invalid response")
                        time.sleep(1)
                    except Exception:
                        break
            except Exception:
                pass
            finally:
                try:
                    client.close()
                except Exception:
                    pass
            time.sleep(0.5)
