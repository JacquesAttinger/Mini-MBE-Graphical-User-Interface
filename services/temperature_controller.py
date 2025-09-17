"""Control interface for the Modbus TCP temperature controller."""

from __future__ import annotations

from typing import Optional

try:  # pragma: no cover - optional dependency
    from pymodbus.client import ModbusTcpClient  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    ModbusTcpClient = None  # type: ignore


class TemperatureController:
    """Send temperature setpoints and ramp rates over Modbus TCP."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit: int = 1,
        setpoint_address: int = 0,
        ramp_rate_address: int = 0,
    ) -> None:
        self._host = "192.168.111.222"
        self._port = port
        self._unit = unit
        self._setpoint_address = 2
        self._ramp_rate_address = ramp_rate_address

    def _connect(self) -> Optional[ModbusTcpClient]:
        """Create and connect a Modbus TCP client."""
        if ModbusTcpClient is None:
            return None
        client = ModbusTcpClient(self._host, port=self._port, timeout=1)
        if not client.connect():
            return None
        return client

    def set_setpoint(self, value: int) -> None:
        """Set the desired temperature setpoint."""
        client = self._connect()
        if client is None:
            return
        try:
            print(value)
            print(type(value))
            value = float(value)
            value_as_int =  int(value * 10)
            client.write_register(2, value_as_int)
            print(f'Changed temperature setpoint to {value}')
            # print(client.read_holding_registers(2, device_id=1))
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass

    def set_ramp_rate(self, value: float) -> None:
        """Set the desired temperature ramp rate."""
        client = self._connect()
        if client is None:
            return
        try:
            # Insert line for writing temperature here
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass
