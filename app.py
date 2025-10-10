"""Application entry point for the miniMBE GUI."""

import argparse
import sys
import logging
from PySide6.QtWidgets import QApplication

from controllers.manipulator_manager import ManipulatorManager
from services.dxf_service import DxfService
from windows.main_window import MainWindow

sys.path.append('/Users/jacques/Documents/UChicago/UChicago Research/Yang Research/Mini-MBE GUI/miniMBE-GUI/services')


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--motion-log", action="store_true", help="Enable detailed motion logging"
    )
    args, qt_args = parser.parse_known_args()
    app = QApplication([sys.argv[0]] + qt_args)
    manager = ManipulatorManager(motion_logging=args.motion_log)
    dxf_service = DxfService()
    status = manager.connect_all()
    window = MainWindow(manager, dxf_service, status)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
