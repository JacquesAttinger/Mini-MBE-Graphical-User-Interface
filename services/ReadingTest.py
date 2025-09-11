# Reading Test
from PySide6.QtCore import QCoreApplication
from sensor_readers import PressureReader, TemperatureReader
import signal
import PfiefferVacuumProtocol as pvp

app = QCoreApplication([])

signal.signal(signal.SIGINT, signal.SIG_DFL)

pressure = PressureReader("/dev/tty.usbserial-BG000M9B", 9600)     # adjust port/baud as needed
pressure.reading.connect(lambda v: print("Pressure:", v))
pressure.start()

temperature = TemperatureReader("192.168.111.222")  # adjust host/unit/address
temperature.reading.connect(lambda v: print("Temperature:", v))
temperature.start()

app.exec()
