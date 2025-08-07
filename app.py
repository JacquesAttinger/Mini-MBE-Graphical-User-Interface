"""Application entry point for the miniMBE GUI."""

import sys
import logging
from PySide6.QtWidgets import QApplication

from controllers.manipulator_manager import ManipulatorManager
from services.dxf_service import DxfService
from windows.main_window import MainWindow


def main():
    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    manager = ManipulatorManager()
    dxf_service = DxfService()
    status = manager.connect_all()
    window = MainWindow(manager, dxf_service, status)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
