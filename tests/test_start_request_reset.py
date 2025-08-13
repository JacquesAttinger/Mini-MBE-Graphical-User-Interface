import controllers.smcd14_controller as smc

class DummyClient:
    def __init__(self):
        self.writes = []
        self.start_val = 0

    def write_register(self, address, value, slave=None):
        self.writes.append((address, value))
        if address == smc.START_REQ_ADDR:
            self.start_val = value
        class Res:
            def isError(self):
                return False
        return Res()

    def write_registers(self, address, values, slave=None):
        class Res:
            def isError(self):
                return False
        return Res()

    def read_holding_registers(self, address, count, slave=None):
        class Res:
            def __init__(self, val):
                self.registers = [val]
            def isError(self):
                return False
        val = self.start_val if address == smc.START_REQ_ADDR else 0
        return Res(val)


def test_move_relative_pulses_start_request():
    ctrl = smc.ManipulatorController(host="localhost")
    ctrl.client = DummyClient()
    ctrl.move_relative(0.1, 0.2)
    # Extract writes to start request register
    start_writes = [v for (addr, v) in ctrl.client.writes if addr == smc.START_REQ_ADDR]
    assert start_writes == [1, 0]
