"""Background readers for pressure and temperature sensors."""

from __future__ import annotations

import threading
import time
import serial
from typing import Optional

from PySide6.QtCore import QObject, Signal

try:  # pragma: no cover - optional dependency
    from serial import Serial  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    Serial = None  # type: ignore

try:
    from . import PfiefferVacuumProtocol as pvp
    print('successfully imported Pfeiffer Vacuum Protocol')
except Exception:
    print('Was not able to import Pfeiffer Vacuum Protocol')

try:  # pragma: no cover - optional dependency
    from pymodbus.client import ModbusTcpClient  # type: ignore
    print('imported ModbusTCPClient')
except Exception:  # pragma: no cover - handled at runtime
    ModbusTcpClient = None  # type: ignore


class PressureReader(QObject):
    """Continuously poll a Pfeiffer gauge for pressure readings."""

    reading = Signal(float)

    def __init__(self, port: str, baudrate: int = 9600) -> None:
        super().__init__()
        self._port = port
        print('the port is:')
        print(self._port)
        self._baudrate = baudrate
        self._address = 122
        self._thread: Optional[threading.Thread] = None
        self._timeout = 1
        self._running = False
        self._ser = serial.Serial(self._port, baudrate=self._baudrate, timeout=self._timeout)

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
        print('trying to run pressure reader')
        if Serial is None or pvp is None:
            print('either serial or pvp is none')
            return
        print(f'self running is {self._running}')
        while self._running:
            print('jaack')
            try:
                with self._ser as ser:
                    print('attempt two of self.running is {self._running}')
                    while self._running:
                        try:
                            print('Tried reading pressure')
                            value = pvp.read_pressure(self._ser, self._address)
                            value_in_millibar = value * 1e3
                            self.reading.emit(float(value_in_millibar))
                            time.sleep(1)
                        except Exception:
                            print('wasnt able to read pressure')
                            break
            except Exception:
                print('wasnt able to connect to serial port')
                time.sleep(0.5)
            time.sleep(0.5)


class TemperatureReader(QObject):
    """Poll a Modbus TCP temperature controller for readings."""

    reading = Signal(float)

    def __init__(self, host: str, port: int = 502, unit: int = 1, address: int = 1) -> None:
        super().__init__()
        self._host = "192.168.111.222" # Eurotherm IP address
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
        print('is it running')
        if ModbusTcpClient is None:
            return
        while self._running:
            client = ModbusTcpClient(self._host, timeout = 1)
            try:
                if not client.connect():
                    raise ConnectionError("Failed to connect")
                while self._running:
                    try:
                        resp = client.read_input_registers(self._address, count=1)
                        print(resp)
                        if resp and not getattr(resp, "isError", lambda: False)():
                            print(type(resp.registers[0]))
                            print(resp.registers[0])
                            converted_temperature = resp.registers[0] / 10.0
                            self.reading.emit(converted_temperature)
                            
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
